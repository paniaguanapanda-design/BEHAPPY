from fastapi import FastAPI, APIRouter, HTTPException, Request, UploadFile, File, Form, Header
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import asyncio
import re
import json
import base64
import logging
import uuid
from PIL import Image, ImageOps
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import httpx
import requests

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from google import genai
from google.genai import types
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ["JWT_SECRET"]
APP_NAME = os.environ.get("APP_NAME", "behappy")

storage_key = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")

CATEGORIES = ["plumbing", "electrical", "hvac", "masonry", "carpentry"]
SUBTRADES = {"masonry": ["muratura", "piastrellista", "pintura", "suelos", "tejados"],
             "carpentry": ["puertas", "ventanas", "parquet", "cerrajeria", "cristales"]}
LANG_NAME = {"es": "Spanish", "it": "Italian"}


GEMINI_MODEL = "gemini-3-flash-preview"
_gemini_client = None


def get_gemini():
    global _gemini_client
    if _gemini_client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Falta GEMINI_API_KEY en backend/.env")
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


# --- Topes diarios de gasto ---
# Gemini y Google Maps se pagan por uso. Ademas de los limites por persona, hay un maximo al dia para TODA la app:
# aunque alguien cree muchas cuentas, no puede gastar mas que esto. Se cambian en Render sin tocar el codigo.
DAILY_CAPS = {
    "gemini": int(os.environ.get("DAILY_MAX_GEMINI", "800")),  # diagnosis + traducciones
    "maps": int(os.environ.get("DAILY_MAX_MAPS", "200")),  # Places + Geocoding (alta de ferreterias)
}


class DailyLimitReached(Exception):
    pass


async def spend_daily(kind: str) -> None:
    """Cuenta una llamada de pago; si se pasa del tope del dia lanza DailyLimitReached (y avisa al admin una vez)."""
    day = now().strftime("%Y-%m-%d")
    doc = await db.usage.find_one_and_update({"_id": f"{kind}:{day}"}, {"$inc": {"count": 1}},
                                             upsert=True, return_document=True)
    count, cap = doc["count"], DAILY_CAPS[kind]
    for level, label in ((cap, "alcanzado"), (int(cap * 0.8), "al 80%")):
        if count == level:
            logger.warning("Tope diario de %s %s (%s/%s)", kind, label, count, cap)
            asyncio.create_task(send_email(
                os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com"), f"Be Happy: tope diario de {kind} {label}",
                f"Hoy se han hecho {count} llamadas a {kind} (tope {cap}). Al llegar al tope se bloquean hasta mañana "
                f"(UTC). Si es uso normal, sube DAILY_MAX_{kind.upper()} en Render.",
                f"<p>Hoy se han hecho {count} llamadas a {kind} (tope {cap}).</p>"))
    if count > cap:
        raise DailyLimitReached(kind)


async def gemini_json(prompt: str, image_b64: Optional[str] = None) -> dict:
    """Pide a Gemini una respuesta en JSON, con o sin foto."""
    rate_limit("gemini-global", 600, 3600)
    await spend_daily("gemini")
    contents = []
    if image_b64:
        contents.append(types.Part.from_bytes(data=base64.b64decode(image_b64), mime_type="image/jpeg"))
    contents.append(prompt)
    response = await get_gemini().aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction="You output valid JSON only, no markdown.",
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )
    return parse_json(response.text or "")


async def caption_both(caption: str) -> dict:
    caption = caption.strip()
    try:
        r = await gemini_json('Translate this short work-photo caption. Return {"es": "<Spanish>", "it": "<Italian>"}. '
                              f'Caption: {json.dumps(caption, ensure_ascii=False)}')
        return {"es": str(r.get("es") or caption), "it": str(r.get("it") or caption)}
    except Exception as e:
        logger.warning("caption translate failed: %s", e)
        return {"es": caption, "it": caption}


def now():
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------- Storage ----------------
# En desarrollo guarda las fotos en backend/uploads_local.
# En produccion, si defines S3_BUCKET (y sus claves), usa S3 o Cloudflare R2.
LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent / "uploads_local"
S3_BUCKET = os.environ.get("S3_BUCKET")
_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
            region_name=os.environ.get("S3_REGION", "auto"),
        )
    return _s3


# En Render el disco se borra en cada despliegue: alli las fotos solo pueden ir a S3 / Cloudflare R2.
ON_RENDER = bool(os.environ.get("RENDER"))


def init_storage():
    if S3_BUCKET:
        _s3_client()
    elif ON_RENDER:
        logger.critical("Falta S3_BUCKET en Render: las subidas de fotos quedan desactivadas")
    else:
        LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if not S3_BUCKET and ON_RENDER:
        raise HTTPException(503, "Almacenamiento de fotos no configurado")
    if S3_BUCKET:
        _s3_client().put_object(Bucket=S3_BUCKET, Key=path, Body=data, ContentType=content_type)
    else:
        target = (LOCAL_UPLOAD_DIR / path).resolve()
        if LOCAL_UPLOAD_DIR.resolve() not in target.parents:
            raise HTTPException(400, "Invalid path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {"path": path}


def get_object(path: str):
    if S3_BUCKET:
        obj = _s3_client().get_object(Bucket=S3_BUCKET, Key=path)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
    target = (LOCAL_UPLOAD_DIR / path).resolve()
    if LOCAL_UPLOAD_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "File not found")
    return target.read_bytes(), "application/octet-stream"
def delete_object(path: str) -> None:
    if S3_BUCKET:
        _s3_client().delete_object(Bucket=S3_BUCKET, Key=path)
    else:
        target = (LOCAL_UPLOAD_DIR / path).resolve()
        if LOCAL_UPLOAD_DIR.resolve() in target.parents and target.is_file():
            target.unlink()
            
            
async def store_bytes(user_id: str, data: bytes, content_type: str, ext: str) -> str:
    path = f"{APP_NAME}/uploads/{user_id}/{uuid.uuid4().hex}.{ext}"
    result = await run_in_threadpool(put_object, path, data, content_type)
    stored = result.get("path", path)
    await db.files.insert_one({"storage_path": stored, "owner_id": user_id, "content_type": content_type,
                               "is_deleted": False, "created_at": iso(now())})
    return stored


# ---------------- Limite de peticiones ----------------
import time as _time
from collections import defaultdict, deque

_hits = defaultdict(deque)


def _valid_ip(v: Optional[str]) -> Optional[str]:
    import ipaddress
    try:
        return str(ipaddress.ip_address((v or "").strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """IP real del visitante, que el visitante no puede inventar.
    - Render tiene Cloudflare delante: Cloudflare pone CF-Connecting-IP y rechaza las peticiones que la traen
      del cliente. X-Forwarded-For NO sirve: el cliente puede escribir lo que quiera al principio.
    - La web (Vercel) llama al servidor en nombre del visitante: manda su IP en X-BeHappy-Client-IP junto con
      la clave secreta WEB_PROXY_KEY; sin la clave esa cabecera se ignora."""
    import hmac
    h = request.headers
    key = os.environ.get("WEB_PROXY_KEY", "")
    if key and hmac.compare_digest(h.get("x-behappy-proxy-key", ""), key):
        ip = _valid_ip(h.get("x-behappy-client-ip"))
        if ip:
            return ip
    ip = _valid_ip(h.get("cf-connecting-ip"))
    if ip:
        return ip
    if os.environ.get("RENDER"):
        return "sin-ip"  # no deberia pasar detras de Cloudflare; no se confia en el resto de cabeceras
    return request.client.host if request.client else "unknown"


def rate_limit(key: str, limit: int, window_s: int) -> None:
    """Permite como maximo `limit` usos de `key` cada `window_s` segundos."""
    t = _time.monotonic()
    if len(_hits) > 20000:
        _hits.clear()
    q = _hits[key]
    while q and q[0] < t - window_s:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Demasiadas peticiones, espera un momento e intentalo de nuevo")
    q.append(t)
    
def own_upload(path: str, user: dict) -> bool:
    return isinstance(path, str) and ".." not in path and path.startswith(f"{APP_NAME}/uploads/{user['user_id']}/")


# ---------------- Auth ----------------
def public_user(u: dict) -> dict:
    return {k: u.get(k) for k in ["user_id", "email", "name", "picture", "role", "specialist_id", "created_at"]}


SESSION_DAYS = 7


async def make_jwt(user_id: str) -> str:
    """Cada inicio de sesion crea una sesion en la base de datos; cerrar sesion la borra y el token deja de valer."""
    jti = uuid.uuid4().hex
    exp = now() + timedelta(days=SESSION_DAYS)
    await db.auth_sessions.insert_one({"jti": jti, "user_id": user_id, "created_at": now(), "expires_at": exp})
    return jwt.encode({"sub": user_id, "jti": jti, "exp": exp, "type": "access"}, JWT_SECRET, algorithm="HS256")


async def user_from_token(token: str) -> Optional[dict]:
    if not token:
        return None
    user_id = None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        jti = payload.get("jti")
        if not jti or not await db.auth_sessions.find_one({"jti": jti, "user_id": payload.get("sub")}, {"_id": 1}):
            return None  # sesion cerrada (o token antiguo sin sesion): hay que volver a entrar
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if sess:
            exp = sess["expires_at"]
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now():
                user_id = sess["user_id"]
    if not user_id:
        return None
    return await db.users.find_one({"user_id": user_id}, {"_id": 0})


async def current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else None
    user = await user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    name: str = Field(max_length=100)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class SessionIn(BaseModel):
    session_id: str


@api.post("/auth/register")
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
            "created_at": iso(now())}
    await db.users.insert_one(user)
    user.pop("_id", None)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}


@api.post("/auth/login")
async def login(body: LoginIn, request: Request):
    email = body.email.strip().lower()
    rate_limit(f"login-ip:{client_ip(request)}", 30, 600)
    rate_limit(f"login-mail:{email}", 8, 600)
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not await run_in_threadpool(bcrypt.checkpw, body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Invalid email or password")
    await apply_prereg(user)
    await start_web_promo(user, request)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}


class GoogleLoginIn(BaseModel):
    id_token: str = Field(max_length=4096)


@api.post("/auth/google")
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
                "picture": info.get("picture"), "role": "client", "specialist_id": None, "created_at": iso(now())}
        await db.users.insert_one(user)
        user.pop("_id", None)
    try:
        if not user.get("specialist_id"):
            await create_profile_from_prereg(user)  # el email de Google esta verificado
    except Exception as e:
        logger.warning("perfil desde pre-registro no creado para %s: %s", user["user_id"], e)
    await apply_prereg(user)
    await start_web_promo(user, request)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}

@api.get("/auth/me")
async def me(request: Request):
    user = await current_user(request)
    await start_web_promo(user, request)
    return public_user(user)


@api.post("/auth/logout")
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


@api.post("/auth/logout-all")
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


def email_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("EMAIL_FROM"))


async def send_email(to: str, subject: str, text: str, html: str) -> bool:
    """Envia un email con Resend (https://resend.com). Devuelve False si falla."""
    if not email_configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.post("https://api.resend.com/emails",
                              headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
                              json={"from": os.environ["EMAIL_FROM"], "to": [to], "subject": subject,
                                    "text": text, "html": html})
        if r.status_code >= 300:
            logger.warning("email no enviado: %s %s", r.status_code, r.text[:200])
        return r.status_code < 300
    except Exception as e:
        logger.warning("email no enviado: %s", e)
        return False


def _reset_hash(user_id: str, code: str) -> str:
    import hmac
    import hashlib
    return hmac.new(JWT_SECRET.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _esc(v: str) -> str:
    import html
    return html.escape(v or "")


class ForgotIn(BaseModel):
    email: str = Field(max_length=254)
    language: str = Field(default="es", max_length=5)


class ResetIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=12)
    new_password: str = Field(max_length=128)


@api.post("/auth/forgot-password")
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
        await send_email(email, tx["google_subject"], text,
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
    if not await send_email(email, tx["subject"], text, html):
        raise HTTPException(503, "No se pudo enviar el email, inténtalo más tarde")
    return {"ok": True}


@api.post("/auth/reset-password")
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
    await start_web_promo(user, request)
    return {"session_token": await make_jwt(user["user_id"]), "user": public_user(user)}


class DeleteAccountIn(BaseModel):
    password: Optional[str] = Field(default=None, max_length=128)


@api.post("/auth/delete-account")
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
            await run_in_threadpool(delete_object, f["storage_path"])
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

# ---------------- Files ----------------
@api.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    user = await current_user(request)
    rate_limit(f"upload:{user['user_id']}", 30, 60)
    max_bytes = 10 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, "File too large")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        width, height = img.size
        img.verify()
    except Exception:
        raise HTTPException(400, "El archivo no es una imagen valida")
    if width * height > 40_000_000:
        raise HTTPException(400, "Imagen demasiado grande")
    allowed = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
    if fmt not in allowed:
        raise HTTPException(400, "Solo se aceptan fotos JPEG, PNG o WEBP")
    ext, content_type = allowed[fmt]
    path = await store_bytes(user["user_id"], data, content_type, ext)
    return {"path": path}


@api.get("/files/{path:path}")
async def get_file(path: str, request: Request):
    # El token solo se acepta en la cabecera Authorization, nunca en la direccion (se filtraria en registros y capturas)
    auth = request.headers.get("Authorization", "")
    user = await user_from_token(auth[7:] if auth.startswith("Bearer ") else None)
    if not user:
        raise HTTPException(401, "Not authenticated")
    rec = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "File not found")
    if rec.get("owner_id") != user["user_id"]:
        in_portfolio = await db.specialists.find_one({"$or": [{"portfolio.image": path}, {"avatar": path}]}, {"_id": 1}) \
            or await db.conversations.find_one({"diagnosis.image_path": path, "participants": user["user_id"]}, {"_id": 1})
        if not in_portfolio:
            raise HTTPException(404, "File not found")
    data, ct = await run_in_threadpool(get_object, path)
    return Response(content=data, media_type=rec.get("content_type", ct), headers={"Cache-Control": "private, max-age=86400"})


# ---------------- AI Diagnosis ----------------
DIAG_PROMPT = """You are an expert home repair technician. Analyze the photo of a household problem.
Respond ONLY with valid JSON (no markdown). All text fields in {lang}, except title_es (Spanish) and title_it (Italian).

BEFORE ANYTHING ELSE, look carefully at the photo:
1. Identify EXACTLY the object or element shown. Be specific: "electric water heater" is not "gas boiler", "sink trap" is not "pipe",
   "wall socket" is not "switch". If you cannot tell which one it is, say so instead of guessing.
2. Describe objectively what you SEE: its state and position (e.g. "water heater detached from the wall and resting on the floor",
   "water dripping under the sink trap", "socket blackened around the holes"). Do not invent damage you cannot see.
3. Base everything only on the photo and the user's note. Never assume local or generic practices
   (never answer things like "in this city it is usually replaced"), and never mention prices or shops.

THEN decide the recommended action, with judgment:
- "reposition": the object is detached, fallen, loose or out of place but looks intact -> it must be put back and fixed securely.
- "repair": it has a repairable fault (gasket, cartridge, cable, hinge, seal, clogged part...).
- "replace": ONLY if it is visibly damaged beyond repair (cracked tank, burnt, broken body, heavy corrosion) or clearly unsafe.
  Explain in "action_reason" what you see that makes repair impossible.
- "inspect": the photo is not enough to decide; say what must be checked.
The action (WHAT must be done) is independent of the difficulty (WHO should do it). A fallen water heater or gas boiler is usually
"reposition" + "expert": a professional must re-hang it and check fixings and connections, but it does NOT need to be replaced just
because it fell. In that case when_to_call_pro must say that a specialist can probably re-hang it, and that replacement is only needed
if they find real damage.

Schema:
{{
 "is_home_problem": true/false,
 "is_appliance": true/false,
 "object": "exact name of the object/element, in {lang}",
 "observed": "objective description of what is visible in the photo, in {lang}",
 "recommended_action": "reposition" | "repair" | "replace" | "inspect",
 "action_reason": "1-2 sentences: why this action, based on what you see",
 "title_es": "specific title in Spanish: object + state + action, e.g. 'Calentador descolgado de la pared – volver a fijar'",
 "title_it": "specific title in Italian: object + state + action, e.g. 'Scaldabagno staccato dalla parete – da ricollocare'",
 "category": one of {cats},
 "description": "2-3 sentences: first what is seen (observed), then the likely cause and the recommended action",
 "difficulty": "easy" | "medium" | "expert",
 "safety_warnings": ["..."],
 "materials": [{{"name": "...", "quantity": "..."}}],
 "tools": ["..."],
 "steps": [{{"title": "...", "detail": "..."}}],
 "estimated_time": "e.g. 1-2 h",
 "when_to_call_pro": "short sentence"
}}
Steps must match the recommended action: for "reposition" explain how to put it back and fix it securely, for "repair" how to repair
the faulty part, for "replace" how to remove the old one and fit the new one.
Difficulty rules:
- easy: a non-expert can safely fix it alone. Give 4-8 clear steps.
- medium: a handy person can try it. Give 4-8 clear steps; when_to_call_pro explains when to stop and call a specialist.
- expert: needs a professional (gas, mains electricity, structural, refrigerant, heavy appliances fixed to the wall such as water
  heaters and boilers, anything risky). steps, materials and tools MUST be empty arrays. Never give repair instructions;
  safety_warnings only says what to avoid and how to stay safe until the specialist arrives (e.g. close the water/gas valve,
  switch off the breaker).
is_appliance is true ONLY for free-standing household appliances (washing machine, fridge, oven, dishwasher, dryer, microwave,
cooker hood...). Water heaters, boilers, radiators, air conditioners, taps, sockets and other fixed installations are NOT
appliances: use their trade category (water heater or boiler -> plumbing or hvac).
For an appliance leave steps, materials and tools empty, but still decide recommended_action with the same criteria: an appliance
is NOT replaced by default. Most faults (door seal, filter, drain pump, hose, plug, cable, thermostat) are "repair" by a technician;
"replace" only with visible damage beyond repair or when the user's note says it is very old or the repair is not worth it.
If the image is not a home problem set is_home_problem false and still fill title/description explaining that.
{extra}"""

ACTIONS = ("reposition", "repair", "replace", "inspect")

TRANSLATABLE = ["object", "observed", "action_reason", "description", "safety_warnings", "materials", "tools", "steps", "estimated_time", "when_to_call_pro"]


APPLIANCE_WORDS = ["lavadora", "horno", "nevera", "frigor", "lavavajillas", "secadora", "microondas", "electrodom",
                   "lavatrice", "forno", "lavastoviglie", "asciugatrice", "microonde", "elettrodom",
                   "washing machine", "oven", "fridge", "refrigerator", "dishwasher", "dryer", "microwave", "appliance"]


# Instalaciones fijas que la IA a veces llama "electrodomestico": van con el fontanero, no se "cambian" por defecto
INSTALLATION_RE = re.compile(r"\b(scaldabagn\w*|scaldacqua|calentador\w*|termo|boiler|caldai\w*|calder\w*|water heater|"
                             r"termosifon\w*|radiador\w*|radiator\w*)\b", re.I)


def normalize_diagnosis(r: dict) -> dict:
    text = " ".join(str(r.get(k) or "") for k in ("title_es", "title_it", "title", "object", "category")).lower()
    if INSTALLATION_RE.search(text):
        r["is_appliance"] = False
        if r.get("category") not in CATEGORIES:
            r["category"] = "plumbing"
    elif r.get("is_appliance") or any(w in text for w in APPLIANCE_WORDS):
        r["is_appliance"] = True
        r["category"] = "appliance"
        r["steps"], r["materials"], r["tools"] = [], [], []
    elif r.get("category") not in CATEGORIES:
        r["category"] = "unknown"  # never force an unknown trade into masonry
    diff = r.get("difficulty")
    r["difficulty"] = "expert" if diff in ("hard", "expert") else diff if diff in ("easy", "medium") else "medium"
    # Seguridad: gas, calderas y calentadores (pesados, con agua/gas/luz) siempre son experto; lo electrico solo puede ser "facil" si la IA lo marca asi
    gas_risk = re.search(r"\b(gas|caldaia|caldera|boiler|stufa|estufa|metano|scaldabagno|scaldacqua|calentador|termo)\b",
                         text + " " + str(r.get("object") or "").lower()) is not None
    if gas_risk or (r.get("category") == "electrical" and r["difficulty"] != "easy"):
        r["difficulty"] = "expert"
    if r["difficulty"] == "expert":
        r["steps"], r["materials"], r["tools"] = [], [], []
    for k in ("steps", "materials", "tools", "safety_warnings"):
        r[k] = r.get(k) or []
    if r.get("recommended_action") not in ACTIONS:
        r["recommended_action"] = "inspect"
    for k in ("object", "observed", "action_reason"):
        r[k] = str(r.get(k) or "")
    r["title_es"] = r.get("title_es") or r.get("title") or ""
    r["title_it"] = r.get("title_it") or r.get("title") or ""
    return r


class DiagnoseIn(BaseModel):
    image_base64: str = Field(max_length=14_000_000)
    language: str = "es"
    note: Optional[str] = Field(default=None, max_length=500)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)  # solo si el usuario ya dio permiso de ubicacion
    lng: Optional[float] = Field(default=None, ge=-180, le=180)

MAX_SIDE = 1024


def shrink_image(data: bytes) -> bytes:
    """Resize to max 1024px and recompress as JPEG so Gemini gets a light payload."""
    im = Image.open(io.BytesIO(data))
    if im.format == "JPEG" and max(im.size) <= MAX_SIDE:
        return data  # already compressed on the phone: don't re-encode
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=72, optimize=True)
    return out.getvalue()


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no json")
    return json.loads(m.group(0))


@api.post("/diagnose")
async def diagnose(body: DiagnoseIn, request: Request):
    user = await current_user(request)
    rate_limit(f"diag-min:{user['user_id']}", 8, 60)
    rate_limit(f"diag-day:{user['user_id']}", 40, 86400)
    b64 = body.image_base64.split(",", 1)[-1]
    try:
        raw = await run_in_threadpool(shrink_image, base64.b64decode(b64))
    except Exception:
        raise HTTPException(400, "Invalid image")
    b64 = base64.b64encode(raw).decode()
    lang = LANG_NAME.get(body.language, "Spanish")
    extra = f"User note: {body.note}" if body.note else ""
    try:
        result = normalize_diagnosis(await gemini_json(DIAG_PROMPT.format(lang=lang, cats=CATEGORIES, extra=extra), b64))
    except DailyLimitReached:
        raise HTTPException(503, "Oggi il servizio è molto richiesto: riprova domani. / Hoy hay mucha demanda: inténtalo mañana.")
    except Exception as e:
        logger.exception("diagnose failed: %s", e)
        raise HTTPException(503, "AI analysis failed, please retry")
    image_path = f"{APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4().hex}.jpg"

    async def _store():
        try:
            await run_in_threadpool(put_object, image_path, raw, "image/jpeg")
            await db.files.insert_one({"storage_path": image_path, "owner_id": user["user_id"], "content_type": "image/jpeg",
                                       "is_deleted": False, "created_at": iso(now())})
        except Exception as e:
            logger.warning("image store failed: %s", e)

    asyncio.create_task(_store())  # don't make the user wait for storage
    doc = {**result, "diagnosis_id": new_id("diag"), "user_id": user["user_id"], "image_path": image_path,
            "language": body.language, "created_at": iso(now())}
    doc.pop("_id", None)
    await db.diagnoses.insert_one(doc)
    doc.pop("_id", None)
    if body.lat is not None and body.lng is not None:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_loc": {
            "lat": round(body.lat, 3), "lng": round(body.lng, 3), "at": iso(now())}}})
        asyncio.create_task(notify_nearby_diagnosis(doc, body.lat, body.lng))
        if not prov_code(user.get("zone")):
            asyncio.create_task(set_user_province(user, body.lat, body.lng, "gps"))
    return doc


@api.get("/diagnoses")
async def list_diagnoses(request: Request):
    user = await current_user(request)
    return await db.diagnoses.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)


@api.get("/diagnoses/{diagnosis_id}")
async def get_diagnosis(diagnosis_id: str, request: Request, lang: Optional[str] = None):
    user = await current_user(request)
    d = await db.diagnoses.find_one({"diagnosis_id": diagnosis_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Not found")
    if d["user_id"] != user["user_id"]:
        raise HTTPException(403, "Forbidden")
    lang = lang if lang in LANG_NAME else d.get("language", "es")
    if lang != d.get("language"):
        cached = (d.get("i18n") or {}).get(lang)
        if not cached:
            src = {k: d.get(k) for k in TRANSLATABLE}
            try:
                cached = await gemini_json(f"Translate every string value of this JSON into {LANG_NAME[lang]}. Keep the same keys and "
                                           f"structure, return JSON only.\n{json.dumps(src, ensure_ascii=False)}")
                cached = {k: cached.get(k, src[k]) for k in TRANSLATABLE}
                await db.diagnoses.update_one({"diagnosis_id": diagnosis_id}, {"$set": {f"i18n.{lang}": cached}})
            except Exception as e:
                logger.warning("translate diagnosis failed: %s", e)
                cached = {}
        d.update(cached)
    d.pop("i18n", None)
    d["title"] = d.get(f"title_{lang}") or d.get("title")
    d["view_language"] = lang
    return d


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
    s.update(public_pro_fields(s, origin))
    for k in PRIVATE_SPEC_FIELDS:
        s.pop(k, None)
    z = s.get("zone")
    s["zone"] = {"label": z.get("label"), "radius_km": z.get("radius_km"), "province": z.get("province")} if z else None
    s["membership_active"] = membership_active(s)
    if (s.get("reviews_count") or 0) < 3:
        s["rating_avg"] = None  # average only shown from 3 ratings
    return s


MEMBERSHIP_REQUIRED = "Necesitas la membresía activa para esto"


async def require_active_specialist(spec: dict):
    if not membership_active(spec):
        raise HTTPException(403, MEMBERSHIP_REQUIRED)


@api.get("/categories")
async def categories():
    return CATEGORIES


@api.post("/specialists")
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
        if client_kind(request) == "web" and PROMO_WEB and not user.get("promo_mes_gratis"):
            # Registrado desde la web: el mes gratis empieza la primera vez que entra en la app
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"promo_mes_gratis": "pendiente"}})
    user["specialist_id"] = sid
    if city and not prov_code((existing or {}).get("zone")):
        # Registro desde la web con su comune: su zona (y su provincia) quedan puestas y ya sale en la app
        zone = await zone_from_city(city)
        if zone:
            await db.specialists.update_one({"specialist_id": sid}, {"$set": {"zone": zone}})
    await apply_prereg(user)
    await start_web_promo(user, request)
    return await specialist_out(await db.specialists.find_one({"specialist_id": sid}, {"_id": 0}))


@api.get("/specialists")
async def list_specialists(request: Request, category: Optional[str] = None, q: Optional[str] = None,
                           lat: Optional[float] = None, lng: Optional[float] = None, available: bool = False):
    user = await current_user(request)
    origin = (lat, lng) if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180 else None
    if origin:
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"last_loc": {"lat": round(lat, 3), "lng": round(lng, 3), "at": iso(now())}}})
        if not prov_code(user.get("zone")):
            await set_user_province(user, lat, lng, "gps")  # primera vez: su provincia sale de su ubicacion
    # Toda Italia, por provincias: solo salen especialistas de la provincia del cliente. Sin provincia, nadie
    # (la app le pide la ubicacion o su comune).
    my_prov = prov_code(user.get("zone"))
    if not my_prov:
        return []
    if not origin:
        z = user["zone"]
        origin = (z["lat"], z["lng"]) if z.get("lat") is not None else None
    # Salen los especialistas con foto de perfil que trabajan en la zona del cliente: destacados, disponibles ahora y
    # con membresia primero. Los ocultos por reportes no salen.
    # Solo especialistas con la suscripcion activa (se paga en la web): sin ella no ofrecen el servicio.
    flt = {"avatar": {"$type": "string"}, "hidden": {"$ne": True}, "membership_expires_at": {"$gt": iso(now())},
           "zone.province.code": my_prov}
    if category and category != "all":
        flt["categories"] = category
    if q:
        flt["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    items = await db.specialists.find(flt, {"_id": 0, "verification_document": 0, "document_number": 0}) \
        .sort([("verified", -1), ("created_at", 1)]).to_list(500)
    hidden = await hidden_user_ids(user["user_id"])
    out = [await specialist_out(it, origin) for it in items if it["user_id"] not in hidden]
    if available:
        out = [it for it in out if it["available_now"]]
    # Como mucho 3 destacados por oficio (los que lo compraron antes)
    featured = sorted([it for it in out if it["featured"]], key=lambda it: it.get("featured_until") or "")
    seen: dict = {}
    for it in featured:
        cat = (it.get("categories") or [""])[0]
        seen[cat] = seen.get(cat, 0) + 1
        if seen[cat] > FEATURED_MAX_PER_TRADE:
            it["featured"] = False
    out.sort(key=lambda it: (not it["featured"], not it["available_now"], not it["membership_active"],
                             it.get("distance_km") if it.get("distance_km") is not None else 999))
    for it in out:
        it.pop("featured_until", None)
    return out


@api.get("/specialists/me")
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


@api.get("/specialists/{sid}")
async def get_specialist(sid: str, request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    await record_view(s, user)
    out = await specialist_out(dict(s))
    out["can_review"] = await can_review(user, s)
    # De otra provincia: se ve la ficha, pero sin telefono ni WhatsApp (tampoco se le puede escribir)
    mine = prov_code(user.get("zone"))
    out["same_province"] = bool(mine) and mine == prov_code(s.get("zone"))
    if not out["same_province"] and s["user_id"] != user["user_id"] and not await db.conversations.find_one(
            {"client_id": user["user_id"], "specialist_id": sid}, {"_id": 1}):
        out.pop("phone", None)
        out.pop("whatsapp", None)
        out["contact_blocked"] = True
    return out


@api.post("/specialists/me/portfolio")
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
    caps = await caption_both(body.caption)
    item = {"item_id": new_id("pf"), "image": body.image, "caption": body.caption.strip(),
            "caption_es": caps["es"], "caption_it": caps["it"], "created_at": iso(now())}
    await db.specialists.update_one({"user_id": user["user_id"]}, {"$push": {"portfolio": {"$each": [item], "$position": 0}}})
    return item


@api.delete("/specialists/me/portfolio/{item_id}")
async def del_portfolio(item_id: str, request: Request):
    user = await current_user(request)
    await db.specialists.update_one({"user_id": user["user_id"]}, {"$pull": {"portfolio": {"item_id": item_id}}})
    return {"ok": True}


@api.post("/specialists/me/verify")
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


@api.get("/specialists/{sid}/reviews")
async def list_reviews(sid: str, request: Request):
    user = await current_user(request)
    hidden = await hidden_user_ids(user["user_id"])
    items = await db.reviews.find({"specialist_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [r for r in items if r.get("user_id") not in hidden]


@api.post("/specialists/{sid}/reviews")
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
        both = await caption_both(review["comment"])
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


# ---------------- Moderation: reports and blocks ----------------
REPORT_TARGETS = {"message", "review", "portfolio", "specialist", "user", "store"}
REPORT_REASONS = {"spam", "inappropriate", "harassment", "fraud", "other", "not_exists", "not_store", "wrong_info",
                  "no_show", "broke_agreement", "overcharged", "bad_work"}


class ReportIn(BaseModel):
    target_type: str = Field(max_length=20)
    target_id: str = Field(max_length=100)
    reason: str = Field(max_length=30)
    details: str = Field(default="", max_length=1000)


class BlockIn(BaseModel):
    user_id: str = Field(max_length=100)


async def blocked_between(a: str, b: str) -> bool:
    return bool(await db.blocks.find_one({"$or": [{"user_id": a, "blocked_id": b}, {"user_id": b, "blocked_id": a}]}))


async def hidden_user_ids(uid: str) -> set:
    ids = set()
    async for b in db.blocks.find({"$or": [{"user_id": uid}, {"blocked_id": uid}]}, {"_id": 0}):
        ids.add(b["blocked_id"] if b["user_id"] == uid else b["user_id"])
    return ids


@api.post("/reports")
async def create_report(body: ReportIn, request: Request):
    user = await current_user(request)
    rate_limit(f"report:{user['user_id']}", 20, 3600)
    if body.target_type not in REPORT_TARGETS or body.reason not in REPORT_REASONS:
        raise HTTPException(400, "Invalid report")
    await db.reports.insert_one({"report_id": new_id("rep"), "user_id": user["user_id"], "target_type": body.target_type,
                                 "target_id": body.target_id, "reason": body.reason, "details": body.details.strip(),
                                 "status": "open", "created_at": iso(now())})
    logger.warning("REPORT %s %s reason=%s by=%s", body.target_type, body.target_id, body.reason, user["user_id"])
    if body.target_type == "store":
        await store_reported(body.target_id, user["user_id"])
    if body.target_type == "specialist":
        await specialist_reported(body.target_id, user["user_id"], body.reason, body.details.strip())
    return {"ok": True}


# ---------------- Admin (moderacion manual) ----------------
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


def require_admin(token: Optional[str]):
    import hmac
    if not ADMIN_TOKEN or not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(403, "Forbidden")


@api.get("/admin/verifications")
async def admin_verifications(x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    items = await db.specialists.find({"verification_status": "in_review"},
                                      {"_id": 0, "specialist_id": 1, "name": 1, "user_id": 1,
                                       "verification_document": 1, "submitted_at": 1}).to_list(100)
    for it in items:
        doc = it.get("verification_document") or ""
        it["verification_document"] = (doc[:80] + "...") if len(doc) > 80 else doc
    return items


@api.get("/admin/verifications/{sid}/document")
async def admin_verification_document(sid: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0, "verification_document": 1})
    if not s or not s.get("verification_document"):
        raise HTTPException(404, "No document")
    doc = s["verification_document"]
    if doc.startswith("data:"):
        head, _, b64 = doc.partition(",")
        ct = head[5:].split(";")[0] or "image/jpeg"
        return Response(content=base64.b64decode(b64), media_type=ct)
    data, ct = await run_in_threadpool(get_object, doc)
    return Response(content=data, media_type=ct)


@api.post("/admin/verifications/{sid}/{decision}")
async def admin_decide_verification(sid: str, decision: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve or reject")
    if decision == "approve":
        upd = {"verified": True, "verification_status": "verified", "verified_by": "admin", "verified_at": iso(now())}
    else:
        upd = {"verified": False, "verification_status": "rejected"}
    r = await db.specialists.update_one({"specialist_id": sid}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Specialist not found")
    return {"ok": True, "status": upd["verification_status"]}


@api.get("/admin/reports")
async def admin_reports(x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    return await db.reports.find({"status": "open"}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api.post("/admin/reports/{rid}/resolve")
async def admin_resolve_report(rid: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    r = await db.reports.update_one({"report_id": rid}, {"$set": {"status": "resolved", "resolved_at": iso(now())}})
    if not r.matched_count:
        raise HTTPException(404, "Report not found")
    return {"ok": True}


@api.post("/blocks")
async def block_user(body: BlockIn, request: Request):
    user = await current_user(request)
    if body.user_id == user["user_id"]:
        raise HTTPException(400, "Invalid user")
    if not await db.users.find_one({"user_id": body.user_id}, {"_id": 1}):
        raise HTTPException(404, "User not found")
    await db.blocks.update_one({"user_id": user["user_id"], "blocked_id": body.user_id},
                               {"$set": {"created_at": iso(now())}}, upsert=True)
    return {"ok": True}


@api.delete("/blocks/{uid}")
async def unblock_user(uid: str, request: Request):
    user = await current_user(request)
    await db.blocks.delete_one({"user_id": user["user_id"], "blocked_id": uid})
    return {"ok": True}


@api.get("/blocks")
async def list_blocks(request: Request):
    user = await current_user(request)
    return await db.blocks.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(500)


# ---------------- Chat ----------------
class MessageIn(BaseModel):
    text: str = Field(max_length=2000)


class ConversationIn(BaseModel):
    specialist_id: str
    diagnosis_id: Optional[str] = Field(default=None, max_length=60)


async def get_or_create_conversation(client_user: dict, spec: dict) -> dict:
    from pymongo.errors import DuplicateKeyError
    if client_user["user_id"] == spec["user_id"]:
        raise HTTPException(400, "Cannot chat with yourself")
    key = {"client_id": client_user["user_id"], "specialist_id": spec["specialist_id"]}
    conv = await db.conversations.find_one(key, {"_id": 0})
    if conv:
        return conv
    conv = {"conversation_id": new_id("conv"), "client_id": client_user["user_id"], "client_name": client_user["name"],
            "client_picture": client_user.get("picture"), "specialist_id": spec["specialist_id"],
            "specialist_user_id": spec["user_id"], "specialist_name": spec["name"], "specialist_avatar": spec.get("avatar"),
            "participants": [client_user["user_id"], spec["user_id"]], "last_message": "", "updated_at": iso(now()),
            "unread": {client_user["user_id"]: 0, spec["user_id"]: 0}}
    try:
        await db.conversations.insert_one(conv)
    except DuplicateKeyError:
        return await db.conversations.find_one(key, {"_id": 0})
    conv.pop("_id", None)
    return conv


async def push_message(conv: dict, sender: dict, text: str, kind: str = "text", quote_id: Optional[str] = None) -> dict:
    msg = {"message_id": new_id("msg"), "conversation_id": conv["conversation_id"], "sender_id": sender["user_id"],
           "sender_name": sender["name"], "text": text, "kind": kind, "quote_id": quote_id, "created_at": iso(now())}
    await db.messages.insert_one(msg)
    msg.pop("_id", None)
    other = [p for p in conv["participants"] if p != sender["user_id"]][0]
    await db.conversations.update_one({"conversation_id": conv["conversation_id"]},
                                      {"$set": {"last_message": text[:120], "updated_at": msg["created_at"]},
                                       "$inc": {f"unread.{other}": 1}})
    asyncio.create_task(after_message(conv, sender, msg))
    return msg


@api.post("/conversations")
async def start_conversation(body: ConversationIn, request: Request):
    user = await current_user(request)
    spec = await db.specialists.find_one({"specialist_id": body.specialist_id}, {"_id": 0})
    if not spec:
        raise HTTPException(404, "Specialist not found")
    if await blocked_between(user["user_id"], spec["user_id"]):
        raise HTTPException(403, "No puedes contactar a este usuario")
    # Cualquier cliente de la misma provincia puede escribir; el especialista necesita membresía para responder.
    # Las conversaciones que ya existen se respetan.
    exists = await db.conversations.find_one({"client_id": user["user_id"], "specialist_id": spec["specialist_id"]}, {"_id": 1})
    if not exists and user["user_id"] != spec["user_id"]:
        mine, theirs = prov_code(user.get("zone")), prov_code(spec.get("zone"))
        if not mine:
            raise HTTPException(409, "Elige primero tu provincia")
        if mine != theirs:
            raise HTTPException(403, "Este especialista trabaja en otra provincia")
    conv = await get_or_create_conversation(user, spec)
    if body.diagnosis_id:
        d = await db.diagnoses.find_one({"diagnosis_id": body.diagnosis_id, "user_id": user["user_id"]}, {"_id": 0})
        if d:
            conv["diagnosis"] = diagnosis_summary(d)
            await db.conversations.update_one({"conversation_id": conv["conversation_id"]}, {"$set": {"diagnosis": conv["diagnosis"]}})
    return conv


@api.get("/conversations")
async def list_conversations(request: Request):
    user = await current_user(request)
    hidden = await hidden_user_ids(user["user_id"])
    convs = await db.conversations.find({"participants": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(100)
    return [c for c in convs if not any(p in hidden for p in c["participants"] if p != user["user_id"])]


async def get_conv_for(cid: str, user: dict) -> dict:
    conv = await db.conversations.find_one({"conversation_id": cid}, {"_id": 0})
    if not conv or user["user_id"] not in conv["participants"]:
        raise HTTPException(404, "Conversation not found")
    return conv


@api.get("/conversations/{cid}")
async def get_conversation(cid: str, request: Request):
    user = await current_user(request)
    conv = await get_conv_for(cid, user)
    spec = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0, "membership_expires_at": 1,
                                                                                     "avatar": 1}) or {}
    conv["specialist_can_reply"] = membership_active(spec)
    conv["specialist_avatar"] = spec.get("avatar") or conv.get("specialist_avatar")
    conv["review_prompt"] = await review_prompt_for(conv, user)
    d = conv.get("diagnosis")
    if d and d.get("materials") and d.get("category") in CATEGORIES:
        # Ferreterias cerca: del cliente (su ultima posicion) o de la zona del especialista
        if user["user_id"] == conv["client_id"] and user.get("last_loc"):
            center = (user["last_loc"]["lat"], user["last_loc"]["lng"])
        else:
            full = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0, "zone": 1}) or {}
            center = spec_zone(full)[0]
        try:
            conv["stores_nearby"] = len([x async for x in db.stores.aggregate([
                {"$geoNear": {"near": {"type": "Point", "coordinates": [center[1], center[0]]}, "distanceField": "d",
                              "maxDistance": 10000, "spherical": True,
                              "query": {"status": "approved", "hidden": {"$ne": True}, "categories": d["category"]}}},
                {"$limit": 50}, {"$project": {"_id": 1}}])])
        except Exception:
            conv["stores_nearby"] = None
        conv["stores_center"] = {"lat": center[0], "lng": center[1]}
    return conv


@api.get("/conversations/{cid}/messages")
async def list_messages(cid: str, request: Request):
    user = await current_user(request)
    await get_conv_for(cid, user)
    await db.conversations.update_one({"conversation_id": cid}, {"$set": {f"unread.{user['user_id']}": 0}})
    msgs = list(reversed(await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", -1).to_list(500)))
    qids = [m["quote_id"] for m in msgs if m.get("quote_id")]
    if qids:
        quotes = {q["quote_id"]: q for q in await db.quotes.find({"quote_id": {"$in": qids}}, {"_id": 0}).to_list(500)}
        for m in msgs:
            if m.get("quote_id"):
                m["quote"] = quotes.get(m["quote_id"])
    return msgs


@api.post("/conversations/{cid}/messages")
async def send_message(cid: str, body: MessageIn, request: Request):
    user = await current_user(request)
    rate_limit(f"msg:{user['user_id']}", 30, 60)
    conv = await get_conv_for(cid, user)
    other_id = [p for p in conv["participants"] if p != user["user_id"]][0]
    if await blocked_between(user["user_id"], other_id):
        raise HTTPException(403, "No puedes enviar mensajes a este usuario")
    if not body.text.strip():
        raise HTTPException(400, "Empty message")
    if user["user_id"] == conv.get("specialist_user_id"):
        await require_active_specialist(await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0}) or {})
    return await push_message(conv, user, body.text.strip())


# ---------------- Service requests ----------------
class RequestIn(BaseModel):
    specialist_id: str
    description: str = Field(max_length=2000)
    address: str = Field(default="", max_length=300)
    preferred_date: str = Field(default="", max_length=50)
    diagnosis_id: Optional[str] = None


class RequestStatusIn(BaseModel):
    status: str


@api.post("/requests")
async def create_request(body: RequestIn, request: Request):
    user = await current_user(request)
    rate_limit(f"req:{user['user_id']}", 10, 3600)
    spec = await db.specialists.find_one({"specialist_id": body.specialist_id}, {"_id": 0})
    if not spec:
        raise HTTPException(404, "Specialist not found")
    if not body.description.strip():
        raise HTTPException(400, "Description required")
    if await blocked_between(user["user_id"], spec["user_id"]):
        raise HTTPException(403, "No puedes contactar a este usuario")
    diag_title = None
    if body.diagnosis_id:
        d = await db.diagnoses.find_one({"diagnosis_id": body.diagnosis_id, "user_id": user["user_id"]}, {"_id": 0, "title_es": 1})
        diag_title = d.get("title_es") if d else None
    conv = await get_or_create_conversation(user, spec)
    req = {"request_id": new_id("req"), "client_id": user["user_id"], "client_name": user["name"],
           "specialist_id": spec["specialist_id"], "specialist_user_id": spec["user_id"], "specialist_name": spec["name"],
           "description": body.description.strip(), "address": body.address, "preferred_date": body.preferred_date,
           "diagnosis_id": body.diagnosis_id, "diagnosis_title": diag_title, "status": "pending",
           "conversation_id": conv["conversation_id"], "created_at": iso(now())}
    await db.service_requests.insert_one(req)
    req.pop("_id", None)
    await push_message(conv, user, f"[REQUEST] {diag_title + ' — ' if diag_title else ''}{req['description']}", kind="request")
    return req


@api.get("/requests")
async def list_requests(request: Request):
    user = await current_user(request)
    reqs = await db.service_requests.find({"$or": [{"client_id": user["user_id"]}, {"specialist_user_id": user["user_id"]}]},
                                          {"_id": 0}).sort("created_at", -1).to_list(200)
    quotes = await db.quotes.find({"request_id": {"$in": [r["request_id"] for r in reqs]}}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for r in reqs:
        r["quotes"] = [q for q in quotes if q["request_id"] == r["request_id"]]
    return reqs


@api.patch("/requests/{rid}")
async def update_request(rid: str, body: RequestStatusIn, request: Request):
    user = await current_user(request)
    req = await db.service_requests.find_one({"request_id": rid}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Not found")
    allowed = {"accepted", "rejected", "completed"} if req["specialist_user_id"] == user["user_id"] else \
        {"cancelled"} if req["client_id"] == user["user_id"] else set()
    if body.status not in allowed:
        raise HTTPException(403, "Not allowed")
    # Solo estos cambios; completada, rechazada y cancelada son finales
    transitions = {"pending": {"accepted", "rejected", "cancelled"}, "accepted": {"completed", "cancelled"}}
    if body.status not in transitions.get(req["status"], set()):
        raise HTTPException(409, f"No se puede cambiar de {req['status']} a {body.status}")
    if body.status == "accepted":
        await require_active_specialist(await db.specialists.find_one({"specialist_id": req["specialist_id"]}, {"_id": 0}))
    res = await db.service_requests.update_one({"request_id": rid, "status": req["status"]},
                                               {"$set": {"status": body.status, "updated_at": iso(now())}})
    if res.modified_count == 0:
        raise HTTPException(409, "La peticion ya cambio de estado")
    if body.status == "completed":
        await db.specialists.update_one({"specialist_id": req["specialist_id"]}, {"$inc": {"jobs_completed": 1}})
    return {**req, "status": body.status}


# ---------------- Quotes (ofertas) ----------------
class QuoteIn(BaseModel):
    price: float = Field(gt=0, lt=1_000_000)
    description: str = Field(max_length=1000)
    estimated_time: str = Field(default="", max_length=50)


class QuoteStatusIn(BaseModel):
    status: str


@api.post("/requests/{rid}/quotes")
async def create_quote(rid: str, body: QuoteIn, request: Request):
    user = await current_user(request)
    req = await db.service_requests.find_one({"request_id": rid}, {"_id": 0})
    if not req or req["specialist_user_id"] != user["user_id"]:
        raise HTTPException(404, "Request not found")
    if req["status"] not in ("pending", "accepted"):
        raise HTTPException(400, "Request is closed")
    spec = await db.specialists.find_one({"specialist_id": req["specialist_id"]}, {"_id": 0})
    await require_active_specialist(spec)
    if not body.description.strip():
        raise HTTPException(400, "Description required")
    quote = {"quote_id": new_id("quote"), "request_id": rid, "conversation_id": req["conversation_id"],
             "specialist_id": req["specialist_id"], "specialist_name": req["specialist_name"], "client_id": req["client_id"],
             "price": round(body.price, 2), "currency": "EUR", "description": body.description.strip(),
             "estimated_time": body.estimated_time, "status": "pending", "created_at": iso(now())}
    await db.quotes.insert_one(quote)
    quote.pop("_id", None)
    conv = await db.conversations.find_one({"conversation_id": req["conversation_id"]}, {"_id": 0})
    await push_message(conv, user, f"[QUOTE] {quote['price']:.2f} EUR — {quote['description']}", kind="quote", quote_id=quote["quote_id"])
    return quote


@api.patch("/quotes/{qid}")
async def update_quote(qid: str, body: QuoteStatusIn, request: Request):
    user = await current_user(request)
    q = await db.quotes.find_one({"quote_id": qid}, {"_id": 0})
    if not q or q["client_id"] != user["user_id"]:
        raise HTTPException(404, "Quote not found")
    if body.status not in ("accepted", "rejected"):
        raise HTTPException(400, "Invalid status")
    if q["status"] != "pending":
        raise HTTPException(400, "Quote already answered")
    await db.quotes.update_one({"quote_id": qid}, {"$set": {"status": body.status, "answered_at": iso(now())}})
    if body.status == "accepted":
        await db.quotes.update_many({"request_id": q["request_id"], "quote_id": {"$ne": qid}, "status": "pending"},
                                    {"$set": {"status": "rejected"}})
        await db.service_requests.update_one({"request_id": q["request_id"]},
                                             {"$set": {"status": "accepted", "accepted_quote_id": qid, "agreed_price": q["price"]}})
    conv = await db.conversations.find_one({"conversation_id": q["conversation_id"]}, {"_id": 0})
    await push_message(conv, user, f"[QUOTE_{body.status.upper()}] {q['price']:.2f} EUR")
    return {**q, "status": body.status}


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


@api.get("/membership/me")
async def membership_me(request: Request):
    user = await current_user(request)
    return await membership_payload(user["user_id"])


@api.post("/membership/revenuecat-sync")
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
    return await send_email(store["email"], tx[f"{kind}_subject"], body, html)


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
        await spend_daily("maps")
    except DailyLimitReached:
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
                    await spend_daily("maps")
                except DailyLimitReached:
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


@api.post("/stores/apply")
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
            photo = shrink_image(photo)
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
        await run_in_threadpool(put_object, path, photo, "image/jpeg")
        store["photo"] = path
    await db.stores.insert_one(dict(store))
    await _send_store_code(store)
    return {"ok": True, "store_id": store_id}


@api.post("/stores/{store_id}/resend")
async def store_resend(store_id: str, request: Request):
    require_web(request)
    rate_limit(f"store-resend:{store_id}", 3, 3600)
    store = await db.stores.find_one({"store_id": store_id, "status": "email_pending"}, {"_id": 0})
    if not store:
        raise HTTPException(404, "not_found")
    await _send_store_code(store)
    return {"ok": True}


@api.post("/stores/{store_id}/confirm")
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


@api.get("/stores/nearby")
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


@api.get("/stores/{store_id}/photo")
async def store_photo(store_id: str):
    s = await db.stores.find_one({"store_id": store_id, "status": "approved"}, {"_id": 0, "photo": 1})
    if not s or not s.get("photo"):
        raise HTTPException(404, "No photo")
    data, ct = await run_in_threadpool(get_object, s["photo"])
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
        ok = await send_email(to, subject, intro + "\n\n" + "\n".join(rows_txt),
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


@api.get("/admin/stores/{store_id}/decide")
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


@api.post("/admin/stores/{store_id}/decide")
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


@api.post("/admin/stores/digest")
async def admin_store_digest(x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    await store_maintenance(force=True)
    return {"ok": True}


# ---------------- Herramientas para especialistas ----------------
# Zona y horario, estadisticas, avisos push, respuestas rapidas, perfil destacado y reportes de clientes.
# BeHappy solo acerca el especialista al cliente: precios y acuerdos los pactan ellos, nosotros no intervenimos.
import math
from zoneinfo import ZoneInfo

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
    active = membership_active(s)
    center, radius = spec_zone(s)
    out = {"available_now": active and in_schedule(s), "featured": active and featured_active(s),
           "urgent": bool(s.get("urgent")), "zone_radius_km": radius,
           "schedule_label_it": schedule_label(s, "it"), "schedule_label_es": schedule_label(s, "es"),
           "response_min": s.get("resp_avg_min") if (s.get("resp_count") or 0) >= 3 else None}
    if origin:
        out["distance_km"] = round(km_between(origin, center), 1)
    return out


# --- Avisos push (Expo) ---
class PushTokenIn(BaseModel):
    token: str = Field(max_length=200)
    lang: str = Field(default="it", max_length=5)


@api.post("/push/token")
async def save_push_token(body: PushTokenIn, request: Request):
    user = await current_user(request)
    if not body.token.startswith(("ExponentPushToken[", "ExpoPushToken[")):
        raise HTTPException(400, "Invalid token")
    await db.users.update_many({"push_tokens": body.token, "user_id": {"$ne": user["user_id"]}},
                               {"$pull": {"push_tokens": body.token}})  # un telefono, una cuenta
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$addToSet": {"push_tokens": body.token},
                               "$set": {"lang": "es" if body.lang == "es" else "it"}})
    return {"ok": True}


async def send_push(user_id: str, title_by_lang: dict, body_by_lang: dict, data: dict) -> None:
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "push_tokens": 1, "lang": 1})
        tokens = (u or {}).get("push_tokens") or []
        if not tokens:
            return
        lang = (u or {}).get("lang") or "it"
        msgs = [{"to": tk, "title": title_by_lang[lang], "body": body_by_lang[lang], "data": data, "sound": "default",
                 "channelId": "default"} for tk in tokens]
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.post("https://exp.host/--/api/v2/push/send", json=msgs)
        for tk, res in zip(tokens, (r.json().get("data") or []) if r.status_code == 200 else []):
            if (res.get("details") or {}).get("error") == "DeviceNotRegistered":
                await db.users.update_one({"user_id": user_id}, {"$pull": {"push_tokens": tk}})
    except Exception as e:
        logger.warning("push a %s no enviado: %s", user_id, e)


def _quote(text: str, n: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


async def notify_message(conv: dict, sender: dict, text: str, first_from_client: bool) -> None:
    other = [p for p in conv["participants"] if p != sender["user_id"]][0]
    data = {"type": "message", "conversation_id": conv["conversation_id"]}
    name = sender["name"].split()[0] if sender.get("name") else ""
    if first_from_client and other == conv.get("specialist_user_id"):
        spec = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0, "zone": 1}) or {}
        loc = sender.get("last_loc")
        dist = f" a {round(km_between((loc['lat'], loc['lng']), spec_zone(spec)[0]))} km" if loc else ""
        title = {"it": f"Nuovo cliente{dist}", "es": f"Nuevo cliente{dist}"}
        body = {"it": f"{name} ti ha scritto: «{_quote(text)}». Rispondi presto!",
                "es": f"{name} te ha escrito: «{_quote(text)}». ¡Responde pronto!"}
    else:
        title = {"it": sender.get("name") or "BeHappy", "es": sender.get("name") or "BeHappy"}
        body = {"it": _quote(text, 140), "es": _quote(text, 140)}
    await send_push(other, title, body, data)


async def reverse_place(lat: float, lng: float) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "BeHappy/1.0 (info@be-happyapp.com)"}) as hc:
            r = await hc.get("https://nominatim.openstreetmap.org/reverse",
                             params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 14, "accept-language": "it"})
        a = r.json().get("address") or {}
        return a.get("suburb") or a.get("quarter") or a.get("neighbourhood") or a.get("city_district") or a.get("city")
    except Exception:
        return None


# --- Provincias: cliente y especialista solo se encuentran dentro de la misma provincia ---
# Toda Italia, sectorizada por provincia: un especialista de Roma no ve ni recibe trabajos de Milan.
# La provincia sale del punto en el mapa (OpenStreetMap / Nominatim) y se guarda: {"code": "TO", "name": "Torino"}.
_nominatim_lock = asyncio.Lock()
_nominatim_last = 0.0


async def _nominatim(path: str, params: dict) -> Optional[object]:
    """Nominatim pide como maximo 1 peticion por segundo: las ponemos en fila."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = 1.05 - (_time.monotonic() - _nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "BeHappy/1.0 (info@be-happyapp.com)"}) as hc:
                r = await hc.get(f"https://nominatim.openstreetmap.org/{path}",
                                 params={**params, "format": "jsonv2", "addressdetails": 1, "accept-language": "it"})
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            logger.warning("nominatim %s: %s", path, e)
            return None
        finally:
            _nominatim_last = _time.monotonic()


def province_from_address(a: dict) -> Optional[dict]:
    """De la direccion de Nominatim a {"code": "TO", "name": "Torino"}. Fuera de Italia: None."""
    if (a.get("country_code") or "it") != "it":
        return None
    iso_code = a.get("ISO3166-2-lvl6") or ""
    code = iso_code.split("-", 1)[1].upper() if iso_code.upper().startswith("IT-") else ""
    name = a.get("county") or a.get("province") or ""
    name = re.sub(r"^(citt[aà] metropolitana d[i'] ?|provincia (di|del|della|dell') ?|libero consorzio comunale di )", "",
                  name.strip(), flags=re.I).strip()
    if not code and not name and "aosta" in (a.get("state") or "").lower():
        code, name = "AO", "Aosta"  # la Valle d'Aosta no tiene provincia: cuenta como una
    if not code and not name:
        return None
    return {"code": code or name.upper(), "name": name or code}


async def province_at(lat: float, lng: float) -> Optional[dict]:
    """Provincia de un punto (con cache de ~1 km)."""
    key = f"rev:{lat:.2f}:{lng:.2f}"
    hit = await db.geo_cache.find_one({"_id": key})
    if hit:
        return hit.get("province")
    data = await _nominatim("reverse", {"lat": lat, "lon": lng, "zoom": 10})
    if not isinstance(data, dict) or data.get("error"):
        return None
    prov = province_from_address(data.get("address") or {})
    if prov:
        await db.geo_cache.update_one({"_id": key}, {"$set": {"province": prov, "at": iso(now())}}, upsert=True)
    return prov


async def place_search(q: str) -> list:
    """Busca un comune italiano por nombre y devuelve su provincia (para quien no da la ubicacion)."""
    q = " ".join(q.split())[:80]
    key = f"q:{q.lower()}"
    hit = await db.geo_cache.find_one({"_id": key})
    if hit:
        return hit.get("results") or []
    data = await _nominatim("search", {"q": q, "countrycodes": "it", "featureType": "settlement", "limit": 8})
    if not isinstance(data, list):
        return []
    out, seen = [], set()
    for it in data:
        a = it.get("address") or {}
        prov = province_from_address(a)
        name = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("hamlet") \
            or (it.get("name") or "")
        if not prov or not name or (name, prov["code"]) in seen:
            continue
        seen.add((name, prov["code"]))
        out.append({"name": name, "province": prov, "lat": float(it["lat"]), "lng": float(it["lon"])})
    await db.geo_cache.update_one({"_id": key}, {"$set": {"results": out[:6], "at": iso(now())}}, upsert=True)
    return out[:6]


async def zone_from_city(city: str) -> Optional[dict]:
    """Zona inicial del especialista a partir del comune que escribio en la web ('settimo-torinese' o texto libre)."""
    name = " ".join(city.replace("-", " ").split())
    if len(name) < 2:
        return None
    results = await place_search(name)
    if not results:
        return None
    best = next((r for r in results if r["name"].lower() == name.lower()), results[0])
    return {"lat": best["lat"], "lng": best["lng"], "radius_km": DEFAULT_RADIUS_KM, "label": best["name"],
            "province": best["province"]}


def prov_code(doc: Optional[dict]) -> Optional[str]:
    return ((doc or {}).get("province") or {}).get("code")


async def set_user_province(user: dict, lat: float, lng: float, source: str) -> Optional[dict]:
    prov = await province_at(lat, lng)
    if prov:
        zone = {"province": prov, "lat": round(lat, 3), "lng": round(lng, 3), "source": source, "at": iso(now())}
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"zone": zone}})
        user["zone"] = zone
    return prov


class MyZoneIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@api.get("/me/zone")
async def get_my_zone(request: Request):
    user = await current_user(request)
    return {"province": (user.get("zone") or {}).get("province")}


@api.put("/me/zone")
async def put_my_zone(body: MyZoneIn, request: Request):
    """El cliente elige su provincia: con su ubicacion o con el comune que escribe."""
    user = await current_user(request)
    rate_limit(f"zone:{user['user_id']}", 10, 60)
    prov = await set_user_province(user, body.lat, body.lng, "manual")
    if not prov:
        raise HTTPException(422, "No encontramos la provincia de ese punto: BeHappy solo funciona en Italia")
    return {"province": prov}


@api.get("/places/search")
async def search_places(q: str, request: Request):
    user = await current_user(request)
    if len(q.strip()) < 2:
        return []
    rate_limit(f"places:{user['user_id']}", 10, 60)
    return await place_search(q)


async def notify_nearby_diagnosis(diag: dict, lat: float, lng: float) -> None:
    """Una persona hizo una diagnosis: avisa a los especialistas de ese oficio que trabajan en esa zona."""
    try:
        cat = diag.get("category")
        if cat not in CATEGORIES:
            return
        prov = await province_at(lat, lng)
        if not prov:
            return
        place = None
        day = now().astimezone(ROME).strftime("%Y-%m-%d")
        async for s in db.specialists.find({"categories": cat, "user_id": {"$ne": diag["user_id"]},
                                            "zone.province.code": prov["code"],
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
                place = await reverse_place(lat, lng) or ""
            where_it, where_es = (f"a {place}", f"en {place}") if place else ("vicino a te", "cerca de ti")
            await send_push(s["user_id"],
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
        await notify_message(conv, sender, msg["text"], False)
    else:
        n = await db.messages.count_documents({"conversation_id": conv["conversation_id"], "sender_id": sender["user_id"]},
                                              limit=2)
        await notify_message(conv, sender, msg["text"], n == 1)


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


@api.get("/specialists/me/stats")
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


@api.get("/specialists/me/settings")
async def my_settings(request: Request, lang: str = "it"):
    user, s = await my_spec(request)
    center, radius = spec_zone(s)
    alerts = s.get("alerts") or {}
    return {"zone": {"lat": center[0], "lng": center[1], "radius_km": radius, "label": (s.get("zone") or {}).get("label"),
                     "province": (s.get("zone") or {}).get("province"), "set": bool(prov_code(s.get("zone")))},
            "schedule": s.get("schedule") or {"days": [1, 2, 3, 4, 5, 6], "from": "08:00", "to": "19:00"},
            "schedule_set": bool(s.get("schedule")), "urgent": bool(s.get("urgent")),
            "alerts": {"enabled": alerts.get("enabled", True), "categories": alerts.get("categories") or s.get("categories") or []},
            "quick_replies": s["quick_replies"] if s.get("quick_replies") is not None
            else DEFAULT_QUICK_REPLIES["es" if lang == "es" else "it"],
            "featured_until": s.get("featured_until") if featured_active(s) else None,
            "categories": s.get("categories") or [], "has_push": bool(user.get("push_tokens"))}


@api.put("/specialists/me/zone")
async def save_zone(body: ZoneIn, request: Request):
    user, s = await my_spec(request)
    days = sorted({d for d in body.days if 1 <= d <= 7})
    if not days or _hm(body.from_) >= _hm(body.to):
        raise HTTPException(400, "Invalid schedule")
    old = s.get("zone") or {}
    moved = old.get("lat") != body.lat or old.get("lng") != body.lng or not old.get("province")
    province = await province_at(body.lat, body.lng) if moved else old["province"]
    if not province:
        raise HTTPException(422, "No encontramos la provincia de ese punto: elige un punto en Italia")
    label = await reverse_place(body.lat, body.lng) if moved else old.get("label")
    await db.specialists.update_one({"specialist_id": s["specialist_id"]}, {"$set": {
        "zone": {"lat": body.lat, "lng": body.lng, "radius_km": body.radius_km, "label": label, "province": province},
        "schedule": {"days": days, "from": body.from_, "to": body.to}, "urgent": body.urgent}})
    return await my_settings(request)


class AlertsIn(BaseModel):
    enabled: bool
    categories: List[str] = Field(max_length=10)


@api.put("/specialists/me/alerts")
async def save_alerts(body: AlertsIn, request: Request):
    user, s = await my_spec(request)
    cats = [c for c in dict.fromkeys(body.categories) if c in (s.get("categories") or [])]
    await db.specialists.update_one({"specialist_id": s["specialist_id"]},
                                    {"$set": {"alerts": {"enabled": body.enabled, "categories": cats}}})
    return {"enabled": body.enabled, "categories": cats}


class QuickRepliesIn(BaseModel):
    items: List[str] = Field(max_length=10)


@api.put("/specialists/me/quick-replies")
async def save_quick_replies(body: QuickRepliesIn, request: Request):
    user, s = await my_spec(request)
    items = [" ".join(x.split())[:200] for x in body.items if x.strip()][:10]
    await db.specialists.update_one({"specialist_id": s["specialist_id"]}, {"$set": {"quick_replies": items}})
    return {"items": items}


# --- Perfil destacado (compra en Google Play via RevenueCat; consumible de 7 o 30 dias) ---
@api.get("/featured/status")
async def featured_status(request: Request):
    user, s = await my_spec(request)
    cat = (s.get("categories") or [None])[0]
    taken = await db.specialists.count_documents({"categories": cat, "featured_until": {"$gt": iso(now())},
                                                  "specialist_id": {"$ne": s["specialist_id"]}}) if cat else 0
    return {"featured_until": s.get("featured_until") if featured_active(s) else None,
            "slots_left": max(0, FEATURED_MAX_PER_TRADE - taken), "category": cat,
            "membership_active": membership_active(s)}


@api.post("/featured/sync")
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
    base = _api_base()
    links = {d: f"{base}/api/admin/specialists/{sid}/decide?d={d}&t={_spec_decision_token(sid, d)}" for d in ("show", "remove")}
    lines = [f"- {r['reason']}: {r.get('details') or '(sin detalles)'} ({r['created_at'][:10]})" for r in reps]
    text = (f"El perfil de {s['name']} ({s.get('phone') or ''}) se ha ocultado: lo han reportado {SPEC_REPORTS_TO_HIDE} clientes "
            f"distintos que hablaron con él.\n\n" + "\n".join(lines) +
            f"\n\nVolver a mostrarlo: {links['show']}\nDarlo de baja: {links['remove']}")
    html = (f"<div style=\"font-family:Arial,sans-serif;color:#0a1628\"><p>El perfil de <b>{_esc(s['name'])}</b> se ha ocultado: "
            f"lo han reportado {SPEC_REPORTS_TO_HIDE} clientes distintos que hablaron con él.</p><ul>"
            + "".join(f"<li>{_esc(x[2:])}</li>" for x in lines) +
            f"</ul><p><a href=\"{_esc(links['show'])}\">Volver a mostrarlo</a> · <a href=\"{_esc(links['remove'])}\">Darlo de baja</a></p></div>")
    await send_email(os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com"), f"Be Happy: perfil de {s['name']} oculto por reportes",
                     text, html)


@api.get("/admin/specialists/{sid}/decide")
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
    return _decide_page(f"{label}: {s['name']}", f"<p>{_esc(s.get('phone') or '')} · reportes: {len(s.get('client_reports') or [])}</p>" + form)


@api.post("/admin/specialists/{sid}/decide")
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
    return _decide_page("Hecho", f"<p>{_esc(s['name'])}: {'visible otra vez' if d == 'show' else 'dado de baja'}.</p>")


# --- Diagnosis compartida en el chat ---
def diagnosis_summary(d: dict) -> dict:
    return {"diagnosis_id": d["diagnosis_id"], "title_es": d.get("title_es"), "title_it": d.get("title_it"),
            "category": d.get("category"), "image_path": d.get("image_path"),
            "materials": [m.get("name") for m in (d.get("materials") or []) if isinstance(m, dict) and m.get("name")][:6],
            "materials_lang": d.get("language")}


async def review_prompt_for(conv: dict, user: dict) -> bool:
    if user["user_id"] != conv.get("client_id") or not conv.get("first_reply_at"):
        return False
    if conv["first_reply_at"] > iso(now() - timedelta(days=REVIEW_PROMPT_DAYS)):
        return False
    s = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0})
    return bool(s) and await can_review(user, s)


# ---------------- Suscripcion de especialistas en la web (Stripe) ----------------
# La app no cobra nada: el especialista entra en be-happyapp.com/abbonamento con un codigo que le llega por correo,
# paga con Stripe Checkout y Stripe avisa a este servidor (webhook), que activa la membresia. En la app solo se ve
# "Profilo attivo / non attivo". Los precios y el webhook se crean solos en Stripe la primera vez (solo hace falta
# STRIPE_SECRET_KEY en Render).
import hashlib
import hmac as _hmac
from urllib.parse import urlencode

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
            "product": product, "currency": "eur", "unit_amount": int(round(PLANS[plan]["amount"] * 100)),
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
    base = _api_base()
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
        await activate_membership(uid, _sub_plan(sub), "stripe", datetime.fromtimestamp(end, timezone.utc) + timedelta(days=1))
    elif sub.get("status") in ("canceled", "unpaid", "incomplete_expired"):
        cur = await db.memberships.find_one({"user_id": uid}, {"_id": 0}) or {}
        if cur.get("source") == "stripe":
            await activate_membership(uid, _sub_plan(sub), "stripe", now())


@api.post("/stripe/webhook")
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


@api.post("/web/login/start")
async def web_login_start(body: WebLoginStartIn, request: Request):
    require_web(request)
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
        await send_email(email, subject, text, f"<div style=\"font-family:Arial,sans-serif;color:#25221e;white-space:pre-line\">"
                                               f"{_esc(text)}</div>")
    return {"ok": True}


@api.post("/web/login/confirm")
async def web_login_confirm(body: WebLoginConfirmIn, request: Request):
    require_web(request)
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
    require_web(request)
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


@api.get("/web/membership")
async def web_membership(request: Request):
    user = await web_user(request)
    spec = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0, "name": 1, "avatar": 1})
    m = await membership_payload(user["user_id"])
    return {"name": (spec or {}).get("name") or user.get("name"), "email": user["email"], "is_specialist": bool(spec),
            "membership": m, "can_manage": bool(user.get("stripe_customer_id")),
            "renews": user.get("stripe_status") in ("active", "trialing")}


class CheckoutIn(BaseModel):
    plan: str = Field(max_length=10)
    lang: str = Field(default="it", max_length=5)


@api.post("/web/checkout")
async def web_checkout(body: CheckoutIn, request: Request):
    user = await web_user(request)
    if body.plan not in PLANS:
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


@api.post("/web/portal")
async def web_portal(request: Request):
    user = await web_user(request)
    if not user.get("stripe_customer_id"):
        raise HTTPException(400, "no_customer")
    s = await stripe_api("POST", "billing_portal/sessions", {"customer": user["stripe_customer_id"],
                                                             "return_url": f"{WEB_URL}/abbonamento"})
    return {"url": s["url"]}


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


@api.get("/web/app-reviews")
async def list_app_reviews(request: Request):
    require_web(request)
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


@api.get("/web/app-reviews/mine")
async def my_app_review(request: Request):
    user = await web_user(request)
    r = await db.app_reviews.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"name": _public_name(user.get("name") or ""), "review": app_review_public(r) if r else None}


@api.post("/web/app-reviews")
async def save_app_review(body: AppReviewIn, request: Request):
    user = await web_user(request)
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
    link = f"{_api_base()}/api/admin/app-reviews/{rid}/hide?t={_review_token(rid)}"
    text = (f"{data['name']} ({role}) · {body.stars}★ · soddisfazione {body.satisfaction}/5 · "
            f"consiglia: {'sì' if body.recommend else 'no'}\n\n{comment or '(senza commento)'}\n\nNascondere: {link}")
    asyncio.create_task(send_email(os.environ.get("ADMIN_EMAIL", "info@be-happyapp.com"),
                                   f"Be Happy: nuova recensione {body.stars}★", text,
                                   f"<div style=\"font-family:Arial,sans-serif;color:#25221e;white-space:pre-line\">"
                                   f"{_esc(text)}</div>"))
    r = await db.app_reviews.find_one({"review_id": rid}, {"_id": 0})
    return app_review_public(r)


@api.get("/admin/app-reviews/{rid}/hide")
async def admin_hide_review_page(rid: str, t: str):
    if not _hmac.compare_digest(t, _review_token(rid)):
        raise HTTPException(403, "Forbidden")
    r = await db.app_reviews.find_one({"review_id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Not found")
    form = (f"<form method=\"post\"><input type=\"hidden\" name=\"t\" value=\"{_esc(t)}\">"
            f"<button style=\"font-size:16px;padding:12px 24px;border-radius:999px;border:0;background:#0a1628;color:#fff\">"
            f"Ocultar reseña</button></form>")
    return _decide_page("Ocultar reseña", f"<p><b>{_esc(r['name'])}</b> · {r['stars']}★<br>{_esc(r.get('comment') or '')}</p>" + form)


@api.post("/admin/app-reviews/{rid}/hide")
async def admin_hide_review(rid: str, request: Request):
    form = await request.form()
    t = str(form.get("t") or "")
    if not _hmac.compare_digest(t, _review_token(rid)):
        raise HTTPException(403, "Forbidden")
    await db.app_reviews.update_one({"review_id": rid}, {"$set": {"hidden": True, "hidden_at": iso(now())}})
    return _decide_page("Hecho", "<p>La reseña ya no se ve en la web.</p>")


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.specialists.create_index("specialist_id", unique=True)
    await db.messages.create_index("conversation_id")
    await db.files.create_index("storage_path")
    await db.reviews.create_index([("specialist_id", 1), ("user_id", 1)], unique=True)
    await db.conversations.create_index([("client_id", 1), ("specialist_id", 1)], unique=True)
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.auth_sessions.create_index("jti", unique=True)
    await db.password_resets.create_index("user_id", unique=True)
    await db.password_resets.create_index("email")
    await db.password_resets.create_index("expires_at", expireAfterSeconds=0)
    await db.auth_sessions.create_index("user_id")
    await db.auth_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.stores.create_index("store_id", unique=True)
    await db.profile_views.create_index([("specialist_id", 1), ("viewer_id", 1), ("day", 1)], unique=True)
    await db.profile_views.create_index([("specialist_id", 1), ("at", 1)])
    await db.response_times.create_index([("specialist_id", 1), ("at", -1)])
    await db.featured_purchases.create_index("tx_id", unique=True)
    await db.push_quota.create_index([("specialist_id", 1), ("day", 1)], unique=True)
    await db.stripe_events.create_index("id", unique=True)
    await db.app_reviews.create_index("user_id", unique=True)
    await db.app_reviews.create_index([("hidden", 1), ("created_at", -1)])
    await db.web_login_codes.create_index("email", unique=True)
    await db.users.create_index("stripe_customer_id", sparse=True)
    asyncio.create_task(ensure_stripe_webhook())
    await db.stores.create_index([("location", "2dsphere")])
    await db.specialists.create_index("zone.province.code")
    await db.stores.create_index([("piva", 1), ("cap", 1)])
    await db.specialists.update_many({"document_number": {"$exists": True}}, {"$unset": {"document_number": ""}})
    try:
        await db[PREREG].create_index("email", unique=True, name="email_unico")
    except Exception as e:
        logger.warning("indice de pre-registro: %s", e)
    # migrate single category -> categories (trades limited to the 5 supported ones)
    async for s in db.specialists.find({"categories": {"$exists": False}}, {"_id": 0, "specialist_id": 1, "category": 1}):
        cats = [s["category"]] if s.get("category") in CATEGORIES else []
        await db.specialists.update_one({"specialist_id": s["specialist_id"]}, {"$set": {"categories": cats}})
    await db.specialists.update_many({"categories": "appliances"}, {"$pull": {"categories": "appliances"}})
    await db.specialists.update_many({"verification_status": "verified", "verified_by": {"$exists": False}},
                                     {"$set": {"verification_status": "in_review", "verified": False}})
    await db.specialists.update_many({}, {"$unset": {"city": "", "years_experience": "", "hourly_rate": "", 
                                                     "recommend_count": "", "category": ""}})
    try:
        init_storage()
    except Exception as e:
        logger.error("Storage init failed: %s", e)


app.include_router(api)

_cors = [o.strip() for o in os.environ.get("CORS_ORIGINS", "https://www.be-happyapp.com").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=_cors, allow_methods=["*"], allow_headers=["*"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
