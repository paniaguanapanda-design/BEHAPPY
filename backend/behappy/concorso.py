"""Concurso «Natale senza guasti»: boton «Ho risolto!» y lista de participantes."""
import io
from fastapi import HTTPException, Request, Header, APIRouter
from fastapi.responses import Response
from typing import Optional
from datetime import datetime, timezone, timedelta
from . import admin, specialists
from .core import db, iso, now
from .security import current_user


router = APIRouter(prefix="/api")


@router.post("/diagnoses/{diagnosis_id}/resolved")
async def mark_diagnosis_resolved(diagnosis_id: str, request: Request):
    """El usuario indica que reparo el guasto (concorso «Natale senza guasti»). Se guarda la primera vez y la provincia."""
    user = await current_user(request)
    d = await db.diagnoses.find_one({"diagnosis_id": diagnosis_id}, {"_id": 0, "user_id": 1, "status": 1, "resolved_at": 1})
    if not d:
        raise HTTPException(404, "Not found")
    if d["user_id"] != user["user_id"]:
        raise HTTPException(403, "Forbidden")
    if d.get("status") in ("processing", "failed"):
        raise HTTPException(409, "Diagnosis not ready")
    if d.get("resolved_at"):
        return {"ok": True, "resolved_at": d["resolved_at"]}
    at = iso(now())
    await db.diagnoses.update_one({"diagnosis_id": diagnosis_id, "resolved_at": {"$exists": False}},
                                  {"$set": {"resolved_at": at, "resolved_province": await specialists.user_province(user)}})
    return {"ok": True, "resolved_at": at}


@router.get("/admin/concorso")
async def admin_concorso(desde: str, hasta: str, provincia: str = "TO", formato: str = "json",
                         x_admin_token: Optional[str] = Header(None)):
    """Lista de participantes con derecho: usuarios (no especialistas) con al menos un diagnostico hecho Y marcado como
    resuelto dentro del periodo, en la provincia indicada. Una fila por persona. formato=csv para entregarlo al sorteo."""
    admin.require_admin(x_admin_token)
    try:
        d0 = datetime.strptime(desde, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        d1 = datetime.strptime(hasta, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    except ValueError:
        raise HTTPException(400, "desde/hasta deben ser AAAA-MM-DD")
    rango = {"$gte": iso(d0), "$lt": iso(d1)}
    diags = await db.diagnoses.find(
        {"created_at": rango, "resolved_at": rango, "resolved_province": provincia.upper()},
        {"_id": 0, "user_id": 1, "diagnosis_id": 1, "resolved_at": 1}).to_list(100000)
    por_usuario: dict = {}
    for x in diags:
        r = por_usuario.setdefault(x["user_id"], {"diagnosi_risolte": 0, "prima_risoluzione": x["resolved_at"]})
        r["diagnosi_risolte"] += 1
        r["prima_risoluzione"] = min(r["prima_risoluzione"], x["resolved_at"])
    users = await db.users.find({"user_id": {"$in": list(por_usuario)}},
                                {"_id": 0, "user_id": 1, "name": 1, "email": 1, "specialist_id": 1, "created_at": 1}).to_list(100000)
    filas = [{"n": 0, "user_id": u["user_id"], "nome": u.get("name"), "email": u.get("email"),
              "registrato": u.get("created_at"), **por_usuario[u["user_id"]]}
             for u in users if not u.get("specialist_id")]
    filas.sort(key=lambda f: f["prima_risoluzione"])
    for i, f in enumerate(filas, 1):
        f["n"] = i
    if formato == "csv":
        import csv
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=["n", "user_id", "nome", "email", "registrato", "diagnosi_risolte", "prima_risoluzione"])
        w.writeheader()
        w.writerows(filas)
        return Response(content=out.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="concorso_{desde}_{hasta}.csv"'})
    return {"desde": desde, "hasta": hasta, "provincia": provincia.upper(), "partecipanti": len(filas), "lista": filas}
