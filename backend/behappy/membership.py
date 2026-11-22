"""Membresia de especialistas, mes gratis, pre-registro y RevenueCat."""
import os
import httpx
from fastapi import HTTPException, Request, APIRouter
from typing import Optional
from datetime import datetime, timezone, timedelta
from .core import db, iso, logger, new_id, now
from .security import current_user


router = APIRouter(prefix="/api")


# ---------------- Membership (Stripe + RevenueCat) ----------------
PLANS = {"monthly": {"amount": 19.99, "days": 30}, "yearly": {"amount": 199.99, "days": 365}}


async def activate_membership(user_id: str, plan: str, source: str, expires_at: Optional[datetime] = None):
    current = await db.memberships.find_one({"user_id": user_id}, {"_id": 0})
    if expires_at is None:
        base = now()
        if current and current.get("expires_at") and current["expires_at"] > iso(base):
            base = datetime.fromisoformat(current["expires_at"])
        expires_at = base + timedelta(days=PLANS[plan]["days"])
    exp = iso(expires_at)
    await db.memberships.update_one({"user_id": user_id}, {"$set": {
        "user_id": user_id, "plan": plan, "source": source, "expires_at": exp, "updated_at": iso(now())}}, upsert=True)
    await db.specialists.update_one({"user_id": user_id}, {"$set": {"membership_expires_at": exp, "membership_plan": plan}})
    return exp


async def membership_payload(user_id: str) -> dict:
    m = await db.memberships.find_one({"user_id": user_id}, {"_id": 0}) or {}
    if not m.get("expires_at"):
        s = await db.specialists.find_one({"user_id": user_id}, {"_id": 0, "membership_expires_at": 1, "membership_plan": 1}) or {}
        if s.get("membership_expires_at"):
            m = {"expires_at": s["membership_expires_at"], "plan": s.get("membership_plan"), "source": "admin"}
    exp = m.get("expires_at")
    return {"active": bool(exp and exp > iso(now())), "plan": m.get("plan"), "source": m.get("source"), "expires_at": exp,
            "plans": {k: v["amount"] for k, v in PLANS.items()}, "currency": "EUR"}


# ---------------- Registro desde la web ----------------
PROMO_WEB = os.environ.get("PROMO_MES_GRATIS_WEB", "true").strip().lower() != "false"


def client_kind(request: Request) -> str:
    """Solo acepta como web las peticiones firmadas por el proxy de confianza."""
    kind = (request.headers.get("x-behappy-client") or "").strip().lower()
    if kind != "web":
        return kind
    import hmac
    key = os.environ.get("WEB_PROXY_KEY", "")
    supplied = request.headers.get("x-behappy-proxy-key", "")
    return "web" if key and hmac.compare_digest(supplied, key) else ""


async def start_web_promo(user: dict, request: Request) -> None:
    """Quien se registro como especialista en la web empieza su mes gratis al entrar por primera vez en la app."""
    try:
        if client_kind(request) != "app" or not user.get("specialist_id"):
            return
        claimed = await db.users.find_one_and_update({"user_id": user["user_id"], "promo_mes_gratis": "pendiente"},
                                                     {"$set": {"promo_mes_gratis": "aplicada", "promo_aplicada_en": iso(now())}})
        if not claimed:
            await grant_welcome_month(user)
            return
        current = await db.memberships.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
        base = now()
        if current.get("expires_at") and current["expires_at"] > iso(base):
            base = datetime.fromisoformat(current["expires_at"])
        await activate_membership(user["user_id"], current.get("plan") or "monthly", "registro_web",
                                  base + timedelta(days=30))
        logger.info("Mes gratis de registro web aplicado a %s", user["user_id"])
    except Exception as e:
        logger.warning("mes gratis web no aplicado a %s: %s", user.get("user_id"), e)


async def grant_welcome_month(user: dict) -> None:
    """Every new specialist gets one free month, also those who sign up straight from the app (before, only web
    sign-ups and pre-registered emails did). Once per user; skipped if they ever had a membership (paid, pre-registro
    or web promo). Existing specialists without one get it the next time they open the app."""
    if not PROMO_WEB or await db.memberships.find_one({"user_id": user["user_id"]}, {"_id": 1}):
        return
    claimed = await db.users.find_one_and_update(
        {"user_id": user["user_id"], "promo_mes_gratis": {"$exists": False}},
        {"$set": {"promo_mes_gratis": "aplicada", "promo_aplicada_en": iso(now()), "promo_origen": "bienvenida"}})
    if not claimed:
        return
    await activate_membership(user["user_id"], "monthly", "bienvenida", now() + timedelta(days=30))
    logger.info("Mes gratis de bienvenida aplicado a %s", user["user_id"])


# ---------------- Pre-registro desde la web ----------------
# La web www.be-happyapp.com guarda los pre-registros en esta coleccion (misma base de datos).
PREREG = "preregistro_especialistas"
PREREG_FREE_DAYS = 30
# Especialidad elegida en la web -> oficio de la app (y sub-oficio si aplica)
PREREG_TRADES = {"idraulica": ("plumbing", None), "elettricita": ("electrical", None), "climatizzazione": ("hvac", None),
                 "muratura": ("masonry", None), "pittura": ("masonry", "pintura"),
                 "falegnameria": ("carpentry", None), "serrature": ("carpentry", "cerrajeria")}


async def claim_prereg_free_month(user: dict) -> bool:
    """Si el email del usuario se pre-registro en la web, le da 1 mes gratis (una sola vez).
    Solo se llama cuando el usuario ya tiene perfil de especialista."""
    email = (user.get("email") or "").strip().lower()
    if not email:
        return False
    pre = await db[PREREG].find_one_and_update(
        {"email": email, "promo.estado": "reservada"},
        {"$set": {"promo.estado": "aplicada", "promo.aplicadaEn": now(), "estado": "activado",
                  "user_id": user["user_id"], "actualizadoEn": now()}})
    if not pre:
        return False
    current = await db.memberships.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    base = now()
    if current.get("expires_at") and current["expires_at"] > iso(base):
        base = datetime.fromisoformat(current["expires_at"])
    await activate_membership(user["user_id"], current.get("plan") or "monthly", "preregistro",
                              base + timedelta(days=PREREG_FREE_DAYS))
    logger.info("Mes gratis de pre-registro aplicado a %s", user["user_id"])
    return True


async def create_profile_from_prereg(user: dict) -> None:
    """Cuenta nueva con email verificado (Google): si se pre-registro en la web, crea su perfil de
    especialista con esos datos y aplica el mes gratis. Con email sin verificar no se rellenan datos
    para no mostrar el telefono de otra persona a quien use su email."""
    email = (user.get("email") or "").strip().lower()
    pre = await db[PREREG].find_one({"email": email, "promo.estado": "reservada"}, {"_id": 0})
    if not pre or await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 1}):
        return
    trade = PREREG_TRADES.get(pre.get("especialidad"))
    if not trade:
        return  # especialidad sin equivalente en la app: el mes gratis se aplica cuando cree su perfil
    cat, sub = trade
    phone = str(pre.get("telefono") or "")[:30]
    if not phone:
        return
    sid = new_id("spec")
    await db.specialists.insert_one({"specialist_id": sid, "user_id": user["user_id"],
                                     "name": str(pre.get("nombre") or user.get("name") or "")[:100],
                                     "categories": [cat], "subtrades": [sub] if sub else [], "bio": "",
                                     "phone": phone, "whatsapp": phone, "portfolio": [], "verified": False,
                                     "verification_status": "none", "rating_avg": 0.0, "reviews_count": 0,
                                     "created_at": iso(now()), "origen": "preregistro"})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "specialist", "specialist_id": sid}})
    user["role"], user["specialist_id"] = "specialist", sid
    await claim_prereg_free_month(user)


async def apply_prereg(user: dict) -> None:
    """Nunca bloquea el login/registro si algo falla aqui."""
    try:
        if user.get("specialist_id"):
            await claim_prereg_free_month(user)
    except Exception as e:
        logger.warning("pre-registro no aplicado a %s: %s", user.get("user_id"), e)


@router.get("/membership/me")
async def membership_me(request: Request):
    user = await current_user(request)
    return await membership_payload(user["user_id"])


@router.post("/membership/revenuecat-sync")
async def revenuecat_sync(request: Request):
    """Ask RevenueCat (server-side, secret key) whether the user's 'pro' entitlement is active; never trust the phone."""
    user = await current_user(request)
    secret = os.environ.get("REVENUECAT_SECRET_API_KEY")
    if not secret:
        raise HTTPException(503, "Subscription check unavailable")
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get(f"https://api.revenuecat.com/v1/subscribers/{user['user_id']}",
                         headers={"Authorization": f"Bearer {secret}"})
    if r.status_code not in (200, 201):
        logger.warning("RevenueCat check failed: %s %s", r.status_code, r.text[:200])
        raise HTTPException(502 if r.status_code >= 500 else 403, "Subscription not verified")
    ent = (r.json().get("subscriber", {}).get("entitlements") or {}).get("pro")
    exp_raw = (ent or {}).get("expires_date")
    if not ent or not exp_raw:
        raise HTTPException(403, "No active subscription")
    exp = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= now():
        raise HTTPException(403, "Subscription expired")
    pid = (ent.get("product_identifier") or "").lower()
    plan = "yearly" if any(k in pid for k in ("anual", "annual", "year")) else "monthly"
    await activate_membership(user["user_id"], plan, "revenuecat", exp)
    return await membership_payload(user["user_id"])
