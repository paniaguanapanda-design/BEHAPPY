"""When the main Gemini model is saturated (503), the request is answered by a "lite" model straight away,
without making the lite model the permanent choice."""
from types import SimpleNamespace

import pytest

import server


class FakeModels:
    def __init__(self, busy: set):
        self.busy = busy
        self.calls = []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        if model in self.busy:
            raise RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")
        return SimpleNamespace(text='{"ok": "%s"}' % model)

    def list(self):
        return [SimpleNamespace(name=f"models/{n}", supported_actions=["generateContent"])
                for n in ("gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.8-flash-image")]


@pytest.fixture
def fake_gemini(monkeypatch):
    aio_models = FakeModels(busy={"gemini-3.8-flash"})
    client = SimpleNamespace(aio=SimpleNamespace(models=aio_models), models=aio_models)
    monkeypatch.setattr(server, "get_gemini", lambda: client)
    monkeypatch.setattr(server, "GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(server, "GEMINI_FALLBACK_MODEL", "")
    monkeypatch.setitem(server._working_model, "name", None)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)

    async def no_spend(_):
        return None

    monkeypatch.setattr(server, "spend_daily", no_spend)
    return aio_models


async def test_busy_main_model_falls_back_to_lite(fake_gemini):
    out = await server.gemini_json("hola")
    assert out == {"ok": "gemini-3.8-flash-lite"}
    assert fake_gemini.calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.8-flash-lite"]
    assert server._working_model["name"] is None  # busy is temporary: the next scan tries the main model again
