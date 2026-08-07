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
ANALYZE_ENDPOINT = "/api/v1/analyze"
MAX_ROUNDS = 8
MAX_CANDIDATES = 300
CHECKPOINT = ROOT / "reports/rotor-a41-cycle-checkpoint.json"


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
        try:
            candidates = list(root.rglob("*.puzzle"))
        except (OSError, PermissionError):
            continue
        for path in candidates:
            if path.name.lower() in wanted_names:
                return path
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


def _normalize_analyze_response(data: dict[str, Any]) -> dict[str, Any]:
    validation = data.get("validation") if isinstance(data, dict) else None
    if not isinstance(validation, dict):
        return {"valid": False, "metrics": {}, "message": "Analyze response missing validation object", "raw": data}
    status = str(validation.get("status") or "").lower()
    valid = validation.get("valid") is True or status == "valid"
    metrics = validation.get("metrics") if isinstance(validation.get("metrics"), dict) else {}
    issues = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    message = validation.get("message")
    if not message and issues:
        message = "; ".join(str(item.get("message") or item.get("code") or item) for item in issues[:4] if isinstance(item, dict))
    return {
        "valid": valid,
        "metrics": metrics,
        "message": message or status or "unknown",
        "validation": validation,
        "raw": data,
    }


def validate_remote(puzzle_path: Path, solution: dict[str, Any], name: str) -> dict[str, Any]:
    payload = encode_solution(solution)
    body, boundary = multipart_bytes(puzzle_path, payload, name)
    request = urllib.request.Request(
        f"{VALIDATOR_URL.rstrip('/')}{ANALYZE_ENDPOINT}",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.load(response)
        return {"ok": True, "response": _normalize_analyze_response(data), "error": None}
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


def write_checkpoint(*, baseline_cycles: int, current: dict[str, Any], current_cycles: int,
                     mutations: list[dict[str, Any]], tested: int, valid: int,
                     rounds: list[dict[str, Any]], round_index: int,
                     next_candidate_index: int, active_round_results: list[dict[str, Any]]) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 2,
        "updatedAt": now(),
        "validatorUrl": VALIDATOR_URL,
        "validatorEndpoint": ANALYZE_ENDPOINT,
        "baselineCycles": baseline_cycles,
        "currentCycles": current_cycles,
        "current": current,
        "mutations": mutations,
        "testedCandidates": tested,
        "validCandidates": valid,
        "rounds": rounds,
        "roundIndex": round_index,
        "nextCandidateIndex": next_candidate_index,
        "activeRoundResults": active_round_results,
    }
    temp = CHECKPOINT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(CHECKPOINT)


def load_checkpoint(baseline_cycles: int) -> dict[str, Any] | None:
    if not CHECKPOINT.is_file():
        return None
    try:
        data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or int(data.get("schemaVersion") or 0) != 2:
        return None
    if data.get("validatorEndpoint") != ANALYZE_ENDPOINT:
        return None
    if int(data.get("baselineCycles") or -1) != baseline_cycles:
        return None
    if not isinstance(data.get("current"), dict):
        return None
    return data


def best_from_partial(current: dict[str, Any], current_cycles: int,
                      results: list[dict[str, Any]]) -> tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    best: tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
    for result in results:
        if not result.get("valid") or result.get("cycles") is None or not isinstance(result.get("shift"), dict):
            continue
        cycles = int(result["cycles"])
        if cycles >= current_cycles:
            continue
        candidate = apply_shift(current, result["shift"])
        if candidate is None:
            continue
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        if best is None or cycles < best[0]:
            best = (cycles, result["shift"], candidate, metrics)
    return best


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

    publish(live, stage="baseline-validation", status="running", message=f"Validation distante de {reference_file} avec {puzzle_path.name} via {ANALYZE_ENDPOINT}.", extra={"validatorUrl": VALIDATOR_URL, "validatorEndpoint": ANALYZE_ENDPOINT, "puzzlePath": str(puzzle_path), "referenceMatch": match_kind})
    baseline = validate_remote(puzzle_path, solution, "a41-reference.solution")
    if not baseline["ok"]:
        publish(live, stage="validator-unavailable", status="blocked", message=f"Validateur inaccessible: {baseline['error']}")
        return 5
    base_response = baseline["response"] or {}
    if not base_response.get("valid"):
        publish(live, stage="baseline-rejected", status="blocked", message=f"Le validateur distant rejette la reference A41 encodee: {base_response.get('message')}", extra={"baselineResponse": base_response})
        return 6
    base_metrics = base_response.get("metrics") or {}
    baseline_cycles = int(base_metrics.get("cycles") or REFERENCE_METRICS["cycles"])

    checkpoint = load_checkpoint(baseline_cycles)
    if checkpoint:
        current = checkpoint["current"]
        current_cycles = int(checkpoint.get("currentCycles") or baseline_cycles)
        mutations = list(checkpoint.get("mutations") or [])
        tested = int(checkpoint.get("testedCandidates") or 0)
        valid = int(checkpoint.get("validCandidates") or 0)
        rounds = list(checkpoint.get("rounds") or [])
        resume_round = max(1, int(checkpoint.get("roundIndex") or (len(rounds) + 1)))
        resume_candidate = max(1, int(checkpoint.get("nextCandidateIndex") or 1))
        resume_results = list(checkpoint.get("activeRoundResults") or [])
        publish(live, stage="checkpoint-resume", status="running", message=f"Reprise checkpoint: round {resume_round}, candidat {resume_candidate}, {tested} deja testes; meilleur {current_cycles} cycles.", extra={"checkpoint": str(CHECKPOINT), "round": resume_round, "bestMutations": mutations})
    else:
        current = copy.deepcopy(solution)
        current_cycles = baseline_cycles
        mutations: list[dict[str, Any]] = []
        tested = 0
        valid = 0
        rounds: list[dict[str, Any]] = []
        resume_round = 1
        resume_candidate = 1
        resume_results: list[dict[str, Any]] = []

    metrics = live.setdefault("metrics", {})
    metrics["baseline"] = {"cycles": baseline_cycles, "cost": int(base_metrics.get("cost") or 220), "area": int(base_metrics.get("area") or 41), "instructions": int(base_metrics.get("instructions") or 302)}
    metrics["best"] = {"cycles": current_cycles, "cost": int(base_metrics.get("cost") or 220), "area": int(base_metrics.get("area") or 41), "instructions": int(base_metrics.get("instructions") or 302)}
    metrics["testedCandidates"] = tested
    metrics["validCandidates"] = valid
    publish(live, stage="candidate-validation", status="running", message=f"Reference validee a {baseline_cycles} cycles. Recherche de retimings; meilleur courant {current_cycles}.", extra={"baselineResponse": base_response})

    for round_index in range(resume_round, MAX_ROUNDS + 1):
        shifts = candidate_shifts(current)
        if not shifts or tested >= MAX_CANDIDATES:
            break
        start_index = resume_candidate if round_index == resume_round else 1
        round_results = resume_results if round_index == resume_round else []
        best_round = best_from_partial(current, current_cycles, round_results)
        publish(live, stage="candidate-validation", status="running", message=f"Round {round_index}: reprise au candidat {start_index}/{len(shifts)}; {tested} deja testes.", extra={"round": round_index, "frontierSize": max(0, len(shifts) - start_index + 1), "bestMutations": mutations})

        for index, shift in enumerate(shifts, start=1):
            if index < start_index:
                continue
            if tested >= MAX_CANDIDATES:
                break
            candidate = apply_shift(current, shift)
            if candidate is None:
                write_checkpoint(baseline_cycles=baseline_cycles, current=current, current_cycles=current_cycles, mutations=mutations, tested=tested, valid=valid, rounds=rounds, round_index=round_index, next_candidate_index=index + 1, active_round_results=round_results)
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
            write_checkpoint(baseline_cycles=baseline_cycles, current=current, current_cycles=current_cycles, mutations=mutations, tested=tested, valid=valid, rounds=rounds, round_index=round_index, next_candidate_index=index + 1, active_round_results=round_results)
            if tested % 2 == 0 or (cycles is not None and cycles < current_cycles):
                publish(live, stage="candidate-validation", status="running", message=f"Round {round_index}: {tested} testes, {valid} valides; meilleur {current_cycles} cycles.", extra={"round": round_index, "frontierSize": max(0, len(shifts) - index), "bestMutations": mutations, "checkpointCandidate": index + 1})

        rounds.append({"round": round_index, "sourceCycles": current_cycles, "candidates": round_results})
        resume_candidate = 1
        resume_results = []
        if best_round is None:
            write_checkpoint(baseline_cycles=baseline_cycles, current=current, current_cycles=current_cycles, mutations=mutations, tested=tested, valid=valid, rounds=rounds, round_index=round_index + 1, next_candidate_index=1, active_round_results=[])
            break
        current_cycles, winning_shift, current, winning_metrics = best_round
        mutations.append(winning_shift)
        metrics["best"] = {"cycles": current_cycles, "cost": int(winning_metrics.get("cost") or 220), "area": int(winning_metrics.get("area") or 41), "instructions": int(winning_metrics.get("instructions") or 302)}
        metrics["improvement"] = {"cycles": baseline_cycles - current_cycles, "instructions": int(metrics["baseline"]["instructions"]) - int(metrics["best"]["instructions"])}
        metrics["testedCandidates"] = tested
        metrics["validCandidates"] = valid
        live["bestResults"] = [{"rank": 1, "kind": "validated-retiming", "metrics": dict(metrics["best"]), "mutations": list(mutations)}]
        save_best(current, current_cycles, mutations, winning_metrics)
        write_checkpoint(baseline_cycles=baseline_cycles, current=current, current_cycles=current_cycles, mutations=mutations, tested=tested, valid=valid, rounds=rounds, round_index=round_index + 1, next_candidate_index=1, active_round_results=[])
        publish(live, stage="improvement-found", status="running", message=f"Nouveau meilleur valide: {current_cycles} cycles (-{baseline_cycles-current_cycles}). Checkpoint sauvegarde.", extra={"round": round_index, "frontierSize": 0, "bestMutations": mutations, "bestSolution": "reports/rotor-a41-cycle-best.solution", "checkpoint": str(CHECKPOINT)})

    ANALYSIS.write_text(json.dumps({"schemaVersion": 5, "updatedAt": now(), "validatorUrl": VALIDATOR_URL, "validatorEndpoint": ANALYZE_ENDPOINT, "puzzlePath": str(puzzle_path), "baselineResponse": base_response, "rounds": rounds, "testedCandidates": tested, "validCandidates": valid, "bestCycles": current_cycles, "mutations": mutations, "checkpoint": str(CHECKPOINT)}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metrics["testedCandidates"] = tested
    metrics["validCandidates"] = valid
    live["elapsedSeconds"] = round(time.monotonic() - started, 1)
    if current_cycles < baseline_cycles:
        publish(live, stage="completed", status="completed", message=f"Campagne terminee: meilleur resultat valide {current_cycles} cycles, gain {baseline_cycles-current_cycles}.", extra={"round": len(rounds), "frontierSize": 0, "bestMutations": mutations, "bestSolution": "reports/rotor-a41-cycle-best.solution", "analysisReport": "reports/rotor-a41-cycle-analysis.json", "checkpoint": str(CHECKPOINT)})
    else:
        publish(live, stage="completed", status="completed", message=f"Campagne terminee: {tested} candidats testes, {valid} valides, aucun gain sous {baseline_cycles}.", extra={"round": len(rounds), "frontierSize": 0, "analysisReport": "reports/rotor-a41-cycle-analysis.json", "checkpoint": str(CHECKPOINT)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
