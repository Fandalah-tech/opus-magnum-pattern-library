from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Frame, Page, sync_playwright


def _inspector_frame(page: Page, timeout_ms: int) -> Frame:
    page.wait_for_selector("#solver-inspector", timeout=timeout_ms)
    page.wait_for_timeout(250)
    for frame in page.frames:
        if "inspector.html" in frame.url:
            return frame
    page.wait_for_timeout(1000)
    for frame in page.frames:
        if "inspector.html" in frame.url:
            return frame
    raise RuntimeError("The embedded inspector frame was not found")


def _set_frame(frame: Frame, index: int) -> None:
    frame.evaluate(
        """
        (index) => {
          const range = document.querySelector('[data-replay-range]');
          if (!range) throw new Error('Replay range is unavailable');
          range.value = String(index);
          range.dispatchEvent(new Event('input', { bubbles: true }));
        }
        """,
        index,
    )


def _delivery_event(frame: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (event for event in frame.get("events", []) if event.get("kind") == "product-delivered"),
        None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture the Solver Lab viewer at every replay frame."
    )
    parser.add_argument(
        "--url",
        default="https://opus-validator-6gflgqb25q-nn.a.run.app/solver-lab.html",
    )
    parser.add_argument("--output", type=Path, default=Path("reports/visual/P007"))
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    args = parser.parse_args()

    output = args.output.resolve()
    image_dir = output / "img"
    image_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1480, "height": 1040}, device_scale_factor=1)
        page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        inspector = _inspector_frame(page, args.timeout_ms)
        inspector.wait_for_function(
            "window.__OPUS_CAPTURE_READY__ === true && window.__OPUS_LAST_ANALYSIS__?.replay?.frames?.length > 0",
            timeout=args.timeout_ms,
        )
        inspector.evaluate("window.__OPUS_CLEAR_SELECTION__?.()")

        payload = inspector.evaluate("window.__OPUS_LAST_ANALYSIS__")
        area = inspector.evaluate("window.__OPUS_USED_AREA__ || null")
        replay = payload["replay"]
        frames = replay.get("frames", [])
        viewer = inspector.locator("#solution-viewer")
        viewer.wait_for(state="visible", timeout=args.timeout_ms)

        manifest_frames: list[dict[str, Any]] = []
        for index, replay_frame in enumerate(frames):
            _set_frame(inspector, index)
            delivery = _delivery_event(replay_frame)
            screenshots: list[str] = []

            if delivery:
                inspector.wait_for_timeout(280)
                mid_name = f"cycle-{index:03d}-delivery-mid.png"
                viewer.screenshot(path=str(image_dir / mid_name), animations="allow")
                screenshots.append(f"img/{mid_name}")
                inspector.wait_for_timeout(520)
            else:
                inspector.wait_for_timeout(260)

            image_name = f"cycle-{index:03d}.png"
            viewer.screenshot(path=str(image_dir / image_name), animations="disabled")
            screenshots.append(f"img/{image_name}")
            label = inspector.locator("[data-replay-cycle]").inner_text()

            manifest_frames.append(
                {
                    "frameIndex": index,
                    "cycle": replay_frame.get("cycle"),
                    "displayCycle": replay_frame.get("displayCycle"),
                    "phase": replay_frame.get("phase"),
                    "label": label,
                    "screenshots": screenshots,
                    "events": replay_frame.get("events", []),
                    "moleculeCount": len(replay_frame.get("molecules", [])),
                    "atomCount": sum(
                        len(molecule.get("atoms", []))
                        for molecule in replay_frame.get("molecules", [])
                    ),
                    "bondCount": sum(
                        len(molecule.get("bonds", []))
                        for molecule in replay_frame.get("molecules", [])
                    ),
                    "usedCells": (area or {}).get("cumulativeByFrame", [])[index]
                    if index < len((area or {}).get("cumulativeByFrame", []))
                    else [],
                    "activeCells": (area or {}).get("activeByFrame", [])[index]
                    if index < len((area or {}).get("activeByFrame", []))
                    else [],
                }
            )

        manifest = {
            "schemaVersion": "1.0.0",
            "sourceUrl": args.url,
            "solution": payload.get("solution", {}).get("name"),
            "puzzle": payload.get("puzzle", {}).get("name"),
            "validation": payload.get("validation"),
            "replay": {
                "traceType": replay.get("traceType"),
                "summary": replay.get("summary"),
                "capabilities": replay.get("capabilities"),
            },
            "frameCount": len(manifest_frames),
            "imageCount": sum(len(item["screenshots"]) for item in manifest_frames),
            "frames": manifest_frames,
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        browser.close()

    print(
        json.dumps(
            {
                "output": str(output),
                "frames": len(manifest_frames),
                "images": manifest["imageCount"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
