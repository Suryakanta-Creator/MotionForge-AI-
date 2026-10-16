"""Autonomous graphics production: planning, layouts, export and audio."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from autonomous import make_storyboard, create_video
from motion_engine import LAYOUTS, frame


def test_five_minute_prompt_builds_full_storyboard():
    plan=make_storyboard(
        "Explain how AI agents organize workflows using planning, tools and review",
        duration=300,ratio="16:9",theme="midnight",use_ai=False,
    )
    assert plan["duration"]==300
    assert 40<=len(plan["scenes"])<=60
    assert plan["planning_mode"]=="offline"
    assert len({scene["layout"] for scene in plan["scenes"]})>=6
    assert all(scene["title"] and scene["items"] for scene in plan["scenes"])


@pytest.mark.parametrize("layout",LAYOUTS)
def test_graphics_scene_draws_valid_image(layout):
    scene={"layout":layout,"theme":"midnight","title":"ANIMATED DESIGN",
           "subtitle":"Smooth motion graphic presentation", "items":["Research","Storyboard","Create","Export"]}
    image=frame(scene,240,426,1.1,5.0)
    assert image.size==(240,426) and image.mode=="RGB"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="Requires FFmpeg")
def test_one_prompt_video_and_audio_are_real(tmp_path):
    output=tmp_path/"automatic.mp4"
    result=create_video(
        "Make a motion graphic about creative video editing with animated text and UI cards",
        output,duration=30,ratio="16:9",theme="ocean",
        quality="draft",ambience=True,use_ai=False,
    )
    assert output.is_file() and output.stat().st_size>5000
    metadata=json.loads(subprocess.check_output([
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","json",str(output),
    ],text=True))
    assert abs(float(metadata["format"]["duration"])-30)<.4
    storyboard=Path(result["storyboard"])
    assert storyboard.is_file()
    assert len(json.loads(storyboard.read_text())["scenes"])>=6
