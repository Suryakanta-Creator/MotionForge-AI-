# MotionForge AI 🎬

A lightweight, prompt-directed video editor built with **FastAPI + FFmpeg + vanilla JavaScript**. Upload still images or video clips, describe the motion, adjust the edit decisions, add audio, and export a real MP4.

## What works

- Browser-based editor designed for desktop and mobile.
- Upload JPG/PNG/WebP images, MP4/MOV/WebM clips, and MP3/WAV/M4A audio.
- Build scenes with zoom, pan/scroll, or still-image effects; trim and change speed for video clips.
- Arrange scenes, set captions and durations, choose cuts or fades.
- Optional background music and narration tracks, including AI-generated WAV narration from a consented voice sample.
- Render actual MP4s with 9:16, 16:9 or 1:1 aspect ratio.
- Prompt-to-edit planning and follow-up editing instructions: offline rules by default; optional Gemini model when configured.
- View render progress and preview/download the result.

**Important:** This is an editor, *not* a text-to-video diffusion model. It needs uploaded media (or the built-in generated illustration demo). It does not animate characters or generate images. Optional Chatterbox speech synthesis is available with a separate local install.

## NEW: Autonomous Motion Studio (v0.4)

Go to **/motion** (or choose **✦ Motion Agent** from the editor). This is a
separate text-to-motion-graphics flow: **topic → public research → storyboard →
animated shapes and kinetic typography → FFmpeg MP4 → download**.

No media uploads or paid AI API key are needed. Each scene is rendered locally
using Pillow drawing primitives, editable Python templates, and FFmpeg. Choose
an aspect ratio (9:16 / 16:9 / 1:1), four design palettes, duration, optional
public research, and optional original synthesized ambient audio. Animated
titles, progress lines, content cards and step sequences are generated for every
video. The results are downloadable through the existing \`/api/export/{job_id}\`
endpoint, and the studio displays research sources and the status of the render.

**Research boundaries:** MotionForge currently searches *English Wikipedia*
using its public API. It does not browse arbitrary websites, check current
news, make assets from web images, or independently verify claims. When the
source is unavailable, the video uses creative phrases based only on your
topic, rather than inventing facts. Review and attribute sources before
publishing; Wikipedia content carries reuse/license obligations. URLs in the
source panel identify the articles used.

**Template learning vs. model training:** This release implements reusable
animation patterns. It does **not** fine-tune model weights or analyze uploaded
reference videos into a new motion model. The next phase can add reference
motion analysis, editable keyframes, source scoring, and opt-in feedback data.

**Free hosting:** The v0.4 motion API limits free Render instances to 45-second
draft videos (360×640 for vertical) at 12 FPS, and two queued/active motion
jobs. Local/stronger servers allow videos up to five minutes, rendered at
18 FPS and up to 720×1280. Longer videos and richer motion require stronger
compute. A short video might still fail on constrained free hosting. The
existing editor's scene/time limitations are unchanged.

**API:**
- \`GET /api/motion/presets\` — render limits, ratio and color style options
- \`POST /api/motion/create\` — accepts a JSON object with \`topic\`, \`duration\`,
  \`ratio\`, \`style\`, \`research\` and \`ambient_audio\`
- \`GET /api/jobs/{job_id}\` — research/render progress plus source and storyboard
  metadata; on success contains the MP4 \`url\`
- \`GET /api/export/{job_id}\` — download the completed MP4

To run checks locally:

\`\`\`bash
MOTIONFORGE_SMOKE_RENDER=1 python -m unittest discover -s tests -p "test_motion_graphics.py" -v
\`\`\`

**Deployment note:** \`render.yaml\` currently sets \`autoDeployTrigger: off\`.
Pushing to GitHub does **not** update the deployed Render service automatically;
redeploy the latest commit manually from Render's dashboard.

## Deploy free on Render (personal test deployment)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Suryakanta-Creator/MotionForge-AI-)

1. Open the **Deploy to Render** link, sign in, and review the imported `render.yaml`.
2. Confirm the service is on the **Free** plan, and enter a strong, unique `MOTIONFORGE_PASSWORD` when Render prompts. **Do not commit the password to GitHub or share it here.**
3. Approve deployment in Render and wait until the service status is **Live**.
4. Open the `.onrender.com` address from the service dashboard. Sign in with username **studio** and the password you set.
5. Select **Try sample project**, **Export video MP4**, and immediately download the output.

**Free-host tradeoffs:** The Render free instance provides limited CPU and 512 MB RAM. This deployment deliberately caps projects to **12 scenes**, **20 MB per uploaded file**, **120 seconds of total scene time**, and **draft-quality video** (normally 360×640 for Shorts), with only one render worker. Even short jobs may be slow; failures due to memory/time limits are possible. Render may shut down the server after 15 idle minutes; a restart/redeploy deletes media and generated exports because the local disk is ephemeral. Re-upload when that happens, and always download your finished video. Do not depend on this deployment to store your projects.

The public URL is **not private by obscurity**: the application requires HTTP Basic authentication using the studio password you choose. Use a strong, unique password, do not share the link and password publicly, and treat this MVP as a personal test studio, not a secure multi-user service. There is no separate account system, encryption-at-rest, quota per user, abuse protection, or persistent database.

If Render prompts for a paid compute plan, stop and select Free: this Blueprint is intended for zero-cost testing.

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

## Agent-like follow-up editing

Once your timeline exists, use **Ask the agent to change something**. Examples: `zoom into scene 2`, `make scene 1 5 seconds`, `use clean cuts`, `remove scene 3`, `caption: A peaceful morning` or `make the last scene slower`. Without a Gemini key, the transparent rule-based interpreter handles these limited commands. With Gemini configured, it can attempt more flexible revisions; every plan is validated before rendering. The follow-up agent changes the edit instructions, not the contents of the underlying source video.

## Optional free local voice cloning

MotionForge's **AI voice lab** uses [Resemble AI Chatterbox Multilingual](https://github.com/resemble-ai/chatterbox) for zero-shot voice cloning. It runs locally without a paid speech API, but requires significant CPU/GPU resources and an initial model-weight download. The default video editor runs without it.

**License:** Chatterbox is MIT-licensed. The referenced project's software and model terms should still be checked before production/commercial deployment. OmniVoice's pretrained weights are CC-BY-NC and are deliberately **not** bundled here. Only clone your own voice or a voice whose speaker explicitly agreed to cloning; don't use it for deception or impersonation.

Recommended environment: Python 3.11 with FFmpeg / ffprobe already installed.

```bash
pip install -r requirements-voice.txt
python server.py
```

Go to **Audio tracks → AI voice lab**, choose a clean 3–30 second spoken audio reference (WAV/MP3/M4A supported), choose **Hindi** or **English**, paste a narration script, confirm consent, and click **Generate cloned narration**. Voice generation runs as a queued background job. When finished, the WAV automatically becomes the video's narration track; you can preview it and save it. Your existing background music continues to work.

The model supports 23 languages; the language selector shows the full published set if the optional engine is installed. **Odia is not among its officially supported languages**, so this feature does not promise Odia output. A 9,000-character text input is divided into smaller speech chunks; large scripts can take considerable time to synthesize. Generated reference files and narration remain in local `user_data/uploads` unless manually removed.

Optional: Set `MOTIONFORGE_VOICE_DEVICE=cuda` (NVIDIA GPU), `mps` (Apple Silicon), or `cpu` (slow). The default setting automatically chooses an available device.

API routes: `GET /api/voice/status`, `POST /api/voice/generate`, `GET /api/jobs/{job_id}`, and `GET /api/media/{media_id}`. Voice generation refuses non-audio reference IDs, non-consented requests, unsupported languages and clips outside 3–30 seconds.

**Safety and privacy:** The server is intended for private/local use. It does not provide authentication or quotas for public production use (beyond a small voice-job queue), and keeps voice references and generated audio on disk. Before any public deployment, add authentication, abuse prevention, upload cleanup, storage quotas and rate limiting. Avoid uploading voices to shared servers without speaker consent.

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
- Source footage audio is currently muted in the finished movie; upload a music or narration track if needed.
- No login, persistent asset registry, cloud storage, shared collaborative editing, billing, automatic subtitles, or autonomous asset generation yet. Optional local voice synthesis requires a separate install.
- Jobs and upload references are kept in server memory; a restart clears the active session.
- Local default: 100 MB per upload, 40-scene projects, 10-minute render limit. Free hosting limits are lower, as described above. Rendering takes longer for large scenes or high resolution.
- Use only media and music you have rights to use.

## Architecture

`studio/index.html` (vanilla HTML/CSS/JS) → `server.py` (FastAPI API, edit planner and job worker) → FFmpeg exporter. Rendering executes server-side and keeps the editing instructions editable.

## License

MIT; see LICENSE.
