"""Perfil de especialista, portfolio, verificacion y resenas."""
import os
import asyncio
import re
from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional
from . import ai, geo, mail, membership, moderation, pro
from .core import CATEGORIES, SUBTRADES, db, iso, new_id, now
from .mail import _esc
from .security import current_user, own_upload


router = APIRouter(prefix="/api")


# ---------------- Specialists ----------------
class SpecialistIn(BaseModel):
    name: str = Field(max_length=100)
    categories: List[str] = Field(max_length=10)
    subtrades: List[str] = Field(default=[], max_length=30)
    bio: str = Field("", max_length=300)
    phone: str = Field(max_length=30)
    whatsapp: Optional[str] = Field(default=None, max_length=30)
    avatar: Optional[str] = Field(default=None, max_length=300)  # foto de perfil (obligatoria)
    city: Optional[str] = Field(default=None, max_length=80)  # comune donde trabaja (formulario de la web)


class PortfolioIn(BaseModel):
    image: str = Field(max_length=300)
    caption: str = Field(default="", max_length=200)


class VerifyIn(BaseModel):
    document_image: str = Field(max_length=300)
    document_number: Optional[str] = Field(default=None, max_length=40)  # ya no se guarda: basta la foto


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field("", max_length=200)


def membership_active(s: dict) -> bool:
    exp = s.get("membership_expires_at")
    return bool(exp) and exp > iso(now())


PRIVATE_SPEC_FIELDS = ("verification_document", "document_number", "quick_replies", "alerts", "client_reports",
                       "resp_avg_min", "resp_count")


async def specialist_out(s: dict, origin: Optional[tuple] = None) -> dict:
    s.update(pro.public_pro_fields(s, origin))
    for k in PRIVATE_SPEC_FIELDS:
        s.pop(k, None)
    z = s.get("zone")
    s["zone"] = {"label": z.get("label"), "radius_km": z.get("radius_km"), "province": z.get("province")} if z else None
    s["membership_active"] = membership_active(s)
    if (s.get("reviews_count") or 0) < 3:
        s["rating_avg"] = None  # average only shown from 3 ratings
    return s


async def user_province(user: dict) -> Optional[str]:
    """Sigla de la provincia del usuario (zona elegida o, si no, la de su ultimo diagnostico con ubicacion)."""
    code = geo.prov_code(user.get("zone"))
    loc = user.get("last_loc") or {}
    if not code and loc.get("lat") is not None and loc.get("lng") is not None:
        try:
            code = geo.prov_code({"province": await geo.province_at(loc["lat"], loc["lng"])})
        except Exception:
            code = None
    return code


MEMBERSHIP_REQUIRED = "Necesitas la membresía activa para esto"


async def require_active_specialist(spec: dict):
    if not membership_active(spec):
        raise HTTPException(403, MEMBERSHIP_REQUIRED)


@router.get("/categories")
async def categories():
    return CATEGORIES


@router.post("/specialists")
async def upsert_specialist(body: SpecialistIn, request: Request):
    user = await current_user(request)
    cats = [c for c in dict.fromkeys(body.categories) if c in CATEGORIES]
    if not cats:
        raise HTTPException(400, "Choose at least one trade")
    if not body.name.strip() or not body.phone.strip():
        raise HTTPException(400, "Name and phone required")
    data = body.model_dump()
    city = (data.pop("city") or "").strip()
    data["categories"] = cats
    data["subtrades"] = [x for x in dict.fromkeys(body.subtrades) if any(x in SUBTRADES.get(c, []) for c in cats)]
    data["bio"] = data["bio"].strip()
    data["whatsapp"] = data.get("whatsapp") or data["phone"]
    existing = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if data.get("avatar"):
        if data["avatar"] != (existing or {}).get("avatar") and not own_upload(data["avatar"], user):
            raise HTTPException(400, "Invalid profile photo")
    elif existing and existing.get("avatar"):
        data.pop("avatar")  # se mantiene la foto actual
    else:
        raise HTTPException(400, "La foto de perfil es obligatoria")
    if existing:
        await db.specialists.update_one({"specialist_id": existing["specialist_id"]}, {"$set": data})
        sid = existing["specialist_id"]
    else:
        sid = new_id("spec")
        await db.specialists.insert_one({"specialist_id": sid, "user_id": user["user_id"], **data,
                                         "portfolio": [], "verified": False, "verification_status": "none",
                                         "rating_avg": 0.0, "reviews_count": 0, "created_at": iso(now())})
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "specialist", "specialist_id": sid}})
        # Tell the owner every time a new specialist signs up.
        _n, _c = _esc(str(data.get("name") or "")), _esc(", ".join(data.get("categories") or []))
        asyncio.create_task(mail.send_email(
            os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com"), f"Be Happy: nuevo especialista {data.get('name') or ''}",
            f"Nuevo especialista inscrito: {data.get('name')} ({', '.join(data.get('categories') or [])}). "
            f"Correo: {user.get('email')}. Id: {sid}.",
            f"<p>Nuevo especialista inscrito: <b>{_n}</b> ({_c}).</p><p>Correo: {_esc(str(user.get('email') or ''))}<br>Id: {sid}</p>"))
        if membership.client_kind(request) == "web" and membership.PROMO_WEB and not user.get("promo_mes_gratis"):
            # Registrado desde la web: el mes gratis empieza la primera vez que entra en la app
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"promo_mes_gratis": "pendiente"}})
    user["specialist_id"] = sid
    if city and not geo.zone_point((existing or {}).get("zone")):
        # Registro desde la web con su comune: su zona (y su provincia) quedan puestas y ya sale en la app
        zone = await geo.zone_from_city(city)
        if zone:
            await db.specialists.update_one({"specialist_id": sid}, {"$set": {"zone": zone}})
    await membership.apply_prereg(user)
    await membership.start_web_promo(user, request)
    return await specialist_out(await db.specialists.find_one({"specialist_id": sid}, {"_id": 0}))


@router.get("/specialists")
async def list_specialists(request: Request, category: Optional[str] = None, q: Optional[str] = None,
                           lat: Optional[float] = None, lng: Optional[float] = None, available: bool = False):
    user = await current_user(request)
    origin = (lat, lng) if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180 else None
    if origin:
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"last_loc": {"lat": round(lat, 3), "lng": round(lng, 3), "at": iso(now())}}})
        if not geo.zone_point(user.get("zone")):
            await geo.set_user_province(user, lat, lng, "gps")  # primera vez: su zona sale de su ubicacion
    # En cualquier pais: salen los especialistas en cuyo radio de trabajo esta el cliente. Sin zona, nadie
    # (la app le pide la ubicacion o su ciudad).
    here = geo.zone_point(user.get("zone")) or origin
    if not here:
        return []
    if not origin:
        origin = here
    # Salen los especialistas con foto de perfil que trabajan en la zona del cliente: destacados, disponibles ahora y
    # con membresia primero. Los ocultos por reportes no salen.
    # Solo especialistas con la suscripcion activa (se paga en la web): sin ella no ofrecen el servicio.
    flt = {"avatar": {"$type": "string"}, "hidden": {"$ne": True}, "membership_expires_at": {"$gt": iso(now())},
           "zone.lat": {"$ne": None}}
    if category and category != "all":
        flt["categories"] = category
    if q:
        flt["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    items = await db.specialists.find(flt, {"_id": 0, "verification_document": 0, "document_number": 0}) \
        .sort([("verified", -1), ("created_at", 1)]).to_list(500)
    hidden = await moderation.hidden_user_ids(user["user_id"])
    out = [await specialist_out(it, origin) for it in items if it["user_id"] not in hidden and geo.in_reach(here, it)]
    if available:
        out = [it for it in out if it["available_now"]]
    # Como mucho 3 destacados por oficio (los que lo compraron antes)
    featured = sorted([it for it in out if it["featured"]], key=lambda it: it.get("featured_until") or "")
    seen: dict = {}
    for it in featured:
        cat = (it.get("categories") or [""])[0]
        seen[cat] = seen.get(cat, 0) + 1
        if seen[cat] > pro.FEATURED_MAX_PER_TRADE:
            it["featured"] = False
    out.sort(key=lambda it: (not it["featured"], not it["available_now"], not it["membership_active"],
                             it.get("distance_km") if it.get("distance_km") is not None else 999))
    for it in out:
        it.pop("featured_until", None)
    return out


@router.get("/specialists/me")
async def my_specialist(request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not a specialist")
    return await specialist_out(s)


async def can_review(user: dict, s: dict) -> bool:
    if s["user_id"] == user["user_id"]:
        return False
    if await db.reviews.find_one({"specialist_id": s["specialist_id"], "user_id": user["user_id"]}):
        return False
    conv = await db.conversations.find_one({"client_id": user["user_id"], "specialist_id": s["specialist_id"]})
    return bool(conv and await db.messages.find_one({"conversation_id": conv["conversation_id"], "sender_id": user["user_id"]}))


@router.get("/specialists/{sid}")
async def get_specialist(sid: str, request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    await pro.record_view(s, user)
    out = await specialist_out(dict(s))
    out["can_review"] = await can_review(user, s)
    # Fuera de su radio de trabajo: se ve la ficha, pero sin telefono ni WhatsApp (tampoco se le puede escribir)
    out["same_province"] = geo.in_reach(geo.zone_point(user.get("zone")), s)
    if not out["same_province"] and s["user_id"] != user["user_id"] and not await db.conversations.find_one(
            {"client_id": user["user_id"], "specialist_id": sid}, {"_id": 1}):
        out.pop("phone", None)
        out.pop("whatsapp", None)
        out["contact_blocked"] = True
    return out


@router.post("/specialists/me/portfolio")
async def add_portfolio(body: PortfolioIn, request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]})
    if not s:
        raise HTTPException(404, "Not a specialist")
    await require_active_specialist(s)
    if not own_upload(body.image, user):
        raise HTTPException(400, "Invalid image")
    if not body.caption.strip():
        raise HTTPException(400, "Describe what was done")
    caps = await ai.caption_both(body.caption)
    item = {"item_id": new_id("pf"), "image": body.image, "caption": body.caption.strip(),
            "caption_es": caps["es"], "caption_it": caps["it"], "created_at": iso(now())}
    await db.specialists.update_one({"user_id": user["user_id"]}, {"$push": {"portfolio": {"$each": [item], "$position": 0}}})
    return item


@router.delete("/specialists/me/portfolio/{item_id}")
async def del_portfolio(item_id: str, request: Request):
    user = await current_user(request)
    await db.specialists.update_one({"user_id": user["user_id"]}, {"$pull": {"portfolio": {"item_id": item_id}}})
    return {"ok": True}


@router.post("/specialists/me/verify")
async def verify(body: VerifyIn, request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]})
    if not s:
        raise HTTPException(404, "Not a specialist")
    if not own_upload(body.document_image, user):
        raise HTTPException(400, "Invalid document image")
    # El numero del documento no se guarda: es un dato de identidad y la revision se hace con la foto
    await db.specialists.update_one({"user_id": user["user_id"]}, {"$set": {
        "verification_document": body.document_image, "verification_status": "in_review", "verified": False,
        "submitted_at": iso(now())}, "$unset": {"document_number": ""}})
    # badge is only granted after a manual review (no auto-approval)
    return {"verified": False, "verification_status": "in_review"}


@router.get("/specialists/{sid}/reviews")
async def list_reviews(sid: str, request: Request):
    user = await current_user(request)
    hidden = await moderation.hidden_user_ids(user["user_id"])
    items = await db.reviews.find({"specialist_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [r for r in items if r.get("user_id") not in hidden]


@router.post("/specialists/{sid}/reviews")
async def add_review(sid: str, body: ReviewIn, request: Request):
    from pymongo.errors import DuplicateKeyError
    user = await current_user(request)
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    if s["user_id"] == user["user_id"]:
        raise HTTPException(400, "You cannot review yourself")
    if await db.reviews.find_one({"specialist_id": sid, "user_id": user["user_id"]}):
        raise HTTPException(400, "You already rated this specialist")
    if not await can_review(user, s):
        raise HTTPException(403, "Write to the specialist before rating")
    review = {"review_id": new_id("rev"), "specialist_id": sid, "user_id": user["user_id"], "user_name": user["name"],
              "rating": body.rating, "comment": body.comment.strip(), "created_at": iso(now())}
    if review["comment"]:
        both = await ai.caption_both(review["comment"])
        review["comment_es"], review["comment_it"] = both["es"], both["it"]
    try:
        await db.reviews.insert_one(review)
    except DuplicateKeyError:
        raise HTTPException(400, "You already rated this specialist")
    review.pop("_id", None)
    all_r = await db.reviews.find({"specialist_id": sid}, {"_id": 0, "rating": 1}).to_list(10000)
    avg = round(sum(r["rating"] for r in all_r) / len(all_r), 1)
    await db.specialists.update_one({"specialist_id": sid}, {"$set": {"rating_avg": avg, "reviews_count": len(all_r)}})
    return review
