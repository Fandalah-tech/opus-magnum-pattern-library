from __future__ import annotations

import copy
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tools.run_rotor_a41_cycle_campaign import (
    ANALYSIS, BEST_PARSED, BEST_SOLUTION, DEFAULT_OPUS_ROOT, REFERENCE_METRICS,
    apply_shift, candidate_shifts, encode_solution, load_live, load_reference, now, publish,
)

ROOT = Path.cwd()
VALIDATOR_URL = os.environ.get("OM_VALIDATOR_URL", "https://opus-validator-6gflgqb25q-nn.a.run.app")
MAX_ROUNDS = 8
MAX_CANDIDATES = 300


def locate_puzzle(solution: dict[str, Any]) -> Path | None:
    raw_wanted = Path(str(solution.get("puzzleFile") or "")).name.lower()
    wanted_names: set[str] = set()
    if raw_wanted:
        wanted_names.add(raw_wanted)
        if not raw_wanted.endswith(".puzzle"):
            wanted_names.add(raw_wanted + ".puzzle")
        else:
            wanted_names.add(raw_wanted[:-7])

    roots: list[Path] = []
    configured = os.environ.get("OM_OPUS_MAGNUM_ROOT")
    if configured:
        roots.append(Path(configured))
    roots.append(DEFAULT_OPUS_ROOT)
    roots.append(Path("C:/Users/bruno/Documents/My Games/Opus Magnum"))

    seen: set[str] = set()
    for root in roots:
        try:
            root = root.resolve()
        except OSError:
            continue
        key = str(root).lower()
        if key in seen or not root.exists():
            continue
        seen.add(key)

        # Opus Magnum stores custom puzzles below the Steam-id directory, e.g.
        # <Opus Magnum>/<steam-id>/custom/weeklies2026_van-berlos-rotor.puzzle.
        # Search recursively instead of assuming custom/ is directly below the root.
        try:
            candidates = list(root.rglob("*.puzzle"))
        except (OSError, PermissionError):
            continue

        for path in candidates:
            if path.name.lower() in wanted_names:
                return path

        # Fallback for historical solution headers that omit/add the .puzzle suffix
        # or differ only by path components.
        wanted_stems = {Path(name).stem.lower() for name in wanted_names}
        for path in candidates:
            if path.stem.lower() in wanted_stems:
                return path

    return None


def multipart_bytes(puzzle_path: Path, solution_bytes: bytes, solution_name: str) -> tuple[bytes, str]:
    boundary = "----omsim-a41-cycle"
    chunks: list[bytes] = []
    for field, filename, payload in (
        ("puzzle", puzzle_path.name, puzzle_path.read_bytes()),
        ("solution", solution_name, solution_bytes),
    ):
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            payload,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def validate_remote(puzzle_path: Path, solution: dict[str, Any], name: str) -> dict[str, Any]:
    payload = encode_solution(solution)
    body, boundary = multipart_bytes(puzzle_path, payload, name)
    request = urllib.request.Request(
        f"{VALIDATOR_URL.rstrip('/')}/validate",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.load(response)
        return {"ok": True, "response": data, "error": None}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "response": None, "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:1200]}"}
    except Exception as exc:
        return {"ok": False, "response": None, "error": f"{type(exc).__name__}: {exc}"}


def save_best(solution: dict[str, Any], cycles: int, mutations: list[dict[str, Any]], remote_metrics: dict[str, Any]) -> None:
    model = copy.deepcopy(solution)
    model.setdefault("metrics", {}).update({
        "cycles": cycles,
        "cost": int(remote_metrics.get("cost", 220)),
        "area": int(remote_metrics.get("area", 41)),
        "instructions": int(remote_metrics.get("instructions", 302)),
    })
    model["name"] = f"A41 OMSIM C{cycles}"
    model["omsimMutations"] = mutations
    BEST_PARSED.write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    BEST_SOLUTION.write_bytes(encode_solution(model))


def main() -> int:
    started = time.monotonic()
    live = load_live()
    publish(live, stage="reference-discovery", status="running", message="A41: demarrage de la validation distante OMSIM.")
    solution, reference_file, match_kind = load_reference()
    if solution is None:
        publish(live, stage="reference-required", status="blocked", message="Reference A41 introuvable.")
        return 3
    puzzle_path = locate_puzzle(solution)
    if puzzle_path is None:
        publish(live, stage="puzzle-required", status="blocked", message=f"Puzzle binaire {solution.get('puzzleFile')} introuvable sous le dossier Opus Magnum, y compris les profils Steam/custom.")
        return 4

    publish(live, stage="baseline-validation", status="running", message=f"Validation distante de {reference_file} avec {puzzle_path.name}.", extra={"validatorUrl": VALIDATOR_URL, "puzzlePath": str(puzzle_path), "referenceMatch": match_kind})
    baseline = validate_remote(puzzle_path, solution, "a41-reference.solution")
    if not baseline["ok"]:
        publish(live, stage="validator-unavailable", status="blocked", message=f"Validateur inaccessible: {baseline['error']}")
        return 5
    base_response = baseline["response"] or {}
    if not base_response.get("valid"):
        publish(live, stage="baseline-rejected", status="blocked", message="Le validateur distant rejette la reference A41 encodee.", extra={"baselineResponse": base_response})
        return 6
    base_metrics = base_response.get("metrics") or {}
    baseline_cycles = int(base_metrics.get("cycles") or REFERENCE_METRICS["cycles"])
    current = copy.deepcopy(solution)
    current_cycles = baseline_cycles
    mutations: list[dict[str, Any]] = []
    tested = 0
    valid = 0
    rounds: list[dict[str, Any]] = []

    metrics = live.setdefault("metrics", {})
    metrics["baseline"] = {"cycles": baseline_cycles, "cost": int(base_metrics.get("cost") or 220), "area": int(base_metrics.get("area") or 41), "instructions": int(base_metrics.get("instructions") or 302)}
    metrics["best"] = dict(metrics["baseline"])
    publish(live, stage="candidate-validation", status="running", message=f"Reference validee a {baseline_cycles} cycles. Recherche de retimings.", extra={"baselineResponse": base_response})

    for round_index in range(1, MAX_ROUNDS + 1):
        shifts = candidate_shifts(current)
        if not shifts or tested >= MAX_CANDIDATES:
            break
        best_round: tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
        round_results = []
        publish(live, stage="candidate-validation", status="running", message=f"Round {round_index}: {len(shifts)} candidats a valider.", extra={"round": round_index, "frontierSize": len(shifts), "bestMutations": mutations})
        for index, shift in enumerate(shifts, start=1):
            if tested >= MAX_CANDIDATES:
                break
            candidate = apply_shift(current, shift)
            if candidate is None:
                continue
            tested += 1
            response = validate_remote(puzzle_path, candidate, f"a41-r{round_index}-c{index}.solution")
            remote = response.get("response") or {}
            is_valid = bool(response.get("ok") and remote.get("valid"))
            remote_metrics = remote.get("metrics") or {}
            cycles = int(remote_metrics.get("cycles")) if is_valid and remote_metrics.get("cycles") is not None else None
            if is_valid:
                valid += 1
            result = {"shift": shift, "valid": is_valid, "cycles": cycles, "metrics": remote_metrics if is_valid else None, "error": response.get("error"), "validatorMessage": remote.get("message")}
            round_results.append(result)
            if is_valid and cycles is not None and cycles < current_cycles:
                if best_round is None or cycles < best_round[0]:
                    best_round = (cycles, shift, candidate, remote_metrics)
            metrics["testedCandidates"] = tested
            metrics["validCandidates"] = valid
            live["elapsedSeconds"] = round(time.monotonic() - started, 1)
            if tested % 2 == 0 or (cycles is not None and cycles < current_cycles):
                publish(live, stage="candidate-validation", status="running", message=f"Round {round_index}: {tested} testes, {valid} valides; meilleur {current_cycles} cycles.", extra={"round": round_index, "frontierSize": max(0, len(shifts) - index), "bestMutations": mutations})
        rounds.append({"round": round_index, "sourceCycles": current_cycles, "candidates": round_results})
        if best_round is None:
            break
        current_cycles, winning_shift, current, winning_metrics = best_round
        mutations.append(winning_shift)
        metrics["best"] = {"cycles": current_cycles, "cost": int(winning_metrics.get("cost") or 220), "area": int(winning_metrics.get("area") or 41), "instructions": int(winning_metrics.get("instructions") or 302)}
        metrics["improvement"] = {"cycles": baseline_cycles - current_cycles, "instructions": int(metrics["baseline"]["instructions"]) - int(metrics["best"]["instructions"])}
        metrics["testedCandidates"] = tested
        metrics["validCandidates"] = valid
        live["bestResults"] = [{"rank": 1, "kind": "validated-retiming", "metrics": dict(metrics["best"]), "mutations": list(mutations)}]
        save_best(current, current_cycles, mutations, winning_metrics)
        publish(live, stage="improvement-found", status="running", message=f"Nouveau meilleur valide: {current_cycles} cycles (-{baseline_cycles-current_cycles}).", extra={"round": round_index, "frontierSize": 0, "bestMutations": mutations, "bestSolution": "reports/rotor-a41-cycle-best.solution"})

    ANALYSIS.write_text(json.dumps({"schemaVersion": 3, "updatedAt": now(), "validatorUrl": VALIDATOR_URL, "puzzlePath": str(puzzle_path), "baselineResponse": base_response, "rounds": rounds, "testedCandidates": tested, "validCandidates": valid, "bestCycles": current_cycles, "mutations": mutations}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metrics["testedCandidates"] = tested
    metrics["validCandidates"] = valid
    live["elapsedSeconds"] = round(time.monotonic() - started, 1)
    if current_cycles < baseline_cycles:
        publish(live, stage="completed", status="completed", message=f"Campagne terminee: meilleur resultat valide {current_cycles} cycles, gain {baseline_cycles-current_cycles}.", extra={"round": len(rounds), "frontierSize": 0, "bestMutations": mutations, "bestSolution": "reports/rotor-a41-cycle-best.solution", "analysisReport": "reports/rotor-a41-cycle-analysis.json"})
    else:
        publish(live, stage="completed", status="completed", message=f"Campagne terminee: {tested} candidats testes, {valid} valides, aucun gain sous {baseline_cycles}.", extra={"round": len(rounds), "frontierSize": 0, "analysisReport": "reports/rotor-a41-cycle-analysis.json"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
