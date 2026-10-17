"""Secure provider adapters for optional AI storyboard planning.

Key values stay server-side in environment variables. No custom URLs.
Only quota-limited free-tier models are chosen by default.
"""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL", "gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta"),
    "groq": ("GROQ_API_KEY", "GROQ_MODEL", "openai/gpt-oss-20b", "https://api.groq.com/openai/v1"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "openrouter/free", "https://openrouter.ai/api/v1"),
    "kilo": ("KILO_API_KEY", "KILO_MODEL", "kilo-auto/free", "https://api.kilo.ai/api/gateway"),
    "nvidia": ("NVIDIA_API_KEY", "NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b", "https://integrate.api.nvidia.com/v1"),
    "ovh": ("OVH_AI_API_KEY", "OVH_AI_MODEL", "gpt-oss-20b", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"),
}
AUTO_ORDER = ("gemini", "groq", "openrouter", "nvidia", "kilo", "ovh")


def available_providers():
    """Never expose API key values to the UI."""
    return [{"id": name, "configured": name in ("kilo", "ovh") or bool(os.getenv(spec[0])),
             "requires_key": name not in ("kilo", "ovh")} for name, spec in PROVIDERS.items()]


def _decode_json_text(content):
    text = content.strip()
    if text.startswith(chr(96) * 3):
        text = re.sub(r"^" + chr(96) * 3 + r"(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*" + chr(96) * 3 + r"$", "", text)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Expected an object")
    return result


def _call(provider, prompt, *, timeout=55):
    key_var, model_var, default_model, base = PROVIDERS[provider]
    key = os.getenv(key_var, "").strip()
    if not key and provider not in ("kilo", "ovh"):
        raise ValueError("Provider API key not configured")
    model = os.getenv(model_var, "").strip() or default_model
    if provider == "gemini":
        from urllib.parse import quote
        endpoint = base + "/models/" + quote(model, safe="-_.") + ":generateContent"
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": {"responseMimeType": "application/json"}}
        headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    else:
        endpoint = base + "/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.65, "max_tokens": 4096}
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
    req = Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                  headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except HTTPError as exc:
        raise RuntimeError(f"{provider} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"{provider} was unreachable") from exc
    if provider == "gemini":
        candidates = data.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        result_text = "".join(p.get("text", "") for p in parts)
    else:
        choices = data.get("choices") or []
        result_text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
    if not isinstance(result_text, str) or not result_text.strip():
        raise RuntimeError("Provider returned no text")
    return _decode_json_text(result_text)


def generate_json(prompt, provider="auto"):
    """Generate a JSON object, returning (data, actual_provider).

    Auto uses configured keys followed by anonymous free endpoints. Explicit
    provider selection never silently switches to another provider.
    """
    if provider != "auto" and provider not in PROVIDERS:
        raise ValueError("Unknown AI provider")
    order = [provider] if provider != "auto" else [
        name for name in AUTO_ORDER
        if name in ("kilo", "ovh") or os.getenv(PROVIDERS[name][0], "").strip()
    ]
    errors = []
    for name in order:
        try:
            return _call(name, prompt), name
        except (RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {type(exc).__name__}")
    raise RuntimeError("No free-tier LLM available: " + ", ".join(errors))
