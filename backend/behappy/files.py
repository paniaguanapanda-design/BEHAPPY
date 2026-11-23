"""Subida y descarga de archivos de los usuarios."""
import io
from fastapi import HTTPException, Request, UploadFile, File, APIRouter
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from PIL import Image
from . import marketplace, storage
from .core import db
from .security import current_user, rate_limit, user_from_token


router = APIRouter(prefix="/api")


# ---------------- Files ----------------
@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    user = await current_user(request)
    rate_limit(f"upload:{user['user_id']}", 30, 60)
    max_bytes = 10 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, "File too large")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        width, height = img.size
        img.verify()
    except Exception:
        raise HTTPException(400, "El archivo no es una imagen valida")
    if width * height > 40_000_000:
        raise HTTPException(400, "Imagen demasiado grande")
    allowed = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
    if fmt not in allowed:
        raise HTTPException(400, "Solo se aceptan fotos JPEG, PNG o WEBP")
    ext, content_type = allowed[fmt]
    path = await storage.store_bytes(user["user_id"], data, content_type, ext)
    return {"path": path}


@router.get("/files/{path:path}")
async def get_file(path: str, request: Request):
    # El token solo se acepta en la cabecera Authorization, nunca en la direccion (se filtraria en registros y capturas)
    auth = request.headers.get("Authorization", "")
    user = await user_from_token(auth[7:] if auth.startswith("Bearer ") else None)
    if not user:
        raise HTTPException(401, "Not authenticated")
    rec = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "File not found")
    if rec.get("owner_id") != user["user_id"]:
        in_portfolio = await db.specialists.find_one({"$or": [{"portfolio.image": path}, {"avatar": path}]}, {"_id": 1}) \
            or await db.conversations.find_one({"diagnosis.image_path": path, "participants": user["user_id"]}, {"_id": 1})
        if not in_portfolio and not await marketplace.can_view_marketplace_photo(path, user):
            raise HTTPException(404, "File not found")
    data, ct = await run_in_threadpool(storage.get_object, path)
    return Response(content=data, media_type=rec.get("content_type", ct), headers={"Cache-Control": "private, max-age=86400"})
