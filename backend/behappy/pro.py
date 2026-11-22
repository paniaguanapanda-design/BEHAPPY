"""Herramientas para especialistas: zona, horario, estadisticas, destacados y reportes de clientes."""
import os
import httpx
import math
from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from . import geo, mail, push, specialists, stores
from .core import CATEGORIES, JWT_SECRET, db, iso, logger, now
from .mail import _esc
from .security import current_user


router = APIRouter(prefix="/api")


# ---------------- Herramientas para especialistas ----------------
# Zona y horario, estadisticas, avisos push, respuestas rapidas, perfil destacado y reportes de clientes.
# BeHappy solo acerca el especialista al cliente: precios y acuerdos los pactan ellos, nosotros no intervenimos.

ROME = ZoneInfo("Europe/Rome")
TURIN = (45.0703, 7.6869)
DEFAULT_RADIUS_KM = 15
SPEC_REPORTS_TO_HIDE = 3
SPEC_REPORT_REASONS = {"no_show", "broke_agreement", "overcharged", "bad_work", "harassment", "fraud"}
FEATURED_MAX_PER_TRADE = 3
FEATURED_DAYS = {"7": 7, "30": 30}
REVIEW_PROMPT_DAYS = 2
NEARBY_PUSH_PER_DAY = 5
CAT_NAME = {
    "it": {"plumbing": "idraulica", "electrical": "elettricità", "hvac": "climatizzazione", "masonry": "muratura",
           "carpentry": "falegnameria"},
    "es": {"plumbing": "fontanería", "electrical": "electricidad", "hvac": "climatización", "masonry": "albañilería",
           "carpentry": "carpintería"},
}
DEFAULT_QUICK_REPLIES = {
    "it": ["Posso passare domani mattina", "Mi mandi una foto da vicino?", "Qual è l'indirizzo?",
           "Oggi pomeriggio sono libero", "Ci sentiamo per telefono?"],
    "es": ["Puedo pasar mañana por la mañana", "¿Me mandas una foto de cerca?", "¿Cuál es la dirección?",
           "Esta tarde estoy libre", "¿Hablamos por teléfono?"],
}


def km_between(a: tuple, b: tuple) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def spec_zone(s: dict) -> tuple:
    z = s.get("zone") or {}
    if z.get("lat") is not None and z.get("lng") is not None:
        return (z["lat"], z["lng"]), float(z.get("radius_km") or DEFAULT_RADIUS_KM)
    return TURIN, float(DEFAULT_RADIUS_KM)


def _hm(v: str) -> int:
    h, m = v.split(":")
    return int(h) * 60 + int(m)


def in_schedule(s: dict, at: Optional[datetime] = None) -> bool:
    sch = s.get("schedule")
    if not sch:
        return True  # sin horario guardado: disponible si tiene la membresia activa (como antes)
    t = (at or now()).astimezone(ROME)
    if t.isoweekday() not in (sch.get("days") or []):
        return False
    mins = t.hour * 60 + t.minute
    return _hm(sch.get("from", "08:00")) <= mins < _hm(sch.get("to", "19:00"))


def featured_active(s: dict) -> bool:
    return bool(s.get("featured_until")) and s["featured_until"] > iso(now())


def schedule_label(s: dict, lang: str) -> str:
    sch = s.get("schedule")
    if not sch or not sch.get("days"):
        return ""
    names = {"it": ["lun", "mar", "mer", "gio", "ven", "sab", "dom"], "es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]}[lang]
    days = sorted(sch["days"])
    if days == list(range(days[0], days[-1] + 1)) and len(days) > 2:
        d = f"{names[days[0] - 1]}–{names[days[-1] - 1]}"
    else:
        d = ", ".join(names[x - 1] for x in days)
    fmt = lambda v: v[:-3] if v.endswith(":00") else v.replace(":", ".")
    hours = f"{fmt(sch.get('from', '08:00')).lstrip('0') or '0'}–{fmt(sch.get('to', '19:00')).lstrip('0') or '0'}"
    return f"{d} {hours}"


def public_pro_fields(s: dict, origin: Optional[tuple] = None) -> dict:
    """Campos calculados que ven los clientes en el muro y en la ficha."""
    active = specialists.membership_active(s)
    center, radius = spec_zone(s)
    out = {"available_now": active and in_schedule(s), "featured": active and featured_active(s),
           "urgent": bool(s.get("urgent")), "zone_radius_km": radius,
           "schedule_label_it": schedule_label(s, "it"), "schedule_label_es": schedule_label(s, "es"),
           "response_min": s.get("resp_avg_min") if (s.get("resp_count") or 0) >= 3 else None}
    if origin:
        out["distance_km"] = round(km_between(origin, center), 1)
    return out


async def notify_nearby_diagnosis(diag: dict, lat: float, lng: float) -> None:
    """Una persona hizo una diagnosis: avisa a los especialistas de ese oficio que trabajan en esa zona."""
    try:
        cat = diag.get("category")
        if cat not in CATEGORIES:
            return
        place = None
        day = now().astimezone(ROME).strftime("%Y-%m-%d")
        async for s in db.specialists.find({"categories": cat, "user_id": {"$ne": diag["user_id"]},
                                            "zone.lat": {"$ne": None},
                                            "membership_expires_at": {"$gt": iso(now())}, "hidden": {"$ne": True}},
                                           {"_id": 0}):
            alerts = s.get("alerts") or {}
            if alerts.get("enabled") is False or cat not in (alerts.get("categories") or s.get("categories") or []):
                continue
            center, radius = spec_zone(s)
            if km_between((lat, lng), center) > radius:
                continue
            quota = await db.push_quota.find_one_and_update({"specialist_id": s["specialist_id"], "day": day},
                                                            {"$inc": {"count": 1}}, upsert=True, return_document=True)
            if (quota or {}).get("count", 0) > NEARBY_PUSH_PER_DAY:
                continue
            if place is None:
                place = await geo.reverse_place(lat, lng) or ""
            where_it, where_es = (f"a {place}", f"en {place}") if place else ("vicino a te", "cerca de ti")
            await push.send_push(s["user_id"],
                            {"it": f"Richiesta di {CAT_NAME['it'][cat]} vicino a te",
                             "es": f"Solicitud de {CAT_NAME['es'][cat]} cerca de ti"},
                            {"it": f"Una persona {where_it} ha fatto una diagnosi: «{diag.get('title_it') or diag.get('title_es')}».",
                             "es": f"Una persona {where_es} ha hecho una diagnosis: «{diag.get('title_es') or diag.get('title_it')}»."},
                            {"type": "nearby"})
    except Exception as e:
        logger.warning("avisos de diagnosis cercana: %s", e)


# --- Tiempo de respuesta del especialista ---
async def record_response_time(conv: dict, sent_at: str) -> None:
    try:
        last_mine = await db.messages.find_one({"conversation_id": conv["conversation_id"],
                                                "sender_id": conv["specialist_user_id"], "created_at": {"$lt": sent_at}},
                                               sort=[("created_at", -1)])
        q = {"conversation_id": conv["conversation_id"], "sender_id": conv["client_id"], "created_at": {"$lt": sent_at}}
        if last_mine:
            q["created_at"]["$gt"] = last_mine["created_at"]
        first_client = await db.messages.find_one(q, sort=[("created_at", 1)])
        if not first_client:
            return
        mins = (datetime.fromisoformat(sent_at) - datetime.fromisoformat(first_client["created_at"])).total_seconds() / 60
        await db.response_times.insert_one({"specialist_id": conv["specialist_id"], "minutes": round(mins, 1), "at": sent_at})
        last = await db.response_times.find({"specialist_id": conv["specialist_id"]}, {"_id": 0, "minutes": 1}) \
            .sort("at", -1).to_list(20)
        avg = sum(x["minutes"] for x in last) / len(last)
        await db.specialists.update_one({"specialist_id": conv["specialist_id"]},
                                        {"$set": {"resp_avg_min": round(avg), "resp_count": len(last)}})
    except Exception as e:
        logger.warning("tiempo de respuesta: %s", e)


async def after_message(conv: dict, sender: dict, msg: dict) -> None:
    if sender["user_id"] == conv.get("specialist_user_id"):
        await record_response_time(conv, msg["created_at"])
        if not conv.get("first_reply_at"):
            await db.conversations.update_one({"conversation_id": conv["conversation_id"],
                                               "first_reply_at": {"$exists": False}},
                                              {"$set": {"first_reply_at": msg["created_at"]}})
        await push.notify_message(conv, sender, msg["text"], False)
    else:
        n = await db.messages.count_documents({"conversation_id": conv["conversation_id"], "sender_id": sender["user_id"]},
                                              limit=2)
        await push.notify_message(conv, sender, msg["text"], n == 1)


# --- Visitas al perfil ---
async def record_view(s: dict, viewer: dict) -> None:
    if viewer["user_id"] == s["user_id"]:
        return
    day = now().astimezone(ROME).strftime("%Y-%m-%d")
    await db.profile_views.update_one({"specialist_id": s["specialist_id"], "viewer_id": viewer["user_id"], "day": day},
                                      {"$setOnInsert": {"at": iso(now())}}, upsert=True)


async def my_spec(request: Request) -> tuple:
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not a specialist")
    return user, s


@router.get("/specialists/me/stats")
async def my_stats(request: Request, days: str = "7"):
    user, s = await my_spec(request)
    sid = s["specialist_id"]
    n = {"7": 7, "30": 30}.get(days)
    start = iso(now() - timedelta(days=n)) if n else "0"
    prev = iso(now() - timedelta(days=2 * n)) if n else None

    async def views(a: str, b: Optional[str] = None) -> int:
        q = {"specialist_id": sid, "at": {"$gte": a}}
        if b:
            q["at"]["$lt"] = b
        return await db.profile_views.count_documents(q)

    conv_ids = [c["conversation_id"] async for c in db.conversations.find({"specialist_id": sid}, {"_id": 0, "conversation_id": 1})]

    async def clients(a: str, b: Optional[str] = None) -> int:
        q = {"conversation_id": {"$in": conv_ids}, "sender_id": {"$ne": user["user_id"]}, "created_at": {"$gte": a}}
        if b:
            q["created_at"]["$lt"] = b
        return len(await db.messages.distinct("conversation_id", q))

    v, c = await views(start), await clients(start)
    v_prev = await views(prev, start) if n else None
    c_prev = await clients(prev, start) if n else None
    rts = [x["minutes"] async for x in db.response_times.find({"specialist_id": sid, "at": {"$gte": start}}, {"_id": 0})]
    today = now().astimezone(ROME).date()
    daily = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily.append({"day": d.isoformat(), "weekday": d.isoweekday(),
                      "views": await db.profile_views.count_documents({"specialist_id": sid, "day": d.isoformat()})})
    return {"views": v, "views_change_pct": (round((v - v_prev) * 100 / v_prev) if v_prev else None),
            "clients": c, "clients_change": (c - c_prev if c_prev is not None else None),
            "response_avg_min": round(sum(rts) / len(rts)) if rts else None,
            "response_within_1h_pct": round(sum(1 for x in rts if x <= 60) * 100 / len(rts)) if rts else None,
            "rating_avg": s.get("rating_avg") if s.get("reviews_count") else None, "reviews_count": s.get("reviews_count") or 0,
            "daily": daily}


# --- Zona, horario, avisos y respuestas rapidas ---
class ZoneIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_km: int = Field(ge=1, le=50)
    days: List[int] = Field(max_length=7)
    from_: str = Field(alias="from", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    to: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")
    urgent: bool = False


@router.get("/specialists/me/settings")
async def my_settings(request: Request, lang: str = "it"):
    user, s = await my_spec(request)
    center, radius = spec_zone(s)
    alerts = s.get("alerts") or {}
    return {"zone": {"lat": center[0], "lng": center[1], "radius_km": radius, "label": (s.get("zone") or {}).get("label"),
                     "province": (s.get("zone") or {}).get("province"), "set": bool(geo.zone_point(s.get("zone")))},
            "schedule": s.get("schedule") or {"days": [1, 2, 3, 4, 5, 6], "from": "08:00", "to": "19:00"},
            "schedule_set": bool(s.get("schedule")), "urgent": bool(s.get("urgent")),
            "alerts": {"enabled": alerts.get("enabled", True), "categories": alerts.get("categories") or s.get("categories") or []},
            "quick_replies": s["quick_replies"] if s.get("quick_replies") is not None
            else DEFAULT_QUICK_REPLIES["es" if lang == "es" else "it"],
            "featured_until": s.get("featured_until") if featured_active(s) else None,
            "categories": s.get("categories") or [], "has_push": bool(user.get("push_tokens"))}


@router.put("/specialists/me/zone")
async def save_zone(body: ZoneIn, request: Request):
    user, s = await my_spec(request)
    days = sorted({d for d in body.days if 1 <= d <= 7})
    if not days or _hm(body.from_) >= _hm(body.to):
        raise HTTPException(400, "Invalid schedule")
    old = s.get("zone") or {}
    moved = old.get("lat") != body.lat or old.get("lng") != body.lng or not old.get("province")
    province = (await geo.province_at(body.lat, body.lng) or {"code": "", "name": ""}) if moved else old["province"]
    label = await geo.reverse_place(body.lat, body.lng) if moved else old.get("label")
    await db.specialists.update_one({"specialist_id": s["specialist_id"]}, {"$set": {
        "zone": {"lat": body.lat, "lng": body.lng, "radius_km": body.radius_km, "label": label, "province": province},
        "schedule": {"days": days, "from": body.from_, "to": body.to}, "urgent": body.urgent}})
    return await my_settings(request)


class AlertsIn(BaseModel):
    enabled: bool
    categories: List[str] = Field(max_length=10)


@router.put("/specialists/me/alerts")
async def save_alerts(body: AlertsIn, request: Request):
    user, s = await my_spec(request)
    cats = [c for c in dict.fromkeys(body.categories) if c in (s.get("categories") or [])]
    await db.specialists.update_one({"specialist_id": s["specialist_id"]},
                                    {"$set": {"alerts": {"enabled": body.enabled, "categories": cats}}})
    return {"enabled": body.enabled, "categories": cats}


class QuickRepliesIn(BaseModel):
    items: List[str] = Field(max_length=10)


@router.put("/specialists/me/quick-replies")
async def save_quick_replies(body: QuickRepliesIn, request: Request):
    user, s = await my_spec(request)
    items = [" ".join(x.split())[:200] for x in body.items if x.strip()][:10]
    await db.specialists.update_one({"specialist_id": s["specialist_id"]}, {"$set": {"quick_replies": items}})
    return {"items": items}


# --- Perfil destacado (compra en Google Play via RevenueCat; consumible de 7 o 30 dias) ---
@router.get("/featured/status")
async def featured_status(request: Request):
    user, s = await my_spec(request)
    cat = (s.get("categories") or [None])[0]
    taken = await db.specialists.count_documents({"categories": cat, "featured_until": {"$gt": iso(now())},
                                                  "specialist_id": {"$ne": s["specialist_id"]}}) if cat else 0
    return {"featured_until": s.get("featured_until") if featured_active(s) else None,
            "slots_left": max(0, FEATURED_MAX_PER_TRADE - taken), "category": cat,
            "membership_active": specialists.membership_active(s)}


@router.post("/featured/sync")
async def featured_sync(request: Request):
    """Pregunta a RevenueCat (clave secreta) por las compras del destacado; cada compra se aplica una sola vez."""
    user, s = await my_spec(request)
    secret = os.environ.get("REVENUECAT_SECRET_API_KEY")
    if not secret:
        raise HTTPException(503, "Purchase check unavailable")
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get(f"https://api.revenuecat.com/v1/subscribers/{user['user_id']}",
                         headers={"Authorization": f"Bearer {secret}"})
    if r.status_code not in (200, 201):
        raise HTTPException(502, "Purchase not verified")
    purchases = r.json().get("subscriber", {}).get("non_subscriptions") or {}
    added = 0
    for pid, txs in purchases.items():
        if "featured" not in pid.lower():
            continue
        days = 30 if "30" in pid else 7
        for tx in txs or []:
            tid = tx.get("id") or tx.get("store_transaction_id")
            if not tid:
                continue
            try:
                await db.featured_purchases.insert_one({"tx_id": tid, "user_id": user["user_id"], "product": pid,
                                                        "days": days, "at": iso(now())})
            except Exception:
                continue  # ya aplicada
            added += days
    if added:
        base = now()
        if featured_active(s):
            base = datetime.fromisoformat(s["featured_until"])
        await db.specialists.update_one({"specialist_id": s["specialist_id"]},
                                        {"$set": {"featured_until": iso(base + timedelta(days=added))}})
    return await featured_status(request)


# --- Reportes de clientes a especialistas ---
def _spec_decision_token(sid: str, decision: str) -> str:
    import hmac
    import hashlib
    return hmac.new(JWT_SECRET.encode(), f"spec-decision:{sid}:{decision}".encode(), hashlib.sha256).hexdigest()


async def specialist_reported(sid: str, reporter_id: str, reason: str, details: str) -> None:
    """Cuenta solo a clientes que hablaron con el. Con 3 clientes distintos el perfil se oculta y te llega un correo."""
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0})
    if not s:
        return
    if not await db.conversations.find_one({"client_id": reporter_id, "specialist_id": sid}):
        return
    s = await db.specialists.find_one_and_update({"specialist_id": sid}, {"$addToSet": {"client_reports": reporter_id}},
                                                 return_document=True, projection={"_id": 0})
    if len(s.get("client_reports") or []) < SPEC_REPORTS_TO_HIDE or s.get("hidden"):
        return
    await db.specialists.update_one({"specialist_id": sid}, {"$set": {"hidden": True, "hidden_at": iso(now())}})
    logger.warning("Especialista %s oculto por reportes", sid)
    reps = await db.reports.find({"target_type": "specialist", "target_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(20)
    base = stores._api_base()
    links = {d: f"{base}/api/admin/specialists/{sid}/decide?d={d}&t={_spec_decision_token(sid, d)}" for d in ("show", "remove")}
    lines = [f"- {r['reason']}: {r.get('details') or '(sin detalles)'} ({r['created_at'][:10]})" for r in reps]
    text = (f"El perfil de {s['name']} ({s.get('phone') or ''}) se ha ocultado: lo han reportado {SPEC_REPORTS_TO_HIDE} clientes "
            f"distintos que hablaron con él.\n\n" + "\n".join(lines) +
            f"\n\nVolver a mostrarlo: {links['show']}\nDarlo de baja: {links['remove']}")
    html = (f"<div style=\"font-family:Arial,sans-serif;color:#0a1628\"><p>El perfil de <b>{_esc(s['name'])}</b> se ha ocultado: "
            f"lo han reportado {SPEC_REPORTS_TO_HIDE} clientes distintos que hablaron con él.</p><ul>"
            + "".join(f"<li>{_esc(x[2:])}</li>" for x in lines) +
            f"</ul><p><a href=\"{_esc(links['show'])}\">Volver a mostrarlo</a> · <a href=\"{_esc(links['remove'])}\">Darlo de baja</a></p></div>")
    await mail.send_email(os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com"), f"Be Happy: perfil de {s['name']} oculto por reportes",
                     text, html)


@router.get("/admin/specialists/{sid}/decide")
async def admin_spec_decide_page(sid: str, d: str, t: str):
    import hmac
    if d not in ("show", "remove") or not hmac.compare_digest(t, _spec_decision_token(sid, d)):
        raise HTTPException(403, "Forbidden")
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    label = "Volver a mostrar" if d == "show" else "Dar de baja"
    form = (f"<form method=\"post\"><input type=\"hidden\" name=\"t\" value=\"{_esc(t)}\">"
            f"<button style=\"font-size:16px;padding:12px 24px;border-radius:999px;border:0;"
            f"background:{'#ff6b00' if d == 'show' else '#0a1628'};color:{'#0a1628' if d == 'show' else '#fff'}\">{label}</button></form>")
    return stores._decide_page(f"{label}: {s['name']}", f"<p>{_esc(s.get('phone') or '')} · reportes: {len(s.get('client_reports') or [])}</p>" + form)


@router.post("/admin/specialists/{sid}/decide")
async def admin_spec_decide(sid: str, d: str, request: Request):
    import hmac
    form = await request.form()
    t = str(form.get("t") or "")
    if d not in ("show", "remove") or not hmac.compare_digest(t, _spec_decision_token(sid, d)):
        raise HTTPException(403, "Forbidden")
    upd = {"hidden": False, "client_reports": []} if d == "show" else {"hidden": True, "removed": True, "removed_at": iso(now())}
    s = await db.specialists.find_one_and_update({"specialist_id": sid}, {"$set": upd}, return_document=True, projection={"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    await db.reports.update_many({"target_type": "specialist", "target_id": sid, "status": "open"}, {"$set": {"status": "resolved"}})
    return stores._decide_page("Hecho", f"<p>{_esc(s['name'])}: {'visible otra vez' if d == 'show' else 'dado de baja'}.</p>")


# --- Diagnosis compartida en el chat ---
def diagnosis_summary(d: dict) -> dict:
    return {"diagnosis_id": d["diagnosis_id"], "title_es": d.get("title_es"), "title_it": d.get("title_it"),
            "category": d.get("category"), "image_path": d.get("image_path"),
            "user_note": d.get("user_note"),
            "materials": [m.get("name") for m in (d.get("materials") or []) if isinstance(m, dict) and m.get("name")][:6],
            "materials_lang": d.get("language")}


async def review_prompt_for(conv: dict, user: dict) -> bool:
    if user["user_id"] != conv.get("client_id") or not conv.get("first_reply_at"):
        return False
    if conv["first_reply_at"] > iso(now() - timedelta(days=REVIEW_PROMPT_DAYS)):
        return False
    s = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0})
    return bool(s) and await specialists.can_review(user, s)
