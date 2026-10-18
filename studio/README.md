# MotionForge AI — Creator Studio Presets

This folder is an **additive starter workflow** for MotionForge's existing FastAPI/Python/Pillow/FFmpeg editor. It does not replace the main app.

## Quick start (without an AI API key)

From the repository root, install `requirements.txt` and make sure **FFmpeg and ffprobe** are available on PATH.

```bash
python studio/render_preset.py --preset studio/presets/creator_intro_30s.json --output studio_exports/creator_intro_30s.mp4 --quality draft --ambience
```

This sample creates a **30-second, 16:9, H.264/AAC MP4** using the existing `autonomous.render_storyboard` renderer. `--quality standard` increases output from 426×240 to 640×360. Use `9:16` or `1:1` inside a copy of the JSON for Shorts or square videos. Note that standard here is not 1080p; export resolution limits are in the project README.

Edit the JSON `scenes` to change title, subtitle, scene layout, palette, labels, and UI card contents. Supported layouts: `kinetic`, `cards`, `steps`, `dashboard`, `scroll`, `split`, `quote`, and `metrics`. Each scene is assigned an equal number of frames, so make sure duration / scene count is 1–16 seconds.

## Connected-app workflow

- **ChatGPT:** creative brief, story and shot planning, editing critique, brand/style directions, code changes.
- **GitHub (connected):** edit presets, version the renderer, review and test proposed changes.
- **HeyGen (connected):** optional separately generated clips, narration or translations; account access, plan limits and licensing still apply.
- **Figma / Canva / Adobe (connect as needed):** build visual assets and branding. Import/export to MotionForge currently requires manual media transfer; do not assume a direct in-chat synchronized timeline.
- **FFmpeg on the render machine:** generate final video and audio streams, export MP4. A Vercel-hosted web interface does not guarantee long-running video render capacity.

## Production stages

1. Brief — topic, target platform, duration, approved assets, language and pacing.
2. Storyboard — 3–8 second beats, copy, animation style, motion direction, visual hierarchy.
3. Design — titles, lower thirds, cards, UI screens, colors, fonts and sound direction.
4. Draft — render preview and check legibility, frame boundaries, audio and safe areas.
5. Revisions — refine timing, typography, scene order, transitions and camera motion.
6. Final export — MP4 H.264/AAC with dimensions and playback inspected with `ffprobe`.

**What this preset actually does:** animated title/UI/card templates and native scene fades. It does **not** yet add independent keyframe curves or camera zoom to arbitrary imported footage. A separate local proof-of-concept demo illustrates kinetic slides/zooms/crossfades; bringing those into the application's fully editable timeline is a next milestone.

Keep uploads, voice samples, API secrets and licensed tracks out of the public repository. The synth ambience in this preset is locally generated; publishing rights for any external assets remain your responsibility.
