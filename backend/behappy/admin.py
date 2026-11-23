"""Moderacion manual del administrador (verificaciones, reportes, referidos)."""
import os
import base64
from fastapi import HTTPException, Header, APIRouter
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from typing import Optional
from datetime import datetime, timezone, timedelta
from . import storage
from .core import db, iso, now


router = APIRouter(prefix="/api")


# ---------------- Admin (moderacion manual) ----------------
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


def require_admin(token: Optional[str]):
    import hmac
    if not ADMIN_TOKEN or not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(403, "Forbidden")


@router.get("/admin/verifications")
async def admin_verifications(x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    items = await db.specialists.find({"verification_status": "in_review"},
                                      {"_id": 0, "specialist_id": 1, "name": 1, "user_id": 1,
                                       "verification_document": 1, "submitted_at": 1}).to_list(100)
    for it in items:
        doc = it.get("verification_document") or ""
        it["verification_document"] = (doc[:80] + "...") if len(doc) > 80 else doc
    return items


@router.get("/admin/verifications/{sid}/document")
async def admin_verification_document(sid: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0, "verification_document": 1})
    if not s or not s.get("verification_document"):
        raise HTTPException(404, "No document")
    doc = s["verification_document"]
    if doc.startswith("data:"):
        head, _, b64 = doc.partition(",")
        ct = head[5:].split(";")[0] or "image/jpeg"
        return Response(content=base64.b64decode(b64), media_type=ct)
    data, ct = await run_in_threadpool(storage.get_object, doc)
    return Response(content=data, media_type=ct)


@router.post("/admin/verifications/{sid}/{decision}")
async def admin_decide_verification(sid: str, decision: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve or reject")
    if decision == "approve":
        upd = {"verified": True, "verification_status": "verified", "verified_by": "admin", "verified_at": iso(now())}
    else:
        upd = {"verified": False, "verification_status": "rejected"}
    r = await db.specialists.update_one({"specialist_id": sid}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Specialist not found")
    return {"ok": True, "status": upd["verification_status"]}


@router.get("/admin/reports")
async def admin_reports(x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    return await db.reports.find({"status": "open"}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/admin/referidos")
async def admin_referidos(desde: Optional[str] = None, hasta: Optional[str] = None,
                          x_admin_token: Optional[str] = Header(None)):
    """Por cada codigo: cuantas cuentas nuevas trajo y cuantas estan activas (al menos 1 diagnostico).
    desde/hasta (AAAA-MM-DD, opcionales) filtran por la fecha de registro."""
    require_admin(x_admin_token)
    q: dict = {"referido_por": {"$type": "string"}}
    rango = {}
    for key, val, op in (("desde", desde, "$gte"), ("hasta", hasta, "$lt")):
        if val:
            try:
                d = datetime.strptime(val, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(400, f"{key} debe ser AAAA-MM-DD")
            rango[op] = iso(d + timedelta(days=1) if key == "hasta" else d)
    if rango:
        q["referido_en"] = rango
    users = await db.users.find(q, {"_id": 0, "user_id": 1, "referido_por": 1}).to_list(100000)
    ids = [u["user_id"] for u in users]
    # Solo cuentan diagnosticos terminados (no los que siguen "processing" ni los "failed")
    activos = set(await db.diagnoses.distinct(
        "user_id", {"user_id": {"$in": ids}, "status": {"$nin": ["processing", "failed"]}})) if ids else set()
    por_codigo: dict = {}
    for u in users:
        r = por_codigo.setdefault(u["referido_por"], {"codigo": u["referido_por"], "registrados": 0, "activos": 0})
        r["registrados"] += 1
        r["activos"] += u["user_id"] in activos
    filas = sorted(por_codigo.values(), key=lambda r: (-r["activos"], -r["registrados"], r["codigo"]))
    return {"desde": desde, "hasta": hasta, "codigos": filas,
            "total_registrados": len(users), "total_activos": len(activos)}


@router.post("/admin/reports/{rid}/resolve")
async def admin_resolve_report(rid: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    r = await db.reports.update_one({"report_id": rid}, {"$set": {"status": "resolved", "resolved_at": iso(now())}})
    if not r.matched_count:
        raise HTTPException(404, "Report not found")
    return {"ok": True}
