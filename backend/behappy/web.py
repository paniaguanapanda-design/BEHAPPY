"""Web: login con codigo por correo y suscripcion con Stripe."""
import os
import json
import jwt
import httpx
import time as _time
import hashlib
import hmac as _hmac
from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from . import mail, membership, stores
from .core import JWT_SECRET, db, iso, logger, now
from .mail import _esc
from .security import client_ip, rate_limit


router = APIRouter(prefix="/api")


# ---------------- Suscripcion de especialistas en la web (Stripe) ----------------
# La app no cobra nada: el especialista entra en be-happyapp.com/abbonamento con un codigo que le llega por correo,
# paga con Stripe Checkout y Stripe avisa a este servidor (webhook), que activa la membresia. En la app solo se ve
# "Profilo attivo / non attivo". Los precios y el webhook se crean solos en Stripe la primera vez (solo hace falta
# STRIPE_SECRET_KEY en Render).

WEB_LOGIN_MINUTES = 15
WEB_LOGIN_ATTEMPTS = 5
WEB_SESSION_HOURS = 2
STRIPE_LOOKUP = {"monthly": "behappy_specialist_monthly", "yearly": "behappy_specialist_yearly"}
STRIPE_INTERVAL = {"monthly": "month", "yearly": "year"}
STRIPE_EVENTS = ["checkout.session.completed", "invoice.paid", "customer.subscription.created",
                 "customer.subscription.updated", "customer.subscription.deleted"]
WEB_URL = os.environ.get("WEB_URL", "https://www.be-happyapp.com").rstrip("/")

WEB_LOGIN_EMAIL = {
    "it": ("Il tuo codice per accedere a Be Happy",
           "Ciao {name},\n\nil tuo codice per gestire l'abbonamento su be-happyapp.com è: {code}\n\nScade tra {m} minuti. "
           "Se non sei stato tu, ignora questa email."),
    "es": ("Tu código para entrar en Be Happy",
           "Hola {name}:\n\ntu código para gestionar la membresía en be-happyapp.com es: {code}\n\nCaduca en {m} minutos. "
           "Si no fuiste tú, ignora este correo."),
}


def _flat(data: dict, prefix: str = "") -> list:
    """Parametros anidados al formato de Stripe: line_items[0][price]=..."""
    out = []
    for k, v in data.items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            out += _flat(v, key)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out += _flat(item, f"{key}[{i}]")
                else:
                    out.append((f"{key}[]", str(item)))
        elif isinstance(v, bool):
            out.append((key, "true" if v else "false"))
        elif v is not None:
            out.append((key, str(v)))
    return out


async def stripe_api(method: str, path: str, data: Optional[dict] = None) -> dict:
    secret = os.environ.get("STRIPE_SECRET_KEY")
    if not secret:
        raise HTTPException(503, "payments_unavailable")
    async with httpx.AsyncClient(timeout=20) as hc:
        url = f"https://api.stripe.com/v1/{path}"
        if method == "GET":
            r = await hc.get(url, params=_flat(data or {}), auth=(secret, ""))
        else:
            r = await hc.request(method, url, content=urlencode(_flat(data or {})), auth=(secret, ""),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    body = r.json() if r.content else {}
    if r.status_code >= 300:
        logger.warning("Stripe %s %s -> %s %s", method, path, r.status_code, str(body)[:300])
        raise HTTPException(502, "payments_error")
    return body


def stripe_key_id() -> str:
    """Huella de la clave en uso: si se cambia de cuenta de Stripe (o de prueba a real) se vuelve a preparar todo."""
    return hashlib.sha256(os.environ.get("STRIPE_SECRET_KEY", "").encode()).hexdigest()[:16]


async def stripe_price(plan: str) -> str:
    """Id del precio de Stripe; si no existe se crea (producto 'Abbonamento specialista' + precio en EUR)."""
    cached = await db.meta.find_one({"_id": "stripe_prices"}) or {}
    if cached.get("key") != stripe_key_id():
        cached = {}
        await db.meta.replace_one({"_id": "stripe_prices"}, {"_id": "stripe_prices", "key": stripe_key_id()}, upsert=True)
    if cached.get(plan):
        return cached[plan]
    found = (await stripe_api("GET", "prices", {"lookup_keys": [STRIPE_LOOKUP[plan]], "active": True})).get("data") or []
    if found:
        pid = found[0]["id"]
    else:
        product = cached.get("product")
        if not product:
            product = (await stripe_api("POST", "products", {"name": "Abbonamento specialista Be Happy"}))["id"]
            await db.meta.update_one({"_id": "stripe_prices"}, {"$set": {"product": product}}, upsert=True)
        pid = (await stripe_api("POST", "prices", {
            "product": product, "currency": "eur", "unit_amount": int(round(membership.PLANS[plan]["amount"] * 100)),
            "recurring": {"interval": STRIPE_INTERVAL[plan]}, "lookup_key": STRIPE_LOOKUP[plan],
            "nickname": "Mensile" if plan == "monthly" else "Annuale"}))["id"]
    await db.meta.update_one({"_id": "stripe_prices"}, {"$set": {plan: pid}}, upsert=True)
    return pid


async def stripe_webhook_secret() -> Optional[str]:
    """Secreto para comprobar los avisos de Stripe: de STRIPE_WEBHOOK_SECRET o del webhook que creamos solos."""
    if os.environ.get("STRIPE_WEBHOOK_SECRET"):
        return os.environ["STRIPE_WEBHOOK_SECRET"]
    meta = await db.meta.find_one({"_id": "stripe_webhook"}) or {}
    return meta.get("secret") if meta.get("key") == stripe_key_id() else None


async def ensure_stripe_webhook() -> None:
    if not os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_WEBHOOK_SECRET"):
        return
    base = stores._api_base()
    if not base:
        return
    url = f"{base}/api/stripe/webhook"
    meta = await db.meta.find_one({"_id": "stripe_webhook"}) or {}
    if meta.get("url") == url and meta.get("secret") and meta.get("key") == stripe_key_id():
        return
    try:
        existing = (await stripe_api("GET", "webhook_endpoints", {"limit": 100})).get("data") or []
        for ep in existing:
            if ep.get("url") == url:
                await stripe_api("DELETE", f"webhook_endpoints/{ep['id']}")
        ep = await stripe_api("POST", "webhook_endpoints", {"url": url, "enabled_events": STRIPE_EVENTS,
                                                            "description": "Be Happy: abbonamenti specialisti"})
        await db.meta.update_one({"_id": "stripe_webhook"}, {"$set": {"url": url, "secret": ep["secret"], "id": ep["id"],
                                                                     "key": stripe_key_id()}}, upsert=True)
        logger.info("Webhook de Stripe creado: %s", url)
    except Exception as e:
        logger.warning("webhook de Stripe no creado: %s", e)


def verify_stripe_signature(payload: bytes, header: str, secret: str, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    sigs = [p.split("=", 1)[1] for p in header.split(",") if p.startswith("v1=")]
    try:
        ts = int(parts.get("t", "0"))
    except ValueError:
        return False
    if abs(_time.time() - ts) > tolerance:
        return False
    expected = _hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(_hmac.compare_digest(expected, s) for s in sigs)


def _period_end(sub: dict) -> Optional[int]:
    if sub.get("current_period_end"):
        return sub["current_period_end"]
    items = (sub.get("items") or {}).get("data") or []
    ends = [it.get("current_period_end") for it in items if it.get("current_period_end")]
    return max(ends) if ends else None


def _sub_plan(sub: dict) -> str:
    items = (sub.get("items") or {}).get("data") or []
    price = (items[0].get("price") if items else None) or {}
    return "yearly" if (price.get("recurring") or {}).get("interval") == "year" else "monthly"


async def sync_subscription(sub: dict, user_id: Optional[str] = None) -> None:
    """Refleja en la membresia el estado de la suscripcion de Stripe."""
    uid = user_id or (sub.get("metadata") or {}).get("user_id")
    if not uid and sub.get("customer"):
        u = await db.users.find_one({"stripe_customer_id": sub["customer"]}, {"_id": 0, "user_id": 1})
        uid = (u or {}).get("user_id")
    if not uid:
        logger.warning("suscripcion %s sin usuario", sub.get("id"))
        return
    await db.users.update_one({"user_id": uid}, {"$set": {"stripe_customer_id": sub.get("customer"),
                                                          "stripe_subscription_id": sub.get("id"),
                                                          "stripe_status": sub.get("status")}})
    end = _period_end(sub)
    if sub.get("status") in ("active", "trialing", "past_due") and end:
        # 1 dia de margen: el cobro de la renovacion puede tardar unas horas
        await membership.activate_membership(uid, _sub_plan(sub), "stripe", datetime.fromtimestamp(end, timezone.utc) + timedelta(days=1))
    elif sub.get("status") in ("canceled", "unpaid", "incomplete_expired"):
        cur = await db.memberships.find_one({"user_id": uid}, {"_id": 0}) or {}
        if cur.get("source") == "stripe":
            await membership.activate_membership(uid, _sub_plan(sub), "stripe", now())


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    secret = await stripe_webhook_secret()
    if not secret or not verify_stripe_signature(payload, request.headers.get("stripe-signature", ""), secret):
        raise HTTPException(400, "Invalid signature")
    event = json.loads(payload)
    if await db.stripe_events.find_one({"id": event.get("id")}):
        return {"ok": True}  # Stripe puede mandar el mismo aviso dos veces
    await db.stripe_events.insert_one({"id": event.get("id"), "type": event.get("type"), "at": iso(now())})
    obj = (event.get("data") or {}).get("object") or {}
    kind = event.get("type")
    if kind == "checkout.session.completed" and obj.get("mode") == "subscription" and obj.get("subscription"):
        uid = obj.get("client_reference_id")
        if uid and obj.get("customer"):
            await db.users.update_one({"user_id": uid}, {"$set": {"stripe_customer_id": obj["customer"]}})
        await sync_subscription(await stripe_api("GET", f"subscriptions/{obj['subscription']}"), uid)
    elif kind == "invoice.paid":
        sub_id = obj.get("subscription") or (((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
        if sub_id:
            await sync_subscription(await stripe_api("GET", f"subscriptions/{sub_id}"))
    elif kind and kind.startswith("customer.subscription."):
        await sync_subscription(obj)
    return {"ok": True}


# --- Acceso a la web con codigo por correo (sirve tambien a quien entra en la app con Google) ---
class WebLoginStartIn(BaseModel):
    email: str = Field(max_length=200)
    lang: str = Field(default="it", max_length=5)


class WebLoginConfirmIn(BaseModel):
    email: str = Field(max_length=200)
    code: str = Field(max_length=10)


def _web_code_hash(email: str, code: str) -> str:
    return _hmac.new(JWT_SECRET.encode(), f"web-login:{email}:{code}".encode(), hashlib.sha256).hexdigest()


@router.post("/web/login/start")
async def web_login_start(body: WebLoginStartIn, request: Request):
    stores.require_web(request)
    rate_limit(f"weblogin:{client_ip(request)}", 10, 3600)
    email = body.email.strip().lower()
    rate_limit(f"weblogin-mail:{email}", 5, 3600)
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:  # la respuesta es la misma exista o no la cuenta
        import secrets
        code = f"{secrets.randbelow(1_000_000):06d}"
        await db.web_login_codes.update_one({"email": email}, {"$set": {
            "email": email, "hash": _web_code_hash(email, code), "attempts": 0,
            "expires_at": now() + timedelta(minutes=WEB_LOGIN_MINUTES)}}, upsert=True)
        lang = "es" if body.lang == "es" else "it"
        subject, text = WEB_LOGIN_EMAIL[lang]
        text = text.format(name=(user.get("name") or "").split(" ")[0], code=code, m=WEB_LOGIN_MINUTES)
        await mail.send_email(email, subject, text, f"<div style=\"font-family:Arial,sans-serif;color:#25221e;white-space:pre-line\">"
                                               f"{_esc(text)}</div>")
    return {"ok": True}


@router.post("/web/login/confirm")
async def web_login_confirm(body: WebLoginConfirmIn, request: Request):
    stores.require_web(request)
    email = body.email.strip().lower()
    rec = await db.web_login_codes.find_one({"email": email})
    exp = (rec or {}).get("expires_at")
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if not rec or exp < now() or rec.get("attempts", 0) >= WEB_LOGIN_ATTEMPTS:
        raise HTTPException(400, "code_expired")
    if not _hmac.compare_digest(rec["hash"], _web_code_hash(email, body.code.strip())):
        await db.web_login_codes.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "code_wrong")
    await db.web_login_codes.delete_one({"email": email})
    user = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    token = jwt.encode({"sub": user["user_id"], "type": "web-billing",
                        "exp": now() + timedelta(hours=WEB_SESSION_HOURS)}, JWT_SECRET, algorithm="HS256")
    return {"token": token}


async def web_user(request: Request) -> dict:
    stores.require_web(request)
    auth = request.headers.get("authorization", "")
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "session_expired")
    if payload.get("type") != "web-billing":
        raise HTTPException(401, "session_expired")
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "session_expired")
    return user


@router.get("/web/membership")
async def web_membership(request: Request):
    user = await web_user(request)
    spec = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0, "name": 1, "avatar": 1})
    m = await membership.membership_payload(user["user_id"])
    return {"name": (spec or {}).get("name") or user.get("name"), "email": user["email"], "is_specialist": bool(spec),
            "membership": m, "can_manage": bool(user.get("stripe_customer_id")),
            "renews": user.get("stripe_status") in ("active", "trialing")}


class CheckoutIn(BaseModel):
    plan: str = Field(max_length=10)
    lang: str = Field(default="it", max_length=5)


@router.post("/web/checkout")
async def web_checkout(body: CheckoutIn, request: Request):
    user = await web_user(request)
    if body.plan not in membership.PLANS:
        raise HTTPException(400, "Invalid plan")
    if not await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 1}):
        raise HTTPException(400, "not_specialist")
    if user.get("stripe_status") in ("active", "trialing", "past_due"):
        raise HTTPException(400, "already_subscribed")
    await ensure_stripe_webhook()
    data = {"mode": "subscription", "line_items": [{"price": await stripe_price(body.plan), "quantity": 1}],
            "client_reference_id": user["user_id"], "subscription_data": {"metadata": {"user_id": user["user_id"]}},
            "success_url": f"{WEB_URL}/abbonamento?pagato=1", "cancel_url": f"{WEB_URL}/abbonamento",
            "locale": "es" if body.lang == "es" else "it", "allow_promotion_codes": True}
    if user.get("stripe_customer_id"):
        data["customer"] = user["stripe_customer_id"]
    else:
        data["customer_email"] = user["email"]
    session = await stripe_api("POST", "checkout/sessions", data)
    return {"url": session["url"]}


@router.post("/web/portal")
async def web_portal(request: Request):
    user = await web_user(request)
    if not user.get("stripe_customer_id"):
        raise HTTPException(400, "no_customer")
    s = await stripe_api("POST", "billing_portal/sessions", {"customer": user["stripe_customer_id"],
                                                             "return_url": f"{WEB_URL}/abbonamento"})
    return {"url": s["url"]}
