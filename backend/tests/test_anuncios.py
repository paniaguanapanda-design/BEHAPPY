"""Novedades y pop-ups: audiencia, una sola vez por persona, fechas, sorteos con bases y permisos de admin."""
from datetime import timedelta

from test_preregistro import api, clean_db, register, server  # noqa: F401
from behappy import admin, core  # noqa: E402
import pytest  # noqa: E402
from behappy.core import iso, now  # noqa: E402

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_TOKEN", "test-admin-token")


async def publish(api, **over):
    body = {"title": "Novedad", "text": "Texto del anuncio", "type": "novedad", "audience": "todos"}
    body.update(over)
    r = await api.post("/api/admin/anuncios", headers=ADMIN, json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def test_only_admin_can_publish(api):
    r = await api.post("/api/admin/anuncios", json={"title": "x", "text": "y"})
    assert r.status_code == 403


async def test_validation_rules(api):
    bad = [
        {"title": "x", "text": "y", "type": "otro"},
        {"title": "x", "text": "y", "audience": "vip"},
        {"title": "x", "text": "y", "link": "http://no-seguro.example"},
        {"title": "x", "text": "y", "type": "sorteo"},  # sorteo sin bases legales
        {"title": "x", "text": "y", "starts_at": "2030-01-02", "ends_at": "2030-01-01"},
    ]
    for body in bad:
        r = await api.post("/api/admin/anuncios", headers=ADMIN, json=body)
        assert r.status_code == 422, body


async def test_audience_and_seen_once(api):
    client_h = await register(api, "anuncio-cliente@example.com")
    await publish(api, title="Para todos", audience="todos")
    await publish(api, title="Solo especialistas", audience="especialistas")

    pend = (await api.get("/api/announcements/pending", headers=client_h)).json()["items"]
    titles = [a["title"] for a in pend]
    assert "Para todos" in titles and "Solo especialistas" not in titles

    aid = next(a["announcement_id"] for a in pend if a["title"] == "Para todos")
    assert (await api.post(f"/api/announcements/{aid}/seen", headers=client_h)).status_code == 200
    again = (await api.get("/api/announcements/pending", headers=client_h)).json()["items"]
    assert all(a["announcement_id"] != aid for a in again)  # ya visto: no vuelve a salir

    lista = (await api.get("/api/announcements", headers=client_h)).json()["items"]
    assert next(a for a in lista if a["announcement_id"] == aid)["seen"] is True


async def test_specialist_sees_specialist_audience(api):
    h = await register(api, "anuncio-especialista@example.com")
    me = (await api.get("/api/auth/me", headers=h)).json()
    await core.db.users.update_one({"user_id": me["user_id"]}, {"$set": {"role": "specialist"}})
    await publish(api, title="Para especialistas", audience="especialistas")
    titles = [a["title"] for a in (await api.get("/api/announcements/pending", headers=h)).json()["items"]]
    assert "Para especialistas" in titles


async def test_expired_and_deactivated_are_hidden(api):
    h = await register(api, "anuncio-fechas@example.com")
    past = await publish(api, title="Caducado",
                         starts_at=iso(now() - timedelta(days=2)), ends_at=iso(now() - timedelta(days=1)))
    off = await publish(api, title="Desactivado")
    r = await api.post(f"/api/admin/anuncios/{off['announcement_id']}/desactivar", headers=ADMIN)
    assert r.status_code == 200
    titles = [a["title"] for a in (await api.get("/api/announcements/pending", headers=h)).json()["items"]]
    assert "Caducado" not in titles and "Desactivado" not in titles
    assert past["announcement_id"]  # se creo, pero no se muestra


async def test_sorteo_with_terms_link_is_allowed(api):
    await publish(api, title="Sorteo", type="sorteo", link="https://www.be-happyapp.com/bases-sorteo")
    r = await api.get("/api/admin/anuncios", headers=ADMIN)
    assert any(a["title"] == "Sorteo" and a["link"].startswith("https://") for a in r.json()["items"])


async def test_user_endpoints_require_login(api):
    assert (await api.get("/api/announcements/pending")).status_code in (401, 403)


PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


async def test_permanent_announcement_has_no_end_date(api):
    h = await register(api, "anuncio-permanente@example.com")
    a = await publish(api, title="Bienvenida permanente", permanente=True)
    assert a["ends_at"] is None
    items = (await api.get("/api/announcements/pending", headers=h)).json()["items"]
    assert any(x["title"] == "Bienvenida permanente" and x["permanente"] for x in items)


async def test_solo_nuevos_only_for_recent_accounts(api):
    old_h = await register(api, "anuncio-antiguo@example.com")
    old_me = (await api.get("/api/auth/me", headers=old_h)).json()
    await core.db.users.update_one({"user_id": old_me["user_id"]},
                                   {"$set": {"created_at": iso(now() - timedelta(days=60))}})
    new_h = await register(api, "anuncio-nuevo@example.com")
    await publish(api, title="Saludo a nuevos", permanente=True, solo_nuevos=True)
    old_titles = [a["title"] for a in (await api.get("/api/announcements/pending", headers=old_h)).json()["items"]]
    new_titles = [a["title"] for a in (await api.get("/api/announcements/pending", headers=new_h)).json()["items"]]
    assert "Saludo a nuevos" not in old_titles
    assert "Saludo a nuevos" in new_titles


async def test_photo_is_stored_and_served(api):
    h = await register(api, "anuncio-foto@example.com")
    a = await publish(api, title="Con foto", imagen_base64="data:image/png;base64," + PNG_1X1)
    assert a.get("image_path") and a.get("image_type") == "image/png"
    img = await api.get(f"/api/announcements/{a['announcement_id']}/imagen")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    items = (await api.get("/api/announcements/pending", headers=h)).json()["items"]
    assert next(x for x in items if x["title"] == "Con foto")["image_url"].endswith("/imagen")


async def test_bad_photo_is_rejected(api):
    r = await api.post("/api/admin/anuncios", headers=ADMIN, json={"title": "x", "text": "y", "imagen_base64": "aGVsbG8="})
    assert r.status_code == 422


async def test_no_photo_means_404(api):
    a = await publish(api, title="Sin foto")
    assert (await api.get(f"/api/announcements/{a['announcement_id']}/imagen")).status_code == 404
