"""IA: Grok (xAI) primero y Gemini de reserva. La app no se frena si Grok falla, se satura o se queda sin creditos."""
import json
import time

import httpx
import pytest

from test_preregistro import server  # noqa: F401  (carga el entorno de pruebas)
from behappy import ai, security  # noqa: E402


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setitem(ai._xai_pause, "until", 0.0)
    monkeypatch.setitem(ai._xai_pause, "why", "")
    security._hits.clear()
    calls = {"xai": 0, "gemini": 0, "spent": []}

    async def spend(kind):
        calls["spent"].append(kind)

    async def gemini(prompt, image_b64=None):
        calls["gemini"] += 1
        return {"by": "gemini"}

    monkeypatch.setattr(ai, "spend_daily", spend)
    monkeypatch.setattr(ai, "gemini_json", gemini)
    return calls


def grok_answers(monkeypatch, calls, error=None):
    async def fake(prompt, image_b64=None, model=None):
        calls["xai"] += 1
        if error:
            raise error
        return {"by": "grok"}
    monkeypatch.setattr(ai, "xai_json", fake)


async def test_grok_answers_first(monkeypatch, setup):
    grok_answers(monkeypatch, setup)
    assert await ai.ai_json("hola") == {"by": "grok"}
    assert setup["gemini"] == 0 and setup["spent"] == ["xai"]


async def test_grok_busy_goes_to_gemini_and_skips_grok_for_a_minute(monkeypatch, setup):
    grok_answers(monkeypatch, setup, ai.XaiError(503, "busy"))
    assert await ai.ai_json("uno") == {"by": "gemini"}
    left = ai._xai_pause["until"] - time.monotonic()
    assert 50 < left <= ai.XAI_PAUSE_BUSY
    # the next people do not wait for Grok to fail again: straight to Gemini
    assert await ai.ai_json("dos") == {"by": "gemini"}
    assert setup["xai"] == 1 and setup["gemini"] == 2


async def test_grok_without_credits_pauses_ten_minutes(monkeypatch, setup):
    grok_answers(monkeypatch, setup, ai.XaiError(402, "no credits"))
    assert await ai.ai_json("uno") == {"by": "gemini"}
    assert ai._xai_pause["until"] - time.monotonic() > ai.XAI_PAUSE_BUSY
    assert "402" in ai._xai_pause["why"]


async def test_grok_back_after_the_pause(monkeypatch, setup):
    grok_answers(monkeypatch, setup)
    ai._xai_pause["until"] = time.monotonic() - 1
    assert await ai.ai_json("hola") == {"by": "grok"}


async def test_grok_daily_cap_goes_to_gemini_without_pausing(monkeypatch, setup):
    grok_answers(monkeypatch, setup)

    async def spend(kind):
        if kind == "xai":
            raise ai.DailyLimitReached(kind)
    monkeypatch.setattr(ai, "spend_daily", spend)
    assert await ai.ai_json("hola") == {"by": "gemini"}
    assert setup["xai"] == 0 and ai._xai_pause["until"] == 0.0


async def test_bad_json_from_grok_only_affects_that_request(monkeypatch, setup):
    grok_answers(monkeypatch, setup, ValueError("not json"))
    assert await ai.ai_json("hola") == {"by": "gemini"}
    assert ai._xai_pause["until"] == 0.0


async def test_without_xai_key_only_gemini(monkeypatch, setup):
    monkeypatch.delenv("XAI_API_KEY")
    grok_answers(monkeypatch, setup)
    assert await ai.ai_json("hola") == {"by": "gemini"}
    assert setup["xai"] == 0


async def test_xai_request_format_and_retry(monkeypatch):
    seen = []

    def handler(request: httpx.Request):
        seen.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        if len(seen) == 1:
            return httpx.Response(503, text="busy")  # first try busy: one quick retry
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"object": "rubinetto"}'}}]})

    client = httpx.AsyncClient(base_url="https://api.x.ai/v1", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ai, "_xai_http", client)

    async def no_sleep(_):
        return None
    monkeypatch.setattr(ai.asyncio, "sleep", no_sleep)
    assert await ai.xai_json("diagnose", "QUJD") == {"object": "rubinetto"}
    body = seen[-1]
    assert body["model"] == ai.XAI_MODEL and body["response_format"] == {"type": "json_object"}
    user = body["messages"][1]["content"]
    assert user[0] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}
    assert user[1] == {"type": "text", "text": "diagnose"}
    assert len(seen) == 2


async def test_xai_account_error_is_not_retried(monkeypatch):
    seen = []

    def handler(request):
        seen.append(1)
        return httpx.Response(401, text="bad key")

    monkeypatch.setattr(ai, "_xai_http", httpx.AsyncClient(base_url="https://api.x.ai/v1",
                                                           transport=httpx.MockTransport(handler)))
    with pytest.raises(ai.XaiError) as e:
        await ai.xai_json("hola")
    assert e.value.status == 401 and len(seen) == 1
