"""Google Gemini: llamadas, modelo de reserva, topes diarios de gasto y /api/health/ai."""
import os
import asyncio
import re
import json
import base64
import time as _time
from fastapi.concurrency import run_in_threadpool
from typing import Optional
from google import genai
from google.genai import types
from fastapi import APIRouter
from . import diagnosis, mail
from .core import db, iso, logger, now
from .security import rate_limit


router = APIRouter(prefix="/api")


# Free-tier key: the full "flash" models are often saturated (503), the lite ones answer. With paid Gemini,
# set GEMINI_MODEL=gemini-3.8-flash in Render for more detailed diagnoses.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_CALL_TIMEOUT = float(os.environ.get("GEMINI_CALL_TIMEOUT", "35"))
GEMINI_THINKING_BUDGET = int(os.environ.get("GEMINI_THINKING_BUDGET", "256"))
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "")  # optional fixed fallback
_gemini_client = None


def get_gemini():
    global _gemini_client
    if _gemini_client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Falta GEMINI_API_KEY en backend/.env")
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


# --- Topes diarios de gasto ---
# Gemini y Google Maps se pagan por uso. Ademas de los limites por persona, hay un maximo al dia para TODA la app:
# aunque alguien cree muchas cuentas, no puede gastar mas que esto. Se cambian en Render sin tocar el codigo.
DAILY_CAPS = {
    "gemini": int(os.environ.get("DAILY_MAX_GEMINI", "800")),  # diagnosis + traducciones
    "maps": int(os.environ.get("DAILY_MAX_MAPS", "200")),  # Places + Geocoding (alta de ferreterias)
}


class DailyLimitReached(Exception):
    pass


async def spend_daily(kind: str) -> None:
    """Cuenta una llamada de pago; si se pasa del tope del dia lanza DailyLimitReached (y avisa al admin una vez)."""
    day = now().strftime("%Y-%m-%d")
    doc = await db.usage.find_one_and_update({"_id": f"{kind}:{day}"}, {"$inc": {"count": 1}},
                                             upsert=True, return_document=True)
    count, cap = doc["count"], DAILY_CAPS[kind]
    for level, label in ((cap, "alcanzado"), (int(cap * 0.8), "al 80%")):
        if count == level:
            logger.warning("Tope diario de %s %s (%s/%s)", kind, label, count, cap)
            asyncio.create_task(mail.send_email(
                os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com"), f"Be Happy: tope diario de {kind} {label}",
                f"Hoy se han hecho {count} llamadas a {kind} (tope {cap}). Al llegar al tope se bloquean hasta mañana "
                f"(UTC). Si es uso normal, sube DAILY_MAX_{kind.upper()} en Render.",
                f"<p>Hoy se han hecho {count} llamadas a {kind} (tope {cap}).</p>"))
    if count > cap:
        raise DailyLimitReached(kind)


async def gemini_json(prompt: str, image_b64: Optional[str] = None) -> dict:
    """Pide a Gemini una respuesta en JSON, con o sin foto."""
    rate_limit("gemini-global", 600, 3600)
    await spend_daily("gemini")
    contents = []
    if image_b64:
        contents.append(types.Part.from_bytes(data=base64.b64decode(image_b64), mime_type="image/jpeg"))
    contents.append(prompt)
    model = _working_model["name"] or GEMINI_MODEL
    # The main model was saturated a moment ago: go straight to the model that answered then (for 15 minutes).
    if _busy_model["until"] > _time.monotonic() and _busy_model["use"]:
        try:
            return await _gemini_call(_busy_model["use"], contents, attempts=1)
        except Exception as e:
            logger.warning("Gemini %s (busy fallback) failed: %s", _busy_model["use"], e)
            _busy_model["until"] = 0.0
    try:
        # Only one quick retry: when the main model is saturated it is faster to move to a lighter one.
        return await _gemini_call(model, contents, attempts=2)
    except Exception as e:
        busy = _gemini_busy(e)
        # Saturated (503/429): try the lighter "lite" models first, they are rarely busy. Retired (404): any flash
        # model the key can use now. A retired model is replaced for good; a busy one only for this request.
        logger.warning("Gemini %s failed (%s); looking for another model", model, e)
        last: Exception = e
        try:
            available = await run_in_threadpool(_available_flash_models)
        except Exception as le:
            logger.warning("Gemini ListModels failed: %s", le)
            available = []
        if busy:
            available = [m for m in available if "lite" in m] + [m for m in available if "lite" not in m]
        tried = {model}
        for candidate in [c for c in [GEMINI_FALLBACK_MODEL, *available] if c][:4]:
            if candidate in tried:
                continue
            tried.add(candidate)
            try:
                result = await _gemini_call(candidate, contents, attempts=1 if busy else 3)
                if not busy:
                    _working_model["name"] = candidate
                    logger.warning("Gemini: now using %s (set GEMINI_MODEL in Render to make it permanent)", candidate)
                else:
                    _busy_model.update(use=candidate, until=_time.monotonic() + 900)
                    logger.warning("Gemini: %s busy, answered with %s (using it for 15 min)", model, candidate)
                return result
            except Exception as ce:
                logger.warning("Gemini %s failed too: %s", candidate, ce)
                last = ce
        raise last


_working_model: dict = {"name": None}
_busy_model: dict = {"use": None, "until": 0.0}  # temporary replacement while the main model is saturated


def _gemini_busy(e: Exception) -> bool:
    return any(x in str(e) for x in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))


async def _gemini_call(model: str, contents: list, attempts: int = 3) -> dict:
    cfg = dict(system_instruction="You output valid JSON only, no markdown.", response_mime_type="application/json")
    if "lite" in model:
        pass  # lite models: default settings (fast)
    elif model.startswith("gemini-3"):
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level="low")
    elif model.startswith("gemini-2.5"):
        # 2.5 models think without limit by default, which makes a photo take much longer: keep it short.
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=GEMINI_THINKING_BUDGET)
    # "High demand" (503) and rate limits (429) are usually over in seconds: wait a little and try again.
    for attempt in range(attempts):
        try:
            # A saturated model can take ~15 s just to say "busy": cap each try so the scan never hangs.
            response = await asyncio.wait_for(get_gemini().aio.models.generate_content(
                model=model, contents=contents, config=types.GenerateContentConfig(**cfg)
            ), timeout=GEMINI_CALL_TIMEOUT)
            return diagnosis.parse_json(response.text or "")
        except Exception as e:
            err = RuntimeError(f"503 UNAVAILABLE (timeout after {GEMINI_CALL_TIMEOUT:.0f}s)") \
                if isinstance(e, asyncio.TimeoutError) else e
            if not _gemini_busy(err) or attempt == attempts - 1:
                raise err
            await asyncio.sleep(1.5 * (attempt + 1))


def _available_flash_models() -> list:
    """Text "flash" models (also "lite") this API key can call now, newest stable first."""
    names = []
    for m in get_gemini().models.list():
        name = (m.name or "").removeprefix("models/")
        actions = getattr(m, "supported_actions", None) or []
        if "flash" not in name or (actions and "generateContent" not in actions):
            continue
        if any(x in name for x in ("tts", "image", "audio", "live", "embedding", "thinking")):
            continue
        names.append(name)

    def rank(n: str):
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return (float(v.group(1)) if v else 0.0, "preview" not in n and "exp" not in n)

    return sorted(names, key=rank, reverse=True)


_ai_check_cache: dict = {"at": 0.0, "out": None}


@router.get("/health/ai")
async def health_ai():
    """Public, cached check of the AI: which Gemini models answer right now (no user data, no keys).
    At most one real check per 2 minutes, with a tiny text prompt."""
    t = _time.monotonic()
    if _ai_check_cache["out"] and t - _ai_check_cache["at"] < 120:
        return _ai_check_cache["out"]
    _ai_check_cache["at"] = t
    results = {}
    try:
        available = await run_in_threadpool(_available_flash_models)
    except Exception as e:
        available = []
        results["list_models"] = str(e)[:160]
    others = [x for x in available if x != GEMINI_MODEL]
    for m in [GEMINI_MODEL] + ([x for x in others if "lite" in x] + [x for x in others if "lite" not in x])[:3]:
        try:
            await _gemini_call(m, ['Return {"ok": true}'], attempts=1)
            results[m] = "ok"
        except Exception as e:
            results[m] = str(e)[:160]
    out = {"main_model": GEMINI_MODEL, "working_model": _working_model["name"], "available": available[:8],
           "results": results, "checked_at": iso(now())}
    _ai_check_cache["out"] = out
    return out


async def caption_both(caption: str) -> dict:
    caption = caption.strip()
    try:
        r = await gemini_json('Translate this short work-photo caption. Return {"es": "<Spanish>", "it": "<Italian>"}. '
                              f'Caption: {json.dumps(caption, ensure_ascii=False)}')
        return {"es": str(r.get("es") or caption), "it": str(r.get("it") or caption)}
    except Exception as e:
        logger.warning("caption translate failed: %s", e)
        return {"es": caption, "it": caption}
