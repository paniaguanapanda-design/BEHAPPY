"""Delete all test_*@fixai.app accounts and their data (keeps owner account). Run from /app/backend."""
import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
OWNER = "paniaguanapan.d.a@gmail.com"


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    users = await db.users.find({"email": {"$ne": OWNER}}, {"_id": 0, "user_id": 1, "email": 1}).to_list(10000)
    uids = [u["user_id"] for u in users]
    print("Deleting users:", [u["email"] for u in users])
    specs = await db.specialists.find({"user_id": {"$in": uids}}, {"_id": 0, "specialist_id": 1}).to_list(10000)
    sids = [s["specialist_id"] for s in specs]
    convs = await db.conversations.find({"$or": [{"client_id": {"$in": uids}}, {"specialist_id": {"$in": sids}}]}, {"_id": 0, "conversation_id": 1}).to_list(10000)
    cids = [c["conversation_id"] for c in convs]
    for name in await db.list_collection_names():
        col = db[name]
        q = {"$or": [{"user_id": {"$in": uids}}, {"specialist_id": {"$in": sids}}, {"client_id": {"$in": uids}},
                     {"conversation_id": {"$in": cids}}, {"sender_id": {"$in": uids}}, {"owner_id": {"$in": uids}}]}
        if name == "users":
            q = {"user_id": {"$in": uids}}
        res = await col.delete_many(q)
        if res.deleted_count:
            print(f"{name}: deleted {res.deleted_count}")
    for name in await db.list_collection_names():
        print(name, await db[name].count_documents({}))
    for d in ["/app/backend/uploads"]:
        for uid in uids:
            p = os.path.join(d, uid)
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
                print("removed", p)


asyncio.run(main())
