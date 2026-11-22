"""Configuracion, base de datos y utilidades comunes (fechas, ids, oficios, idiomas)."""
import os
import logging
import uuid
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).resolve().parent.parent  # carpeta backend/
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ["JWT_SECRET"]
APP_NAME = os.environ.get("APP_NAME", "behappy")

storage_key = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


CATEGORIES = ["plumbing", "electrical", "hvac", "masonry", "carpentry"]
SUBTRADES = {"masonry": ["muratura", "piastrellista", "pintura", "suelos", "tejados"],
             "carpentry": ["puertas", "ventanas", "parquet", "cerrajeria", "cristales"]}
LANG_NAME = {"es": "Spanish", "it": "Italian", "en": "English"}


def now():
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
