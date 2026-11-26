"""Novedades, promociones, eventos y sorteos de BE HAPPY. El administrador publica; la app muestra un pop-up
una sola vez por anuncio y lista las novedades en el perfil. Audiencia: todos, clientes o especialistas."""
import base64
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import storage
from .admin import require_admin
from .core import APP_NAME, db, iso, new_id, now
from .security import current_user

router = APIRouter(prefix="/api")

TYPES = ("novedad", "promocion", "evento", "sorteo")
AUDIENCES = ("todos", "clientes", "especialistas")
MAX_SHOWN = 3  # como mucho 3 pop-ups pendientes a la vez
NEW_DAYS = 30  # "solo nuevos": personas registradas en los ultimos 30 dias
MAX_IMAGE_BYTES = 2 * 1024 * 1024


class AnuncioIn(BaseModel):
    type: str = Field(default="novedad")
    title: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=500)
    audience: str = Field(default="todos")
    link: Optional[str] = Field(default=None, max_length=500)
    starts_at: Optional[str] = None  # ISO 8601; por defecto ahora
    ends_at: Optional[str] = None    # por defecto, 30 dias (si es temporal)
    permanente: bool = False         # sin fecha de fin: sigue hasta que lo quites
    solo_nuevos: bool = False        # solo personas registradas en los ultimos 30 dias
    imagen_base64: Optional[str] = Field(default=None, max_length=3_000_000)  # JPEG o PNG, data URL o base64


def _parse(value: Optional[str], default: datetime) -> str:
    if not value:
        return iso(default)
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "Fecha no valida")
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return iso(d)


def _image(data_b64: str) -> tuple:
    """Devuelve (bytes, content_type, extension) si es JPEG o PNG y pesa lo razonable."""
    raw = data_b64.split(",", 1)[-1] if data_b64.startswith("data:") else data_b64
    try:
        data = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(422, "La imagen no es valida")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(422, "La imagen pesa mas de 2 MB")
    if data[:3] == b"\xff\xd8\xff":
        return data, "image/jpeg", "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "image/png", "png"
    raise HTTPException(422, "Solo JPEG o PNG")


def _check(body: AnuncioIn) -> dict:
    if body.type not in TYPES:
        raise HTTPException(422, "Tipo no valido")
    if body.audience not in AUDIENCES:
        raise HTTPException(422, "Audiencia no valida")
    link = (body.link or "").strip() or None
    if link and not link.startswith("https://"):
        raise HTTPException(422, "El enlace debe empezar por https://")
    if body.type == "sorteo" and not link:
        raise HTTPException(422, "Un sorteo necesita el enlace a sus bases legales")
    start = _parse(body.starts_at, now())
    end = None if body.permanente else _parse(body.ends_at, now() + timedelta(days=30))
    if end and end <= start:
        raise HTTPException(422, "La fecha de fin debe ser posterior al inicio")
    doc = {"announcement_id": new_id("anu"), "type": body.type, "title": body.title.strip(),
           "text": body.text.strip(), "audience": body.audience, "link": link, "solo_nuevos": bool(body.solo_nuevos),
           "starts_at": start, "ends_at": end, "active": True, "created_at": iso(now())}
    if body.imagen_base64:
        doc["_imagen"] = _image(body.imagen_base64)  # se guarda en el almacenamiento, no en la base de datos
    return doc


def _public(a: dict, seen: bool = False) -> dict:
    return {"announcement_id": a["announcement_id"], "type": a["type"], "title": a["title"], "text": a["text"],
            "link": a.get("link"), "ends_at": a.get("ends_at"), "permanente": a.get("ends_at") is None, "seen": seen,
            "image_url": f"/api/announcements/{a['announcement_id']}/imagen" if a.get("image_path") else None}


def _audience_for(user: dict) -> List[str]:
    return ["todos", "especialistas" if user.get("role") == "specialist" else "clientes"]


async def _active_for(user: dict) -> List[dict]:
    t = iso(now())
    items = await db.announcements.find(
        {"active": True, "starts_at": {"$lte": t}, "audience": {"$in": _audience_for(user)},
         "$or": [{"ends_at": None}, {"ends_at": {"$gte": t}}]},
        {"_id": 0, "_imagen": 0}).sort("starts_at", -1).to_list(100)
    cutoff = iso(now() - timedelta(days=NEW_DAYS))
    created = user.get("created_at") or ""
    if not created:
        created = ((await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "created_at": 1})) or {}).get("created_at") or ""
    es_nueva = bool(created) and created >= cutoff
    return [a for a in items if not a.get("solo_nuevos") or es_nueva]


# ---------------- Para la app ----------------
@router.get("/announcements/pending")
async def pending(request: Request):
    """Anuncios que esta persona todavia no ha visto (para el pop-up)."""
    user = await current_user(request)
    items = await _active_for(user)
    if not items:
        return {"items": []}
    seen_ids = {d["announcement_id"] for d in await db.announcement_seen.find(
        {"user_id": user["user_id"], "announcement_id": {"$in": [a["announcement_id"] for a in items]}},
        {"_id": 0, "announcement_id": 1}).to_list(1000)}
    pendientes = [a for a in items if a["announcement_id"] not in seen_ids][:MAX_SHOWN]
    return {"items": [_public(a) for a in pendientes]}


@router.get("/announcements")
async def list_mine(request: Request):
    """Lista de novedades activas para la pantalla de Novedades (vistas y no vistas)."""
    user = await current_user(request)
    items = await _active_for(user)
    seen_ids = {d["announcement_id"] for d in await db.announcement_seen.find(
        {"user_id": user["user_id"]}, {"_id": 0, "announcement_id": 1}).to_list(5000)}
    return {"items": [_public(a, a["announcement_id"] in seen_ids) for a in items[:50]]}


@router.post("/announcements/{aid}/seen")
async def mark_seen(aid: str, request: Request):
    user = await current_user(request)
    exists = await db.announcements.find_one({"announcement_id": aid}, {"_id": 1})
    if not exists:
        raise HTTPException(404, "Anuncio no encontrado")
    await db.announcement_seen.update_one(
        {"_id": f"{aid}:{user['user_id']}"},
        {"$setOnInsert": {"announcement_id": aid, "user_id": user["user_id"], "seen_at": iso(now())}},
        upsert=True)
    return {"ok": True}


# ---------------- Para el administrador ----------------
@router.post("/admin/anuncios")
async def create_announcement(body: AnuncioIn, x_admin_token: Optional[str] = Header(default=None)):
    require_admin(x_admin_token)
    doc = _check(body)
    img = doc.pop("_imagen", None)
    if img:
        data, ctype, ext = img
        path = f"{APP_NAME}/anuncios/{doc['announcement_id']}.{ext}"
        await run_in_threadpool(storage.put_object, path, data, ctype)
        doc["image_path"], doc["image_type"] = path, ctype
    await db.announcements.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/announcements/{aid}/imagen")
async def announcement_image(aid: str):
    """Foto del anuncio. Publica: es la misma foto que ve cualquiera que abra el anuncio."""
    a = await db.announcements.find_one({"announcement_id": aid, "image_path": {"$exists": True}}, {"_id": 0, "image_path": 1, "image_type": 1})
    if not a:
        raise HTTPException(404, "Sin imagen")
    try:
        data, _ = await run_in_threadpool(storage.get_object, a["image_path"])
    except Exception:
        raise HTTPException(404, "Sin imagen")
    return Response(content=data, media_type=a.get("image_type") or "image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/admin/anuncios")
async def admin_list(x_admin_token: Optional[str] = Header(default=None)):
    require_admin(x_admin_token)
    items = await db.announcements.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": items}


@router.post("/admin/anuncios/{aid}/desactivar")
async def deactivate(aid: str, x_admin_token: Optional[str] = Header(default=None)):
    require_admin(x_admin_token)
    res = await db.announcements.update_one({"announcement_id": aid}, {"$set": {"active": False}})
    if res.matched_count == 0:
        raise HTTPException(404, "Anuncio no encontrado")
    return {"ok": True}
