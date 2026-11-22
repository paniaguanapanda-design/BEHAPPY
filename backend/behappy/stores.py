"""Ferreterias: alta con comprobaciones (correo, VIES, Google Maps), mapa y moderacion."""
import os
import asyncio
import re
import base64
import httpx
import time as _time
from fastapi import HTTPException, Request, Header, APIRouter
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import timezone, timedelta
from . import admin, ai, diagnosis, mail, storage
from .core import APP_NAME, CATEGORIES, JWT_SECRET, db, iso, logger, new_id, now
from .mail import _esc, email_configured
from .security import client_ip, rate_limit


router = APIRouter(prefix="/api")


# ---------------- Ferreterias: inscripcion desde la web, verificacion automatica y mapa ----------------
# Una ferreteria se inscribe en la web (be-happyapp.com/ferramenta). Sale en el mapa de la app sola si pasa
# tres comprobaciones: correo confirmado con codigo, Partita IVA activa en VIES (registro IVA de la UE) y
# ficha de Google Maps clasificada como ferreteria. Si falla alguna queda "in_review" y entra en el resumen
# semanal que recibe el administrador, que la aprueba o rechaza con un clic.
STORE_CODE_MINUTES = 15
STORE_CODE_ATTEMPTS = 5
STORE_TERMS_VERSION = "2026-10-28"
STORE_CATEGORIES = CATEGORIES  # lo que vende: mismas claves que el diagnostico (fontaneria, electricidad...)
STORE_GOOGLE_TYPES = {"hardware_store", "home_improvement_store"}
STORE_REPORTS_TO_HIDE = 3
STORE_DIGEST_DAYS = 7
STORE_PHOTO_MAX = 4 * 1024 * 1024
UNAVAILABLE = {"vies_unavailable", "google_unavailable"}

STORE_EMAIL = {
    "it": {
        "code_subject": "Il tuo codice per iscrivere la ferramenta su Be Happy",
        "code_body": "Ciao {name},\n\nil codice per confermare l'iscrizione di «{store}» è: {code}\n\nScade tra {m} minuti.",
        "approved_subject": "La tua ferramenta è sulla mappa di Be Happy",
        "approved_body": "Ciao {name},\n\n«{store}» ha superato le verifiche ed è già visibile sulla mappa dell'app Be Happy.\n\nPer modificare i dati o cancellare l'iscrizione scrivi a info@be-happyapp.com.",
        "review_subject": "Stiamo verificando la tua ferramenta",
        "review_body": "Ciao {name},\n\nabbiamo ricevuto l'iscrizione di «{store}». Non siamo riusciti a verificare tutto in automatico, quindi la controlliamo a mano: ti scriviamo entro 7 giorni.",
        "rejected_subject": "Iscrizione della ferramenta non approvata",
        "rejected_body": "Ciao {name},\n\nnon abbiamo potuto approvare l'iscrizione di «{store}». Se pensi che sia un errore scrivi a info@be-happyapp.com.",
    },
    "es": {
        "code_subject": "Tu código para inscribir la ferretería en Be Happy",
        "code_body": "Hola {name}:\n\nel código para confirmar la inscripción de «{store}» es: {code}\n\nCaduca en {m} minutos.",
        "approved_subject": "Tu ferretería ya está en el mapa de Be Happy",
        "approved_body": "Hola {name}:\n\n«{store}» ha superado las comprobaciones y ya se ve en el mapa de la app Be Happy.\n\nPara cambiar los datos o darte de baja escribe a info@be-happyapp.com.",
        "review_subject": "Estamos verificando tu ferretería",
        "review_body": "Hola {name}:\n\nhemos recibido la inscripción de «{store}». No pudimos verificarlo todo automáticamente, así que la revisamos a mano: te escribimos en 7 días como máximo.",
        "rejected_subject": "Inscripción de la ferretería no aprobada",
        "rejected_body": "Hola {name}:\n\nno hemos podido aprobar la inscripción de «{store}». Si crees que es un error escribe a info@be-happyapp.com.",
    },
}


def piva_valid(piva: str) -> bool:
    """Partita IVA italiana: 11 cifras con digito de control (algoritmo de Luhn modificado)."""
    if not re.fullmatch(r"\d{11}", piva or "") or piva == "0" * 11:
        return False
    total = 0
    for i, ch in enumerate(piva[:10]):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(piva[10])


def _norm(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (v or "").lower()).strip()


async def _send_store_email(store: dict, kind: str, **extra) -> bool:
    tx = STORE_EMAIL["es" if store.get("language") == "es" else "it"]
    body = tx[f"{kind}_body"].format(name=store.get("owner_name") or "", store=store.get("name") or "", **extra)
    html = "<div style=\"font-family:Arial,sans-serif;max-width:520px;color:#0a1628\">" + "".join(
        f"<p>{_esc(p)}</p>" for p in body.split("\n\n")) + "</div>"
    return await mail.send_email(store["email"], tx[f"{kind}_subject"], body, html)


async def vies_check(piva: str) -> dict:
    """Registro IVA de la UE (gratis). {'ok': bool|None, 'name', 'address'}; ok=None si VIES no responde."""
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.get(f"https://ec.europa.eu/taxation_customs/vies/rest-api/ms/IT/vat/{piva}")
        data = r.json()
        if r.status_code >= 500 or data.get("userError") not in (None, "VALID", "INVALID"):
            return {"ok": None}
        return {"ok": bool(data.get("isValid")), "name": data.get("name") or "", "address": data.get("address") or ""}
    except Exception as e:
        logger.warning("VIES no disponible: %s", e)
        return {"ok": None}


async def places_check(name: str, address: str, cap: str, city: str) -> dict:
    """Busca la tienda en Google Maps. {'ok': bool|None, 'location', 'types', 'place_id'}; ok=None sin clave o si falla."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not key:
        return {"ok": None}
    fields = "places.id,places.displayName,places.formattedAddress,places.location,places.types,places.businessStatus"
    try:
        await ai.spend_daily("maps")
    except ai.DailyLimitReached:
        return {"ok": None}  # queda en revision manual, sin gastar
    try:
        async with httpx.AsyncClient(timeout=20) as hc:
            r = await hc.post("https://places.googleapis.com/v1/places:searchText",
                              headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": fields},
                              json={"textQuery": f"{name}, {address}, {cap} {city}", "languageCode": "it",
                                    "regionCode": "IT", "maxResultCount": 5})
        if r.status_code >= 300:
            logger.warning("Places %s %s", r.status_code, r.text[:200])
            return {"ok": None}
        places = r.json().get("places") or []
    except Exception as e:
        logger.warning("Places no disponible: %s", e)
        return {"ok": None}
    for p in places:
        types = set(p.get("types") or [])
        here = cap in (p.get("formattedAddress") or "")
        if here and types & STORE_GOOGLE_TYPES and p.get("businessStatus") != "CLOSED_PERMANENTLY":
            loc = p.get("location") or {}
            return {"ok": True, "place_id": p.get("id"), "types": sorted(types),
                    "location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}}
    return {"ok": False, "found": [sorted(p.get("types") or []) for p in places]}


async def geocode(address: str, cap: str, city: str) -> Optional[dict]:
    """Direccion -> coordenadas: Google si hay clave; si no, OpenStreetMap (Nominatim, gratis)."""
    q = f"{address}, {cap} {city}, Italia"
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "BeHappy/1.0 (info@be-happyapp.com)"}) as hc:
            use_google = bool(key)
            if use_google:
                try:
                    await ai.spend_daily("maps")
                except ai.DailyLimitReached:
                    use_google = False  # se usa OpenStreetMap, que es gratis
            if use_google:
                r = await hc.get("https://maps.googleapis.com/maps/api/geocode/json",
                                 params={"address": q, "region": "it", "key": key})
                res = r.json().get("results") or []
                if res:
                    loc = res[0]["geometry"]["location"]
                    return {"lat": loc["lat"], "lng": loc["lng"]}
            r = await hc.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 1, "countrycodes": "it"})
            res = r.json()
            if res:
                return {"lat": float(res[0]["lat"]), "lng": float(res[0]["lon"])}
    except Exception as e:
        logger.warning("geocodificacion fallida: %s", e)
    return None


async def run_store_checks(store: dict) -> dict:
    """Pasa las comprobaciones y deja la tienda 'approved' o 'in_review'. Devuelve el documento actualizado."""
    reasons = []
    vies = await vies_check(store["piva"])
    if vies["ok"] is None:
        reasons.append("vies_unavailable")
    elif not vies["ok"]:
        reasons.append("vies_invalid")
    elif store["cap"] not in vies.get("address", "") and _norm(store["city"]) not in _norm(vies.get("address", "")):
        reasons.append("vies_address_mismatch")
    places = await places_check(store["name"], store["address"], store["cap"], store["city"])
    if places["ok"] is None:
        reasons.append("google_unavailable")
    elif not places["ok"]:
        reasons.append("google_not_hardware_store")
    location = places.get("location") if places.get("ok") else None
    if not location or location.get("lat") is None:
        location = await geocode(store["address"], store["cap"], store["city"])
    if not location:
        reasons.append("no_location")
    upd = {"checks": {"vies": {k: v for k, v in vies.items()}, "google": {k: v for k, v in places.items() if k != "location"},
                      "checked_at": iso(now())},
           "review_reasons": reasons, "status": "in_review" if reasons else "approved"}
    if location:
        upd["location"] = {"type": "Point", "coordinates": [location["lng"], location["lat"]]}
    if not reasons:
        upd["approved_at"] = iso(now())
        upd["approved_by"] = "auto"
    await db.stores.update_one({"store_id": store["store_id"]}, {"$set": upd})
    return {**store, **upd}


def store_public(s: dict, origin: Optional[tuple] = None) -> dict:
    lng, lat = (s.get("location") or {}).get("coordinates") or [None, None]
    out = {"store_id": s["store_id"], "name": s["name"], "address": s["address"], "cap": s["cap"], "city": s["city"],
           "phone": s.get("phone") or "", "whatsapp": s.get("whatsapp") or "", "hours": s.get("hours") or "",
           "categories": s.get("categories") or [], "lat": lat, "lng": lng,
           "photo_url": f"/api/stores/{s['store_id']}/photo" if s.get("photo") else None}
    if "distance_m" in s:
        out["distance_km"] = round(s["distance_m"] / 1000, 2)
    return out


def require_web(request: Request) -> None:
    """Las inscripciones solo llegan desde la web (que firma con WEB_PROXY_KEY), no directamente de cualquiera."""
    import hmac
    key = os.environ.get("WEB_PROXY_KEY", "")
    if key and not hmac.compare_digest(request.headers.get("x-behappy-proxy-key", ""), key):
        raise HTTPException(403, "Forbidden")


class StoreApplyIn(BaseModel):
    name: str = Field(max_length=120)
    owner_name: str = Field(max_length=120)
    email: str = Field(max_length=254)
    phone: str = Field(max_length=30)
    whatsapp: str = Field(default="", max_length=30)
    address: str = Field(max_length=160)
    cap: str = Field(max_length=5)
    city: str = Field(max_length=80)
    province: str = Field(default="", max_length=40)
    piva: str = Field(max_length=13)
    hours: str = Field(default="", max_length=300)
    categories: List[str] = Field(default_factory=list, max_length=10)
    photo_b64: str = Field(default="", max_length=6_000_000)
    accept_terms: bool = False
    language: str = Field(default="it", max_length=5)


class StoreCodeIn(BaseModel):
    code: str = Field(max_length=12)


def _store_code_hash(store_id: str, code: str) -> str:
    import hmac
    import hashlib
    return hmac.new(JWT_SECRET.encode(), f"store:{store_id}:{code}".encode(), hashlib.sha256).hexdigest()


async def _send_store_code(store: dict) -> None:
    import secrets
    code = f"{secrets.randbelow(10**6):06d}"
    await db.stores.update_one({"store_id": store["store_id"]}, {"$set": {
        "code_hash": _store_code_hash(store["store_id"], code), "code_attempts": 0,
        "code_expires_at": now() + timedelta(minutes=STORE_CODE_MINUTES)}})
    if not await _send_store_email(store, "code", code=code, m=STORE_CODE_MINUTES):
        raise HTTPException(503, "No se pudo enviar el email, inténtalo más tarde")


@router.post("/stores/apply")
async def store_apply(body: StoreApplyIn, request: Request):
    require_web(request)
    rate_limit(f"store-apply:{client_ip(request)}", 10, 3600)
    if not email_configured():
        raise HTTPException(503, "Las inscripciones no están disponibles ahora")
    email = body.email.strip().lower()
    piva = re.sub(r"\s+", "", body.piva).upper().removeprefix("IT")
    errors = {}
    if not body.accept_terms:
        errors["accept_terms"] = "required"
    for f in ("name", "owner_name", "address", "city", "phone"):
        if len(getattr(body, f).strip()) < 2:
            errors[f] = "required"
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email):
        errors["email"] = "invalid"
    if not re.fullmatch(r"\d{5}", body.cap.strip()):
        errors["cap"] = "invalid"
    if not piva_valid(piva):
        errors["piva"] = "invalid"
    cats = [c for c in body.categories if c in STORE_CATEGORIES]
    if not cats:
        errors["categories"] = "required"
    photo = b""
    if body.photo_b64:
        try:
            photo = base64.b64decode(body.photo_b64.split(",")[-1], validate=True)
            if len(photo) > STORE_PHOTO_MAX:
                raise ValueError("too big")
            photo = diagnosis.shrink_image(photo)
        except Exception:
            errors["photo"] = "invalid"
    if errors:
        raise HTTPException(400, {"fields": errors})
    rate_limit(f"store-apply-mail:{email}", 5, 3600)
    cap, address = body.cap.strip(), body.address.strip()
    dup = await db.stores.find_one({"piva": piva, "cap": cap, "address_norm": _norm(address),
                                    "status": {"$in": ["approved", "in_review"]}})
    if dup:
        raise HTTPException(409, "already_registered")
    store_id = new_id("store")
    store = {"store_id": store_id, "name": body.name.strip(), "owner_name": body.owner_name.strip(), "email": email,
             "phone": body.phone.strip(), "whatsapp": body.whatsapp.strip(), "address": address,
             "address_norm": _norm(address), "cap": cap, "city": body.city.strip(), "province": body.province.strip(),
             "piva": piva, "hours": body.hours.strip(), "categories": cats, "status": "email_pending",
             "language": "es" if body.language == "es" else "it", "reports": [], "hidden": False,
             "terms_version": STORE_TERMS_VERSION, "terms_accepted_at": iso(now()), "terms_ip": client_ip(request),
             "created_at": iso(now())}
    if photo:
        path = f"{APP_NAME}/stores/{store_id}/photo.jpg"
        await run_in_threadpool(storage.put_object, path, photo, "image/jpeg")
        store["photo"] = path
    await db.stores.insert_one(dict(store))
    await _send_store_code(store)
    return {"ok": True, "store_id": store_id}


@router.post("/stores/{store_id}/resend")
async def store_resend(store_id: str, request: Request):
    require_web(request)
    rate_limit(f"store-resend:{store_id}", 3, 3600)
    store = await db.stores.find_one({"store_id": store_id, "status": "email_pending"}, {"_id": 0})
    if not store:
        raise HTTPException(404, "not_found")
    await _send_store_code(store)
    return {"ok": True}


@router.post("/stores/{store_id}/confirm")
async def store_confirm(store_id: str, body: StoreCodeIn, request: Request):
    import hmac
    require_web(request)
    rate_limit(f"store-confirm-ip:{client_ip(request)}", 30, 3600)
    bad = HTTPException(400, "bad_code")
    store = await db.stores.find_one({"store_id": store_id, "status": "email_pending"}, {"_id": 0})
    if not store or not store.get("code_hash"):
        raise bad
    exp = store["code_expires_at"]
    if exp.replace(tzinfo=exp.tzinfo or timezone.utc) < now() or store.get("code_attempts", 0) >= STORE_CODE_ATTEMPTS:
        raise bad
    if not hmac.compare_digest(store["code_hash"], _store_code_hash(store_id, body.code.strip())):
        await db.stores.update_one({"store_id": store_id}, {"$inc": {"code_attempts": 1}})
        raise bad
    await db.stores.update_one({"store_id": store_id}, {"$set": {"status": "checking", "email_verified_at": iso(now())},
                                                        "$unset": {"code_hash": "", "code_expires_at": ""}})
    store = await run_store_checks(store)
    await _send_store_email(store, "approved" if store["status"] == "approved" else "review")
    return {"ok": True, "status": store["status"]}


@router.get("/stores/nearby")
async def stores_nearby(request: Request, lat: float, lng: float, radius_km: float = 10, category: Optional[str] = None):
    rate_limit(f"store-nearby:{client_ip(request)}", 120, 3600)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(400, "Invalid position")
    radius_km = max(1.0, min(radius_km, 50.0))
    pipeline = [{"$geoNear": {"near": {"type": "Point", "coordinates": [lng, lat]}, "distanceField": "distance_m",
                              "maxDistance": radius_km * 1000, "spherical": True,
                              "query": {"status": "approved", "hidden": {"$ne": True}}}},
                {"$limit": 60}, {"$project": {"_id": 0}}]
    items = [store_public(s) async for s in db.stores.aggregate(pipeline)]
    if category in STORE_CATEGORIES:
        items.sort(key=lambda s: (category not in s["categories"], s.get("distance_km", 0)))
    asyncio.create_task(store_maintenance())
    return items


@router.get("/stores/{store_id}/photo")
async def store_photo(store_id: str):
    s = await db.stores.find_one({"store_id": store_id, "status": "approved"}, {"_id": 0, "photo": 1})
    if not s or not s.get("photo"):
        raise HTTPException(404, "No photo")
    data, ct = await run_in_threadpool(storage.get_object, s["photo"])
    return Response(content=data, media_type=ct, headers={"Cache-Control": "public, max-age=86400"})


async def store_reported(store_id: str, user_id: str) -> None:
    """Llamado al crear un reporte de tipo 'store': con 3 usuarios distintos la tienda se oculta del mapa."""
    s = await db.stores.find_one_and_update({"store_id": store_id}, {"$addToSet": {"reports": user_id}},
                                            return_document=True, projection={"_id": 0, "reports": 1, "hidden": 1})
    if s and len(s.get("reports") or []) >= STORE_REPORTS_TO_HIDE and not s.get("hidden"):
        await db.stores.update_one({"store_id": store_id}, {"$set": {"hidden": True, "hidden_at": iso(now()),
                                                                     "status": "in_review",
                                                                     "review_reasons": ["reported_by_users"]}})
        logger.warning("Ferreteria %s oculta por reportes", store_id)


# --- Revision semanal (sin tareas programadas: se dispara con el uso normal, como mucho una vez por hora) ---
_store_maint_last = 0.0


def _decision_token(store_id: str, decision: str) -> str:
    import hmac
    import hashlib
    return hmac.new(JWT_SECRET.encode(), f"store-decision:{store_id}:{decision}".encode(), hashlib.sha256).hexdigest()


def _api_base() -> str:
    return (os.environ.get("PUBLIC_API_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")


async def store_maintenance(force: bool = False) -> None:
    global _store_maint_last
    if not force and _time.monotonic() - _store_maint_last < 3600:
        return
    _store_maint_last = _time.monotonic()
    try:
        # 1) Si VIES o Google no respondian, se vuelve a intentar (3 dias como maximo)
        cutoff = iso(now() - timedelta(days=3))
        async for s in db.stores.find({"status": "in_review", "created_at": {"$gte": cutoff},
                                       "review_reasons": {"$not": {"$elemMatch": {"$nin": list(UNAVAILABLE)}}}},
                                      {"_id": 0}).limit(20):
            s = await run_store_checks(s)
            if s["status"] == "approved":
                await _send_store_email(s, "approved")
        # 2) Resumen semanal al administrador con las que siguen en revision
        meta = await db.meta.find_one({"_id": "store_digest"}) or {}
        if not force and meta.get("last") and meta["last"] > iso(now() - timedelta(days=STORE_DIGEST_DAYS)):
            return
        pending = await db.stores.find({"status": "in_review"}, {"_id": 0}).sort("created_at", 1).to_list(200)
        if not pending:
            return
        base = _api_base()
        rows_txt, rows_html = [], []
        for s in pending:
            links = {d: f"{base}/api/admin/stores/{s['store_id']}/decide?d={d}&t={_decision_token(s['store_id'], d)}"
                     for d in ("approve", "reject")}
            line = (f"{s['name']} — {s['address']}, {s['cap']} {s['city']} — P.IVA {s['piva']} — "
                    f"motivos: {', '.join(s.get('review_reasons') or [])}")
            rows_txt.append(f"- {line}\n  Aprobar: {links['approve']}\n  Rechazar: {links['reject']}")
            rows_html.append(f"<li style=\"margin-bottom:12px\">{_esc(line)}<br>"
                             f"<a href=\"{_esc(links['approve'])}\">Aprobar</a> · "
                             f"<a href=\"{_esc(links['reject'])}\">Rechazar</a></li>")
        to = os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com")
        subject = f"Be Happy: {len(pending)} ferretería(s) por revisar"
        intro = "Estas ferreterías no pasaron alguna comprobación automática y no salen en el mapa:"
        ok = await mail.send_email(to, subject, intro + "\n\n" + "\n".join(rows_txt),
                              f"<div style=\"font-family:Arial,sans-serif;color:#0a1628\"><p>{intro}</p>"
                              f"<ul>{''.join(rows_html)}</ul></div>")
        if ok:
            await db.meta.update_one({"_id": "store_digest"}, {"$set": {"last": iso(now())}}, upsert=True)
    except Exception as e:
        logger.warning("mantenimiento de ferreterias: %s", e)


def _decide_page(title: str, body: str) -> Response:
    html = (f"<!doctype html><html lang=\"es\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            f"<title>{_esc(title)}</title><body style=\"font-family:Arial,sans-serif;max-width:520px;margin:48px auto;"
            f"padding:0 16px;color:#0a1628\"><h1 style=\"font-size:22px\">{_esc(title)}</h1>{body}</body></html>")
    return Response(content=html, media_type="text/html")


@router.get("/admin/stores/{store_id}/decide")
async def admin_store_decide_page(store_id: str, d: str, t: str):
    """El enlace del correo solo muestra un boton: los antivirus del correo abren los enlaces y no deben aprobar nada."""
    import hmac
    if d not in ("approve", "reject") or not hmac.compare_digest(t, _decision_token(store_id, d)):
        raise HTTPException(403, "Forbidden")
    s = await db.stores.find_one({"store_id": store_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    label = "Aprobar" if d == "approve" else "Rechazar"
    info = (f"<p><b>{_esc(s['name'])}</b><br>{_esc(s['address'])}, {_esc(s['cap'])} {_esc(s['city'])}<br>"
            f"P.IVA {_esc(s['piva'])} · {_esc(s['email'])} · {_esc(s.get('phone') or '')}<br>"
            f"Estado: {_esc(s['status'])} · Motivos: {_esc(', '.join(s.get('review_reasons') or []))}</p>")
    form = (f"<form method=\"post\"><input type=\"hidden\" name=\"t\" value=\"{_esc(t)}\">"
            f"<button style=\"font-size:16px;padding:12px 24px;border-radius:999px;border:0;"
            f"background:{'#ff6b00' if d == 'approve' else '#0a1628'};color:{'#0a1628' if d == 'approve' else '#fff'}\">"
            f"{label}</button></form>")
    return _decide_page(f"{label} ferretería", info + form)


@router.post("/admin/stores/{store_id}/decide")
async def admin_store_decide(store_id: str, d: str, request: Request):
    import hmac
    form = await request.form()
    t = str(form.get("t") or request.query_params.get("t") or "")
    if d not in ("approve", "reject") or not hmac.compare_digest(t, _decision_token(store_id, d)):
        raise HTTPException(403, "Forbidden")
    if d == "approve":
        upd = {"status": "approved", "hidden": False, "reports": [], "approved_at": iso(now()), "approved_by": "admin"}
    else:
        upd = {"status": "rejected", "rejected_at": iso(now())}
    s = await db.stores.find_one_and_update({"store_id": store_id}, {"$set": upd}, return_document=True,
                                            projection={"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    await _send_store_email(s, "approved" if d == "approve" else "rejected")
    return _decide_page("Hecho", f"<p>«{_esc(s['name'])}» queda {'aprobada y visible en el mapa' if d == 'approve' else 'rechazada'}.</p>")


@router.post("/admin/stores/digest")
async def admin_store_digest(x_admin_token: Optional[str] = Header(None)):
    admin.require_admin(x_admin_token)
    await store_maintenance(force=True)
    return {"ok": True}
