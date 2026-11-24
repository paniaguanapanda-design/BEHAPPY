"""Avisos de BE HAPPY a los especialistas: se envian desde el panel (correo + push) y se leen en la app."""
import pytest

from test_preregistro import api, clean_db, make_profile, register, server  # noqa: F401
from behappy import admin, mail, push  # noqa: E402

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_TOKEN", "test-admin-token")


@pytest.fixture
def sent(monkeypatch):
    calls = {"email": [], "push": []}

    async def fake_email(to, subject, text, html):
        calls["email"].append((to, subject, text, html))
        return True

    async def fake_push(user_id, title, body, data):
        calls["push"].append((user_id, title, body, data))

    monkeypatch.setattr(mail, "send_email", fake_email)
    monkeypatch.setattr(push, "send_push", fake_push)
    return calls


def to_specialist(sent, email):
    # El alta de un especialista tambien escribe al administrador: aqui solo miramos los correos al especialista.
    return [m for m in sent["email"] if m[0] == email]


async def specialist(api, email="aviso@example.com"):
    h = await register(api, email)
    await make_profile(api, h)
    me = (await api.get("/api/specialists/me", headers=h)).json()
    return h, me["specialist_id"]


async def test_admin_sends_notice_by_email_and_push(api, sent):
    h, sid = await specialist(api)
    body = {"subject": "Falta tu documento", "text": "Hola.\nSube tu documento para verificarte."}
    r = await api.post(f"/api/admin/specialists/{sid}/notice", json=body)
    assert r.status_code == 403
    r = await api.post(f"/api/admin/specialists/{sid}/notice", json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["email"] is True and r.json()["push"] is True
    mails = to_specialist(sent, "aviso@example.com")
    assert len(mails) == 1 and "Falta tu documento" in mails[0][1]
    assert "<p>Hola.</p>" in mails[0][3]  # el texto se parte en parrafos
    assert sent["push"][0][1]["es"] == "Falta tu documento"


async def test_only_chosen_channels_are_used(api, sent):
    _, sid = await specialist(api, "solo@example.com")
    r = await api.post(f"/api/admin/specialists/{sid}/notice", headers=ADMIN,
                       json={"subject": "Aviso", "text": "Solo correo", "channels": ["email"]})
    assert r.status_code == 200 and sent["push"] == [] and len(to_specialist(sent, "solo@example.com")) == 1


async def test_notice_must_have_a_channel_and_a_known_specialist(api, sent):
    _, sid = await specialist(api, "canal@example.com")
    r = await api.post(f"/api/admin/specialists/{sid}/notice", headers=ADMIN,
                       json={"subject": "Aviso", "text": "x", "channels": ["sms"]})
    assert r.status_code == 400
    r = await api.post("/api/admin/specialists/no-existe/notice", headers=ADMIN,
                       json={"subject": "Aviso", "text": "x"})
    assert r.status_code == 404


async def test_daily_limit_per_specialist(api, sent):
    _, sid = await specialist(api, "tope@example.com")
    for i in range(5):
        r = await api.post(f"/api/admin/specialists/{sid}/notice", headers=ADMIN, json={"subject": f"A{i}", "text": "x"})
        assert r.status_code == 200
    r = await api.post(f"/api/admin/specialists/{sid}/notice", headers=ADMIN, json={"subject": "Sexto", "text": "x"})
    assert r.status_code == 429


async def test_specialist_reads_and_marks_notices(api, sent):
    h, sid = await specialist(api, "lee@example.com")
    await api.post(f"/api/admin/specialists/{sid}/notice", headers=ADMIN, json={"subject": "Hola", "text": "Primer aviso"})
    mine = (await api.get("/api/specialists/me/notices", headers=h)).json()
    assert mine["unread"] == 1 and mine["items"][0]["subject"] == "Hola" and mine["items"][0]["read"] is False
    assert (await api.post("/api/specialists/me/notices/read", headers=h)).status_code == 200
    mine = (await api.get("/api/specialists/me/notices", headers=h)).json()
    assert mine["unread"] == 0 and mine["items"][0]["read"] is True


async def test_admin_sees_history_and_clients_do_not(api, sent):
    h, sid = await specialist(api, "hist@example.com")
    await api.post(f"/api/admin/specialists/{sid}/notice", headers=ADMIN, json={"subject": "Uno", "text": "x"})
    r = await api.get(f"/api/admin/specialists/{sid}/notices", headers=ADMIN)
    assert r.status_code == 200 and r.json()[0]["subject"] == "Uno"
    assert (await api.get(f"/api/admin/specialists/{sid}/notices")).status_code == 403
    cliente = await register(api, "cliente@example.com")
    assert (await api.get("/api/specialists/me/notices", headers=cliente)).status_code == 404
