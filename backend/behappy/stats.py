"""Panel de administracion: cuantas personas usan la app, diagnosticos, IA, especialistas, solicitudes y tiendas."""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Header

from . import admin, ai
from .core import db, now


router = APIRouter(prefix="/api")


def _day(dt) -> str:
    return dt.strftime("%Y-%m-%d")


async def _per_day(coll: str, since_day: str, match: Optional[dict] = None, field: str = "created_at") -> dict:
    """{dia: cuantos} de una coleccion cuyas fechas son texto ISO ("2026-11-23T...")."""
    pipeline = [
        {"$match": {**(match or {}), field: {"$gte": since_day}}},
        {"$group": {"_id": {"$substrCP": [f"${field}", 0, 10]}, "n": {"$sum": 1}}},
    ]
    return {r["_id"]: r["n"] async for r in db[coll].aggregate(pipeline)}


async def _count(coll: str, match: Optional[dict] = None) -> int:
    return await db[coll].count_documents(match or {})


@router.get("/admin/specialists")
async def admin_specialists(x_admin_token: Optional[str] = Header(None)):
    """Lista de especialistas inscritos (los mas nuevos primero) para el panel. Sin fotos ni documentos."""
    admin.require_admin(x_admin_token)
    items = await db.specialists.find({}, {"_id": 0, "specialist_id": 1, "user_id": 1, "name": 1, "categories": 1,
                                           "phone": 1, "verification_status": 1, "membership_expires_at": 1,
                                           "created_at": 1}) \
        .sort("created_at", -1).to_list(500)
    emails = {u["user_id"]: u.get("email") async for u in db.users.find(
        {"user_id": {"$in": [it["user_id"] for it in items]}}, {"_id": 0, "user_id": 1, "email": 1})}
    now_iso = now().isoformat()
    return [{"specialist_id": it["specialist_id"], "name": it.get("name") or "", "categories": it.get("categories") or [],
             "phone": it.get("phone") or "", "email": emails.get(it["user_id"]) or "",
             "verification_status": it.get("verification_status") or "none",
             "membership_active": (it.get("membership_expires_at") or "") > now_iso,
             "created_at": it.get("created_at") or ""} for it in items]


@router.get("/admin/stats")
async def admin_stats(days: int = 30, x_admin_token: Optional[str] = Header(None)):
    """Numeros de la app para el panel /admin. Solo con la clave de administrador (cabecera X-Admin-Token)."""
    admin.require_admin(x_admin_token)
    days = max(7, min(days, 90))
    t = now()
    today = _day(t)
    since = _day(t - timedelta(days=days - 1))
    d7 = _day(t - timedelta(days=6))
    d30 = _day(t - timedelta(days=29))
    now_iso = t.isoformat()

    new_users = await _per_day("users", since)
    diagnoses = await _per_day("diagnoses", since)
    requests_day = await _per_day("service_requests", since)
    active = {r["_id"]: r["n"] async for r in db.activity_days.aggregate([
        {"$match": {"day": {"$gte": since}}}, {"$group": {"_id": "$day", "n": {"$sum": 1}}}])}
    usage = {r["_id"]: r["count"] async for r in db.usage.find({"_id": {"$regex": r"^(xai|gemini):"}})}

    series = []
    for i in range(days):
        day = _day(t - timedelta(days=days - 1 - i))
        series.append({"day": day, "new_users": new_users.get(day, 0), "active_users": active.get(day, 0),
                       "diagnoses": diagnoses.get(day, 0), "requests": requests_day.get(day, 0),
                       "ai_grok": usage.get(f"xai:{day}", 0), "ai_gemini": usage.get(f"gemini:{day}", 0)})

    def total(key: str, since_day: str) -> int:
        return sum(s[key] for s in series if s["day"] >= since_day)

    top = [{"category": r["_id"], "count": r["n"]} async for r in db.diagnoses.aggregate([
        {"$match": {"created_at": {"$gte": d30}, "category": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$category", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}, {"$limit": 6}])]

    return {
        "generated_at": now_iso,
        "days": days,
        "users": {
            "total": await _count("users"),
            "specialists": await _count("users", {"role": "specialist"}),
            "new_today": new_users.get(today, 0),
            "new_7d": total("new_users", d7),
            "new_30d": await _count("users", {"created_at": {"$gte": d30}}),
            "active_today": active.get(today, 0),
            "active_7d": len(await db.activity_days.distinct("user_id", {"day": {"$gte": d7}})),
            "active_30d": len(await db.activity_days.distinct("user_id", {"day": {"$gte": d30}})),
        },
        "diagnoses": {
            "total": await _count("diagnoses"),
            "today": diagnoses.get(today, 0),
            "last_7d": total("diagnoses", d7),
            "failed_7d": await _count("diagnoses", {"status": "failed", "created_at": {"$gte": d7}}),
            "top_categories_30d": top,
        },
        "ai": {
            "primary": "grok" if ai.xai_configured() else "gemini",
            "grok_today": usage.get(f"xai:{today}", 0),
            "gemini_today": usage.get(f"gemini:{today}", 0),
            "grok_daily_cap": ai.DAILY_CAPS["xai"],
            "gemini_daily_cap": ai.DAILY_CAPS["gemini"],
        },
        "specialists": {
            "total": await _count("specialists"),
            "active_membership": await _count("specialists", {"membership_expires_at": {"$gt": now_iso}}),
            "verified": await _count("specialists", {"verification_status": "verified"}),
            "in_review": await _count("specialists", {"verification_status": "in_review"}),
        },
        "marketplace": {
            "requests_total": await _count("service_requests"),
            "requests_open": await _count("service_requests", {"status": "open"}),
            "requests_30d": await _count("service_requests", {"created_at": {"$gte": d30}}),
            "quotes_30d": await _count("quotes", {"created_at": {"$gte": d30}}),
            "quotes_accepted_30d": await _count("quotes", {"status": "accepted", "created_at": {"$gte": d30}}),
            "conversations_total": await _count("conversations"),
            "conversations_30d": await _count("conversations", {"created_at": {"$gte": d30}}),
        },
        "stores": {
            "on_map": await _count("stores", {"status": "approved"}),
            "pending": await _count("stores", {"status": {"$in": ["email_pending", "checking", "in_review"]}}),
        },
        "series": series,
    }
