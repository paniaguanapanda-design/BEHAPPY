"""Reportes de contenido y bloqueos entre usuarios."""
from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field
from . import pro, stores
from .core import db, iso, logger, new_id, now
from .security import current_user, rate_limit


router = APIRouter(prefix="/api")


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


@router.post("/reports")
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
        await stores.store_reported(body.target_id, user["user_id"])
    if body.target_type == "specialist":
        await pro.specialist_reported(body.target_id, user["user_id"], body.reason, body.details.strip())
    return {"ok": True}


@router.post("/blocks")
async def block_user(body: BlockIn, request: Request):
    user = await current_user(request)
    if body.user_id == user["user_id"]:
        raise HTTPException(400, "Invalid user")
    if not await db.users.find_one({"user_id": body.user_id}, {"_id": 1}):
        raise HTTPException(404, "User not found")
    await db.blocks.update_one({"user_id": user["user_id"], "blocked_id": body.user_id},
                               {"$set": {"created_at": iso(now())}}, upsert=True)
    return {"ok": True}


@router.delete("/blocks/{uid}")
async def unblock_user(uid: str, request: Request):
    user = await current_user(request)
    await db.blocks.delete_one({"user_id": user["user_id"], "blocked_id": uid})
    return {"ok": True}


@router.get("/blocks")
async def list_blocks(request: Request):
    user = await current_user(request)
    return await db.blocks.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(500)
