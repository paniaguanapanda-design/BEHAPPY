"""Recuperar contrasena con codigo de 6 digitos por email."""
import re
from datetime import timedelta

import pytest

from test_preregistro import api, clean_db, register, server  # noqa: F401


@pytest.fixture
def mailbox(monkeypatch):
    sent = []

    async def fake_send(to, subject, text, html):
        sent.append({"to": to, "subject": subject, "text": text, "html": html})
        return True

    monkeypatch.setenv("RESEND_API_KEY", "test")
    monkeypatch.setenv("EMAIL_FROM", "Be Happy <no-reply@be-happyapp.com>")
    monkeypatch.setattr(server, "send_email", fake_send)
    return sent


def code_in(mail) -> str:
    return re.search(r"\b(\d{6})\b", mail["text"]).group(1)


async def test_full_reset_flow(api, mailbox):
    old = await register(api, "olvido@example.com")
    r = await api.post("/api/auth/forgot-password", json={"email": " Olvido@Example.com ", "language": "it"})
    assert r.status_code == 200 and len(mailbox) == 1
    assert mailbox[0]["to"] == "olvido@example.com" and "password" in mailbox[0]["subject"]
    code = code_in(mailbox[0])
    r = await api.post("/api/auth/reset-password", json={"email": "olvido@example.com", "code": code, "new_password": "nueva123"})
    assert r.status_code == 200 and r.json()["session_token"]
    # la contrasena vieja ya no sirve, la nueva si
    assert (await api.post("/api/auth/login", json={"email": "olvido@example.com", "password": "secret123"})).status_code == 401
    assert (await api.post("/api/auth/login", json={"email": "olvido@example.com", "password": "nueva123"})).status_code == 200
    # las sesiones anteriores se cierran
    assert (await api.get("/api/auth/me", headers=old)).status_code == 401
    # el codigo solo vale una vez
    r = await api.post("/api/auth/reset-password", json={"email": "olvido@example.com", "code": code, "new_password": "otra1234"})
    assert r.status_code == 400


async def test_unknown_email_gets_same_answer_and_no_mail(api, mailbox):
    r = await api.post("/api/auth/forgot-password", json={"email": "nadie@example.com"})
    assert r.status_code == 200 and r.json() == {"ok": True} and mailbox == []


async def test_wrong_code_blocks_after_five_attempts(api, mailbox):
    await register(api, "fuerza@example.com")
    await api.post("/api/auth/forgot-password", json={"email": "fuerza@example.com"})
    code = code_in(mailbox[0])
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = await api.post("/api/auth/reset-password", json={"email": "fuerza@example.com", "code": wrong, "new_password": "nueva123"})
        assert r.status_code == 400
    # aunque ahora acierte, el codigo ya esta anulado
    r = await api.post("/api/auth/reset-password", json={"email": "fuerza@example.com", "code": code, "new_password": "nueva123"})
    assert r.status_code == 400


async def test_expired_code(api, mailbox):
    await register(api, "tarde@example.com")
    await api.post("/api/auth/forgot-password", json={"email": "tarde@example.com"})
    await server.db.password_resets.update_many({}, {"$set": {"expires_at": server.now() - timedelta(minutes=1)}})
    r = await api.post("/api/auth/reset-password", json={"email": "tarde@example.com", "code": code_in(mailbox[0]), "new_password": "nueva123"})
    assert r.status_code == 400


async def test_code_is_stored_hashed(api, mailbox):
    await register(api, "hash@example.com")
    await api.post("/api/auth/forgot-password", json={"email": "hash@example.com"})
    rec = await server.db.password_resets.find_one({})
    assert code_in(mailbox[0]) not in str(rec)


async def test_google_account_gets_explanation_not_code(api, mailbox):
    await server.db.users.insert_one({"user_id": "user_g", "email": "google@example.com", "name": "G", "role": "client"})
    await api.post("/api/auth/forgot-password", json={"email": "google@example.com"})
    assert len(mailbox) == 1 and "Google" in mailbox[0]["text"]
    assert await server.db.password_resets.count_documents({}) == 0


async def test_too_many_requests_per_email(api, mailbox):
    await register(api, "spam@example.com")
    for _ in range(3):
        assert (await api.post("/api/auth/forgot-password", json={"email": "spam@example.com"})).status_code == 200
    assert (await api.post("/api/auth/forgot-password", json={"email": "spam@example.com"})).status_code == 429


async def test_short_new_password_rejected(api, mailbox):
    await register(api, "corta@example.com")
    await api.post("/api/auth/forgot-password", json={"email": "corta@example.com"})
    r = await api.post("/api/auth/reset-password", json={"email": "corta@example.com", "code": code_in(mailbox[0]), "new_password": "123"})
    assert r.status_code == 400


async def test_not_configured_returns_503(api, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert (await api.post("/api/auth/forgot-password", json={"email": "x@example.com"})).status_code == 503
