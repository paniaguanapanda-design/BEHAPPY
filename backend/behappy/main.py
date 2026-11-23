import os
import asyncio
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from . import admin, ai, app_reviews, auth, chat, diagnosis, files, geo, marketplace, membership, moderation, pro, push, specialists, stats, storage, stores, web
from .core import CATEGORIES, client, db, logger


app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


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
    asyncio.create_task(web.ensure_stripe_webhook())
    await db.stores.create_index([("location", "2dsphere")])
    await db.specialists.create_index("zone.province.code")
    await db.activity_days.create_index("day")
    await db.activity_days.create_index("at", expireAfterSeconds=400 * 86400)  # panel admin: 400 dias
    await db.stores.create_index([("piva", 1), ("cap", 1)])
    await db.specialists.update_many({"document_number": {"$exists": True}}, {"$unset": {"document_number": ""}})
    try:
        await db[membership.PREREG].create_index("email", unique=True, name="email_unico")
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
        storage.init_storage()
    except Exception as e:
        logger.error("Storage init failed: %s", e)


app.include_router(ai.router)
app.include_router(auth.router)
app.include_router(files.router)
app.include_router(diagnosis.router)
app.include_router(specialists.router)
app.include_router(moderation.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(marketplace.router)
app.include_router(membership.router)
app.include_router(stores.router)
app.include_router(push.router)
app.include_router(geo.router)
app.include_router(pro.router)
app.include_router(web.router)
app.include_router(app_reviews.router)
app.include_router(stats.router)

_cors = [o.strip() for o in os.environ.get("CORS_ORIGINS", "https://www.be-happyapp.com").split(",") if o.strip()]
# The installable web app calls the server directly (through Cloudflare), so each visitor keeps their own IP for the
# per-IP limits; going through the Vercel proxy would put every web user behind the same address.
if "https://app.be-happyapp.com" not in _cors:
    _cors.append("https://app.be-happyapp.com")
app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=_cors, allow_methods=["*"], allow_headers=["*"])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
