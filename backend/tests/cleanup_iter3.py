"""Borra SOLO las cuentas de prueba (test_*@fixai.app) y sus datos.
Usar solo con la base de datos de DESARROLLO, nunca con la real."""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
TEST_PATTERN = r"^test_.*@fixai\.app$"


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    print("Base de datos:", os.environ["DB_NAME"])
    users = await db.users.find(
        {"email": {"$regex": TEST_PATTERN, "$options": "i"}},
        {"_id": 0, "user_id": 1, "email": 1},
    ).to_list(10000)
    if not users:
        print("No hay cuentas de prueba. No se borra nada.")
        return
    print("Se borrarán estas cuentas:", [u["email"] for u in users])
    if input("Escribe BORRAR para continuar: ").strip() != "BORRAR":
        print("Cancelado.")
        return
    uids = [u["user_id"] for u in users]
    specs = await db.specialists.find({"user_id": {"$in": uids}}, {"_id": 0, "specialist_id": 1}).to_list(10000)
    sids = [s["specialist_id"] for s in specs]
    convs = await db.conversations.find(
        {"$or": [{"client_id": {"$in": uids}}, {"specialist_id": {"$in": sids}}]},
        {"_id": 0, "conversation_id": 1},
    ).to_list(10000)
    cids = [c["conversation_id"] for c in convs]
    for name in await db.list_collection_names():
        if name == "users":
            q = {"user_id": {"$in": uids}}
        else:
            q = {"$or": [{"user_id": {"$in": uids}}, {"specialist_id": {"$in": sids}},
                         {"client_id": {"$in": uids}}, {"conversation_id": {"$in": cids}},
                         {"sender_id": {"$in": uids}}, {"owner_id": {"$in": uids}}]}
        res = await db[name].delete_many(q)
        if res.deleted_count:
            print(f"{name}: borrados {res.deleted_count}")


asyncio.run(main())