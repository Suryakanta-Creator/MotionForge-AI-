"""Smoke validation for the editable creator studio preset."""
from pathlib import Path
import pytest
from studio.render_preset import load_preset

PRESET=Path(__file__).resolve().parents[1]/"studio/presets/creator_intro_30s.json"

def test_creator_studio_preset_valid():
    p=load_preset(PRESET)
    assert p["duration"]==30 and p["fps"]==20
    assert p["ratio"]=="16:9"
    assert len(p["scenes"])==6
    assert {s["layout"] for s in p["scenes"]} >= {"kinetic","cards","steps","dashboard","scroll"}

def test_invalid_duration_rejected(tmp_path):
    text=PRESET.read_text(encoding="utf-8").replace('"duration": 30', '"duration": 12')
    p=tmp_path/"short.json"
    p.write_text(text,encoding="utf-8")
    with pytest.raises(ValueError,match="Duration"):
        load_preset(p)
