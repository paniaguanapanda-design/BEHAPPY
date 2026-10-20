from fastapi import FastAPI, APIRouter, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import json
import base64
import logging
import uuid
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
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest  # noqa: E402

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

CATEGORIES = ["plumbing", "electrical", "carpentry", "painting", "masonry", "appliances", "hvac", "roofing", "general"]


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
Respond ONLY with valid JSON (no markdown), written entirely in {lang}, with this exact schema:
{{
 "is_home_problem": true/false,
 "title": "short problem name",
 "category": one of {cats},
 "description": "2-3 sentences explaining what is wrong and likely cause",
 "difficulty": "easy" | "medium" | "hard" | "expert",
 "diy_recommended": true/false,
 "safety_warnings": ["..."],
 "materials": [{{"name": "...", "quantity": "..."}}],
 "tools": ["..."],
 "steps": [{{"title": "...", "detail": "..."}}],
 "estimated_time": "e.g. 1-2 h",
 "estimated_cost": "e.g. 20-40 EUR",
 "when_to_call_pro": "short sentence"
}}
Use 4-8 clear steps. If the image is not a home problem set is_home_problem false and still fill title/description explaining that.
{extra}"""


class DiagnoseIn(BaseModel):
    image_base64: str
    language: str = "es"
    note: Optional[str] = None


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
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "Invalid image")
    lang = "Italian" if body.language == "it" else "Spanish"
    extra = f"User note: {body.note}" if body.note else ""
    chat = LlmChat(api_key=EMERGENT_KEY, session_id=new_id("diag"),
                   system_message="You are a precise home repair diagnostic assistant that outputs JSON only.").with_model("gemini", "gemini-3-flash-preview")
    text = ""
    try:
        async for ev in chat.stream_message(UserMessage(text=DIAG_PROMPT.format(lang=lang, cats=CATEGORIES, extra=extra),
                                                        file_contents=[ImageContent(image_base64=b64)])):
            if isinstance(ev, TextDelta):
                text += ev.content
            elif isinstance(ev, StreamDone):
                break
        result = parse_json(text)
    except Exception as e:
        logger.exception("diagnose failed: %s", e)
        raise HTTPException(502, "AI analysis failed, please retry")
    if result.get("category") not in CATEGORIES:
        result["category"] = "general"
    image_path = None
    try:
        image_path = await store_bytes(user["user_id"], raw, "image/jpeg", "jpg")
    except Exception as e:
        logger.warning("image store failed: %s", e)
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
async def get_diagnosis(diagnosis_id: str, request: Request):
    user = await current_user(request)
    d = await db.diagnoses.find_one({"diagnosis_id": diagnosis_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Not found")
    if d["user_id"] != user["user_id"] and user.get("role") != "specialist":
        raise HTTPException(403, "Forbidden")
    return d


# ---------------- Specialists ----------------
class SpecialistIn(BaseModel):
    name: str
    category: str
    bio: str = ""
    phone: str
    whatsapp: Optional[str] = None
    city: str = ""
    years_experience: int = 0
    hourly_rate: Optional[str] = None
    avatar: Optional[str] = None


class PortfolioIn(BaseModel):
    image: str
    caption: str = ""


class VerifyIn(BaseModel):
    document_image: str
    document_number: str


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""
    recommend: bool = True


def membership_active(s: dict) -> bool:
    exp = s.get("membership_expires_at")
    return bool(exp) and exp > iso(now())


async def specialist_out(s: dict) -> dict:
    s.pop("verification_document", None)
    s.pop("document_number", None)
    s["membership_active"] = membership_active(s)
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
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Invalid category")
    if not body.phone.strip():
        raise HTTPException(400, "Phone required")
    data = body.model_dump()
    data["whatsapp"] = data.get("whatsapp") or data["phone"]
    existing = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if existing:
        await db.specialists.update_one({"specialist_id": existing["specialist_id"]}, {"$set": data})
        sid = existing["specialist_id"]
    else:
        sid = new_id("spec")
        await db.specialists.insert_one({"specialist_id": sid, "user_id": user["user_id"], **data,
                                         "portfolio": [], "verified": False, "verification_status": "none",
                                         "rating_avg": 0.0, "reviews_count": 0, "recommend_count": 0,
                                         "jobs_completed": 0, "created_at": iso(now())})
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "specialist", "specialist_id": sid}})
    return await specialist_out(await db.specialists.find_one({"specialist_id": sid}, {"_id": 0}))


@api.get("/specialists")
async def list_specialists(request: Request, category: Optional[str] = None, q: Optional[str] = None):
    await current_user(request)
    flt = {"membership_expires_at": {"$gt": iso(now())}}
    if category and category != "all":
        flt["category"] = category
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        flt["$or"] = [{"name": rx}, {"city": rx}, {"bio": rx}]
    items = await db.specialists.find(flt, {"_id": 0, "verification_document": 0, "document_number": 0}) \
        .sort([("verified", -1), ("rating_avg", -1)]).to_list(200)
    for it in items:
        it["membership_active"] = True
    return items


@api.get("/specialists/me")
async def my_specialist(request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not a specialist")
    return await specialist_out(s)


@api.get("/specialists/{sid}")
async def get_specialist(sid: str, request: Request):
    await current_user(request)
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Not found")
    return await specialist_out(s)


@api.post("/specialists/me/portfolio")
async def add_portfolio(body: PortfolioIn, request: Request):
    user = await current_user(request)
    s = await db.specialists.find_one({"user_id": user["user_id"]})
    if not s:
        raise HTTPException(404, "Not a specialist")
    item = {"item_id": new_id("pf"), "image": body.image, "caption": body.caption, "created_at": iso(now())}
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
        "verification_status": "verified", "verified": True, "verified_at": iso(now())}})
    return {"verified": True, "verification_status": "verified"}


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
    review = {"review_id": new_id("rev"), "specialist_id": sid, "user_id": user["user_id"], "user_name": user["name"],
              "user_picture": user.get("picture"), "rating": body.rating, "comment": body.comment.strip(),
              "recommend": body.recommend, "created_at": iso(now())}
    await db.reviews.update_one({"specialist_id": sid, "user_id": user["user_id"]}, {"$set": review}, upsert=True)
    all_r = await db.reviews.find({"specialist_id": sid}, {"_id": 0, "rating": 1, "recommend": 1}).to_list(10000)
    avg = round(sum(r["rating"] for r in all_r) / len(all_r), 1)
    await db.specialists.update_one({"specialist_id": sid}, {"$set": {
        "rating_avg": avg, "reviews_count": len(all_r), "recommend_count": sum(1 for r in all_r if r.get("recommend"))}})
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


class CheckoutIn(BaseModel):
    plan: str
    origin_url: str


class RCSyncIn(BaseModel):
    plan: str
    expiration_date: Optional[str] = None


def stripe_client(request: Request, origin: Optional[str] = None) -> StripeCheckout:
    host = (origin or str(request.base_url)).rstrip("/")
    return StripeCheckout(api_key=os.environ["STRIPE_API_KEY"], webhook_url=f"{host}/api/webhook/stripe")


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


@api.post("/membership/checkout")
async def membership_checkout(body: CheckoutIn, request: Request):
    user = await current_user(request)
    if body.plan not in PLANS:
        raise HTTPException(400, "Invalid plan")
    if not await db.specialists.find_one({"user_id": user["user_id"]}):
        raise HTTPException(400, "Create your specialist profile first")
    origin = body.origin_url.rstrip("/")
    amount = PLANS[body.plan]["amount"]
    sc = stripe_client(request, origin)
    session = await sc.create_checkout_session(CheckoutSessionRequest(
        amount=amount + 0.004,  # library truncates int(amount*100); offset avoids 19.99 -> 1998 float error
        success_url=f"{origin}/membership?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/membership",
        metadata={"user_id": user["user_id"], "plan": body.plan, "type": "specialist_membership"}))
    await db.payment_transactions.insert_one({
        "session_id": session.session_id, "user_id": user["user_id"], "email": user["email"], "plan": body.plan,
        "amount": amount, "currency": "eur", "payment_status": "initiated", "status": "open", "processed": False,
        "created_at": iso(now())})
    return {"url": session.url, "session_id": session.session_id}


async def process_paid_session(session_id: str, payment_status: str, status: str):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        return None
    await db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"payment_status": payment_status, "status": status}})
    if payment_status == "paid":
        res = await db.payment_transactions.update_one({"session_id": session_id, "processed": False}, {"$set": {"processed": True}})
        if res.modified_count == 1:
            await activate_membership(tx["user_id"], tx["plan"], "stripe")
    return tx


@api.get("/membership/checkout/status/{session_id}")
async def membership_status(session_id: str, request: Request):
    user = await current_user(request)
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx or tx["user_id"] != user["user_id"]:
        raise HTTPException(404, "Session not found")
    st = await stripe_client(request).get_checkout_status(session_id)
    await process_paid_session(session_id, st.payment_status, st.status)
    return {"payment_status": st.payment_status, "status": st.status, "membership": await membership_payload(user["user_id"])}


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    try:
        ev = await stripe_client(request).handle_webhook(body, request.headers.get("Stripe-Signature"))
    except Exception as e:
        logger.warning("stripe webhook error: %s", e)
        raise HTTPException(400, "Invalid webhook")
    if ev.session_id:
        await process_paid_session(ev.session_id, ev.payment_status, "complete" if ev.payment_status == "paid" else "open")
    return {"received": True}


@api.post("/membership/revenuecat-sync")
async def revenuecat_sync(body: RCSyncIn, request: Request):
    """Mirror the in-app (RevenueCat) entitlement expiry so the specialist is listed for other users."""
    user = await current_user(request)
    if body.plan not in PLANS:
        raise HTTPException(400, "Invalid plan")
    exp = None
    if body.expiration_date:
        exp = datetime.fromisoformat(body.expiration_date.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    else:
        exp = now() + timedelta(days=PLANS[body.plan]["days"])
    await activate_membership(user["user_id"], body.plan, "revenuecat", exp)
    return await membership_payload(user["user_id"])


# ---------------- Seed ----------------
SEED = [
    {"name": "Marco Rossi", "category": "plumbing", "city": "Milano", "years_experience": 12, "hourly_rate": "35 EUR/h",
     "bio": "Idraulico certificato. Perdite, scarichi, caldaie e bagni completi. / Fontanero certificado.",
     "avatar": "https://images.pexels.com/photos/8487397/pexels-photo-8487397.jpeg?auto=compress&cs=tinysrgb&w=600",
     "portfolio": ["https://images.unsplash.com/photo-1607472586893-edb57bdc0e39?w=800&q=80",
                   "https://images.unsplash.com/photo-1585704032915-c3400ca199e7?w=800&q=80"],
     "rating": 4.9, "reviews": 3, "verified": True},
    {"name": "Lucía Fernández", "category": "electrical", "city": "Madrid", "years_experience": 8, "hourly_rate": "30 EUR/h",
     "bio": "Electricista autorizada. Cuadros eléctricos, enchufes, iluminación LED y averías urgentes.",
     "avatar": "https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=600&q=80",
     "portfolio": ["https://images.pexels.com/photos/19841115/pexels-photo-19841115.jpeg?auto=compress&cs=tinysrgb&w=800",
                   "https://images.unsplash.com/photo-1558002038-1055907df827?w=800&q=80"],
     "rating": 4.8, "reviews": 2, "verified": True},
    {"name": "Giovanni Bianchi", "category": "carpentry", "city": "Roma", "years_experience": 15, "hourly_rate": "32 EUR/h",
     "bio": "Falegname: porte, finestre, mobili su misura e parquet.",
     "avatar": "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=600&q=80",
     "portfolio": ["https://images.unsplash.com/photo-1588854337236-6889d631faa8?w=800&q=80"],
     "rating": 4.6, "reviews": 2, "verified": False},
    {"name": "Carlos Méndez", "category": "painting", "city": "Barcelona", "years_experience": 6, "hourly_rate": "25 EUR/h",
     "bio": "Pintor profesional. Humedades, grietas, pintura interior y exterior.",
     "avatar": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=600&q=80",
     "portfolio": ["https://images.unsplash.com/photo-1562259949-e8e7689d7828?w=800&q=80"],
     "rating": 4.7, "reviews": 2, "verified": True},
]


async def seed():
    if await db.specialists.count_documents({"seed": True}) > 0:
        return
    pw = bcrypt.hashpw(b"specialist123", bcrypt.gensalt()).decode()
    for i, s in enumerate(SEED):
        uid, sid = new_id("user"), new_id("spec")
        email = f"specialist{i + 1}@fixai.app"
        await db.users.update_one({"email": email}, {"$setOnInsert": {
            "user_id": uid, "email": email, "name": s["name"], "picture": s["avatar"], "role": "specialist",
            "specialist_id": sid, "password_hash": pw, "created_at": iso(now())}}, upsert=True)
        u = await db.users.find_one({"email": email})
        uid, sid = u["user_id"], u["specialist_id"]
        await db.specialists.insert_one({
            "specialist_id": sid, "user_id": uid, "name": s["name"], "category": s["category"], "bio": s["bio"],
            "phone": f"+3933312345{i}", "whatsapp": f"+3933312345{i}", "city": s["city"],
            "years_experience": s["years_experience"], "hourly_rate": s["hourly_rate"], "avatar": s["avatar"],
            "portfolio": [{"item_id": new_id("pf"), "image": p, "caption": "", "created_at": iso(now())} for p in s["portfolio"]],
            "verified": s["verified"], "verification_status": "verified" if s["verified"] else "none",
            "rating_avg": s["rating"], "reviews_count": s["reviews"], "recommend_count": s["reviews"],
            "jobs_completed": s["years_experience"] * 10, "seed": True, "created_at": iso(now())})
        names = ["Anna", "Pedro", "Sofia"]
        for j in range(s["reviews"]):
            await db.reviews.insert_one({"review_id": new_id("rev"), "specialist_id": sid, "user_id": f"seed_{j}",
                                         "user_name": names[j], "user_picture": None, "rating": 5 if j == 0 else 4,
                                         "comment": ["Lavoro perfetto, puntuale e pulito!", "Muy profesional, lo recomiendo.",
                                                     "Ottimo rapporto qualità/prezzo."][j],
                                         "recommend": True, "created_at": iso(now())})


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.specialists.create_index("specialist_id", unique=True)
    await db.messages.create_index("conversation_id")
    await db.files.create_index("storage_path")
    await seed()
    await db.specialists.update_many({"seed": True, "membership_expires_at": {"$exists": False}},
                                     {"$set": {"membership_expires_at": iso(now() + timedelta(days=3650)), "membership_plan": "yearly"}})
    await db.payment_transactions.create_index("session_id", unique=True)
    try:
        init_storage()
    except Exception as e:
        logger.error("Storage init failed: %s", e)


app.include_router(api)

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
