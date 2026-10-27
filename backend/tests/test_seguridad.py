"""Sesiones revocables, token solo en cabecera, documento sin numero e IP real."""
import os

from starlette.requests import Request

from test_preregistro import api, clean_db, make_profile, register, server  # noqa: F401


async def test_logout_invalidates_token(api):
    h = await register(api, "out@example.com")
    assert (await api.get("/api/auth/me", headers=h)).status_code == 200
    await api.post("/api/auth/logout", headers=h)
    assert (await api.get("/api/auth/me", headers=h)).status_code == 401


async def test_logout_all_closes_every_device(api):
    await register(api, "multi@example.com")
    t1 = (await api.post("/api/auth/login", json={"email": "multi@example.com", "password": "secret123"})).json()["session_token"]
    t2 = (await api.post("/api/auth/login", json={"email": "multi@example.com", "password": "secret123"})).json()["session_token"]
    h1, h2 = {"Authorization": f"Bearer {t1}"}, {"Authorization": f"Bearer {t2}"}
    await api.post("/api/auth/logout", headers=h1)
    assert (await api.get("/api/auth/me", headers=h1)).status_code == 401
    assert (await api.get("/api/auth/me", headers=h2)).status_code == 200  # el otro movil sigue dentro
    await api.post("/api/auth/logout-all", headers=h2)
    assert (await api.get("/api/auth/me", headers=h2)).status_code == 401


async def test_old_token_without_session_is_rejected(api):
    import jwt
    h = await register(api, "old@example.com")
    uid = (await api.get("/api/auth/me", headers=h)).json()["user_id"]
    old = jwt.encode({"sub": uid, "exp": server.now() + server.timedelta(days=7)}, server.JWT_SECRET, algorithm="HS256")
    assert (await api.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"})).status_code == 401


async def test_file_token_in_url_is_not_accepted(api):
    h = await register(api, "files@example.com")
    spec = await make_profile(api, h)
    await server.db.files.insert_one({"storage_path": spec["avatar"], "owner_id": spec["user_id"],
                                      "content_type": "image/jpeg", "is_deleted": False})
    server.LOCAL_UPLOAD_DIR.joinpath(spec["avatar"]).parent.mkdir(parents=True, exist_ok=True)
    server.LOCAL_UPLOAD_DIR.joinpath(spec["avatar"]).write_bytes(b"jpg")
    token = h["Authorization"][7:]
    assert (await api.get(f"/api/files/{spec['avatar']}?token={token}")).status_code == 401
    assert (await api.get(f"/api/files/{spec['avatar']}", headers=h)).status_code == 200


async def test_document_number_is_not_stored(api):
    h = await register(api, "doc@example.com")
    spec = await make_profile(api, h)
    doc = spec["avatar"].replace("cara", "documento")
    r = await api.post("/api/specialists/me/verify", headers=h, json={"document_image": doc, "document_number": "X1234567"})
    assert r.status_code == 200
    s = await server.db.specialists.find_one({"specialist_id": spec["specialist_id"]})
    assert "document_number" not in s and s["verification_status"] == "in_review"
    r = await api.post("/api/specialists/me/verify", headers=h, json={"document_image": doc})  # sin numero tambien vale
    assert r.status_code == 200


def fake_request(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": ("10.0.0.9", 1234)})


def test_client_ip_ignores_forged_forwarded_for(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("WEB_PROXY_KEY", "clave-secreta")
    # X-Forwarded-For inventado por el visitante: no cuenta
    assert server.client_ip(fake_request({"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "217.0.0.1"})) == "217.0.0.1"
    assert server.client_ip(fake_request({"X-Forwarded-For": "1.2.3.4"})) == "sin-ip"
    # La web manda la IP del visitante con la clave correcta
    web = {"CF-Connecting-IP": "76.76.21.1", "X-BeHappy-Client-IP": "93.40.1.2", "X-BeHappy-Proxy-Key": "clave-secreta"}
    assert server.client_ip(fake_request(web)) == "93.40.1.2"
    # Sin la clave (o con otra) se ignora
    assert server.client_ip(fake_request({**web, "X-BeHappy-Proxy-Key": "otra"})) == "76.76.21.1"
    assert server.client_ip(fake_request({**web, "X-BeHappy-Client-IP": "no-es-ip"})) == "76.76.21.1"


def test_client_ip_local_development(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    assert server.client_ip(fake_request({})) == "10.0.0.9"


def test_uploads_refused_on_render_without_bucket(monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setattr(server, "ON_RENDER", True)
    monkeypatch.setattr(server, "S3_BUCKET", None)
    with pytest.raises(HTTPException) as e:
        server.put_object("behappy/uploads/u/x.jpg", b"x", "image/jpeg")
    assert e.value.status_code == 503
    assert os.environ.get("MONGO_URL")
