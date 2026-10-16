"""Autonomous, template-trained motion graphics generator.

No diffusion models or paid API keys are required. Research (Wikipedia) is
best-effort and explicitly labeled; when unavailable, output contains only
non-factual creative copy derived from the user's topic.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont

PALETTES = {
    "midnight": ("#0A0D18", "#11182B", "#B9A4FF", "#E9EEFF", "#8E9AB6"),
    "mint": ("#071D1B", "#0D302B", "#B1F7D8", "#F3FFF9", "#9DBAB4"),
    "sunset": ("#20101D", "#402337", "#FFB89B", "#FFF6E9", "#D0ADBD"),
    "paper": ("#F1EEE8", "#DFE6E1", "#164E63", "#112331", "#596B73"),
}
RATIOS = ("9:16", "16:9", "1:1")
MAX_RESEARCH_CHARS = 720
USER_AGENT = "MotionForgeAI/0.4 (research storyboard; https://github.com/Suryakanta-Creator/MotionForge-AI-)"
_FONT_FILES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_FONT_CACHE = {}


class MotionRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    duration: int = Field(default=24, ge=12, le=300)
    ratio: str = "9:16"
    style: str = "midnight"
    research: bool = True
    ambient_audio: bool = True


def _font(size: int, text: str = ""):
    """Select fonts with Devanagari/Odia glyph coverage for local-language titles."""
    size = max(12, int(size))
    script = ("odia" if any("\u0b00" <= c <= "\u0b7f" for c in text)
              else "devanagari" if any("\u0900" <= c <= "\u097f" for c in text)
              else "latin")
    key = (size, script)
    if key not in _FONT_CACHE:
        additional = {
            "odia": ("/usr/share/fonts/truetype/noto/NotoSansOriya-Regular.ttf",
                     "/usr/share/fonts/truetype/noto/NotoSansOdia-Regular.ttf"),
            "devanagari": ("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",),
            "latin": (),
        }
        for filename in (*additional[script], *_FONT_FILES):
            try:
                _FONT_CACHE[key] = ImageFont.truetype(filename, size)
                break
            except OSError:
                pass
        else:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def _wiki_json(params: dict) -> dict:
    endpoint = "https://en.wikipedia.org/w/api.php?"
    url = endpoint + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=7) as response:
        if response.status != 200:
            raise ValueError("Research provider unavailable")
        return json.loads(response.read(120_000).decode("utf-8"))


def research_topic(topic: str) -> dict:
    """Use a fixed host, never arbitrary URLs supplied by users."""
    try:
        data = _wiki_json({"action": "query", "list": "search", "srsearch": topic,
                           "srlimit": "2", "srnamespace": "0"})
        results = data.get("query", {}).get("search", [])
        if not results:
            return {"status": "no_sources", "sources": []}
        titles = [r["title"] for r in results if isinstance(r.get("title"), str)][:2]
        if not titles:
            return {"status": "no_sources", "sources": []}
        pages = _wiki_json({"action": "query", "prop": "extracts", "exintro": "1",
                            "explaintext": "1", "exchars": "1000",
                            "titles": "|".join(titles)})
        sources = []
        for page in pages.get("query", {}).get("pages", []):
            extract = re.sub(r"\s+", " ", page.get("extract", "")).strip()
            title = page.get("title", "")
            if not title or len(extract) < 35:
                continue
            sources.append({
                "title": title[:110],
                "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                "summary": extract[:MAX_RESEARCH_CHARS],
            })
        return {"status": "sourced" if sources else "no_sources", "sources": sources}
    except Exception:
        return {"status": "unavailable", "sources": []}


def _snippets(research: dict) -> list[str]:
    sentences = []
    for source in research.get("sources", []):
        raw = source.get("summary", "")
        for sentence in re.split(r"(?<=[.!?])\s+", raw):
            sentence = re.sub(r"\s+", " ", sentence).strip(" -")
            if 33 <= len(sentence) <= 170 and sentence not in sentences:
                sentences.append(sentence)
    return sentences[:5]


def make_storyboard(request: MotionRequest, facts: dict) -> dict:
    topic = " ".join(request.topic.strip().split())
    count = 5 if request.duration < 30 else 6 if request.duration < 45 else 8
    snippets = _snippets(facts)
    titles = ["THE BIG PICTURE", "WHAT TO KNOW", "LOOK CLOSER", "THE DETAILS",
              "IN CONTEXT", "KEY TAKEAWAY", "THE STORY", "WHAT'S NEXT"]
    scenes = [{
        "kind": "hero", "heading": topic[:72], "body": "A motion graphics explainer",
        "number": 1,
    }]
    for i in range(1, count - 1):
        if snippets:
            body = snippets[(i - 1) % len(snippets)]
            heading = titles[(i - 1) % len(titles)]
        else:
            heading = ["EXPLORE THE IDEA", "IN FOCUS", "PIECE BY PIECE", "VISUAL EXPLAINER",
                       "GO DEEPER", "THE CREATIVE VIEW"][(i - 1) % 6]
            body = topic[:130]
        scenes.append({
            "kind": ("statement", "interface", "timeline", "card", "steps", "quote")[((i - 1) % 6)],
            "heading": heading,
            "body": body,
            "number": i + 1,
        })
    scenes.append({
        "kind": "outro", "heading": "KEEP EXPLORING", "body": topic[:110], "number": count,
    })
    if facts.get("sources"):
        credit = "Wikipedia: " + facts["sources"][0]["title"][:32]
        for scene in scenes:
            scene["source_credit"] = credit
    # Whole frame counts are distributed exactly, avoiding time drift.
    duration = request.duration
    frames = int(duration * (12 if os.getenv("MOTIONFORGE_FREE_MODE") == "1" else 18))
    per, remainder = divmod(frames, count)
    for i, scene in enumerate(scenes):
        scene["frames"] = per + (1 if i < remainder else 0)
    return {"topic": topic, "ratio": request.ratio, "style": request.style,
            "duration": duration, "research_status": facts["status"],
            "sources": facts["sources"], "scenes": scenes,
            "generation": "deterministic animation / sourced research; no model weight training"}


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[n:n + 2], 16) for n in (1, 3, 5))


def _mix(a: str, b: str, amount: float) -> tuple[int, int, int]:
    ac, bc = _rgb(a), _rgb(b)
    return tuple(round(x * (1 - amount) + y * amount) for x, y in zip(ac, bc))


def _background(w: int, h: int, colors: tuple[str, ...], offset: int):
    bg = Image.new("RGB", (w, h), _rgb(colors[0]))
    d = ImageDraw.Draw(bg)
    # Cheap gradient strips avoid heavyweight per-frame image operations.
    for y in range(0, h, 8):
        blend = min(.87, .22 + .40 * y / h)
        d.rectangle((0, y, w, y + 8), fill=_mix(colors[0], colors[1], blend))
    space = max(26, w // 15)
    grid = _mix(colors[1], colors[4], .16)
    for x in range((offset * 17) % space, w, space):
        d.line((x, 0, x, h), fill=grid, width=1)
    for y in range(0, h, space):
        d.line((0, y, w, y), fill=grid, width=1)
    d.ellipse((w * .57, -h * .11, w * 1.28, h * .38),
              outline=_mix(colors[1], colors[2], .3), width=max(2, w // 180))
    return bg


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int = 5):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) >= max_lines and len(words) > len(" ".join(lines).split()):
        lines[-1] = lines[-1][:max(0, len(lines[-1]) - 3)].rstrip() + "..."
    return lines


def _ease(t: float):
    u = max(0.0, min(1.0, t))
    return 1 - (1 - u) ** 3


def _text_block(d, text, x, y, max_w, size, fill, line_height=1.2, max_lines=4):
    font = _font(size, text)
    rows = _wrap(d, text, font, max_w, max_lines)
    step = round(size * line_height)
    for n, row in enumerate(rows):
        d.text((int(x), int(y + n * step)), row, font=font, fill=fill,
               stroke_width=0)
    return step * len(rows)


def _draw_frame(background, scene, colors, index, total, global_pos, all_frames):
    w, h = background.size
    frame = background.copy()
    d = ImageDraw.Draw(frame)
    sx = w / 720
    sy = h / 1280
    scale = max(.5, min(sx, sy * 1.3))
    pad = int(w * .09)
    accent, white, muted = (_rgb(colors[i]) for i in (2, 3, 4))
    u = index / max(1, total - 1)
    intro = _ease(min(1, u * 5))
    exit_fade = max(0, (u - .86) / .14)
    k = intro * (1 - .22 * exit_fade)
    # All elements stay within a 9% safe margin.
    d.rounded_rectangle((pad, int(h * .076), pad + int(90 * scale), int(h * .076) + int(6 * scale)),
                        radius=4, fill=accent)
    d.text((pad, int(h * .095)), "MOTIONFORGE  /  STORY",
           font=_font(int(17 * scale)), fill=muted)
    kind = scene["kind"]
    heading = scene["heading"]
    body = scene["body"]
    start_y = h * (.29 if kind in ("hero", "outro") else .22)
    title_size = int(min(w * .071, 59 * scale))
    title_y = int(start_y + (1 - intro) * 52 * scale)
    title_h = _text_block(d, heading, pad, title_y, w - pad * 2,
                          title_size, white, 1.14, 5)
    if kind == "hero":
        d.ellipse((w * .68 + math.sin(u * 3) * w * .04, h * .13,
                   w * .93 + math.sin(u * 3) * w * .04, h * .13 + w * .25),
                  outline=accent, width=max(2, int(4 * scale)))
    if kind in ("statement", "quote", "hero", "outro"):
        y = title_y + title_h + int(h * .032)
        width = max(12, int((w - 2 * pad) * k))
        d.rounded_rectangle((pad, y, pad + width, y + max(3, int(4 * scale))),
                            radius=2, fill=accent)
        y += int(h * .033)
        _text_block(d, body, pad + int((1 - intro) * w * .07),
                    y, w - 2 * pad, int(min(31 * scale, w * .045)),
                    muted, 1.35, 5)
    elif kind == "card":
        y = title_y + title_h + int(h * .045)
        x0 = pad + int((1 - intro) * w * .16)
        d.rounded_rectangle((x0, y, w - pad, min(h - pad * 2, y + h * .36)),
                            radius=int(23 * scale),
                            fill=_mix(colors[1], colors[2], .16),
                            outline=accent, width=max(2, int(2 * scale)))
        _text_block(d, body, x0 + pad // 2, y + int(h * .055),
                    w - 3 * pad, int(28 * scale), white, 1.34, 6)
    elif kind == "interface":
        # A responsive browser mockup: floating cards, scrolling and a moving cursor.
        y = title_y + title_h + int(h * .035)
        bottom = min(int(h * .81), y + int(h * .43))
        x0, x1 = pad, w - pad
        d.rounded_rectangle((x0, y, x1, bottom), radius=int(18 * scale),
                            fill=_mix(colors[1], colors[0], .24), outline=muted,
                            width=max(1, int(scale * 2)))
        toolbar = y + int(39 * scale)
        d.line((x0, toolbar, x1, toolbar), fill=_mix(colors[4], colors[1], .54))
        for j in range(3):
            rad = 5 * scale
            cx = x0 + (17 + j * 16) * scale
            cy = y + 19 * scale
            d.ellipse((cx-rad, cy-rad, cx+rad, cy+rad), fill=accent if j == 0 else muted)
        content_top = toolbar + int(18 * scale)
        shift = int(_ease(u) * h * .045)
        inner_width = x1 - x0 - int(42 * scale)
        for j in range(3):
            cy = content_top + j * int(h * .123) - shift
            if cy < content_top - 8 or cy + 25 > bottom:
                continue
            x = x0 + int(19 * scale)
            d.rounded_rectangle((x, cy, x + inner_width, min(bottom - 8, cy + int(h * .105))),
                                radius=int(10 * scale), fill=_mix(colors[1], colors[2], .12))
            d.rounded_rectangle((x + 12 * scale, cy + 14 * scale,
                                 x + 52 * scale, cy + 54 * scale),
                                radius=int(7 * scale), fill=accent)
            if j == 0:
                _text_block(d, body, x + 63 * scale, cy + 14 * scale,
                            inner_width - 75 * scale, int(18 * scale), white, 1.1, 3)
            else:
                d.rounded_rectangle((x + 63 * scale, cy + 18 * scale,
                                     x + inner_width - 14 * scale, cy + 24 * scale),
                                    radius=3, fill=muted)
                d.rounded_rectangle((x + 63 * scale, cy + 36 * scale,
                                     x + inner_width * .68, cy + 42 * scale),
                                    radius=3, fill=_mix(colors[2], colors[1], .4))
        cursor_x = x0 + inner_width * (.72 - .17 * _ease(u))
        cursor_y = content_top + h * (.17 + .13 * math.sin(u * math.pi))
        d.ellipse((cursor_x-8*scale, cursor_y-8*scale,
                   cursor_x+8*scale, cursor_y+8*scale),
                  fill=white, outline=accent, width=max(1, int(3*scale)))
    elif kind == "timeline":
        # Timeline tracks and a sweeping playhead, reminiscent of a real editor.
        y = title_y + title_h + int(h * .045)
        bottom = min(int(h * .80), y + int(h * .35))
        x0, x1 = pad, w - pad
        d.rounded_rectangle((x0, y, x1, bottom), radius=int(17 * scale),
                            fill=_mix(colors[1], colors[0], .2),
                            outline=muted, width=max(1, int(2 * scale)))
        d.text((x0 + 17*scale, y + 13*scale), "MOTION / TIMELINE",
               font=_font(int(17 * scale)), fill=white)
        top = y + int(h * .08)
        for track in range(3):
            ty = top + track * int(h * .072)
            d.rounded_rectangle((x0+15*scale, ty, x1-15*scale,
                                 ty+int(h*.053)), radius=int(7*scale),
                                fill=_mix(colors[1], colors[4], .2))
            widths = [.28, .19, .31]
            cursor = x0 + int(22 * scale)
            for k, fraction in enumerate(widths):
                span = (x1 - x0 - int(60*scale)) * fraction
                d.rounded_rectangle((cursor, ty+5*scale, cursor+span,
                                     ty+int(h*.053)-5*scale),
                                    radius=int(6*scale),
                                    fill=_mix(colors[1], colors[2], (.70 if (k+track)%2 else .45)))
                cursor += span + int(5*scale)
        playhead = x0 + 20*scale + (x1-x0-40*scale)*_ease(u)
        d.line((playhead, top-7*scale, playhead, bottom-12*scale),
               fill=white, width=max(2, int(3*scale)))
        _text_block(d, body, x0 + int(15*scale), bottom + int(h*.024),
                    w - 2*pad, int(19*scale), muted, 1.2, 2)
    elif kind == "steps":
        y = title_y + title_h + int(h * .04)
        parts = _wrap(d, body, _font(int(22 * scale)), w - 3 * pad, 3)
        if len(parts) == 1:
            parts = [body[:45], body[45:90] or "A closer view", body[90:135] or "The connection"]
        for j in range(min(3, len(parts))):
            delay = _ease(min(1, max(0, u * 5 - .35 * j)))
            x0 = pad + int((1 - delay) * w * .21)
            top = y + j * int(h * .12)
            d.rounded_rectangle((x0, top, w - pad, top + int(h * .095)),
                                radius=int(14 * scale), fill=_mix(colors[1], colors[2], .13))
            d.ellipse((x0 + 12 * scale, top + 16 * scale,
                       x0 + 50 * scale, top + 54 * scale), fill=accent)
            d.text((x0 + 25 * scale, top + 18 * scale), str(j + 1),
                   font=_font(int(20 * scale)), fill=_rgb(colors[0]))
            _text_block(d, parts[j], x0 + 65 * scale, top + 20 * scale,
                        w - pad * 2 - 80 * scale, int(20 * scale), white, 1.2, 2)
    # Research attribution is burned into each exported video frame.
    if scene.get("source_credit"):
        d.text((pad, int(h * .877)), scene["source_credit"],
               font=_font(int(13 * scale)), fill=muted)
    # Timeline and page counter.
    bar_y = int(h * .91)
    d.rounded_rectangle((pad, bar_y, w - pad, bar_y + max(3, int(5 * scale))),
                        radius=4, fill=_mix(colors[1], colors[4], .5))
    complete = pad + int((w - 2 * pad) * (global_pos / max(1, all_frames)))
    d.rounded_rectangle((pad, bar_y, max(pad + 3, complete), bar_y + max(3, int(5 * scale))),
                        radius=3, fill=accent)
    d.text((pad, int(h * .936)), f"SCENE {scene['number']:02d}",
           font=_font(int(16 * scale)), fill=muted)
    d.text((w - pad - 70 * scale, int(h * .936)), "●  MF",
           font=_font(int(16 * scale)), fill=accent)
    return frame


def _dimensions(ratio: str, free_mode: bool) -> tuple[int, int]:
    if ratio == "9:16":
        return (360, 640) if free_mode else (720, 1280)
    if ratio == "16:9":
        return (640, 360) if free_mode else (1280, 720)
    return (480, 480) if free_mode else (720, 720)


def _ambient_wav(path: Path, seconds: int):
    rate = 16000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        # Generated original ambient tones, not a copyrighted track.
        data = bytearray()
        for n in range(rate * seconds):
            t = n / rate
            fade = min(1.0, t / .75, (seconds - t) / .9)
            notes = (math.sin(t * 2 * math.pi * 110) +
                     .42 * math.sin(t * 2 * math.pi * 164.81) +
                     .18 * math.sin(t * 2 * math.pi * 220))
            sample = int(max(-1.0, min(1.0, notes * .065 * max(0, fade))) * 32767)
            data.extend(sample.to_bytes(2, "little", signed=True))
            if len(data) > 65536:
                output.writeframesraw(data)
                data.clear()
        if data:
            output.writeframesraw(data)


def render_motion(plan: dict, export_path: Path, work_dir: Path, progress, free_mode: bool):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed on the server")
    work_dir.mkdir(parents=True, exist_ok=True)
    fps = 12 if free_mode else 18
    w, h = _dimensions(plan["ratio"], free_mode)
    silent = work_dir / "visual.mp4"
    all_frames = sum(scene["frames"] for scene in plan["scenes"])
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
               "-i", "-", "-an", "-c:v", "libx264", "-preset", "ultrafast",
               "-crf", "25", "-pix_fmt", "yuv420p", "-threads", "1",
               "-movflags", "+faststart", str(silent)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_no = 0
    try:
        for i, scene in enumerate(plan["scenes"]):
            progress(12 + int(75 * frame_no / all_frames),
                     f"Animating scene {i + 1} of {len(plan['scenes'])}")
            base = _background(w, h, PALETTES[plan["style"]], i)
            for frame_index in range(scene["frames"]):
                image = _draw_frame(base, scene, PALETTES[plan["style"]],
                                    frame_index, scene["frames"], frame_no, all_frames)
                process.stdin.write(image.tobytes())
                frame_no += 1
                if frame_no % (fps * 2) == 0:
                    progress(12 + int(75 * frame_no / all_frames),
                             f"Rendered {frame_no}/{all_frames} frames")
        process.stdin.close()
        error_text = process.stderr.read().decode("utf-8", "replace")
        return_code = process.wait(timeout=30)
        if return_code:
            raise RuntimeError("Video encoder failed: " + error_text[-280:])
    except Exception:
        process.kill()
        process.wait()
        raise
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        if process.stderr:
            process.stderr.close()
    progress(92, "Finishing MP4")
    if plan.get("ambient_audio"):
        audio = work_dir / "ambient.wav"
        _ambient_wav(audio, plan["duration"])
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent),
            "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-b:a", "96k",
            "-shortest", "-movflags", "+faststart", str(export_path)
        ], capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError("Audio mux failed: " + result.stderr[-280:])
    else:
        shutil.move(silent, export_path)
    if not export_path.is_file() or export_path.stat().st_size < 1000:
        raise RuntimeError("Export was not created correctly")
    progress(100, "MP4 ready to download")


def install_motion_routes(app, jobs, mutex: threading.Lock, pool, exports: Path,
                          work: Path, free_mode: bool, studio_root: Path):
    @app.get("/motion")
    def motion_page():
        return FileResponse(studio_root / "motion.html", media_type="text/html")

    @app.get("/api/motion/presets")
    def presets():
        return {"styles": list(PALETTES), "ratios": list(RATIOS),
                "maximum_duration": 45 if free_mode else 300,
                "research_provider": "Wikipedia (best effort)",
                "export": "MP4"}

    def execute(job_id: str, settings: MotionRequest):
        temporary = work / ("motion_" + job_id)
        target = exports / (job_id + ".mp4")

        def update(percent, message):
            with mutex:
                jobs[job_id].update(state="rendering", progress=percent, message=message)
        try:
            update(3, "Researching your topic")
            research = research_topic(settings.topic) if settings.research else {
                "status": "disabled", "sources": []}
            update(9, "Preparing research-based storyboard")
            plan = make_storyboard(settings, research)
            plan["ambient_audio"] = settings.ambient_audio
            with mutex:
                jobs[job_id]["storyboard"] = plan
            render_motion(plan, target, temporary, update, free_mode)
            with mutex:
                jobs[job_id].update(state="done", progress=100, message="Video complete",
                                    url=f"/api/export/{job_id}",
                                    research_status=plan["research_status"],
                                    sources=plan["sources"])
        except Exception as exc:
            target.unlink(missing_ok=True)
            with mutex:
                jobs[job_id].update(state="failed", message=str(exc)[-450:])
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    @app.post("/api/motion/create")
    def create(request: MotionRequest):
        if request.ratio not in RATIOS:
            raise HTTPException(400, "Unsupported aspect ratio")
        if request.style not in PALETTES:
            raise HTTPException(400, "Unsupported animation style")
        if request.duration > (45 if free_mode else 300):
            raise HTTPException(400, "Duration exceeds this server's render limit")
        if not request.topic.strip():
            raise HTTPException(400, "Enter a descriptive topic")
        with mutex:
            active = sum(1 for j in jobs.values()
                         if j.get("kind") == "motion" and j.get("state") in ("queued", "rendering"))
            if active >= 2:
                raise HTTPException(429, "The motion queue is full; retry after a render finishes")
            job_id = uuid.uuid4().hex
            jobs[job_id] = {"id": job_id, "kind": "motion", "state": "queued",
                            "progress": 0, "message": "Waiting for render worker"}
        pool.submit(execute, job_id, request)
        return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}
