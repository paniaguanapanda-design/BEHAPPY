"""Pruebas backend; requieren las dependencias de requirements-test.txt y un MongoDB de pruebas."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "behappy_test")
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-more-than-32-bytes")
os.environ["GOOGLE_CLIENT_IDS"] = "test-client"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402

def prereg(email, especialidad="idraulica", estado="reservada"):
    return {"nombre": "Mario Rossi", "email": email, "telefono": "+39 333 1234567", "especialidad": especialidad,
            "zona": "Torino", "estado": "preregistrado", "promo": {"tipo": "1_mes_gratis", "estado": estado}}


# Provincias falsas para las pruebas (sin llamar a OpenStreetMap): el punto conocido mas cercano.
PROVINCES = {"TO": ("Torino", 45.0703, 7.6869), "MI": ("Milano", 45.4642, 9.1900), "RM": ("Roma", 41.9028, 12.4964)}
TORINO_POINT = (45.0703, 7.6869)


async def fake_province_at(lat, lng):
    if not (36 <= lat <= 47.2 and 6.5 <= lng <= 18.6):
        return None  # fuera de Italia
    code = min(PROVINCES, key=lambda c: (PROVINCES[c][1] - lat) ** 2 + (PROVINCES[c][2] - lng) ** 2)
    return {"code": code, "name": PROVINCES[code][0]}


@pytest.fixture(autouse=True)
async def clean_db(monkeypatch):
    monkeypatch.setattr(server, "province_at", fake_province_at)
    monkeypatch.setattr(server, "S3_BUCKET", None)
    monkeypatch.setattr(server, "ON_RENDER", False)
    monkeypatch.setenv("WEB_PROXY_KEY", "test-web-proxy-key")
    for name in await server.db.list_collection_names():
        await server.db[name].drop()
    await server.startup()
    server._hits.clear()
    yield


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def register(api, email, at=TORINO_POINT):
    """Crea una cuenta; por defecto la persona esta en la provincia de Torino (at=None: sin provincia)."""
    r = await api.post("/api/auth/register", json={"email": email, "password": "secret123", "name": "Mario"})
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['session_token']}"}
    if at:
        z = await api.put("/api/me/zone", headers=h, json={"lat": at[0], "lng": at[1]})
        assert z.status_code == 200, z.text
    return h


async def make_profile(api, headers, zone="TO", **extra):
    """Perfil de especialista; por defecto trabaja en la provincia de Torino (zone=None: sin zona)."""
    uid = (await api.get("/api/auth/me", headers=headers)).json()["user_id"]
    body = {"name": "Mario Rossi", "categories": ["plumbing"], "phone": "+39 333 1234567",
            "avatar": f"behappy/uploads/{uid}/cara.jpg", **extra}
    r = await api.post("/api/specialists", headers=headers, json=body)
    assert r.status_code == 200, r.text
    if zone:
        name, lat, lng = PROVINCES[zone]
        await server.db.specialists.update_one({"specialist_id": r.json()["specialist_id"]}, {"$set": {"zone": {
            "lat": lat, "lng": lng, "radius_km": 15, "label": name, "province": {"code": zone, "name": name}}}})
    return r.json()


def days_left(exp: str) -> float:
    return (datetime.fromisoformat(exp) - datetime.now(timezone.utc)) / timedelta(days=1)


async def google_login(api, monkeypatch, email):
    from google.oauth2 import id_token
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *a, **k: {
        "aud": "test-client", "email": email, "email_verified": True, "name": "Google User"})
    r = await api.post("/api/auth/google", json={"id_token": "fake"})
    assert r.status_code == 200, r.text
    return r.json()


async def test_password_account_gets_free_month_when_creating_profile(api):
    await server.db[server.PREREG].insert_one(prereg("mario@example.com"))
    h = await register(api, "Mario@Example.com")
    assert (await api.get("/api/membership/me", headers=h)).json()["active"] is False  # aun no es especialista
    spec = await make_profile(api, h)
    assert spec["membership_active"] is True
    m = (await api.get("/api/membership/me", headers=h)).json()
    assert m["active"] and m["source"] == "preregistro"
    assert 29.9 < days_left(m["expires_at"]) <= 30
    pre = await server.db[server.PREREG].find_one({"email": "mario@example.com"})
    assert pre["promo"]["estado"] == "aplicada" and pre["estado"] == "activado"


async def test_free_month_only_once(api):
    await server.db[server.PREREG].insert_one(prereg("once@example.com"))
    h = await register(api, "once@example.com")
    await make_profile(api, h)
    first = (await api.get("/api/membership/me", headers=h)).json()["expires_at"]
    await make_profile(api, h)  # editar el perfil
    await api.post("/api/auth/login", json={"email": "once@example.com", "password": "secret123"})
    assert (await api.get("/api/membership/me", headers=h)).json()["expires_at"] == first


async def test_password_account_profile_is_not_prefilled(api):
    await server.db[server.PREREG].insert_one(prereg("victim@example.com"))
    r = await api.post("/api/auth/register", json={"email": "victim@example.com", "password": "secret123", "name": "X"})
    assert r.json()["user"]["specialist_id"] is None
    assert await server.db.specialists.count_documents({}) == 0


async def test_google_signup_creates_profile_with_free_month(api, monkeypatch):
    await server.db[server.PREREG].insert_one(prereg("luca@example.com", "serrature"))
    out = await google_login(api, monkeypatch, "luca@example.com")
    assert out["user"]["role"] == "specialist" and out["user"]["specialist_id"]
    s = await server.db.specialists.find_one({"user_id": out["user"]["user_id"]})
    assert s["categories"] == ["carpentry"] and s["subtrades"] == ["cerrajeria"]
    assert s["phone"] == "+39 333 1234567" and s["name"] == "Mario Rossi"
    assert days_left(s["membership_expires_at"]) > 29.9


async def test_google_signup_unmapped_specialty_waits_for_profile(api, monkeypatch):
    await server.db[server.PREREG].insert_one(prereg("giulia@example.com", "giardinaggio"))
    out = await google_login(api, monkeypatch, "giulia@example.com")
    assert out["user"]["specialist_id"] is None
    h = {"Authorization": f"Bearer {out['session_token']}"}
    spec = await make_profile(api, h)
    assert spec["membership_active"] is True


async def test_no_prereg_no_free_month(api):
    h = await register(api, "nobody@example.com")
    spec = await make_profile(api, h)
    assert spec["membership_active"] is False


async def test_already_claimed_prereg_is_ignored(api):
    await server.db[server.PREREG].insert_one(prereg("used@example.com", estado="aplicada"))
    h = await register(api, "used@example.com")
    assert (await make_profile(api, h))["membership_active"] is False


async def test_free_month_extends_active_membership(api):
    await server.db[server.PREREG].insert_one(prereg("paid@example.com"))
    h = await register(api, "paid@example.com")
    uid = (await api.get("/api/auth/me", headers=h)).json()["user_id"]
    await server.db.memberships.insert_one({"user_id": uid, "plan": "yearly", "source": "revenuecat",
                                            "expires_at": server.iso(server.now() + timedelta(days=10))})
    await make_profile(api, h)
    m = (await api.get("/api/membership/me", headers=h)).json()
    assert 39.9 < days_left(m["expires_at"]) <= 40 and m["plan"] == "yearly"
