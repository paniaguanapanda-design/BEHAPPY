"""Conversaciones y mensajes entre cliente y especialista."""
import asyncio
from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field
from typing import Optional
from . import geo, moderation, pro, specialists
from .core import CATEGORIES, db, iso, new_id, now
from .security import current_user, rate_limit


router = APIRouter(prefix="/api")


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
    asyncio.create_task(pro.after_message(conv, sender, msg))
    return msg


@router.post("/conversations")
async def start_conversation(body: ConversationIn, request: Request):
    user = await current_user(request)
    spec = await db.specialists.find_one({"specialist_id": body.specialist_id}, {"_id": 0})
    if not spec:
        raise HTTPException(404, "Specialist not found")
    if await moderation.blocked_between(user["user_id"], spec["user_id"]):
        raise HTTPException(403, "No puedes contactar a este usuario")
    # Cualquier cliente de la misma provincia puede escribir; el especialista necesita membresía para responder.
    # Las conversaciones que ya existen se respetan.
    exists = await db.conversations.find_one({"client_id": user["user_id"], "specialist_id": spec["specialist_id"]}, {"_id": 1})
    if not exists and user["user_id"] != spec["user_id"]:
        here = geo.zone_point(user.get("zone"))
        if not here:
            raise HTTPException(409, "Elige primero tu zona")
        if not geo.in_reach(here, spec):
            raise HTTPException(403, "Este especialista no trabaja en tu zona")
    conv = await get_or_create_conversation(user, spec)
    if body.diagnosis_id:
        d = await db.diagnoses.find_one({"diagnosis_id": body.diagnosis_id, "user_id": user["user_id"]}, {"_id": 0})
        if d:
            conv["diagnosis"] = pro.diagnosis_summary(d)
            await db.conversations.update_one({"conversation_id": conv["conversation_id"]}, {"$set": {"diagnosis": conv["diagnosis"]}})
    return conv


@router.get("/conversations")
async def list_conversations(request: Request):
    user = await current_user(request)
    hidden = await moderation.hidden_user_ids(user["user_id"])
    convs = await db.conversations.find({"participants": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(100)
    return [c for c in convs if not any(p in hidden for p in c["participants"] if p != user["user_id"])]


async def get_conv_for(cid: str, user: dict) -> dict:
    conv = await db.conversations.find_one({"conversation_id": cid}, {"_id": 0})
    if not conv or user["user_id"] not in conv["participants"]:
        raise HTTPException(404, "Conversation not found")
    return conv


@router.get("/conversations/{cid}")
async def get_conversation(cid: str, request: Request):
    user = await current_user(request)
    conv = await get_conv_for(cid, user)
    spec = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0, "membership_expires_at": 1,
                                                                                     "avatar": 1}) or {}
    conv["specialist_can_reply"] = specialists.membership_active(spec)
    conv["specialist_avatar"] = spec.get("avatar") or conv.get("specialist_avatar")
    conv["review_prompt"] = await pro.review_prompt_for(conv, user)
    d = conv.get("diagnosis")
    if d and d.get("materials") and d.get("category") in CATEGORIES:
        # Ferreterias cerca: del cliente (su ultima posicion) o de la zona del especialista
        if user["user_id"] == conv["client_id"] and user.get("last_loc"):
            center = (user["last_loc"]["lat"], user["last_loc"]["lng"])
        else:
            full = await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0, "zone": 1}) or {}
            center = pro.spec_zone(full)[0]
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


@router.get("/conversations/{cid}/messages")
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


@router.post("/conversations/{cid}/messages")
async def send_message(cid: str, body: MessageIn, request: Request):
    user = await current_user(request)
    rate_limit(f"msg:{user['user_id']}", 30, 60)
    conv = await get_conv_for(cid, user)
    other_id = [p for p in conv["participants"] if p != user["user_id"]][0]
    if await moderation.blocked_between(user["user_id"], other_id):
        raise HTTPException(403, "No puedes enviar mensajes a este usuario")
    if not body.text.strip():
        raise HTTPException(400, "Empty message")
    if user["user_id"] == conv.get("specialist_user_id"):
        await specialists.require_active_specialist(await db.specialists.find_one({"specialist_id": conv["specialist_id"]}, {"_id": 0}) or {})
    return await push_message(conv, user, body.text.strip())
