# MotionForge AI 🎬

A lightweight, prompt-directed video editor built with **FastAPI + FFmpeg + vanilla JavaScript**. Upload still images or video clips, describe the motion, adjust the edit decisions, add audio, and export a real MP4.

## What works

- Browser-based editor designed for desktop and mobile.
- Upload JPG/PNG/WebP images, MP4/MOV/WebM clips, and MP3/WAV/M4A audio.
- Build scenes with zoom, pan/scroll, or still-image effects; trim and change speed for video clips.
- Arrange scenes, set captions and durations, choose cuts or fades.
- Optional background music and narration tracks.
- Render actual MP4s with 9:16, 16:9 or 1:1 aspect ratio.
- Prompt-to-edit planning: offline rules by default; optional Gemini model when configured.
- View render progress and preview/download the result.

**Important:** This is an editor, *not* a text-to-video diffusion model. It needs uploaded media (or the built-in generated illustration demo). It does not yet animate characters, generate images or automatically create speech.

## Run locally

Install Python 3.10+ and FFmpeg (both `ffmpeg` and `ffprobe` in PATH).

```bash
git clone https://github.com/Suryakanta-Creator/MotionForge-AI-.git
cd MotionForge-AI-
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Open **http://localhost:7860** on your computer; for phone access on the same Wi-Fi, open `http://YOUR_COMPUTER_LAN_IP:7860` while the server runs.

## Optional Gemini AI planning

```bash
pip install -r requirements-ai.txt
export GEMINI_API_KEY="YOUR_KEY"
# optional: export GEMINI_MODEL="gemini-2.5-flash"
python server.py
```

Without a key, MotionForge uses the honest offline fallback. AI planning sends the **prompt and media filenames** to the API, not the uploaded media bytes. API use may incur provider fees.

## Deploy

This repo includes a `Dockerfile` for any container host with persistent storage and FFmpeg support. Recommended: a small, private container deployment (e.g. Render or Railway); do **not** deploy this anonymous upload service openly without adding authentication, quotas, and rate limits first. Video encoding needs CPU and disk and may exceed serverless platform limits. Vercel static hosting alone will not run this backend.

## Security / limitations

- Intended for local/private trusted use in its current MVP form.
- Uploaded files and exports are saved to `MOTIONFORGE_DATA` (default `./user_data`) and not automatically deleted. Do not upload sensitive media to shared instances.
- No login, persistent asset registry, cloud storage, shared collaborative editing, billing, voice synthesis, automatic subtitles, or autonomous asset generation yet.
- Jobs and upload references are kept in server memory; a restart clears the active session.
- 100 MB per upload, 40-scene projects, 10-minute render limit. Rendering takes longer for large scenes or high resolution.
- Use only media and music you have rights to use.

## Architecture

`studio/index.html` (vanilla HTML/CSS/JS) → `server.py` (FastAPI API, edit planner and job worker) → FFmpeg exporter. Rendering executes server-side and keeps the editing instructions editable.

## License

MIT; see LICENSE.
