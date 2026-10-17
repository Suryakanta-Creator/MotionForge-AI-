"""API provider and paid Veo safety checks; never make network calls."""
import json

from fastapi.testclient import TestClient

import ai_providers
from autonomous import make_storyboard
from server import app


def test_all_providers_are_fixed_https_endpoints():
    assert {"gemini", "groq", "openrouter", "kilo", "nvidia", "ovh"} <= set(ai_providers.PROVIDERS)
    assert all(spec[3].startswith("https://") for spec in ai_providers.PROVIDERS.values())


def test_provider_list_never_leaks_secret(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "top-secret-test-token")
    payload = json.dumps(ai_providers.available_providers())
    assert "top-secret-test-token" not in payload
    assert any(p["id"] == "groq" and p["configured"] for p in ai_providers.available_providers())


def test_auto_prefers_configured_and_falls_back(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-token")
    for env in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    invoked = []

    def fake_call(name, prompt, **kwargs):
        invoked.append(name)
        if name == "groq":
            raise RuntimeError("quota")
        assert name == "kilo"
        return {"scenes": []}

    monkeypatch.setattr(ai_providers, "_call", fake_call)
    result, provider = ai_providers.generate_json("test", provider="auto")
    assert provider == "kilo"
    assert result["scenes"] == []
    assert invoked == ["groq", "kilo"]


def test_selected_provider_never_falls_back(monkeypatch):
    def fail(name, prompt, **kwargs):
        raise RuntimeError("quota")
    monkeypatch.setattr(ai_providers, "_call", fail)
    try:
        ai_providers.generate_json("test", "groq")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected provider failure")


def test_auto_storyboard_uses_response_without_web(monkeypatch):
    def mock_generate(prompt, provider):
        import re
        count=int(re.search(r"EXACTLY (\d+) objects", prompt).group(1))
        return {"scenes": [{"title": f"Test {i}", "subtitle": "Verified planning mock",
                            "items": ["One", "Two", "Three"], "layout": "kinetic"}
                           for i in range(count)]}, "groq"
    monkeypatch.setattr(ai_providers, "generate_json", mock_generate)
    result=make_storyboard("Create interesting graphics about motion design",
                           duration=30, use_ai=True, ai_provider="groq")
    assert result["planning_mode"] == "groq"
    assert result["scenes"][0]["title"] == "Test 0"


def test_veo_disabled_by_default_and_requires_server_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MOTIONFORGE_ENABLE_PAID_VEO", raising=False)
    client = TestClient(app)
    assert client.get("/api/veo/capabilities").json()["available"] is False
    response=client.post("/api/veo/start", json={
        "prompt": "A beautiful original animation of a village morning",
        "confirm_paid": True})
    assert response.status_code == 503


def test_provider_route_has_no_key_fields():
    response = TestClient(app).get("/api/ai/providers")
    assert response.status_code == 200
    assert response.json()["video_model_included"] is False
