"""Voice cloning API tests. Heavy TTS weights are mocked; CI never downloads models."""
from __future__ import annotations

import io
import shutil
import time
import wave

import pytest
from fastapi.testclient import TestClient

import server
from voice_cloning import LANGUAGES, split_narration, voice_status

client = TestClient(server.app)


def make_wav(seconds: float = 3.5) -> bytes:
    data = io.BytesIO()
    with wave.open(data, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * round(seconds * 16000))
    return data.getvalue()


def test_chunking_preserves_words_and_works_with_hindi():
    script = "नमस्ते। यह हमारी कहानी है। " + "A long narration sentence. " * 30
    chunks = split_narration(script, max_chars=100)
    assert chunks
    assert all(0 < len(chunk) <= 100 for chunk in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(script.split())


def test_voice_engine_status_is_lazy():
    result = voice_status()
    assert result["provider"] == "chatterbox_multilingual"
    assert result["license"] == "MIT"
    assert result["languages"]["hi"] == "Hindi"
    assert "or" not in result["languages"]  # Odia is not a supported Chatterbox language.
    assert "en" in LANGUAGES


def test_rejects_missing_consent_and_unsupported_language():
    response = client.post("/api/voice/generate",
        json={"reference_id": "not-a-real-id", "text": "A simple narration", "language": "hi"})
    assert response.status_code == 400
    assert "permission" in response.json()["detail"]

    response = client.post("/api/voice/generate",
        json={"reference_id": "not-a-real-id", "text": "A simple narration",
              "language": "or", "consent": True})
    assert response.status_code == 400
    assert "Odia" in response.json()["detail"]


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg not available")
def test_generate_voice_creates_audio_asset(monkeypatch):
    # Mock only the heavy synthesizer; exercise real upload, request validation,
    # queue, generated-asset registration, and media delivery.
    monkeypatch.setattr(server, "voice_status", lambda: {"available": True})

    def fake_clone(reference, text, language, target, temp_dir, report):
        assert reference.is_file()
        assert text == "Hello there"
        assert language == "en"
        report(50, "Synthesizing")
        target.write_bytes(make_wav(seconds=.8))

    monkeypatch.setattr(server, "clone_voice", fake_clone)
    uploaded = client.post("/api/upload", files={
        "file": ("my-own-reference.wav", make_wav(), "audio/wav")
    })
    assert uploaded.status_code == 200, uploaded.text
    reference_id = uploaded.json()["id"]

    too_short = client.post("/api/voice/generate",
        json={"reference_id": reference_id, "text": " ", "language": "en", "consent": True})
    assert too_short.status_code == 400

    started = client.post("/api/voice/generate",
        json={"reference_id": reference_id, "text": "Hello there",
              "language": "en", "consent": True})
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]
    for _ in range(80):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["state"] in ("done", "failed"):
            break
        time.sleep(.05)
    assert status["state"] == "done", status
    assert status["asset"]["kind"] == "audio"
    audio = client.get(status["asset"]["url"])
    assert audio.status_code == 200
    assert audio.content.startswith(b"RIFF")
