"""Almacenamiento de fotos y documentos: carpeta local en desarrollo, S3 / Cloudflare R2 en produccion."""
import os
import uuid
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from pathlib import Path
from .core import APP_NAME, db, iso, logger, now


# ---------------- Storage ----------------
# En desarrollo guarda las fotos en backend/uploads_local.
# En produccion, si defines S3_BUCKET (y sus claves), usa S3 o Cloudflare R2.
LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads_local"
S3_BUCKET = os.environ.get("S3_BUCKET")
_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
            region_name=os.environ.get("S3_REGION", "auto"),
        )
    return _s3


# En Render el disco se borra en cada despliegue: alli las fotos solo pueden ir a S3 / Cloudflare R2.
ON_RENDER = bool(os.environ.get("RENDER"))


def init_storage():
    if S3_BUCKET:
        _s3_client()
    elif ON_RENDER:
        logger.critical("Falta S3_BUCKET en Render: las subidas de fotos quedan desactivadas")
    else:
        LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if not S3_BUCKET and ON_RENDER:
        raise HTTPException(503, "Almacenamiento de fotos no configurado")
    if S3_BUCKET:
        _s3_client().put_object(Bucket=S3_BUCKET, Key=path, Body=data, ContentType=content_type)
    else:
        target = (LOCAL_UPLOAD_DIR / path).resolve()
        if LOCAL_UPLOAD_DIR.resolve() not in target.parents:
            raise HTTPException(400, "Invalid path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {"path": path}


def get_object(path: str):
    if S3_BUCKET:
        obj = _s3_client().get_object(Bucket=S3_BUCKET, Key=path)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
    target = (LOCAL_UPLOAD_DIR / path).resolve()
    if LOCAL_UPLOAD_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "File not found")
    return target.read_bytes(), "application/octet-stream"
def delete_object(path: str) -> None:
    if S3_BUCKET:
        _s3_client().delete_object(Bucket=S3_BUCKET, Key=path)
    else:
        target = (LOCAL_UPLOAD_DIR / path).resolve()
        if LOCAL_UPLOAD_DIR.resolve() in target.parents and target.is_file():
            target.unlink()
            
            
async def store_bytes(user_id: str, data: bytes, content_type: str, ext: str) -> str:
    path = f"{APP_NAME}/uploads/{user_id}/{uuid.uuid4().hex}.{ext}"
    result = await run_in_threadpool(put_object, path, data, content_type)
    stored = result.get("path", path)
    await db.files.insert_one({"storage_path": stored, "owner_id": user_id, "content_type": content_type,
                               "is_deleted": False, "created_at": iso(now())})
    return stored
