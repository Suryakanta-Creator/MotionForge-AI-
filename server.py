"""MotionForge AI: lightweight private video-editing web app.

Run: python server.py
Requires Python 3.10+, FFmpeg and ffprobe installed. No API key needed.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv("MOTIONFORGE_DATA", str(ROOT / "user_data"))).resolve()
UPLOADS, EXPORTS, WORK = [DATA / part for part in ("uploads", "exports", "jobs")]
for directory in (UPLOADS, EXPORTS, WORK):
    directory.mkdir(parents=True, exist_ok=True)

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_TYPES = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}
AUDIO_TYPES = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
EFFECTS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "still")
SIZES = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (720, 720)}
MAX_UPLOAD = 100 * 1024 * 1024
assets: dict[str, dict] = {}
jobs: dict[str, dict] = {}
mutex = threading.Lock()
pool = ThreadPoolExecutor(max_workers=2)
app = FastAPI(title="MotionForge AI", version="0.3.0")


class PlanRequest(BaseModel):
    media_ids: list[str] = Field(min_length=1, max_length=40)
    instructions: str = Field(default="Smooth gentle movement", max_length=4000)
    ratio: str = "9:16"
    duration: float = Field(default=3, ge=0.5, le=30)
    captions: bool = False
    use_ai: bool = False


class RenderRequest(BaseModel):
    plan: dict
    music_id: str | None = None
    voice_id: str | None = None


def run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise RuntimeError((result.stderr or "FFmpeg error")[-950:])


def probe(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode:
        raise ValueError("Unrecognised media file")
    try:
        seconds = float(result.stdout.strip())
    except ValueError as exc:
        raise ValueError("Media duration is unavailable") from exc
    if not math.isfinite(seconds) or not 0.1 <= seconds <= 36000:
        raise ValueError("Unsupported media duration")
    return seconds


def asset_by_id(media_id: str) -> dict:
    with mutex:
        info = assets.get(media_id)
    if not info or not Path(info["path"]).is_file():
        raise HTTPException(status_code=404, detail="Media unavailable. Upload again.")
    return info


@app.get("/")
def index():
    return FileResponse(ROOT / "studio" / "index.html", media_type="text/html")


@app.get("/api/health")
def health():
    return {"ok": True, "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY")), "version": "0.3.0"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext in IMAGE_TYPES:
        kind = "image"
    elif ext in VIDEO_TYPES:
        kind = "video"
    elif ext in AUDIO_TYPES:
        kind = "audio"
    else:
        raise HTTPException(400, "Supported: JPG, PNG, WebP, MP4, MOV, WebM, MP3, WAV, M4A")
    media_id = uuid.uuid4().hex
    path = UPLOADS / f"{media_id}{ext}"
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "100 MB maximum per file")
                output.write(chunk)
        if not size:
            raise ValueError("File is empty")
        if kind == "image":
            with Image.open(path) as im:
                if im.width * im.height > 80_000_000:
                    raise ValueError("Image is too large")
                im.verify()
            duration = 0
        else:
            duration = probe(path)
            if kind == "video" and duration < 0.5:
                raise ValueError("Video clips must be at least 0.5 seconds long")
        info = {"id": media_id, "path": str(path), "kind": kind,
                "duration": round(duration, 3), "name": Path(file.filename or "media").name[:120]}
        with mutex:
            assets[media_id] = info
        return {"id": media_id, "name": info["name"], "kind": kind,
                "duration": info["duration"], "url": f"/api/media/{media_id}"}
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Invalid media: {str(exc)[:160]}")
    finally:
        await file.close()


@app.get("/api/media/{media_id}")
def media(media_id: str):
    info = asset_by_id(media_id)
    return FileResponse(info["path"], filename=info["name"], content_disposition_type="inline")


def rule_effects(prompt: str) -> list[str]:
    prompt = prompt.lower()
    if any(t in prompt for t in ("scroll", "vertical", "downward")):
        return ["pan_down", "pan_up", "zoom_in", "pan_down", "zoom_out"]
    if "left" in prompt and "right" not in prompt:
        return ["pan_left", "zoom_in", "pan_left", "zoom_out"]
    if "right" in prompt:
        return ["pan_right", "zoom_in", "pan_right", "zoom_out"]
    if "zoom" in prompt:
        return ["zoom_in", "zoom_out"]
    if any(t in prompt for t in ("static", "no motion", "still")):
        return ["still"]
    return ["zoom_in", "pan_right", "pan_down", "zoom_out", "pan_left"]


def ai_scenes(prompt: str, selected: list[dict], seconds: float, captions: bool):
    """Only descriptive text and filenames are sent to Gemini, never file bytes."""
    if not os.getenv("GEMINI_API_KEY"):
        return None
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        description = [{"index": i, "filename": a["name"], "type": a["kind"]}
                       for i, a in enumerate(selected)]
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=(
                "You are a careful timeline editor. Return JSON only, an object with a "
                "'scenes' array of EXACTLY the number of input assets, in SAME ORDER. "
                "Each scene has 'effect' (one of: " + ", ".join(EFFECTS) +
                ") and 'caption' (short text or empty). Keep camera movement subtle. "
                "You cannot generate new images, alter content of footage, or invent assets. "
                f"Captions enabled: {captions}. Target scene length: {seconds}. "
                f"User request: {prompt}. Input assets: {json.dumps(description)}"
            ),
            config={"response_mime_type": "application/json"},
        )
        parsed = json.loads(response.text or "{}")
        scenes = parsed.get("scenes")
        if isinstance(scenes, list) and len(scenes) == len(selected):
            return scenes
    except Exception:
        pass
    return None


@app.post("/api/plan")
def make_plan(request: PlanRequest):
    if request.ratio not in SIZES:
        raise HTTPException(400, "Invalid canvas ratio")
    selected = [asset_by_id(i) for i in request.media_ids]
    if any(a["kind"] == "audio" for a in selected):
        raise HTTPException(400, "Add audio to the music or voice track")
    generated = ai_scenes(request.instructions, selected, request.duration, request.captions) if request.use_ai else None
    pattern = rule_effects(request.instructions)
    match = re.search(r"caption\s*:\s*([^\n]+)", request.instructions, flags=re.I)
    default_caption = match.group(1)[:140].strip() if request.captions and match else ""
    scenes = []
    for i, a in enumerate(selected):
        scene_hint = generated[i] if generated and isinstance(generated[i], dict) else {}
        effect = scene_hint.get("effect", pattern[i % len(pattern)])
        if effect not in EFFECTS:
            effect = pattern[i % len(pattern)]
        caption = str(scene_hint.get("caption", ""))[:140] if request.captions else ""
        if not caption and i == 0:
            caption = default_caption
        duration = request.duration if a["kind"] == "image" else min(request.duration, a["duration"])
        scenes.append({"media_id": a["id"], "duration": round(duration, 2), "effect": effect,
                       "trim_start": 0, "speed": 1, "caption": caption})
    return {"plan": {"ratio": request.ratio, "transition": "fade",
                     "quality": "draft", "scenes": scenes},
            "mode": "gemini" if generated else "offline"}


def validate_plan(plan: dict, selection: dict[str, dict]) -> dict:
    if not isinstance(plan, dict) or plan.get("ratio") not in SIZES:
        raise ValueError("Choose a valid canvas ratio")
    if plan.get("transition") not in ("fade", "cut"):
        raise ValueError("Transition must be fade or cut")
    if plan.get("quality") not in ("draft", "hd"):
        raise ValueError("Quality must be draft or hd")
    raw_scenes = plan.get("scenes")
    if not isinstance(raw_scenes, list) or not 1 <= len(raw_scenes) <= 40:
        raise ValueError("Include between 1 and 40 scenes")
    result = []
    total = 0.0
    for number, scene in enumerate(raw_scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {number} is invalid")
        asset = selection.get(scene.get("media_id"))
        if not asset or asset["kind"] not in ("image", "video"):
            raise ValueError(f"Scene {number} has a missing or invalid media file")
        try:
            duration = float(scene.get("duration", 3))
            trim_start = float(scene.get("trim_start", 0))
            speed = float(scene.get("speed", 1))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Scene {number} has invalid timing") from exc
        if not all(math.isfinite(v) for v in (duration, trim_start, speed)):
            raise ValueError(f"Scene {number} has invalid timing")
        if not 0.5 <= duration <= 90 or not 0 <= trim_start <= 36000 or not 0.5 <= speed <= 2:
            raise ValueError(f"Scene {number}: invalid duration, trim, or speed")
        if asset["kind"] == "video" and trim_start + duration * speed > asset["duration"] + 0.08:
            raise ValueError(f"Scene {number}: clip extends past source media")
        effect = scene.get("effect", "still")
        if effect not in EFFECTS:
            raise ValueError(f"Scene {number}: unsupported movement")
        caption = str(scene.get("caption", ""))[:140]
        result.append({"media_id": asset["id"], "duration": duration, "trim_start": trim_start,
                       "speed": speed, "effect": effect, "caption": caption})
        total += duration
    if total > 600:
        raise ValueError("10 minute maximum for one render")
    return {"ratio": plan["ratio"], "quality": plan["quality"],
            "transition": plan["transition"], "scenes": result}


def caption_png(text: str, w: int, h: int, output: Path):
    canvas = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(canvas)
    font_path = next((p for p in (
        "/usr/share/fonts/truetype/noto/NotoSansOriya-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ) if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, max(17, int(w * .046))) if font_path else ImageFont.load_default()
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if line and draw.textbbox((0, 0), candidate, font=font)[2] > .76 * w:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    lines = lines[:4]
    if lines:
        block_h = len(lines) * int(w * .079) + int(w * .045)
        top = h - int(h * .12) - block_h
        draw.rounded_rectangle((w * .09, top, w * .91, top + block_h),
                               radius=14, fill=(9, 12, 24, 184))
        for i, value in enumerate(lines):
            width = draw.textbbox((0, 0), value, font=font)[2]
            draw.text(((w - width) / 2, top + int(w * .015) + i * int(w * .079)),
                      value, fill="white", font=font)
    canvas.save(output)


def motion_filter(effect: str, frames: int, w: int, h: int):
    factor = max(1, frames - 1)
    zoom = {"zoom_in": f"1+0.13*on/{factor}", "zoom_out": f"1.13-0.13*on/{factor}"}.get(
        effect, "1.15" if effect.startswith("pan") else "1.025"
    )
    x, y = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    if effect == "pan_left":
        x = f"(iw-iw/zoom)*(1-on/{factor})"
    elif effect == "pan_right":
        x = f"(iw-iw/zoom)*on/{factor}"
    elif effect == "pan_up":
        y = f"(ih-ih/zoom)*(1-on/{factor})"
    elif effect == "pan_down":
        y = f"(ih-ih/zoom)*on/{factor}"
    ww = math.ceil(w * 1.2 / 2) * 2
    hh = math.ceil(h * 1.2 / 2) * 2
    return (f"scale={ww}:{hh}:force_original_aspect_ratio=increase,crop={ww}:{hh},setsar=1,"
            f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps=24")


def render_job(job_id: str, request: RenderRequest, selection: dict[str, dict]):
    def status(pct: int, message: str):
        with mutex:
            jobs[job_id].update(progress=pct, message=message)
    try:
        plan = validate_plan(request.plan, selection)
        work = WORK / job_id
        work.mkdir(parents=True, exist_ok=True)
        target = EXPORTS / f"{job_id}.mp4"
        w, h = SIZES[plan["ratio"]]
        if plan["quality"] == "draft":
            w, h = w // 2, h // 2
        clips, durations = [], []
        for i, scene in enumerate(plan["scenes"]):
            status(round(85 * i / len(plan["scenes"])), f"Rendering scene {i + 1} of {len(plan['scenes'])}")
            frames = max(12, round(scene["duration"] * 24))
            duration = frames / 24
            inp = Path(selection[scene["media_id"]]["path"])
            clip = work / f"scene_{i:03d}.mp4"
            if selection[scene["media_id"]]["kind"] == "image":
                normalized = work / f"img_{i:03d}.jpg"
                with Image.open(inp) as source:
                    ImageOps.exif_transpose(source).convert("RGB").save(normalized, quality=91)
                args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-loop", "1", "-framerate", "1", "-i", str(normalized)]
                effect = motion_filter(scene["effect"], frames, w, h)
            else:
                args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{scene['trim_start']:.3f}", "-i", str(inp)]
                effect = (f"setpts=(PTS-STARTPTS)/{scene['speed']:.6f},fps=24,"
                          f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                          f"crop={w}:{h},setsar=1,trim=duration={duration:.5f},setpts=PTS-STARTPTS")
            if scene["caption"]:
                overlay = work / f"caption_{i:03d}.png"
                caption_png(scene["caption"], w, h, overlay)
                args += ["-loop", "1", "-framerate", "1", "-i", str(overlay),
                         "-filter_complex", f"[0:v]{effect}[base];[base][1:v]overlay=0:0,format=yuv420p[v]",
                         "-map", "[v]"]
            else:
                args += ["-vf", f"{effect},format=yuv420p"]
            args += ["-frames:v", str(frames), "-an", "-c:v", "libx264",
                     "-preset", "ultrafast" if plan["quality"] == "draft" else "veryfast",
                     "-crf", "25" if plan["quality"] == "draft" else "22",
                     "-pix_fmt", "yuv420p", "-r", "24", str(clip)]
            run(args)
            clips.append(clip)
            durations.append(duration)

        status(88, "Joining your scenes")
        joined = work / "joined.mp4"
        fade = min(.35, min(durations) / 3) if plan["transition"] == "fade" and len(clips) > 1 else 0
        if fade:
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
            for clip in clips:
                command += ["-i", str(clip)]
            steps, previous, elapsed = [], "0:v", durations[0]
            for i in range(1, len(clips)):
                label = f"x{i}"
                steps.append(f"[{previous}][{i}:v]xfade=transition=fade:duration={fade:.4f}:offset={elapsed-fade:.4f}[{label}]")
                previous = label
                elapsed += durations[i] - fade
            command += ["-filter_complex", ";".join(steps), "-map", f"[{previous}]",
                        "-an", "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "23", "-pix_fmt", "yuv420p", str(joined)]
            run(command)
        else:
            list_file = work / "concat.txt"
            list_file.write_text("".join(f"file '{clip.name}'\n" for clip in clips), encoding="utf-8")
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-c", "copy", str(joined)])

        status(95, "Mixing audio and finishing MP4")
        final_duration = sum(durations) - fade * (len(durations) - 1)
        track_ids = [x for x in (request.music_id, request.voice_id) if x]
        if track_ids:
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined)]
            for name in (request.music_id, request.voice_id):
                if name:
                    if name == request.music_id:
                        command += ["-stream_loop", "-1"]
                    command += ["-i", selection[name]["path"]]
            if len(track_ids) == 2:
                command += ["-filter_complex",
                            "[1:a]volume=0.23,aresample=async=1:first_pts=0[m];"
                            "[2:a]volume=1.0,aresample=async=1:first_pts=0[v];"
                            "[m][v]amix=inputs=2:duration=longest:normalize=0[a]",
                            "-map", "0:v:0", "-map", "[a]"]
            else:
                volume = "0.23" if request.music_id else "1.0"
                command += ["-filter:a", f"volume={volume}", "-map", "0:v:0", "-map", "1:a:0"]
            command += ["-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                        "-t", f"{final_duration:.3f}", "-movflags", "+faststart", str(target)]
            run(command)
        else:
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined),
                 "-c", "copy", "-movflags", "+faststart", str(target)])
        status(100, "Export complete")
        with mutex:
            jobs[job_id].update(state="done", url=f"/api/export/{job_id}")
    except Exception as exc:
        with mutex:
            jobs[job_id].update(state="failed", message=str(exc)[-600:])


@app.post("/api/render")
def start_render(request: RenderRequest):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(503, "FFmpeg or ffprobe is not installed")
    raw_scenes = request.plan.get("scenes", []) if isinstance(request.plan, dict) else []
    if not isinstance(raw_scenes, list) or len(raw_scenes) > 40:
        raise HTTPException(400, "Invalid scene list")
    if not all(isinstance(s, dict) and isinstance(s.get("media_id"), str) for s in raw_scenes):
        raise HTTPException(400, "Each scene must reference an uploaded media ID")
    ids = {s["media_id"] for s in raw_scenes}
    ids.update(x for x in (request.music_id, request.voice_id) if x)
    selection = {item: asset_by_id(item) for item in ids}
    try:
        validate_plan(request.plan, selection)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    for track in (request.music_id, request.voice_id):
        if track and selection[track]["kind"] != "audio":
            raise HTTPException(400, "Music and voice must be audio uploads")
    job_id = uuid.uuid4().hex
    with mutex:
        jobs[job_id] = {"id": job_id, "state": "rendering", "progress": 0,
                        "message": "Preparing project"}
    pool.submit(render_job, job_id, request, selection)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with mutex:
        job = jobs.get(job_id)
        if job:
            return dict(job)
    raise HTTPException(404, "Job not found")


@app.get("/api/export/{job_id}")
def export(job_id: str):
    with mutex:
        job = jobs.get(job_id)
    if not job or job.get("state") != "done":
        raise HTTPException(404, "Video is not ready")
    return FileResponse(EXPORTS / f"{job_id}.mp4", media_type="video/mp4",
                        filename="MotionForge-export.mp4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
