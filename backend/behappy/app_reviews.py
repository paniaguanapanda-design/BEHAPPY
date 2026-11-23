"""Resenas de la app en la web."""
import os
import asyncio
import hashlib
import hmac as _hmac
from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field
from . import mail, stores, web
from .core import JWT_SECRET, db, iso, new_id, now
from .mail import _esc
from .security import rate_limit


router = APIRouter(prefix="/api")


# ---------------- Reseñas de la app (pestaña "Recensioni" de la web) ----------------
# Solo quien tiene cuenta en la app puede opinar: entra en la web con el codigo por correo (como en la suscripcion).
# Una reseña por cuenta (se puede cambiar). Se publica al momento; al administrador le llega un correo con un enlace
# para ocultarla si es spam u ofensiva.
class AppReviewIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    satisfaction: int = Field(ge=1, le=5)  # 1 molto insoddisfatto ... 5 molto soddisfatto
    recommend: bool
    comment: str = Field(default="", max_length=600)
    lang: str = Field(default="it", max_length=5)


def _review_token(rid: str) -> str:
    return _hmac.new(JWT_SECRET.encode(), f"app-review-hide:{rid}".encode(), hashlib.sha256).hexdigest()


def _public_name(name: str) -> str:
    parts = (name or "").split()
    if not parts:
        return "Utente BeHappy"
    return parts[0] + (f" {parts[1][0]}." if len(parts) > 1 and parts[1] else "")


def app_review_public(r: dict) -> dict:
    return {"id": r["review_id"], "name": r["name"], "role": r["role"], "stars": r["stars"],
            "satisfaction": r["satisfaction"], "recommend": r["recommend"], "comment": r.get("comment") or "",
            "created_at": r["created_at"], "updated_at": r.get("updated_at")}


@router.get("/web/app-reviews")
async def list_app_reviews(request: Request):
    stores.require_web(request)
    visible = {"hidden": {"$ne": True}}
    items = await db.app_reviews.find(visible, {"_id": 0}).sort("created_at", -1).to_list(60)
    total = await db.app_reviews.count_documents(visible)
    agg = await db.app_reviews.aggregate([
        {"$match": visible},
        {"$group": {"_id": None, "stars": {"$avg": "$stars"}, "rec": {"$sum": {"$cond": ["$recommend", 1, 0]}},
                    "s1": {"$sum": {"$cond": [{"$eq": ["$satisfaction", 1]}, 1, 0]}},
                    "s2": {"$sum": {"$cond": [{"$eq": ["$satisfaction", 2]}, 1, 0]}},
                    "s3": {"$sum": {"$cond": [{"$eq": ["$satisfaction", 3]}, 1, 0]}},
                    "s4": {"$sum": {"$cond": [{"$eq": ["$satisfaction", 4]}, 1, 0]}},
                    "s5": {"$sum": {"$cond": [{"$eq": ["$satisfaction", 5]}, 1, 0]}}}}]).to_list(1)
    a = agg[0] if agg else {}
    return {"count": total, "stars_avg": round(a.get("stars") or 0, 1),
            "recommend_pct": round((a.get("rec") or 0) * 100 / total) if total else 0,
            "satisfaction": [a.get(f"s{i}", 0) for i in range(1, 6)],
            "items": [app_review_public(r) for r in items]}


@router.get("/web/app-reviews/mine")
async def my_app_review(request: Request):
    user = await web.web_user(request)
    r = await db.app_reviews.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"name": _public_name(user.get("name") or ""), "review": app_review_public(r) if r else None}


@router.post("/web/app-reviews")
async def save_app_review(body: AppReviewIn, request: Request):
    user = await web.web_user(request)
    rate_limit(f"appreview:{user['user_id']}", 10, 3600)
    role = "specialist" if user.get("specialist_id") else "client"
    comment = " ".join(body.comment.split())[:600]
    existing = await db.app_reviews.find_one({"user_id": user["user_id"]}, {"_id": 0})
    data = {"stars": body.stars, "satisfaction": body.satisfaction, "recommend": body.recommend, "comment": comment,
            "name": _public_name(user.get("name") or ""), "role": role, "lang": "es" if body.lang == "es" else "it"}
    if existing:
        await db.app_reviews.update_one({"review_id": existing["review_id"]},
                                        {"$set": {**data, "updated_at": iso(now())}})
        rid = existing["review_id"]
    else:
        rid = new_id("arev")
        await db.app_reviews.insert_one({"review_id": rid, "user_id": user["user_id"], **data, "hidden": False,
                                         "created_at": iso(now())})
    link = f"{stores._api_base()}/api/admin/app-reviews/{rid}/hide?t={_review_token(rid)}"
    text = (f"{data['name']} ({role}) · {body.stars}★ · soddisfazione {body.satisfaction}/5 · "
            f"consiglia: {'sì' if body.recommend else 'no'}\n\n{comment or '(senza commento)'}\n\nNascondere: {link}")
    asyncio.create_task(mail.send_email(os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com"),
                                   f"Be Happy: nuova recensione {body.stars}★", text,
                                   f"<div style=\"font-family:Arial,sans-serif;color:#25221e;white-space:pre-line\">"
                                   f"{_esc(text)}</div>"))
    r = await db.app_reviews.find_one({"review_id": rid}, {"_id": 0})
    return app_review_public(r)


@router.get("/admin/app-reviews/{rid}/hide")
async def admin_hide_review_page(rid: str, t: str):
    if not _hmac.compare_digest(t, _review_token(rid)):
        raise HTTPException(403, "Forbidden")
    r = await db.app_reviews.find_one({"review_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Not found")
    form = (f"<form method=\"post\"><input type=\"hidden\" name=\"t\" value=\"{_esc(t)}\">"
            f"<button style=\"font-size:16px;padding:12px 24px;border-radius:999px;border:0;background:#0a1628;color:#fff\">"
            f"Ocultar reseña</button></form>")
    return stores._decide_page("Ocultar reseña", f"<p><b>{_esc(r['name'])}</b> · {r['stars']}★<br>{_esc(r.get('comment') or '')}</p>" + form)


@router.post("/admin/app-reviews/{rid}/hide")
async def admin_hide_review(rid: str, request: Request):
    form = await request.form()
    t = str(form.get("t") or "")
    if not _hmac.compare_digest(t, _review_token(rid)):
        raise HTTPException(403, "Forbidden")
    await db.app_reviews.update_one({"review_id": rid}, {"$set": {"hidden": True, "hidden_at": iso(now())}})
    return stores._decide_page("Hecho", "<p>La reseña ya no se ve en la web.</p>")
