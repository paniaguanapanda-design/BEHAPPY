"""Membresia pagada en la web con Stripe: la web avisa al servidor con la clave WEB_PROXY_KEY."""
import os
from datetime import timedelta

from test_preregistro import api, clean_db, days_left, make_profile, register, server  # noqa: F401

os.environ["WEB_PROXY_KEY"] = "proxy-test"
PROXY = {"X-BeHappy-Proxy-Key": "proxy-test", "X-BeHappy-Client": "web"}


async def uid_of(api, h):
    return (await api.get("/api/auth/me", headers=h)).json()["user_id"]


def sync_body(uid, days=30, status="active", **extra):
    return {"user_id": uid, "plan": "monthly", "status": status,
            "period_end": int((server.now() + timedelta(days=days)).timestamp()),
            "subscription_id": "sub_123", "customer_id": "cus_123", **extra}


async def test_sync_needs_the_proxy_key(api):
    h = await register(api, "a@example.com")
    uid = await uid_of(api, h)
    r = await api.post("/api/membership/stripe-sync", json=sync_body(uid))
    assert r.status_code == 403
    r = await api.post("/api/membership/stripe-sync", headers={"X-BeHappy-Proxy-Key": "mala"}, json=sync_body(uid))
    assert r.status_code == 403


async def test_paid_subscription_activates_membership(api):
    h = await register(api, "b@example.com")
    await make_profile(api, h)
    uid = await uid_of(api, h)
    r = await api.post("/api/membership/stripe-sync", headers=PROXY, json=sync_body(uid, days=30))
    assert r.status_code == 200, r.text
    assert r.json()["active"] and r.json()["source"] == "stripe"
    assert 29 < days_left(r.json()["expires_at"]) <= 30
    me = (await api.get("/api/membership/me", headers=h)).json()
    assert me["active"]


async def test_renewal_moves_the_end_date(api):
    h = await register(api, "c@example.com")
    uid = await uid_of(api, h)
    await api.post("/api/membership/stripe-sync", headers=PROXY, json=sync_body(uid, days=30))
    r = await api.post("/api/membership/stripe-sync", headers=PROXY, json=sync_body(uid, days=60))
    assert 59 < days_left(r.json()["expires_at"]) <= 60


async def test_full_cancellation_ends_membership(api):
    h = await register(api, "d@example.com")
    uid = await uid_of(api, h)
    await api.post("/api/membership/stripe-sync", headers=PROXY, json=sync_body(uid, days=30))
    r = await api.post("/api/membership/stripe-sync", headers=PROXY,
                       json=sync_body(uid, days=30, status="canceled", ended_at=int(server.now().timestamp()) - 5))
    assert not r.json()["active"]


async def test_cancellation_does_not_touch_other_sources(api):
    h = await register(api, "e@example.com")
    uid = await uid_of(api, h)
    await server.activate_membership(uid, "monthly", "revenuecat", server.now() + timedelta(days=20))
    r = await api.post("/api/membership/stripe-sync", headers=PROXY,
                       json=sync_body(uid, status="canceled", ended_at=int(server.now().timestamp())))
    assert r.json()["active"] and r.json()["source"] == "revenuecat"


async def test_trial_uses_up_the_web_free_month(api):
    r = await api.post("/api/auth/register", headers={"X-BeHappy-Client": "web"},
                       json={"email": "f@example.com", "password": "secret123", "name": "F"})
    h = {"Authorization": f"Bearer {r.json()['session_token']}"}
    await make_profile(api, {**h, "X-BeHappy-Client": "web"})
    uid = await uid_of(api, h)
    await server.db.users.update_one({"user_id": uid}, {"$set": {"promo_mes_gratis": "pendiente"}})
    ctx = (await api.get("/api/membership/web-context", headers={**h, **PROXY})).json()
    assert ctx["is_specialist"] and ctx["promo_pending"]
    await api.post("/api/membership/stripe-sync", headers=PROXY, json=sync_body(uid, days=30, status="trialing", promo_used=True))
    # Al entrar en la app no se suma otro mes
    await api.get("/api/auth/me", headers={**h, "X-BeHappy-Client": "app"})
    me = (await api.get("/api/membership/me", headers=h)).json()
    assert 29 < days_left(me["expires_at"]) <= 30
    ctx = (await api.get("/api/membership/web-context", headers={**h, **PROXY})).json()
    assert not ctx["promo_pending"]


async def test_web_context_needs_key_and_login(api):
    h = await register(api, "g@example.com")
    assert (await api.get("/api/membership/web-context", headers=h)).status_code == 403
    assert (await api.get("/api/membership/web-context", headers=PROXY)).status_code == 401
