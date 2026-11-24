"""Avisos de BE HAPPY a los especialistas. Es una sola via: el administrador escribe, el especialista lee.
Llegan por correo y, si tiene la app con notificaciones, por push. Quedan guardados en la app (perfil > Avisos)."""
import html as htmllib
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import admin, mail, push
from .core import db, iso, new_id, now
from .security import current_user


router = APIRouter(prefix="/api")

CHANNELS = ("email", "push")
MAX_PER_DAY = 5  # tope por especialista: evita enviar en exceso por error


class NoticeIn(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    channels: List[str] = Field(default_factory=lambda: list(CHANNELS))


def _email_html(subject: str, text: str) -> str:
    paras = "".join(f"<p>{htmllib.escape(p)}</p>" for p in text.split("\n") if p.strip())
    return ("<div style='font-family:Arial,sans-serif;font-size:15px;color:#142422'>"
            "<h2 style='color:#0B5C55;margin:0 0 8px'>BE HAPPY</h2>"
            f"<h3 style='margin:0 0 12px'>{htmllib.escape(subject)}</h3>{paras}"
            "<p style='color:#666;font-size:12px'>Aviso del equipo de BE HAPPY a los especialistas inscritos.</p></div>")


def _public(doc: dict) -> dict:
    return {"notice_id": doc["notice_id"], "subject": doc["subject"], "text": doc["text"],
            "created_at": doc["created_at"], "read": bool(doc.get("read_at"))}


@router.post("/admin/specialists/{sid}/notice")
async def admin_send_notice(sid: str, body: NoticeIn, x_admin_token: Optional[str] = Header(None)):
    admin.require_admin(x_admin_token)
    chans = [c for c in dict.fromkeys(body.channels) if c in CHANNELS]
    if not chans:
        raise HTTPException(400, "Elige correo, push o ambos")
    subject, text = body.subject.strip(), body.text.strip()
    if not subject or not text:
        raise HTTPException(400, "Escribe asunto y texto")
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0, "user_id": 1})
    if not s:
        raise HTTPException(404, "Specialist not found")
    today = now().strftime("%Y-%m-%d")
    sent_today = await db.specialist_notices.count_documents({"specialist_id": sid, "created_at": {"$gte": today}})
    if sent_today >= MAX_PER_DAY:
        raise HTTPException(429, f"Ya se han enviado {MAX_PER_DAY} avisos hoy a este especialista")
    u = await db.users.find_one({"user_id": s["user_id"]}, {"_id": 0, "email": 1}) or {}
    nid = new_id("notice")
    email_sent = None
    if "email" in chans:
        email_sent = bool(u.get("email")) and await mail.send_email(
            u["email"], f"BE HAPPY: {subject}", text, _email_html(subject, text))
    push_sent = False
    if "push" in chans:
        snippet = text if len(text) <= 140 else text[:137] + "..."
        # El mismo texto en los tres idiomas: el aviso se escribe en un idioma y llega tal cual.
        await push.send_push(s["user_id"], {"es": subject, "it": subject, "en": subject},
                             {"es": snippet, "it": snippet, "en": snippet}, {"type": "notice", "notice_id": nid})
        push_sent = True  # send_push no devuelve resultado; si falla, lo registra en el log del servidor
    doc = {"notice_id": nid, "specialist_id": sid, "user_id": s["user_id"], "subject": subject, "text": text,
           "channels": chans, "email_sent": email_sent, "push_attempted": push_sent,
           "created_at": iso(now()), "read_at": None}
    await db.specialist_notices.insert_one(doc)
    return {"ok": True, "notice_id": nid, "email": email_sent, "push": push_sent}


@router.get("/admin/specialists/{sid}/notices")
async def admin_list_notices(sid: str, x_admin_token: Optional[str] = Header(None)):
    admin.require_admin(x_admin_token)
    items = await db.specialist_notices.find({"specialist_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return [{**_public(it), "channels": it.get("channels", []), "email_sent": it.get("email_sent"),
             "read_at": it.get("read_at")} for it in items]


@router.get("/specialists/me/notices")
async def my_notices(request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0, "specialist_id": 1})
    if not s:
        raise HTTPException(404, "Not a specialist")
    items = await db.specialist_notices.find({"specialist_id": s["specialist_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(100)
    unread = sum(1 for it in items if not it.get("read_at"))
    return {"unread": unread, "items": [_public(it) for it in items]}


@router.post("/specialists/me/notices/read")
async def read_notices(request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0, "specialist_id": 1})
    if not s:
        raise HTTPException(404, "Not a specialist")
    await db.specialist_notices.update_many({"specialist_id": s["specialist_id"], "read_at": None},
                                            {"$set": {"read_at": iso(now())}})
    return {"ok": True}
