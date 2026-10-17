@echo off
setlocal
cd /d "%~dp0"
title MotionForge AI - Local Studio
echo.
echo ===========================================
echo          MotionForge AI Desktop
echo ===========================================
echo.
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg is missing. Install FFmpeg and ensure ffmpeg is in PATH.
  echo Instructions: https://ffmpeg.org/download.html
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo Could not set up Python. Install Python 3.10+ and try again.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install -r requirements-ai.txt
if errorlevel 1 (
  echo Python dependencies failed to install.
  pause
  exit /b 1
)
set "MOTIONFORGE_HOST=127.0.0.1"
set "MOTIONFORGE_REQUIRE_AUTH=0"
set "MOTIONFORGE_PASSWORD="
set "PORT=7860"
echo.
echo Studio: http://127.0.0.1:7860
echo The local app uses your own PC. Press Ctrl+C here to stop.
echo.
start "" "http://127.0.0.1:7860"
python server.py
pause
