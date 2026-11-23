"""Solicitudes de trabajo, tablon de solicitudes y presupuestos."""
import io
import uuid
from fastapi import HTTPException, Request, UploadFile, File, APIRouter
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from typing import List, Optional
from . import chat, geo, moderation, pro, push, specialists, storage
from .core import APP_NAME, CATEGORIES, db, iso, new_id, now
from .security import current_user, rate_limit


router = APIRouter(prefix="/api")


# ---------------- Service requests ----------------
class RequestIn(BaseModel):
    specialist_id: str
    description: str = Field(max_length=2000)
    address: str = Field(default="", max_length=300)
    preferred_date: str = Field(default="", max_length=50)
    diagnosis_id: Optional[str] = None


class RequestStatusIn(BaseModel):
    status: str


class QuoteIn(BaseModel):
    price: float = Field(gt=0, lt=1_000_000)
    description: str = Field(max_length=1000)
    estimated_time: str = Field(default="", max_length=50)


@router.post("/requests")
async def create_request(body: RequestIn, request: Request):
    user = await current_user(request)
    rate_limit(f"req:{user['user_id']}", 10, 3600)
    spec = await db.specialists.find_one({"specialist_id": body.specialist_id}, {"_id": 0})
    if not spec:
        raise HTTPException(404, "Specialist not found")
    if not body.description.strip():
        raise HTTPException(400, "Description required")
    if await moderation.blocked_between(user["user_id"], spec["user_id"]):
        raise HTTPException(403, "No puedes contactar a este usuario")
    diag_title = None
    if body.diagnosis_id:
        d = await db.diagnoses.find_one({"diagnosis_id": body.diagnosis_id, "user_id": user["user_id"]}, {"_id": 0, "title_es": 1})
        diag_title = d.get("title_es") if d else None
    conv = await chat.get_or_create_conversation(user, spec)
    req = {"request_id": new_id("req"), "client_id": user["user_id"], "client_name": user["name"],
           "specialist_id": spec["specialist_id"], "specialist_user_id": spec["user_id"], "specialist_name": spec["name"],
           "description": body.description.strip(), "address": body.address, "preferred_date": body.preferred_date,
           "diagnosis_id": body.diagnosis_id, "diagnosis_title": diag_title, "status": "pending",
           "conversation_id": conv["conversation_id"], "created_at": iso(now())}
    await db.service_requests.insert_one(req)
    req.pop("_id", None)
    await chat.push_message(conv, user, f"[REQUEST] {diag_title + ' — ' if diag_title else ''}{req['description']}", kind="request")
    return req


class MarketplaceRequestIn(BaseModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=2000)
    category: str = Field(max_length=30)
    photos: List[str] = Field(default_factory=list, max_length=4)


@router.post("/requests/photos")
async def upload_marketplace_photo(request: Request, file: UploadFile = File(...)):
    user = await current_user(request)
    rate_limit(f"request-photo:{user['user_id']}", 20, 3600)
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    try:
        image = Image.open(io.BytesIO(data))
        if (image.format or "").upper() not in {"JPEG", "PNG", "WEBP"}:
            raise HTTPException(400, "Solo se aceptan fotos JPEG, PNG o WEBP")
        if image.width * image.height > 40_000_000:
            raise HTTPException(400, "Imagen demasiado grande")
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1600, 1600))
        clean = io.BytesIO()
        image.save(clean, "JPEG", quality=82, optimize=True)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "El archivo no es una imagen valida")
    path = f"{APP_NAME}/request-photos/{uuid.uuid4().hex}.jpg"
    await run_in_threadpool(storage.put_object, path, clean.getvalue(), "image/jpeg")
    await db.files.insert_one({"storage_path": path, "owner_id": user["user_id"], "content_type": "image/jpeg",
                               "is_deleted": False, "created_at": iso(now())})
    return {"path": path}


def marketplace_request_matches(spec: dict, req: dict) -> tuple[bool, float]:
    if req.get("status") != "open" or req.get("category") not in (spec.get("categories") or []):
        return False, 0
    request_zone = req.get("zone") or {}
    if not geo.zone_point(spec.get("zone")):
        return False, 0
    point = request_zone.get("point") or {}
    coords = point.get("coordinates") or []
    if len(coords) != 2:
        return False, 0
    center, radius = pro.spec_zone(spec)
    distance = pro.km_between((coords[1], coords[0]), center)
    return distance <= radius, distance


async def can_view_marketplace_photo(path: str, user: dict) -> bool:
    req = await db.service_requests.find_one({"broadcast": True, "photos": path}, {"_id": 0})
    if not req:
        return False
    if req.get("client_id") == user.get("user_id"):
        return True
    if req.get("status") == "open" and user.get("specialist_id"):
        spec = await db.specialists.find_one({"specialist_id": user["specialist_id"], "user_id": user["user_id"]}, {"_id": 0})
        if spec and specialists.membership_active(spec) and not spec.get("hidden") and marketplace_request_matches(spec, req)[0]:
            return True
    accepted = await db.quotes.find_one({"request_id": req["request_id"], "client_id": req["client_id"],
                                         "status": "accepted", "specialist_user_id": user["user_id"]}, {"_id": 1})
    return bool(accepted)


def public_marketplace_request(req: dict, distance: Optional[float] = None) -> dict:
    """Only fields needed to quote; never return client identity or exact location."""
    out = {
        "request_id": req["request_id"],
        "title": req["title"],
        "description": req["description"],
        "category": req["category"],
        "photos": req.get("photos") or [],
        "city": req.get("city") or (geo.prov_code(req.get("zone")) or ""),
        "status": req["status"],
        "created_at": req["created_at"],
    }
    if distance is not None:
        out["distance_km"] = round(distance)
    return out


@router.post("/requests/board")
async def publish_marketplace_request(body: MarketplaceRequestIn, request: Request):
    user = await current_user(request)
    if user.get("specialist_id"):
        raise HTTPException(403, "Solo los clientes pueden publicar solicitudes")
    title, description = body.title.strip(), body.description.strip()
    if not title or not description:
        raise HTTPException(400, "Title and description required")
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Invalid category")
    if len(body.photos) > 4 or len(set(body.photos)) != len(body.photos):
        raise HTTPException(400, "Add at most 4 unique photos")
    zone = user.get("zone") or {}
    if zone.get("lat") is None or zone.get("lng") is None:
        raise HTTPException(409, "Elige primero tu ciudad para publicar una solicitud")
    rate_limit(f"board-request:{user['user_id']}", 5, 3600)
    for path in body.photos:
        if not await db.files.find_one({"storage_path": path, "owner_id": user["user_id"], "is_deleted": False}, {"_id": 1}):
            raise HTTPException(400, "Una foto no pertenece a tu cuenta")
    request_id = new_id("req")
    city = await geo.reverse_place(zone["lat"], zone["lng"]) or (zone.get("province") or {}).get("name", "")
    req = {
        "request_id": request_id,
        "broadcast": True,
        "client_id": user["user_id"],
        "title": title,
        "description": description,
        "category": body.category,
        "photos": body.photos,
        "city": city,
        "zone": {"province": zone.get("province") or {}, "point": {
            "type": "Point", "coordinates": [zone["lng"], zone["lat"]]}},
        "status": "open",
        "created_at": iso(now()),
        "updated_at": iso(now()),
    }
    await db.service_requests.insert_one(req)
    if body.photos:
        await db.files.update_many({"storage_path": {"$in": body.photos}, "owner_id": user["user_id"]},
                                   {"$set": {"marketplace_request_id": request_id}})
    return public_marketplace_request(req)


@router.get("/requests/board")
async def list_marketplace_requests(request: Request):
    user = await current_user(request)
    if user.get("specialist_id"):
        spec = await db.specialists.find_one({"specialist_id": user["specialist_id"], "user_id": user["user_id"]}, {"_id": 0})
        if not spec or spec.get("hidden") or not specialists.membership_active(spec):
            return []
        requests = await db.service_requests.find({"broadcast": True, "status": "open",
                                                   "category": {"$in": spec.get("categories") or []}},
                                                  {"_id": 0}).sort("created_at", -1).to_list(200)
        out = []
        for req in requests:
            matches, distance = marketplace_request_matches(spec, req)
            if not matches or await moderation.blocked_between(user["user_id"], req["client_id"]):
                continue
            item = public_marketplace_request(req, distance)
            item["my_quote"] = await db.quotes.find_one(
                {"request_id": req["request_id"], "specialist_id": spec["specialist_id"]},
                {"_id": 0, "quote_id": 1, "price": 1, "status": 1},
            )
            item["quotes_count"] = await db.quotes.count_documents({"request_id": req["request_id"]})
            out.append(item)
        return out
    requests = await db.service_requests.find({"broadcast": True, "client_id": user["user_id"]},
                                               {"_id": 0}).sort("created_at", -1).to_list(100)
    quotes = await db.quotes.find({"request_id": {"$in": [r["request_id"] for r in requests]}},
                                  {"_id": 0, "quote_id": 1, "request_id": 1, "specialist_id": 1, "specialist_name": 1,
                                   "price": 1, "currency": 1, "description": 1, "estimated_time": 1, "status": 1,
                                   "created_at": 1, "conversation_id": 1}).sort("created_at", -1).to_list(500)
    return [{**public_marketplace_request(req), "quotes": [q for q in quotes if q["request_id"] == req["request_id"]]}
            for req in requests]


@router.post("/requests/board/{rid}/quotes")
async def quote_marketplace_request(rid: str, body: QuoteIn, request: Request):
    user = await current_user(request)
    spec = await db.specialists.find_one({"user_id": user["user_id"]}, {"_id": 0})
    req = await db.service_requests.find_one({"request_id": rid, "broadcast": True}, {"_id": 0})
    if not spec or not req or not specialists.membership_active(spec) or spec.get("hidden"):
        raise HTTPException(404, "Request not found")
    if not marketplace_request_matches(spec, req)[0]:
        raise HTTPException(404, "Request not found")
    if await moderation.blocked_between(user["user_id"], req["client_id"]):
        raise HTTPException(403, "No puedes responder a esta solicitud")
    if not body.description.strip():
        raise HTTPException(400, "Description required")
    if await db.quotes.find_one({"request_id": rid, "specialist_id": spec["specialist_id"]}, {"_id": 1}):
        raise HTTPException(409, "Ya has enviado un presupuesto para este trabajo")
    quote = {
        "quote_id": new_id("quote"),
        "request_id": rid,
        "marketplace": True,
        "specialist_id": spec["specialist_id"],
        "specialist_user_id": user["user_id"],
        "specialist_name": spec["name"],
        "client_id": req["client_id"],
        "price": round(body.price, 2),
        "currency": "EUR",
        "description": body.description.strip(),
        "estimated_time": body.estimated_time.strip(),
        "status": "pending",
        "created_at": iso(now()),
    }
    await db.quotes.insert_one(quote)
    quote.pop("_id", None)
    await push.send_push(req["client_id"],
                    {"it": "Nuovo preventivo per il tuo lavoro", "es": "Nuevo presupuesto para tu trabajo"},
                    {"it": f"{spec['name']} ti ha inviato un preventivo.",
                     "es": f"{spec['name']} te ha enviado un presupuesto."},
                    {"type": "marketplace_quote", "request_id": rid})
    return quote


@router.get("/requests")
async def list_requests(request: Request):
    user = await current_user(request)
    reqs = await db.service_requests.find({"$or": [{"client_id": user["user_id"]}, {"specialist_user_id": user["user_id"]}]},
                                          {"_id": 0}).sort("created_at", -1).to_list(200)
    quotes = await db.quotes.find({"request_id": {"$in": [r["request_id"] for r in reqs]}}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for r in reqs:
        r["quotes"] = [q for q in quotes if q["request_id"] == r["request_id"]]
    return reqs


@router.patch("/requests/{rid}")
async def update_request(rid: str, body: RequestStatusIn, request: Request):
    user = await current_user(request)
    req = await db.service_requests.find_one({"request_id": rid}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Not found")
    allowed = {"accepted", "rejected", "completed"} if req.get("specialist_user_id") == user["user_id"] else \
        {"cancelled"} if req["client_id"] == user["user_id"] else set()
    if body.status not in allowed:
        raise HTTPException(403, "Not allowed")
    # Solo estos cambios; completada, rechazada y cancelada son finales
    transitions = {"pending": {"accepted", "rejected", "cancelled"}, "open": {"cancelled"},
                   "accepted": {"completed", "cancelled"}}
    if body.status not in transitions.get(req["status"], set()):
        raise HTTPException(409, f"No se puede cambiar de {req['status']} a {body.status}")
    if body.status == "accepted":
        await specialists.require_active_specialist(await db.specialists.find_one({"specialist_id": req["specialist_id"]}, {"_id": 0}))
    res = await db.service_requests.update_one({"request_id": rid, "status": req["status"]},
                                               {"$set": {"status": body.status, "updated_at": iso(now())}})
    if res.modified_count == 0:
        raise HTTPException(409, "La peticion ya cambio de estado")
    if req.get("broadcast") and body.status == "cancelled":
        await db.quotes.update_many(
            {"request_id": rid, "status": "pending"},
            {"$set": {"status": "rejected", "answered_at": iso(now())}},
        )
    if body.status == "completed":
        await db.specialists.update_one({"specialist_id": req["specialist_id"]}, {"$inc": {"jobs_completed": 1}})
    return {**req, "status": body.status}


# ---------------- Quotes (ofertas) ----------------
class QuoteStatusIn(BaseModel):
    status: str


@router.post("/requests/{rid}/quotes")
async def create_quote(rid: str, body: QuoteIn, request: Request):
    user = await current_user(request)
    req = await db.service_requests.find_one({"request_id": rid}, {"_id": 0})
    if not req or req["specialist_user_id"] != user["user_id"]:
        raise HTTPException(404, "Request not found")
    if req["status"] not in ("pending", "accepted"):
        raise HTTPException(400, "Request is closed")
    spec = await db.specialists.find_one({"specialist_id": req["specialist_id"]}, {"_id": 0})
    await specialists.require_active_specialist(spec)
    if not body.description.strip():
        raise HTTPException(400, "Description required")
    quote = {"quote_id": new_id("quote"), "request_id": rid, "conversation_id": req["conversation_id"],
             "specialist_id": req["specialist_id"], "specialist_name": req["specialist_name"], "client_id": req["client_id"],
             "price": round(body.price, 2), "currency": "EUR", "description": body.description.strip(),
             "estimated_time": body.estimated_time, "status": "pending", "created_at": iso(now())}
    await db.quotes.insert_one(quote)
    quote.pop("_id", None)
    conv = await db.conversations.find_one({"conversation_id": req["conversation_id"]}, {"_id": 0})
    await chat.push_message(conv, user, f"[QUOTE] {quote['price']:.2f} EUR — {quote['description']}", kind="quote", quote_id=quote["quote_id"])
    return quote


@router.patch("/quotes/{qid}")
async def update_quote(qid: str, body: QuoteStatusIn, request: Request):
    user = await current_user(request)
    q = await db.quotes.find_one({"quote_id": qid}, {"_id": 0})
    if not q or q["client_id"] != user["user_id"]:
        raise HTTPException(404, "Quote not found")
    if body.status not in ("accepted", "rejected"):
        raise HTTPException(400, "Invalid status")
    if q["status"] != "pending":
        raise HTTPException(400, "Quote already answered")
    if q.get("marketplace"):
        req = await db.service_requests.find_one({"request_id": q["request_id"], "broadcast": True,
                                                  "client_id": user["user_id"]}, {"_id": 0})
        if not req:
            raise HTTPException(404, "Request not found")
        if body.status == "accepted":
            spec = await db.specialists.find_one({"specialist_id": q["specialist_id"], "user_id": q["specialist_user_id"]},
                                                 {"_id": 0})
            if not spec:
                raise HTTPException(409, "El especialista ya no está disponible")
            claimed = await db.service_requests.update_one(
                {"request_id": req["request_id"], "status": "open"},
                {"$set": {"status": "accepted", "accepted_quote_id": qid, "agreed_price": q["price"],
                          "updated_at": iso(now())}},
            )
            if claimed.modified_count == 0:
                raise HTTPException(409, "La solicitud ya está cerrada o tiene otro presupuesto aceptado")
            conv = await chat.get_or_create_conversation(user, spec)
            await db.quotes.update_one({"quote_id": qid, "status": "pending"},
                                       {"$set": {"status": "accepted", "answered_at": iso(now()),
                                                 "conversation_id": conv["conversation_id"]}})
            await db.quotes.update_many({"request_id": q["request_id"], "quote_id": {"$ne": qid}, "status": "pending"},
                                        {"$set": {"status": "rejected", "answered_at": iso(now())}})
            q["conversation_id"] = conv["conversation_id"]
            q["status"] = "accepted"
            await chat.push_message(conv, user, f"[QUOTE_ACCEPTED] {q['price']:.2f} EUR", kind="quote", quote_id=qid)
            return {**q, "conversation_id": conv["conversation_id"]}
        await db.quotes.update_one({"quote_id": qid, "status": "pending"},
                                   {"$set": {"status": "rejected", "answered_at": iso(now())}})
        return {**q, "status": "rejected"}
    await db.quotes.update_one({"quote_id": qid}, {"$set": {"status": body.status, "answered_at": iso(now())}})
    if body.status == "accepted":
        await db.quotes.update_many({"request_id": q["request_id"], "quote_id": {"$ne": qid}, "status": "pending"},
                                    {"$set": {"status": "rejected"}})
        await db.service_requests.update_one({"request_id": q["request_id"]},
                                             {"$set": {"status": "accepted", "accepted_quote_id": qid, "agreed_price": q["price"]}})
    conv = await db.conversations.find_one({"conversation_id": q["conversation_id"]}, {"_id": 0})
    await chat.push_message(conv, user, f"[QUOTE_{body.status.upper()}] {q['price']:.2f} EUR")
    return {**q, "status": body.status}
