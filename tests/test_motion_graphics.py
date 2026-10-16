"""Offline regression tests for MotionForge's autonomous motion generator."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from motion_graphics import MotionRequest, _dimensions, make_storyboard, research_topic, render_motion


class StoryboardTests(unittest.TestCase):
    def test_no_research_means_no_invented_claims(self):
        request = MotionRequest(topic="The curious story of computer graphics", duration=24)
        plan = make_storyboard(request, {"status": "unavailable", "sources": []})
        self.assertEqual(plan["research_status"], "unavailable")
        self.assertEqual(len(plan["scenes"]), 5)
        self.assertTrue(all(scene["frames"] > 0 for scene in plan["scenes"]))
        self.assertTrue(all(
            scene["body"] == request.topic
            or scene["body"] == "A motion graphics explainer"
            for scene in plan["scenes"]
        ))

    def test_sourced_storyboard_uses_provided_excerpt(self):
        request = MotionRequest(topic="Digital animation", duration=30)
        source = {"status": "sourced", "sources": [
            {"title": "Animation", "summary": (
                "Animation is a method in which figures are manipulated to appear as moving images. "
                "Traditional animation images are drawn or painted by hand on transparent sheets."
            ), "url": "https://en.wikipedia.org/wiki/Animation"}
        ]}
        plan = make_storyboard(request, source)
        self.assertEqual(len(plan["scenes"]), 6)
        self.assertEqual(plan["sources"][0]["title"], "Animation")
        self.assertIn("Animation is a method", plan["scenes"][1]["body"])

    def test_research_failure_is_explicit(self):
        with patch("motion_graphics._wiki_json", side_effect=TimeoutError("offline")):
            response = research_topic("animation")
        self.assertEqual(response, {"status": "unavailable", "sources": []})

    def test_dimension_presets(self):
        self.assertEqual(_dimensions("9:16", True), (360, 640))
        self.assertEqual(_dimensions("16:9", True), (640, 360))
        self.assertEqual(_dimensions("1:1", False), (720, 720))


class VideoSmokeTests(unittest.TestCase):
    def test_short_video_is_a_real_mp4(self):
        if not os.environ.get("MOTIONFORGE_SMOKE_RENDER"):
            self.skipTest("Set MOTIONFORGE_SMOKE_RENDER=1 to run FFmpeg smoke test")
        request = MotionRequest(topic="Animated design", duration=12, research=False)
        plan = make_storyboard(request, {"status": "disabled", "sources": []})
        for scene in plan["scenes"]:
            scene["frames"] = 2
        plan["ambient_audio"] = False
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "result.mp4"
            render_motion(plan, target, root / "work", lambda *_: None, True)
            self.assertGreater(target.stat().st_size, 1500)
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "default=nokey=1:noprint_wrappers=1",
                str(target)
            ], check=True, text=True, capture_output=True)
            self.assertEqual(probe.stdout.strip(), "h264")


if __name__ == "__main__":
    unittest.main()
