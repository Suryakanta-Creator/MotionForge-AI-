"""Run an editable MotionForge JSON studio preset through the EXISTING MP4 engine.

Usage:
    python studio/render_preset.py --preset studio/presets/creator_intro_30s.json --output exports/studio_intro.mp4
    python studio/render_preset.py --quality standard --ambience
No external AI APIs, downloaded footage, or billing accounts required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonomous import render_storyboard
from motion_engine import LAYOUTS, PALETTES


def load_preset(path: str | Path) -> dict:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Preset must be an object")
    if data.get("ratio") not in ("9:16", "16:9", "1:1"):
        raise ValueError("Unknown aspect ratio")
    duration = data.get("duration")
    if type(duration) is not int or not 30 <= duration <= 300:
        raise ValueError("Duration must be 30–300 seconds")
    fps = data.get("fps", 20)
    if type(fps) is not int or not 10 <= fps <= 30:
        raise ValueError("FPS must be between 10 and 30")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 60:
        raise ValueError("Preset must contain 1–60 scenes")
    per_scene = duration / len(scenes)
    if not 1 <= per_scene <= 16:
        raise ValueError("Each scene must be 1–16 seconds")
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or scene.get("layout") not in LAYOUTS:
            raise ValueError(f"Scene {index + 1}: invalid motion layout")
        if scene.get("theme") not in PALETTES:
            raise ValueError(f"Scene {index + 1}: unknown color palette")
        for key in ("title", "subtitle"):
            if not isinstance(scene.get(key), str):
                raise ValueError(f"Scene {index + 1}: missing {key}")
        if not isinstance(scene.get("items", []), list):
            raise ValueError(f"Scene {index + 1}: items must be a list")
    return data


def render_preset(preset: str | Path, output: str | Path, *, quality: str = "draft",
                  ambience: bool = False) -> str:
    storyboard = load_preset(preset)
    if quality not in ("draft", "standard"):
        raise ValueError("Quality must be draft or standard")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    def progress(value: float, message: str):
        print(f"[{value:5.1f}%] {message}", flush=True)
    return render_storyboard(storyboard, out, quality=quality,
                             ambience=ambience, progress=progress)


def main():
    parser = argparse.ArgumentParser(description="MotionForge editable JSON video preset")
    parser.add_argument("--preset", default=str(ROOT / "studio/presets/creator_intro_30s.json"))
    parser.add_argument("--output", default="studio_exports/creator_intro_30s.mp4")
    parser.add_argument("--quality", choices=("draft", "standard"), default="draft")
    parser.add_argument("--ambience", action="store_true", help="Synthesized original ambient soundtrack")
    args = parser.parse_args()
    output = render_preset(args.preset, args.output,
                           quality=args.quality, ambience=args.ambience)
    print(f"Export ready: {output}")


if __name__ == "__main__":
    main()
