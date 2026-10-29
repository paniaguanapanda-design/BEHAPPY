"""Suscripcion en la web: codigo por correo, Stripe Checkout y webhook que activa la membresia."""
import hashlib
import hmac
import json
import re
import time

import pytest

from test_preregistro import api, clean_db, make_profile, register, server  # noqa: F401

SECRET = "whsec_test"


@pytest.fixture
def stripe(monkeypatch):
    state = {"mail": [], "calls": [], "subs": {}}

    async def fake_mail(to, subject, text, html):
        state["mail"].append({"to": to, "text": text})
        return True

    async def fake_stripe(method, path, data=None):
        state["calls"].append((method, path, data))
        if path == "prices" and method == "GET":
            return {"data": []}
        if path == "products":
            return {"id": "prod_1"}
        if path == "prices":
            return {"id": f"price_{data['recurring']['interval']}"}
        if path == "checkout/sessions":
            return {"url": "https://checkout.stripe.com/c/pay/cs_test"}
        if path == "billing_portal/sessions":
            return {"url": "https://billing.stripe.com/p/session"}
        if path.startswith("subscriptions/"):
            return state["subs"][path.split("/", 1)[1]]
        raise AssertionError(path)

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("WEB_PROXY_KEY", raising=False)
    monkeypatch.setattr(server, "send_email", fake_mail)
    monkeypatch.setattr(server, "stripe_api", fake_stripe)
    return state


async def web_login(api, stripe, email):
    assert (await api.post("/api/web/login/start", json={"email": email, "lang": "it"})).status_code == 200
    code = re.search(r"\b(\d{6})\b", stripe["mail"][-1]["text"]).group(1)
    r = await api.post("/api/web/login/confirm", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def signed(event: dict) -> tuple:
    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}


def subscription(uid, status="active", interval="month", days=30):
    return {"id": "sub_1", "customer": "cus_1", "status": status, "metadata": {"user_id": uid},
            "items": {"data": [{"current_period_end": int(time.time()) + days * 86400,
                                "price": {"recurring": {"interval": interval}}}]}}


async def test_unknown_email_gets_same_answer_and_no_mail(api, stripe):
    r = await api.post("/api/web/login/start", json={"email": "nessuno@x.it"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert stripe["mail"] == []


async def test_wrong_code_then_limit(api, stripe):
    await register(api, "m@x.it")
    await api.post("/api/web/login/start", json={"email": "m@x.it"})
    for _ in range(5):
        r = await api.post("/api/web/login/confirm", json={"email": "m@x.it", "code": "000000"})
    r = await api.post("/api/web/login/confirm", json={"email": "m@x.it", "code": "000000"})
    assert r.status_code == 400 and r.json()["detail"] == "code_expired"


async def test_app_token_is_not_a_web_session(api, stripe):
    h = await register(api, "m@x.it")
    assert (await api.get("/api/web/membership", headers=h)).status_code == 401


async def test_full_flow_checkout_webhook_activates_and_cancel_ends(api, stripe):
    h = await register(api, "marco@x.it")
    await make_profile(api, h)
    uid = (await api.get("/api/auth/me", headers=h)).json()["user_id"]
    w = await web_login(api, stripe, "Marco@x.it")
    st = (await api.get("/api/web/membership", headers=w)).json()
    assert st["is_specialist"] and st["membership"]["active"] is False

    r = await api.post("/api/web/checkout", headers=w, json={"plan": "monthly"})
    assert r.json()["url"].startswith("https://checkout.stripe.com/")
    method, path, data = stripe["calls"][-1]
    assert data["client_reference_id"] == uid and data["line_items"][0]["price"] == "price_month"

    stripe["subs"]["sub_1"] = subscription(uid)
    body, headers = signed({"id": "evt_1", "type": "checkout.session.completed",
                            "data": {"object": {"mode": "subscription", "subscription": "sub_1", "customer": "cus_1",
                                                "client_reference_id": uid}}})
    assert (await api.post("/api/stripe/webhook", content=body, headers=headers)).status_code == 200
    m = (await api.get("/api/membership/me", headers=h)).json()
    assert m["active"] and m["source"] == "stripe" and m["plan"] == "monthly"
    # el especialista ya sale en el muro
    c = await register(api, "cliente@x.it")
    assert len((await api.get("/api/specialists", headers=c)).json()) == 1
    # ya suscrito: no puede pagar otra vez, pero si gestionar
    assert (await api.post("/api/web/checkout", headers=w, json={"plan": "yearly"})).status_code == 400
    assert (await api.post("/api/web/portal", headers=w)).json()["url"].startswith("https://billing.stripe.com/")

    # el mismo aviso dos veces no hace nada raro; la baja al final del periodo apaga el perfil
    assert (await api.post("/api/stripe/webhook", content=body, headers=headers)).status_code == 200
    body, headers = signed({"id": "evt_2", "type": "customer.subscription.deleted",
                            "data": {"object": subscription(uid, status="canceled")}})
    await api.post("/api/stripe/webhook", content=body, headers=headers)
    assert (await api.get("/api/membership/me", headers=h)).json()["active"] is False


async def test_webhook_rejects_bad_signature(api, stripe):
    body = json.dumps({"id": "evt_x", "type": "invoice.paid", "data": {"object": {}}}).encode()
    r = await api.post("/api/stripe/webhook", content=body, headers={"stripe-signature": f"t={int(time.time())},v1=bad"})
    assert r.status_code == 400


async def test_client_without_profile_cannot_pay(api, stripe):
    await register(api, "cliente@x.it")
    w = await web_login(api, stripe, "cliente@x.it")
    r = await api.post("/api/web/checkout", headers=w, json={"plan": "monthly"})
    assert r.status_code == 400 and r.json()["detail"] == "not_specialist"
