"""Limite de peticiones, IP del cliente, sesiones JWT, usuario actual y codigos de referido."""
import os
import re
import uuid
import jwt
import time as _time
from fastapi import HTTPException, Request
from typing import Optional
from datetime import datetime, timezone, timedelta
from collections import deque
from .core import APP_NAME, JWT_SECRET, db, iso, now


# ---------------- Limite de peticiones ----------------

_hits: dict = {}  # key -> deque of hit times, oldest-used first
_HITS_MAX = 50000


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
    # Forget only the least recently used keys when there are too many. Clearing everything (as before) let
    # anyone wipe every limit, login ones included, just by sending requests with lots of different emails.
    if len(_hits) > _HITS_MAX:
        for k in list(_hits)[: len(_hits) - _HITS_MAX + 1000]:
            _hits.pop(k, None)
    q = _hits.pop(key, None) or deque()
    _hits[key] = q  # move to the end: most recently used
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
    await mark_active(user)
    return user


async def mark_active(user: dict) -> None:
    """Apunta que la persona uso la app hoy (para el panel de administracion): una sola escritura por persona y dia."""
    day = now().strftime("%Y-%m-%d")
    if user.get("last_seen_day") == day:
        return
    try:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_seen_day": day}})
        await db.activity_days.update_one({"_id": f"{day}:{user['user_id']}"},
                                          {"$setOnInsert": {"day": day, "user_id": user["user_id"],
                                                            "role": user.get("role") or "client", "at": now()}},
                                          upsert=True)
        user["last_seen_day"] = day
    except Exception:
        pass  # contar la actividad nunca debe impedir usar la app


REF_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")


def clean_ref(value: Optional[str]) -> Optional[str]:
    """Codigo de quien recomendo la app (embajador, cartel con QR...): minusculas, letras/numeros/-/_, 2-40 caracteres."""
    ref = (value or "").strip().lower()
    return ref if REF_RE.match(ref) else None


def referral_fields(value: Optional[str]) -> dict:
    """Solo se guarda al crear la cuenta: luego no se puede cambiar (asi nadie cobra dos veces por el mismo usuario)."""
    ref = clean_ref(value)
    return {"referido_por": ref, "referido_en": iso(now())} if ref else {}
