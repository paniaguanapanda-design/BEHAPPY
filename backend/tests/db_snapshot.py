# DB snapshot helper: prints collection counts + users/specialists (for seed-removal & cleanup verification)
import os, sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
for c in sorted(db.list_collection_names()):
    print(c, db[c].count_documents({}))
print("USERS:", [u.get("email") for u in db.users.find({}, {"email": 1})])
print("SPECIALISTS:", [(s.get("name"), s.get("user_id"), s.get("membership_expires_at")) for s in db.specialists.find({})])
