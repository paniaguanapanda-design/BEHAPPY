"""Registro, login (correo y Google), cierre de sesion, recuperar contrasena y borrar cuenta."""
import os
import secrets
import re
import bcrypt
import jwt
from fastapi import HTTPException, Request, APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Optional
from datetime import timezone, timedelta
from . import mail, membership, storage
from .core import JWT_SECRET, db, iso, logger, new_id, now
from .mail import _esc, email_configured
from .security import client_ip, current_user, make_jwt, public_user, rate_limit, referral_fields


router = APIRouter(prefix="/api")


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    name: str = Field(max_length=100)
    ref: Optional[str] = Field(None, max_length=60)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class SessionIn(BaseModel):
    session_id: str


@router.post("/auth/register")
async def register(body: RegisterIn, request: Request):
    rate_limit(f"reg:{client_ip(request)}", 10, 3600)
    email = body.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Invalid email")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if len(body.password) > 128:
        raise HTTPException(400, "Password too long")
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    user = {"user_id": new_id("user"), "email": email, "name": body.name.strip() or email.split("@")[0],
            "picture": None, "role": "client", "specialist_id": None,
            "password_hash": (await run_in_threadpool(bcrypt.hashpw, body.password.encode(), bcrypt.gensalt())).decode(),
            "created_at": iso(now()), **referral_fields(body.ref)}
    await db.users.insert_one(user)
    user.pop("_id", None)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}


@router.post("/auth/login")
async def login(body: LoginIn, request: Request):
    email = body.email.strip().lower()
    rate_limit(f"login-ip:{client_ip(request)}", 30, 600)
    rate_limit(f"login-mail:{email}", 8, 600)
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not await run_in_threadpool(bcrypt.checkpw, body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Invalid email or password")
    await membership.apply_prereg(user)
    await membership.start_web_promo(user, request)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}


class GoogleLoginIn(BaseModel):
    id_token: str = Field(max_length=4096)
    ref: Optional[str] = Field(None, max_length=60)


@router.post("/auth/google")
async def google_login(body: GoogleLoginIn, request: Request):
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
    rate_limit(f"google-ip:{client_ip(request)}", 30, 600)
    allowed = [c.strip() for c in os.environ.get("GOOGLE_CLIENT_IDS", "").split(",") if c.strip()]
    if not allowed:
        raise HTTPException(503, "Login con Google no configurado")
    try:
        info = await run_in_threadpool(google_id_token.verify_oauth2_token, body.id_token, google_requests.Request())
    except Exception:
        raise HTTPException(401, "Token de Google invalido")
    if info.get("aud") not in allowed or not info.get("email_verified"):
        raise HTTPException(401, "Token de Google invalido")
    email = info["email"].lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user and user.get("password_hash"):
        # Evita que alguien que registro antes ese correo con contrasena entre en la cuenta de otra persona
        raise HTTPException(409, "Este correo ya tiene una cuenta con contrasena. Entra con tu contrasena.")
    if user:
        if not user.get("picture") and info.get("picture"):
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": info["picture"]}})
            user["picture"] = info["picture"]
    else:
        user = {"user_id": new_id("user"), "email": email, "name": info.get("name") or email.split("@")[0],
                "picture": info.get("picture"), "role": "client", "specialist_id": None, "created_at": iso(now()),
                **referral_fields(body.ref)}
        await db.users.insert_one(user)
        user.pop("_id", None)
    try:
        if not user.get("specialist_id"):
            await membership.create_profile_from_prereg(user)  # el email de Google esta verificado
    except Exception as e:
        logger.warning("perfil desde pre-registro no creado para %s: %s", user["user_id"], e)
    await membership.apply_prereg(user)
    await membership.start_web_promo(user, request)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}

@router.get("/auth/me")
async def me(request: Request):
    user = await current_user(request)
    await membership.start_web_promo(user, request)
    return public_user(user)


INVITE_BASE = "https://app.be-happyapp.com/?ref="


@router.get("/auth/invite")
async def invite(request: Request):
    """Codigo de invitacion propio de la persona: quien se registre con su enlace queda contado en su nombre
    (panel admin > referidos). Se crea la primera vez y ya no cambia."""
    user = await current_user(request)
    code = user.get("codigo_invitacion")
    if not code:
        code = "u" + secrets.token_hex(4)
        for _ in range(5):  # colision practicamente imposible, pero se comprueba
            if not await db.users.find_one({"codigo_invitacion": code}, {"_id": 1}):
                break
            code = "u" + secrets.token_hex(4)
        # Solo se escribe si aun no tiene codigo (dos peticiones a la vez no cambian el enlace).
        await db.users.update_one({"user_id": user["user_id"], "codigo_invitacion": {"$exists": False}},
                                  {"$set": {"codigo_invitacion": code}})
        saved = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "codigo_invitacion": 1}) or {}
        code = saved.get("codigo_invitacion") or code
    return {"code": code, "url": INVITE_BASE + code}


@router.post("/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
            if payload.get("jti"):
                await db.auth_sessions.delete_one({"jti": payload["jti"]})
        except jwt.PyJWTError:
            pass
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


@router.post("/auth/logout-all")
async def logout_all(request: Request):
    """Cierra la sesion en todos los dispositivos."""
    user = await current_user(request)
    await db.auth_sessions.delete_many({"user_id": user["user_id"]})
    await db.user_sessions.delete_many({"user_id": user["user_id"]})
    return {"ok": True}


# ---------------- Recuperar contrasena (codigo de 6 digitos por email) ----------------
RESET_MINUTES = 15
RESET_MAX_ATTEMPTS = 5

RESET_EMAIL = {
    "es": {"subject": "Tu código para cambiar la contraseña de Be Happy",
           "hello": "Hola {name}:",
           "body": "Tu código para crear una contraseña nueva es:",
           "expires": "Caduca en {m} minutos. Si no lo has pedido tú, ignora este correo: tu contraseña no cambia.",
           "google_subject": "Tu cuenta de Be Happy usa Google",
           "google_body": "Has pedido cambiar la contraseña, pero tu cuenta no tiene contraseña: entras con el botón «Continuar con Google»."},
    "it": {"subject": "Il tuo codice per cambiare la password di Be Happy",
           "hello": "Ciao {name},",
           "body": "Il tuo codice per creare una nuova password è:",
           "expires": "Scade tra {m} minuti. Se non l'hai chiesto tu, ignora questa email: la password non cambia.",
           "google_subject": "Il tuo account Be Happy usa Google",
           "google_body": "Hai chiesto di cambiare la password, ma il tuo account non ne ha una: entri con il pulsante «Continua con Google»."},
}


def _reset_hash(user_id: str, code: str) -> str:
    import hmac
    import hashlib
    return hmac.new(JWT_SECRET.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


class ForgotIn(BaseModel):
    email: str = Field(max_length=254)
    language: str = Field(default="es", max_length=5)


class ResetIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=12)
    new_password: str = Field(max_length=128)


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotIn, request: Request):
    """Siempre responde lo mismo, exista o no la cuenta, para no revelar que emails estan registrados."""
    import secrets
    email = body.email.strip().lower()
    rate_limit(f"forgot-ip:{client_ip(request)}", 10, 3600)
    rate_limit(f"forgot-mail:{email}", 3, 3600)
    if not email_configured():
        raise HTTPException(503, "La recuperación de contraseña no está disponible ahora")
    lang = "it" if body.language == "it" else "es"
    tx = RESET_EMAIL[lang]
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        return {"ok": True}
    name = _esc(user.get("name") or "")
    if not user.get("password_hash"):
        text = f"{tx['hello'].format(name=user.get('name') or '')}\n\n{tx['google_body']}"
        await mail.send_email(email, tx["google_subject"], text,
                         f"<p>{tx['hello'].format(name=name)}</p><p>{tx['google_body']}</p>")
        return {"ok": True}
    code = f"{secrets.randbelow(10**6):06d}"
    await db.password_resets.update_one({"user_id": user["user_id"]}, {"$set": {
        "user_id": user["user_id"], "email": email, "code_hash": _reset_hash(user["user_id"], code), "attempts": 0,
        "created_at": now(), "expires_at": now() + timedelta(minutes=RESET_MINUTES)}}, upsert=True)
    expires = tx["expires"].format(m=RESET_MINUTES)
    text = f"{tx['hello'].format(name=user.get('name') or '')}\n\n{tx['body']} {code}\n\n{expires}"
    html = (f"<div style=\"font-family:Arial,sans-serif;max-width:480px;color:#0a1628\">"
            f"<p>{tx['hello'].format(name=name)}</p><p>{tx['body']}</p>"
            f"<p style=\"font-size:32px;font-weight:bold;letter-spacing:6px;margin:24px 0\">{code}</p>"
            f"<p style=\"color:#64748b;font-size:13px\">{expires}</p></div>")
    if not await mail.send_email(email, tx["subject"], text, html):
        raise HTTPException(503, "No se pudo enviar el email, inténtalo más tarde")
    return {"ok": True}


@router.post("/auth/reset-password")
async def reset_password(body: ResetIn, request: Request):
    email = body.email.strip().lower()
    rate_limit(f"reset-ip:{client_ip(request)}", 20, 3600)
    bad = HTTPException(400, "Código incorrecto o caducado")
    if not (6 <= len(body.new_password) <= 128):
        raise HTTPException(400, "Password must be at least 6 characters")
    rec = await db.password_resets.find_one({"email": email}, {"_id": 0})
    if not rec or rec["expires_at"].replace(tzinfo=rec["expires_at"].tzinfo or timezone.utc) < now():
        raise bad
    if rec.get("attempts", 0) >= RESET_MAX_ATTEMPTS:
        await db.password_resets.delete_one({"user_id": rec["user_id"]})
        raise bad
    import hmac
    if not hmac.compare_digest(rec["code_hash"], _reset_hash(rec["user_id"], body.code.strip())):
        await db.password_resets.update_one({"user_id": rec["user_id"]}, {"$inc": {"attempts": 1}})
        raise bad
    await db.password_resets.delete_one({"user_id": rec["user_id"]})
    pw_hash = (await run_in_threadpool(bcrypt.hashpw, body.new_password.encode(), bcrypt.gensalt())).decode()
    await db.users.update_one({"user_id": rec["user_id"]}, {"$set": {"password_hash": pw_hash,
                                                                      "password_changed_at": iso(now())}})
    # Cambiar la contrasena cierra todas las sesiones abiertas (por si alguien mas tenia acceso)
    await db.auth_sessions.delete_many({"user_id": rec["user_id"]})
    await db.user_sessions.delete_many({"user_id": rec["user_id"]})
    user = await db.users.find_one({"user_id": rec["user_id"]}, {"_id": 0})
    await membership.start_web_promo(user, request)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}


class DeleteAccountIn(BaseModel):
    password: Optional[str] = Field(default=None, max_length=128)


@router.post("/auth/delete-account")
async def delete_account(body: DeleteAccountIn, request: Request):
    user = await current_user(request)
    uid = user["user_id"]
    full = await db.users.find_one({"user_id": uid}, {"_id": 0})
    if full and full.get("password_hash"):
        ok = body.password and await run_in_threadpool(bcrypt.checkpw, body.password.encode(), full["password_hash"].encode())
        if not ok:
            raise HTTPException(403, "Contrasena incorrecta")
    specs = await db.specialists.find({"user_id": uid}, {"_id": 0, "specialist_id": 1}).to_list(10)
    sids = [s["specialist_id"] for s in specs]
    convs = await db.conversations.find({"participants": uid}, {"_id": 0, "conversation_id": 1}).to_list(10000)
    cids = [c["conversation_id"] for c in convs]
    reviewed = await db.reviews.find({"user_id": uid}, {"_id": 0, "specialist_id": 1}).to_list(10000)
    files = await db.files.find({"owner_id": uid}, {"_id": 0, "storage_path": 1}).to_list(10000)
    for f in files:
        try:
            await run_in_threadpool(storage.delete_object, f["storage_path"])
        except Exception as e:
            logger.warning("no se pudo borrar archivo %s: %s", f["storage_path"], e)
    for name in await db.list_collection_names():
        if name == "payment_transactions":
            continue  # los registros de pagos se conservan por obligacion legal
        if name == "users":
            q = {"user_id": uid}
        else:
            q = {"$or": [{"user_id": uid}, {"client_id": uid}, {"specialist_user_id": uid}, {"sender_id": uid},
                         {"owner_id": uid}, {"specialist_id": {"$in": sids}}, {"conversation_id": {"$in": cids}}]}
        await db[name].delete_many(q)
    await db.blocks.delete_many({"blocked_id": uid})
    for sid in {r["specialist_id"] for r in reviewed} - set(sids):
        rest = await db.reviews.find({"specialist_id": sid}, {"_id": 0, "rating": 1}).to_list(10000)
        avg = round(sum(r["rating"] for r in rest) / len(rest), 1) if rest else None
        await db.specialists.update_one({"specialist_id": sid}, {"$set": {"rating_avg": avg, "reviews_count": len(rest)}})
    return {"ok": True}
