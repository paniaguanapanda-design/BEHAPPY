"""Cuota mensual de diagnosticos: clientes y especialistas con membresia, devolucion si la IA falla."""
import asyncio
from datetime import timedelta

from test_preregistro import api, clean_db, register, server  # noqa: F401
from behappy import ai, core, diagnosis  # noqa: E402
from behappy.core import iso, now  # noqa: E402

GOOD = {"is_home_problem": True, "is_appliance": False, "title_es": "Pintar", "title_it": "Pittura",
        "category": "masonry", "description": "Pintar una habitacion.", "difficulty": "expert",
        "safety_warnings": [], "materials": [], "tools": [], "steps": []}


async def wait_done(api, headers, diag_id):
    for _ in range(100):  # el analisis corre en segundo plano
        d = (await api.get(f"/api/diagnoses/{diag_id}", headers=headers)).json()
        if d.get("status") != "processing":
            return d
        await asyncio.sleep(0.02)
    raise AssertionError("el diagnostico no termino")


async def test_client_gets_monthly_limit_then_429(api, monkeypatch):
    monkeypatch.setattr(diagnosis, "QUOTA_CLIENT", 2)
    async def fake(prompt, image_b64=None):
        return GOOD
    monkeypatch.setattr(ai, "gemini_json", fake)
    headers = await register(api, "cuota-cliente@example.com")

    for _ in range(2):
        r = await api.post("/api/diagnose", headers=headers, json={"note": "pintar", "language": "es"})
        assert r.status_code == 200, r.text
    third = await api.post("/api/diagnose", headers=headers, json={"note": "pintar", "language": "es"})
    assert third.status_code == 429
    assert third.json()["detail"] == "monthly_limit"

    q = (await api.get("/api/diagnoses/quota", headers=headers)).json()
    assert q["limit"] == 2 and q["used"] == 2 and q["remaining"] == 0
    assert q["resets_at"].endswith("Z") or "T" in q["resets_at"]


async def test_failed_ai_does_not_use_quota(api, monkeypatch):
    monkeypatch.setattr(diagnosis, "QUOTA_CLIENT", 1)
    async def broken(prompt, image_b64=None):
        raise RuntimeError("IA caida")
    monkeypatch.setattr(ai, "gemini_json", broken)
    headers = await register(api, "cuota-fallo@example.com")

    r = await api.post("/api/diagnose", headers=headers, json={"note": "pintar", "language": "es"})
    assert r.status_code == 200
    d = await wait_done(api, headers, r.json()["diagnosis_id"])
    assert d["status"] == "failed"

    q = (await api.get("/api/diagnoses/quota", headers=headers)).json()
    assert q["used"] == 0 and q["remaining"] == 1  # la IA no llego a analizarlo: no gasta cuota


async def test_specialist_with_membership_gets_larger_limit(api, monkeypatch):
    monkeypatch.setattr(diagnosis, "QUOTA_CLIENT", 1)
    monkeypatch.setattr(diagnosis, "QUOTA_SPECIALIST", 3)
    headers = await register(api, "cuota-especialista@example.com")
    me = (await api.get("/api/auth/me", headers=headers)).json()
    await core.db.users.update_one({"user_id": me["user_id"]}, {"$set": {"role": "specialist"}})
    await core.db.memberships.insert_one({"user_id": me["user_id"], "plan": "monthly", "source": "test",
                                          "expires_at": iso(now() + timedelta(days=30))})
    q = (await api.get("/api/diagnoses/quota", headers=headers)).json()
    assert q["limit"] == 3


async def test_quota_endpoint_requires_login(api):
    r = await api.get("/api/diagnoses/quota")
    assert r.status_code in (401, 403)
