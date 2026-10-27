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


async def gemini_json(prompt: str, image_b64: Optional[str] = None) -> dict:
    """Pide a Gemini una respuesta en JSON, con o sin foto."""
    rate_limit("gemini-global", 600, 3600)
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
        in_portfolio = await db.specialists.find_one({"$or": [{"portfolio.image": path}, {"avatar": path}]}, {"_id": 1})
        if not in_portfolio:
            raise HTTPException(404, "File not found")
    data, ct = await run_in_threadpool(get_object, path)
    return Response(content=data, media_type=rec.get("content_type", ct), headers={"Cache-Control": "private, max-age=86400"})


# ---------------- AI Diagnosis ----------------
DIAG_PROMPT = """You are an expert home repair technician. Analyze the photo of a household problem.
Respond ONLY with valid JSON (no markdown). All text fields in {lang}, except title_es (Spanish) and title_it (Italian). Schema:
{{
 "is_home_problem": true/false,
 "is_appliance": true/false,
 "title_es": "short problem name in Spanish",
 "title_it": "short problem name in Italian",
 "category": one of {cats},
 "description": "2-3 sentences explaining what is wrong and likely cause",
 "difficulty": "easy" | "medium" | "expert",
 "safety_warnings": ["..."],
 "materials": [{{"name": "...", "quantity": "..."}}],
 "tools": ["..."],
 "steps": [{{"title": "...", "detail": "..."}}],
 "estimated_time": "e.g. 1-2 h",
 "when_to_call_pro": "short sentence"
}}
Difficulty rules:
- easy: a non-expert can safely fix it alone. Give 4-8 clear steps.
- medium: a handy person can try it. Give 4-8 clear steps; when_to_call_pro explains when to stop and call a specialist.
- expert: needs a professional (gas, mains electricity, structural, refrigerant, anything risky). steps, materials and tools MUST be empty arrays. Never give repair instructions; safety_warnings only says what to avoid and how to stay safe until the specialist arrives.
If the problem is a household appliance (washing machine, oven, fridge, dishwasher, dryer, microwave or any other appliance) set is_appliance true and leave steps, materials and tools empty.
If the image is not a home problem set is_home_problem false and still fill title/description explaining that.
{extra}"""

TRANSLATABLE = ["description", "safety_warnings", "materials", "tools", "steps", "estimated_time", "when_to_call_pro"]


APPLIANCE_WORDS = ["lavadora", "horno", "nevera", "frigor", "lavavajillas", "secadora", "microondas", "electrodom",
                   "lavatrice", "forno", "lavastoviglie", "asciugatrice", "microonde", "elettrodom",
                   "washing machine", "oven", "fridge", "refrigerator", "dishwasher", "dryer", "microwave", "appliance"]


def normalize_diagnosis(r: dict) -> dict:
    text = " ".join(str(r.get(k) or "") for k in ("title_es", "title_it", "title", "category")).lower()
    if r.get("is_appliance") or any(w in text for w in APPLIANCE_WORDS):
        r["is_appliance"] = True
        r["category"] = "appliance"
        r["steps"], r["materials"], r["tools"] = [], [], []
    elif r.get("category") not in CATEGORIES:
        r["category"] = "unknown"  # never force an unknown trade into masonry
    diff = r.get("difficulty")
    r["difficulty"] = "expert" if diff in ("hard", "expert") else diff if diff in ("easy", "medium") else "medium"
    # Seguridad: el gas siempre es experto; lo electrico solo puede ser "facil" si la IA lo marca asi
    gas_risk = re.search(r"\b(gas|caldaia|caldera|boiler|stufa|estufa|metano)\b", text) is not None
    if gas_risk or (r.get("category") == "electrical" and r["difficulty"] != "easy"):
        r["difficulty"] = "expert"
    if r["difficulty"] == "expert":
        r["steps"], r["materials"], r["tools"] = [], [], []
    for k in ("steps", "materials", "tools", "safety_warnings"):
        r[k] = r.get(k) or []
    r["title_es"] = r.get("title_es") or r.get("title") or ""
    r["title_it"] = r.get("title_it") or r.get("title") or ""
    return r


class DiagnoseIn(BaseModel):
    image_base64: str = Field(max_length=14_000_000)
    language: str = "es"
    note: Optional[str] = Field(default=None, max_length=500)

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


async def specialist_out(s: dict) -> dict:
    s.pop("verification_document", None)
    s.pop("document_number", None)
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
    await apply_prereg(user)
    await start_web_promo(user, request)
    return await specialist_out(await db.specialists.find_one({"specialist_id": sid}, {"_id": 0}))


@api.get("/specialists")
async def list_specialists(request: Request, category: Optional[str] = None, q: Optional[str] = None):
    user = await current_user(request)
    # Salen todos los especialistas con foto de perfil; los que tienen membresía activa ("disponibles") primero
    flt = {"avatar": {"$type": "string"}}
    if category and category != "all":
        flt["categories"] = category
    if q:
        flt["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    items = await db.specialists.find(flt, {"_id": 0, "verification_document": 0, "document_number": 0}) \
        .sort([("verified", -1), ("created_at", 1)]).to_list(500)
    hidden = await hidden_user_ids(user["user_id"])
    out = [await specialist_out(it) for it in items if it["user_id"] not in hidden]
    out.sort(key=lambda it: not it["membership_active"])  # orden estable: disponibles primero
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
    out = await specialist_out(s)
    out["can_review"] = await can_review(user, s)
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
REPORT_TARGETS = {"message", "review", "portfolio", "specialist", "user"}
REPORT_REASONS = {"spam", "inappropriate", "harassment", "fraud", "other"}


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
    return msg


@api.post("/conversations")
async def start_conversation(body: ConversationIn, request: Request):
    user = await current_user(request)
    spec = await db.specialists.find_one({"specialist_id": body.specialist_id}, {"_id": 0})
    if not spec:
        raise HTTPException(404, "Specialist not found")
    if await blocked_between(user["user_id"], spec["user_id"]):
        raise HTTPException(403, "No puedes contactar a este usuario")
    # Cualquier cliente puede escribir; el especialista necesita membresía para responder
    return await get_or_create_conversation(user, spec)


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
    """'web' (www.be-happyapp.com), 'app' o '' segun la cabecera que envia cada cliente."""
    return (request.headers.get("x-behappy-client") or "").strip().lower()


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
