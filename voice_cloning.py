"""Optional, local voice cloning with Resemble AI Chatterbox Multilingual.

This module is imported by the lightweight editor, but torch and the model are
loaded only when a voice job is requested. The voice model is never downloaded
or loaded at web-server startup. Use only recordings with the speaker's consent.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable

# Chatterbox's published supported-language list. Odia is NOT currently listed.
LANGUAGES = {
    "en": "English", "hi": "Hindi", "ar": "Arabic", "da": "Danish",
    "de": "German", "el": "Greek", "es": "Spanish", "fi": "Finnish",
    "fr": "French", "he": "Hebrew", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "pt": "Portuguese", "ru": "Russian", "sv": "Swedish",
    "sw": "Swahili", "tr": "Turkish", "zh": "Chinese",
}
_model = None
_model_device = None
_model_lock = threading.Lock()


def voice_status() -> dict:
    """Report actual dependency availability without loading model weights."""
    installed = importlib.util.find_spec("chatterbox") is not None
    return {
        "available": installed,
        "provider": "chatterbox_multilingual",
        "model": "Resemble AI Chatterbox Multilingual",
        "license": "MIT",
        "languages": LANGUAGES,
        "note": ("Install requirements-voice.txt to enable local synthesis."
                 if not installed else "Ready to load model on first generation."),
    }


def split_narration(text: str, max_chars: int = 240) -> list[str]:
    """Produce bounded chunks without losing text in long paragraphs/sentences."""
    if not 80 <= max_chars <= 500:
        raise ValueError("Invalid segment length")
    parts = re.split(r"(?<=[.!?।！？])\s+|\n+", text.strip())
    chunks: list[str] = []
    current = ""
    for part in parts:
        if not part.strip():
            continue
        # Split overlong sentences at words, then at characters as a last resort.
        words = re.findall(r"\S+", part)
        for word in words:
            if len(word) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                while len(word) > max_chars:
                    chunks.append(word[:max_chars])
                    word = word[max_chars:]
            if word:
                if current and len(current) + 1 + len(word) > max_chars:
                    chunks.append(current)
                    current = ""
                current = (current + " " + word).strip()
    if current:
        chunks.append(current)
    return chunks


def _get_model():
    """Cache one model per server process; serialize access to model loading."""
    global _model, _model_device
    with _model_lock:
        if _model is None:
            import torch
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            preferred = os.getenv("MOTIONFORGE_VOICE_DEVICE", "auto").lower()
            if preferred not in {"auto", "cuda", "mps", "cpu"}:
                raise RuntimeError("MOTIONFORGE_VOICE_DEVICE must be auto, cuda, mps or cpu")
            if preferred == "auto":
                preferred = ("cuda" if torch.cuda.is_available() else
                             "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
                             else "cpu")
            if preferred == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA is not available. Set MOTIONFORGE_VOICE_DEVICE=cpu to try CPU inference.")
            _model = ChatterboxMultilingualTTS.from_pretrained(device=preferred)
            _model_device = preferred
    return _model


def clone_voice(reference: Path, text: str, language: str, target: Path,
                temp_dir: Path, report: Callable[[int, str], None]) -> None:
    """Generate a single WAV from an uploaded sample and script.

    Called only from the application's single-worker voice queue. The reference
    is re-encoded to 24 kHz mono WAV; each script segment is synthesized with
    the same reference, then combined with brief pauses.
    """
    if language not in LANGUAGES:
        raise ValueError("Language is not supported by Chatterbox Multilingual")
    chunks = split_narration(text)
    if not chunks:
        raise ValueError("Narration is empty")
    if not voice_status()["available"]:
        raise RuntimeError("Chatterbox is not installed. See requirements-voice.txt")

    temp_dir.mkdir(parents=True, exist_ok=True)
    reference_wav = temp_dir / "reference.wav"
    conversion = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i",
         str(reference), "-vn", "-ac", "1", "-ar", "24000", str(reference_wav)],
        capture_output=True, text=True, timeout=120,
    )
    if conversion.returncode:
        raise RuntimeError("Cannot decode the reference recording")
    report(5, "Loading Chatterbox model (first run may download weights)")
    model = _get_model()
    import torch
    import torchaudio
    snippets = []
    for idx, chunk in enumerate(chunks):
        report(8 + round(86 * idx / len(chunks)),
               f"Generating narration segment {idx + 1} of {len(chunks)}")
        with torch.inference_mode():
            audio = model.generate(
                chunk, language_id=language, audio_prompt_path=str(reference_wav)
            )
        snippets.append(audio.detach().cpu())
        if idx != len(chunks) - 1:
            snippets.append(torch.zeros_like(audio[:, :max(1, round(model.sr * .20))]).cpu()
                            if audio.shape[1] >= round(model.sr * .20)
                            else torch.zeros((audio.shape[0], round(model.sr * .20))))
    report(95, "Saving WAV narration")
    combined = torch.cat(snippets, dim=-1)
    torchaudio.save(str(target), combined, sample_rate=model.sr)
