"""Registro de especialistas desde la web, foto de perfil y permisos de la membresia."""
from datetime import timedelta

import pytest

from test_preregistro import api, clean_db, days_left, make_profile, register, server  # noqa: F401

WEB = {"X-BeHappy-Client": "web"}
APP = {"X-BeHappy-Client": "app"}


async def give_membership(headers_api, h, days=10):
    api = headers_api
    uid = (await api.get("/api/auth/me", headers=h)).json()["user_id"]
    await server.activate_membership(uid, "monthly", "test", server.now() + timedelta(days=days))


async def test_profile_photo_is_required(api):
    h = await register(api, "nophoto@example.com")
    r = await api.post("/api/specialists", headers=h, json={"name": "A", "categories": ["plumbing"], "phone": "123456"})
    assert r.status_code == 400
    r = await api.post("/api/specialists", headers=h, json={"name": "A", "categories": ["plumbing"], "phone": "123456",
                                                            "avatar": "behappy/uploads/otro_user/x.jpg"})
    assert r.status_code == 400  # foto de otra persona


async def test_editing_keeps_photo(api):
    h = await register(api, "keep@example.com")
    first = await make_profile(api, h)
    r = await api.post("/api/specialists", headers=h, json={"name": "Nuevo", "categories": ["electrical"], "phone": "123456"})
    assert r.status_code == 200 and r.json()["avatar"] == first["avatar"]


async def test_web_signup_free_month_starts_in_app(api):
    r = await api.post("/api/auth/register", headers=WEB, json={"email": "juan@example.com", "password": "secret123", "name": "Juan"})
    h = {"Authorization": f"Bearer {r.json()['session_token']}"}
    await make_profile(api, {**h, **WEB})
    # sin suscripcion activa no sale en la lista
    client = await register(api, "cliente@example.com")
    names = [s["name"] for s in (await api.get("/api/specialists", headers=client)).json()]
    assert "Mario Rossi" not in names
    assert (await api.get("/api/membership/me", headers=h)).json()["active"] is False
    await api.get("/api/auth/me", headers=h)  # la web no activa el mes
    assert (await api.get("/api/membership/me", headers=h)).json()["active"] is False
    await api.get("/api/auth/me", headers={**h, **APP})  # primera vez en la app
    m = (await api.get("/api/membership/me", headers=h)).json()
    assert m["active"] and m["source"] == "registro_web" and 29.9 < days_left(m["expires_at"]) <= 30
    names = [s["name"] for s in (await api.get("/api/specialists", headers=client)).json()]
    assert "Mario Rossi" in names  # con el mes activo ya sale
    await api.get("/api/auth/me", headers={**h, **APP})
    assert (await api.get("/api/membership/me", headers=h)).json()["expires_at"] == m["expires_at"]


async def test_fake_web_header_without_key_gets_no_promo(api, monkeypatch):
    monkeypatch.setenv("WEB_PROXY_KEY", "clave-de-la-web")
    # alguien escribe a mano la cabecera "web" desde fuera de la web: no hay mes gratis
    h = await register(api, "tramposo@example.com")
    await make_profile(api, {**h, **WEB})
    await api.get("/api/auth/me", headers={**h, **APP})
    assert (await api.get("/api/membership/me", headers=h)).json()["active"] is False
    # la web de verdad firma con la clave: el mes gratis empieza al entrar en la app
    h2 = await register(api, "vero@example.com")
    await make_profile(api, {**h2, **WEB, "X-BeHappy-Proxy-Key": "clave-de-la-web"})
    await api.get("/api/auth/me", headers={**h2, **APP})
    m = (await api.get("/api/membership/me", headers=h2)).json()
    assert m["active"] and m["source"] == "registro_web"


async def test_app_signup_gets_no_web_promo(api):
    h = await register(api, "app@example.com")
    await make_profile(api, {**h, **APP})
    await api.get("/api/auth/me", headers={**h, **APP})
    assert (await api.get("/api/membership/me", headers=h)).json()["active"] is False


async def test_list_only_members_with_photo(api):
    a = await register(api, "a@example.com")
    await make_profile(api, a, name="Sin membresia")
    b = await register(api, "b@example.com")
    await make_profile(api, b, name="Con membresia")
    await give_membership(api, b)
    uid = (await api.get("/api/auth/me", headers=a)).json()["user_id"]
    await server.db.specialists.insert_one({"specialist_id": "spec_x", "user_id": "user_x", "name": "Sin foto",
                                            "categories": ["plumbing"], "created_at": server.iso(server.now())})
    client = await register(api, "c@example.com")
    lst = (await api.get("/api/specialists", headers=client)).json()
    assert [s["name"] for s in lst] == ["Con membresia"]
    assert lst[0]["membership_active"]
    assert uid


async def test_client_can_write_specialist_needs_membership_to_reply(api):
    sh = await register(api, "spec@example.com")
    spec = await make_profile(api, sh)
    ch = await register(api, "client@example.com")
    conv = (await api.post("/api/conversations", headers=ch, json={"specialist_id": spec["specialist_id"]})).json()
    cid = conv["conversation_id"]
    assert (await api.post(f"/api/conversations/{cid}/messages", headers=ch, json={"text": "Hola"})).status_code == 200
    c = (await api.get(f"/api/conversations/{cid}", headers=sh)).json()
    assert c["specialist_can_reply"] is False
    msgs = (await api.get(f"/api/conversations/{cid}/messages", headers=sh)).json()
    assert [m["text"] for m in msgs] == ["Hola"]  # ve el mensaje en espera
    assert (await api.post(f"/api/conversations/{cid}/messages", headers=sh, json={"text": "Respuesta"})).status_code == 403
    await give_membership(api, sh)
    assert (await api.post(f"/api/conversations/{cid}/messages", headers=sh, json={"text": "Respuesta"})).status_code == 200


async def test_requests_wait_but_contracts_need_membership(api):
    sh = await register(api, "s2@example.com")
    spec = await make_profile(api, sh)
    ch = await register(api, "c2@example.com")
    r = await api.post("/api/requests", headers=ch, json={"specialist_id": spec["specialist_id"], "description": "Grifo"})
    assert r.status_code == 200
    rid = r.json()["request_id"]
    assert (await api.post(f"/api/requests/{rid}/quotes", headers=sh, json={"price": 50, "description": "Cambio"})).status_code == 403
    assert (await api.patch(f"/api/requests/{rid}", headers=sh, json={"status": "accepted"})).status_code == 403
    await give_membership(api, sh)
    assert (await api.post(f"/api/requests/{rid}/quotes", headers=sh, json={"price": 50, "description": "Cambio"})).status_code == 200


async def test_portfolio_needs_membership(api, monkeypatch):
    async def fake_caption(c):
        return {"es": c, "it": c}
    monkeypatch.setattr(server, "caption_both", fake_caption)
    sh = await register(api, "s3@example.com")
    spec = await make_profile(api, sh)
    img = spec["avatar"].replace("cara", "trabajo")
    body = {"image": img, "caption": "Baño"}
    assert (await api.post("/api/specialists/me/portfolio", headers=sh, json=body)).status_code == 403
    await give_membership(api, sh)
    assert (await api.post("/api/specialists/me/portfolio", headers=sh, json=body)).status_code == 200


async def test_avatar_file_visible_to_clients(api):
    sh = await register(api, "s4@example.com")
    spec = await make_profile(api, sh)
    await server.db.files.insert_one({"storage_path": spec["avatar"], "owner_id": spec["user_id"],
                                      "content_type": "image/jpeg", "is_deleted": False})
    server.LOCAL_UPLOAD_DIR.joinpath(spec["avatar"]).parent.mkdir(parents=True, exist_ok=True)
    server.LOCAL_UPLOAD_DIR.joinpath(spec["avatar"]).write_bytes(b"jpg")
    ch = await register(api, "c4@example.com")
    r = await api.get(f"/api/files/{spec['avatar']}", headers=ch)
    assert r.status_code == 200
