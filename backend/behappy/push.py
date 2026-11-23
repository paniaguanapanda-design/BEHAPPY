"""Avisos push (Expo)."""
import httpx
from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field
from . import pro
from .core import db, logger
from .security import current_user


router = APIRouter(prefix="/api")


# --- Avisos push (Expo) ---
class PushTokenIn(BaseModel):
    token: str = Field(max_length=200)
    lang: str = Field(default="it", max_length=5)


@router.post("/push/token")
async def save_push_token(body: PushTokenIn, request: Request):
    user = await current_user(request)
    if not body.token.startswith(("ExponentPushToken[", "ExpoPushToken[")):
        raise HTTPException(400, "Invalid token")
    await db.users.update_many({"push_tokens": body.token, "user_id": {"$ne": user["user_id"]}},
                               {"$pull": {"push_tokens": body.token}})  # un telefono, una cuenta
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$addToSet": {"push_tokens": body.token},
                               "$set": {"lang": "es" if body.lang == "es" else "it"}})
    return {"ok": True}


async def send_push(user_id: str, title_by_lang: dict, body_by_lang: dict, data: dict) -> None:
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "push_tokens": 1, "lang": 1})
        tokens = (u or {}).get("push_tokens") or []
        if not tokens:
            return
        lang = (u or {}).get("lang") or "it"
        msgs = [{"to": tk, "title": title_by_lang[lang], "body": body_by_lang[lang], "data": data, "sound": "default",
                 "channelId": "default"} for tk in tokens]
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.post("https://exp.host/--/api/v2/push/send", json=msgs)
        for tk, res in zip(tokens, (r.json().get("data") or []) if r.status_code == 200 else []):
            if (res.get("details") or {}).get("error") == "DeviceNotRegistered":
                await db.users.update_one({"user_id": user_id}, {"$pull": {"push_tokens": tk}})
    except Exception as e:
        logger.warning("push a %s no enviado: %s", user_id, e)


def _quote(text: str, n: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


async def notify_message(conv: dict, sender: dict, text: str, first_from_client: bool) -> None:
    other = [p for p in conv["participants"] if p != sender["user_id"]][0]
    data = {"type": "message", "conversation_id": conv["conversation_id"]}
    name = sender["name"].split()[0] if sender.get("name") else ""
    if first_from_client and other == conv.get("specialist_user_id"):
        spec = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0, "zone": 1}) or {}
        loc = sender.get("last_loc")
        dist = f" a {round(pro.km_between((loc['lat'], loc['lng']), pro.spec_zone(spec)[0]))} km" if loc else ""
        title = {"it": f"Nuovo cliente{dist}", "es": f"Nuevo cliente{dist}"}
        body = {"it": f"{name} ti ha scritto: «{_quote(text)}». Rispondi presto!",
                "es": f"{name} te ha escrito: «{_quote(text)}». ¡Responde pronto!"}
    else:
        title = {"it": sender.get("name") or "BeHappy", "es": sender.get("name") or "BeHappy"}
        body = {"it": _quote(text, 140), "es": _quote(text, 140)}
    await send_push(other, title, body, data)
