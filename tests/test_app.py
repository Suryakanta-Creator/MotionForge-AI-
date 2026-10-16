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
    assert health.json()["version"] == "0.4.0"
    assert health.json()["version"] == "0.4.0"


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
    revised = client.post("/api/revise", json={"plan": body["plan"],
        "instructions": "zoom into scene 2, make scene 2 1 second, use clean cuts", "use_ai": False})
    assert revised.status_code == 200, revised.text
    assert revised.json()["plan"]["transition"] == "cut"
    assert revised.json()["plan"]["scenes"][1]["effect"] == "zoom_in"
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



@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable")
def test_footage_trim_speed_and_music(tmp_path):
    raw = tmp_path / "source.mp4"
    song = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=blue:s=160x240:r=24",
                    "-t", "1.5", "-pix_fmt", "yuv420p", str(raw)], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
                    str(song)], check=True)
    response = client.post("/api/upload", files={"file": ("test.mp4", raw.read_bytes(), "video/mp4")})
    assert response.status_code == 200, response.text
    video_id = response.json()["id"]
    response = client.post("/api/upload", files={"file": ("test.wav", song.read_bytes(), "audio/wav")})
    assert response.status_code == 200, response.text
    music_id = response.json()["id"]
    plan = {"ratio": "9:16", "quality": "draft", "transition": "cut",
            "scenes": [{"media_id": video_id, "duration": .7, "trim_start": .2,
                        "speed": 1.25, "effect": "still", "caption": "Hello world"}]}
    response = client.post("/api/render", json={"plan": plan, "music_id": music_id})
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    for _ in range(150):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "failed"):
            break
        time.sleep(.4)
    assert job["state"] == "done", job
    video = client.get(f"/api/export/{job_id}")
    assert video.status_code == 200 and len(video.content) > 1000


def test_private_deployment_access(monkeypatch):
    import base64
    monkeypatch.setenv("MOTIONFORGE_REQUIRE_AUTH", "1")
    monkeypatch.setenv("MOTIONFORGE_PASSWORD", "test-password-123")
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 401
    assert client.post("/api/plan", json={}).status_code == 401
    bad = base64.b64encode(b"studio:wrong").decode()
    assert client.get("/", headers={"Authorization": "Basic " + bad}).status_code == 401
    good = base64.b64encode(b"studio:test-password-123").decode()
    assert client.get("/", headers={"Authorization": "Basic " + good}).status_code == 200
