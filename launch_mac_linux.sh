#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python 3.10 or later to run MotionForge AI."
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "Install FFmpeg and ffprobe, then try again: https://ffmpeg.org/download.html"
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install -r requirements-ai.txt
export MOTIONFORGE_HOST=127.0.0.1
export MOTIONFORGE_REQUIRE_AUTH=0
unset MOTIONFORGE_PASSWORD || true
export PORT=7860
printf '\nMotionForge AI is running at http://127.0.0.1:7860\n'
if command -v xdg-open >/dev/null 2>&1; then
  (sleep 2; xdg-open http://127.0.0.1:7860 >/dev/null 2>&1) &
elif command -v open >/dev/null 2>&1; then
  (sleep 2; open http://127.0.0.1:7860) &
fi
python server.py
