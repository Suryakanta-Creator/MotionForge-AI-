"""End-to-end API smoke tests using generated media and the real FFmpeg renderer."""
import io
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server import app

client = TestClient(app)


def picture(color):
    image = Image.new("RGB", (256, 384), color)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_home_and_health():
    response = client.get("/")
    assert response.status_code == 200
    assert "MotionForge AI" in response.text
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["version"] == "0.3.0"


def test_bad_media_rejected():
    response = client.post("/api/upload", files={"file": ("bad.exe", b"xyz", "application/octet-stream")})
    assert response.status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable")
def test_image_to_real_mp4():
    ids = []
    for i, color in enumerate(("#6596aa", "#d7a1a4")):
        response = client.post("/api/upload", files={"file": (f"frame_{i}.png", picture(color), "image/png")})
        assert response.status_code == 200, response.text
        ids.append(response.json()["id"])

    planned = client.post("/api/plan", json={
        "media_ids": ids, "instructions": "gentle scroll down", "ratio": "9:16",
        "duration": 0.65, "captions": False, "use_ai": False,
    })
    assert planned.status_code == 200, planned.text
    body = planned.json()
    assert body["mode"] == "offline"
    assert len(body["plan"]["scenes"]) == 2
    assert body["plan"]["scenes"][0]["effect"] == "pan_down"
    invalid = client.post("/api/render", json={"plan": {**body["plan"], "ratio": "33:2"}})
    assert invalid.status_code == 400

    rendering = client.post("/api/render", json={"plan": body["plan"]})
    assert rendering.status_code == 200, rendering.text
    job_id = rendering.json()["job_id"]
    job = None
    for _ in range(150):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "failed"):
            break
        time.sleep(.4)
    assert job["state"] == "done", job
    video = client.get(f"/api/export/{job_id}")
    assert video.status_code == 200
    assert video.content[:4] != b"" and len(video.content) > 1000
    assert "video/mp4" in video.headers["content-type"]
