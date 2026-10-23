from fastapi import FastAPI, APIRouter, HTTPException, Request, UploadFile, File, Form, Query
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

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone  # noqa: E402

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
JWT_SECRET = os.environ["JWT_SECRET"]
APP_NAME = os.environ.get("APP_NAME", "fixai-home")
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
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


async def _gemini_once(api_key: str, prompt: str, image_b64: Optional[str]) -> dict:
    chat = LlmChat(api_key=api_key, session_id=new_id("ai"),
                   system_message="You output valid JSON only, no markdown.").with_model("gemini", "gemini-3-flash-preview")
    if api_key != EMERGENT_KEY:  # Emergent proxy (openai-compatible) rejects reasoning_effort -> UnsupportedParamsError
        chat = chat.with_params(reasoning_effort="low")  # default thinking took ~25s; low keeps quality at ~5s
    text = ""
    msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)] if image_b64 else None)
    async for ev in chat.stream_message(msg):
        if isinstance(ev, TextDelta):
            text += ev.content
        elif isinstance(ev, StreamDone):
            break
    return parse_json(text)


async def gemini_json(prompt: str, image_b64: Optional[str] = None) -> dict:
    """Use the owner's Gemini key first; if it fails (e.g. daily quota reached) fall back to the Emergent universal key."""
    own = os.environ.get("GEMINI_API_KEY")
    if own:
        try:
            return await _gemini_once(own, prompt, image_b64)
        except Exception as e:
            logger.warning("own Gemini key failed, falling back to universal key: %s", str(e)[:200])
    return await _gemini_once(EMERGENT_KEY, prompt, image_b64)


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
def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    global storage_key
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    if resp.status_code == 503:
        storage_key = None
        key = init_storage()
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
    if resp.status_code == 402:
        raise HTTPException(402, "Storage credits exhausted")
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


async def store_bytes(user_id: str, data: bytes, content_type: str, ext: str) -> str:
    path = f"{APP_NAME}/uploads/{user_id}/{uuid.uuid4().hex}.{ext}"
    result = await run_in_threadpool(put_object, path, data, content_type)
    stored = result.get("path", path)
    await db.files.insert_one({"storage_path": stored, "owner_id": user_id, "content_type": content_type,
                               "is_deleted": False, "created_at": iso(now())})
    return stored


# ---------------- Auth ----------------
def public_user(u: dict) -> dict:
    return {k: u.get(k) for k in ["user_id", "email", "name", "picture", "role", "specialist_id", "created_at"]}


def make_jwt(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": now() + timedelta(days=7), "type": "access"}, JWT_SECRET, algorithm="HS256")


async def user_from_token(token: str) -> Optional[dict]:
    if not token:
        return None
    user_id = None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
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
    email: str
    password: str
    name: str


class LoginIn(BaseModel):
    email: str
    password: str


class SessionIn(BaseModel):
    session_id: str


@api.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Invalid email")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    user = {"user_id": new_id("user"), "email": email, "name": body.name.strip() or email.split("@")[0],
            "picture": None, "role": "client", "specialist_id": None,
            "password_hash": bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode(),
            "created_at": iso(now())}
    await db.users.insert_one(user)
    return {"session_token": make_jwt(user["user_id"]), "user": public_user(user)}


@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Invalid email or password")
    return {"session_token": make_jwt(user["user_id"]), "user": public_user(user)}


@api.post("/auth/session")
async def google_session(body: SessionIn):
    async with httpx.AsyncClient(timeout=20) as hc:
        r = await hc.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                         headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(401, "Invalid session")
    data = r.json()
    email = data["email"].lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": user.get("picture") or data.get("picture")}})
        user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    else:
        user = {"user_id": new_id("user"), "email": email, "name": data.get("name") or email.split("@")[0],
                "picture": data.get("picture"), "role": "client", "specialist_id": None, "created_at": iso(now())}
        await db.users.insert_one(user)
        user.pop("_id", None)
    token = data["session_token"]
    await db.user_sessions.insert_one({"session_token": token, "user_id": user["user_id"],
                                       "expires_at": now() + timedelta(days=7), "created_at": now()})
    return {"session_token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(request: Request):
    return public_user(await current_user(request))


@api.post("/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        await db.user_sessions.delete_one({"session_token": auth[7:]})
    return {"ok": True}


# ---------------- Files ----------------
@api.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    user = await current_user(request)
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    ext = (file.filename or "img.jpg").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    path = await store_bytes(user["user_id"], data, file.content_type or "image/jpeg", ext)
    return {"path": path}


@api.get("/files/{path:path}")
async def get_file(path: str, request: Request, token: Optional[str] = Query(None)):
    auth = request.headers.get("Authorization", "")
    tok = auth[7:] if auth.startswith("Bearer ") else token
    if not await user_from_token(tok):
        raise HTTPException(401, "Not authenticated")
    rec = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not rec:
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
    if r["difficulty"] == "expert":
        r["steps"], r["materials"], r["tools"] = [], [], []
    for k in ("steps", "materials", "tools", "safety_warnings"):
        r[k] = r.get(k) or []
    r["title_es"] = r.get("title_es") or r.get("title") or ""
    r["title_it"] = r.get("title_it") or r.get("title") or ""
    return r


class DiagnoseIn(BaseModel):
    image_base64: str
    language: str = "es"
    note: Optional[str] = None


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
    doc = {"diagnosis_id": new_id("diag"), "user_id": user["user_id"], "image_path": image_path,
           "language": body.language, "created_at": iso(now()), **result}
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
    name: str
    categories: List[str]
    subtrades: List[str] = []
    bio: str = Field("", max_length=300)
    phone: str
    whatsapp: Optional[str] = None


class PortfolioIn(BaseModel):
    image: str
    caption: str = ""


class VerifyIn(BaseModel):
    document_image: str
    document_number: str


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


async def require_active_specialist(spec: dict):
    if not membership_active(spec):
        raise HTTPException(403, "Specialist membership inactive")


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
    if existing:
        await db.specialists.update_one({"specialist_id": existing["specialist_id"]}, {"$set": data})
        sid = existing["specialist_id"]
    else:
        sid = new_id("spec")
        await db.specialists.insert_one({"specialist_id": sid, "user_id": user["user_id"], **data,
                                         "portfolio": [], "verified": False, "verification_status": "none",
                                         "rating_avg": 0.0, "reviews_count": 0, "created_at": iso(now())})
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "specialist", "specialist_id": sid}})
    return await specialist_out(await db.specialists.find_one({"specialist_id": sid}, {"_id": 0}))


@api.get("/specialists")
async def list_specialists(request: Request, category: Optional[str] = None, q: Optional[str] = None):
    await current_user(request)
    # Showcase: only members with at least one work photo; no distance sorting, no assignment
    flt = {"membership_expires_at": {"$gt": iso(now())}, "portfolio.0": {"$exists": True}}
    if category and category != "all":
        flt["categories"] = category
    if q:
        flt["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    items = await db.specialists.find(flt, {"_id": 0, "verification_document": 0, "document_number": 0}) \
        .sort([("verified", -1), ("created_at", 1)]).to_list(200)
    return [await specialist_out(it) for it in items]


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
    if len(body.document_number.strip()) < 5:
        raise HTTPException(400, "Invalid document number")
    # MVP: identity document + number submitted => verified automatically
    await db.specialists.update_one({"user_id": user["user_id"]}, {"$set": {
        "verification_document": body.document_image, "document_number": body.document_number.strip(),
        "verification_status": "in_review", "verified": False, "submitted_at": iso(now())}})
    # badge is only granted after a manual review (no auto-approval)
    return {"verified": False, "verification_status": "in_review"}


@api.get("/specialists/{sid}/reviews")
async def list_reviews(sid: str, request: Request):
    await current_user(request)
    return await db.reviews.find({"specialist_id": sid}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api.post("/specialists/{sid}/reviews")
async def add_review(sid: str, body: ReviewIn, request: Request):
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
    await db.reviews.insert_one(review)
    review.pop("_id", None)
    all_r = await db.reviews.find({"specialist_id": sid}, {"_id": 0, "rating": 1}).to_list(10000)
    avg = round(sum(r["rating"] for r in all_r) / len(all_r), 1)
    await db.specialists.update_one({"specialist_id": sid}, {"$set": {"rating_avg": avg, "reviews_count": len(all_r)}})
    return review


# ---------------- Chat ----------------
class MessageIn(BaseModel):
    text: str


class ConversationIn(BaseModel):
    specialist_id: str


async def get_or_create_conversation(client_user: dict, spec: dict) -> dict:
    if client_user["user_id"] == spec["user_id"]:
        raise HTTPException(400, "Cannot chat with yourself")
    conv = await db.conversations.find_one({"client_id": client_user["user_id"], "specialist_id": spec["specialist_id"]}, {"_id": 0})
    if conv:
        return conv
    conv = {"conversation_id": new_id("conv"), "client_id": client_user["user_id"], "client_name": client_user["name"],
            "client_picture": client_user.get("picture"), "specialist_id": spec["specialist_id"],
            "specialist_user_id": spec["user_id"], "specialist_name": spec["name"], "specialist_avatar": spec.get("avatar"),
            "participants": [client_user["user_id"], spec["user_id"]], "last_message": "", "updated_at": iso(now()),
            "unread": {client_user["user_id"]: 0, spec["user_id"]: 0}}
    await db.conversations.insert_one(conv)
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
    existing = await db.conversations.find_one({"client_id": user["user_id"], "specialist_id": spec["specialist_id"]}, {"_id": 0})
    if existing:
        return existing
    await require_active_specialist(spec)
    return await get_or_create_conversation(user, spec)


@api.get("/conversations")
async def list_conversations(request: Request):
    user = await current_user(request)
    return await db.conversations.find({"participants": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(100)


async def get_conv_for(cid: str, user: dict) -> dict:
    conv = await db.conversations.find_one({"conversation_id": cid}, {"_id": 0})
    if not conv or user["user_id"] not in conv["participants"]:
        raise HTTPException(404, "Conversation not found")
    return conv


@api.get("/conversations/{cid}")
async def get_conversation(cid: str, request: Request):
    user = await current_user(request)
    return await get_conv_for(cid, user)


@api.get("/conversations/{cid}/messages")
async def list_messages(cid: str, request: Request):
    user = await current_user(request)
    await get_conv_for(cid, user)
    await db.conversations.update_one({"conversation_id": cid}, {"$set": {f"unread.{user['user_id']}": 0}})
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(500)
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
    conv = await get_conv_for(cid, user)
    if not body.text.strip():
        raise HTTPException(400, "Empty message")
    return await push_message(conv, user, body.text.strip())


# ---------------- Service requests ----------------
class RequestIn(BaseModel):
    specialist_id: str
    description: str
    address: str = ""
    preferred_date: str = ""
    diagnosis_id: Optional[str] = None


class RequestStatusIn(BaseModel):
    status: str


@api.post("/requests")
async def create_request(body: RequestIn, request: Request):
    user = await current_user(request)
    spec = await db.specialists.find_one({"specialist_id": body.specialist_id}, {"_id": 0})
    if not spec:
        raise HTTPException(404, "Specialist not found")
    if not body.description.strip():
        raise HTTPException(400, "Description required")
    await require_active_specialist(spec)
    diag_title = None
    if body.diagnosis_id:
        d = await db.diagnoses.find_one({"diagnosis_id": body.diagnosis_id}, {"_id": 0, "title": 1})
        diag_title = d.get("title") if d else None
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
    if body.status == "accepted":
        await require_active_specialist(await db.specialists.find_one({"specialist_id": req["specialist_id"]}, {"_id": 0}))
    await db.service_requests.update_one({"request_id": rid}, {"$set": {"status": body.status, "updated_at": iso(now())}})
    if body.status == "completed":
        await db.specialists.update_one({"specialist_id": req["specialist_id"]}, {"$inc": {"jobs_completed": 1}})
    return {**req, "status": body.status}


# ---------------- Quotes (ofertas) ----------------
class QuoteIn(BaseModel):
    price: float = Field(gt=0)
    description: str
    estimated_time: str = ""


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
    await db.payment_transactions.create_index("session_id", unique=True)
    # migrate single category -> categories (trades limited to the 5 supported ones)
    async for s in db.specialists.find({"categories": {"$exists": False}}, {"_id": 0, "specialist_id": 1, "category": 1}):
        cats = [s["category"]] if s.get("category") in CATEGORIES else []
        await db.specialists.update_one({"specialist_id": s["specialist_id"]}, {"$set": {"categories": cats}})
    await db.specialists.update_many({"categories": "appliances"}, {"$pull": {"categories": "appliances"}})
    await db.specialists.update_many({"verification_status": "verified", "verified_by": {"$exists": False}},
                                     {"$set": {"verification_status": "in_review", "verified": False}})
    await db.specialists.update_many({}, {"$unset": {"city": "", "years_experience": "", "hourly_rate": "", "jobs_completed": "",
                                                     "recommend_count": "", "category": ""}})
    try:
        init_storage()
    except Exception as e:
        logger.error("Storage init failed: %s", e)


app.include_router(api)

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
