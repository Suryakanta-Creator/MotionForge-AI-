"""Opt-in paid Google Veo video clips. NO Veo free-tier API is available.

Disabled by default; each request requires explicit acceptance of billing.
Uses the official google-genai SDK and saves returned MP4s to existing exports.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel, Field

VEO_PRICES_USD_PER_SECOND = {
    "veo-3.1-lite-generate-preview": 0.05,
    "veo-3.1-fast-generate-preview": 0.10,
    "veo-3.1-generate-preview": 0.40,
}

class VeoRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=1024)
    model: str = "veo-3.1-lite-generate-preview"
    aspect_ratio: str = "16:9"
    duration: int = 8
    confirm_paid: bool = False


def veo_job(job_id, params, jobs, mutex, exports):
    def progress(message):
        with mutex:
            jobs[job_id]["message"] = message
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        progress("Submitting paid Veo request to Google")
        operation = client.models.generate_videos(
            model=params.model,
            prompt=params.prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=params.aspect_ratio,
                duration_seconds=params.duration,
                resolution="720p",
                number_of_videos=1,
            ),
        )
        deadline = time.monotonic() + 20 * 60
        while not operation.done:
            if time.monotonic() >= deadline:
                raise TimeoutError("Veo status polling timed out. Check Google billing and jobs.")
            time.sleep(10)
            operation = client.operations.get(operation)
            progress("Google Veo is producing the clip")
        if getattr(operation, "error", None):
            raise RuntimeError("Veo could not complete this request")
        videos = getattr(getattr(operation, "response", None), "generated_videos", None)
        if not videos:
            raise RuntimeError("Veo returned no video")
        target = Path(exports) / (job_id + ".mp4")
        client.files.download(file=videos[0].video, destination=str(target))
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError("Empty video was downloaded")
        with mutex:
            jobs[job_id].update(state="done", progress=100, message="Veo clip ready",
                                url=f"/api/export/{job_id}")
    except Exception as exc:
        # Return a short error, not tokens, prompt, or SDK request details.
        with mutex:
            jobs[job_id].update(state="failed", message=f"Veo failed ({type(exc).__name__}). Check server logs.")


def install_veo_routes(app, jobs, mutex, pool, exports):
    @app.get("/api/veo/capabilities")
    def veo_capabilities():
        return {"available": bool(os.getenv("GEMINI_API_KEY")) and
                os.getenv("MOTIONFORGE_ENABLE_PAID_VEO") == "1",
                "paid_only": True, "pricing_720p_usd_per_second": VEO_PRICES_USD_PER_SECOND,
                "durations": [4, 6, 8], "aspect_ratios": ["16:9", "9:16"],
                "docs": "https://ai.google.dev/gemini-api/docs/veo"}

    @app.post("/api/veo/start")
    def start_veo(request: VeoRequest):
        if not os.getenv("GEMINI_API_KEY"):
            raise HTTPException(503, "Configure GEMINI_API_KEY in the server environment")
        if os.getenv("MOTIONFORGE_ENABLE_PAID_VEO") != "1":
            raise HTTPException(403, "Veo is disabled until MOTIONFORGE_ENABLE_PAID_VEO=1")
        if not request.confirm_paid:
            raise HTTPException(400, "Confirm that Google's paid video API may charge you")
        if request.model not in VEO_PRICES_USD_PER_SECOND:
            raise HTTPException(400, "Unknown Veo model")
        if request.aspect_ratio not in ("16:9", "9:16") or request.duration not in (4, 6, 8):
            raise HTTPException(400, "Unsupported Veo aspect ratio or duration")
        try:
            from google import genai
        except ImportError as exc:
            raise HTTPException(503, "Install requirements-ai.txt to enable Google Veo") from exc
        with mutex:
            active = sum(j.get("type") == "veo" and j.get("state") == "rendering"
                         for j in jobs.values())
            if active:
                raise HTTPException(429, "A Veo job is already running")
            job_id = uuid.uuid4().hex
            jobs[job_id] = {"id": job_id, "type": "veo", "state": "rendering",
                            "progress": 0, "message": "Starting paid Veo clip"}
        pool.submit(veo_job, job_id, request, jobs, mutex, exports)
        return {"job_id": job_id, "paid": True,
                "estimated_usd": round(request.duration *
                                       VEO_PRICES_USD_PER_SECOND[request.model], 2)}
