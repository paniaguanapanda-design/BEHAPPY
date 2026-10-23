"""Iteration 3 retest: can_review after chat, review comment translation (comment_es/comment_it), membership plans.
Writes /tmp/t3_ctx.json for UI tests. Cleanup: python tests/cleanup_iter3.py"""
import os
import json
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
API = f"{BASE_URL}/api"
CTX = {"emails": []}


def _register(prefix):
    email = f"test_{prefix}_{uuid.uuid4().hex[:6]}@fixai.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "test123", "name": f"TEST {prefix}"})
    assert r.status_code == 200, r.text
    d = r.json()
    CTX["emails"].append(email)
    return {"email": email, "token": d["session_token"], "user": d["user"], "h": {"Authorization": f"Bearer {d['session_token']}"}}


def _make_specialist(u, cats, caption):
    r = requests.post(f"{API}/specialists", headers=u["h"], json={"name": u["user"]["name"], "categories": cats, "bio": "TEST bio", "phone": "+390111234567"})
    assert r.status_code == 200, r.text
    sid = r.json()["specialist_id"]
    r = requests.post(f"{API}/membership/revenuecat-sync", headers=u["h"], json={"plan": "yearly"})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True
    with open("/tmp/leak.jpg", "rb") as f:
        r = requests.post(f"{API}/upload", headers=u["h"], files={"file": ("leak.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    path = r.json()["path"]
    r = requests.post(f"{API}/specialists/me/portfolio", headers=u["h"], json={"image": path, "caption": caption}, timeout=90)
    assert r.status_code == 200, r.text
    return sid


@pytest.fixture(scope="module")
def ctx():
    spec = _register("spec")
    spec_hvac = _register("spechvac")
    client = _register("client")
    long_cap = "Sostituzione completa del rubinetto della cucina con riparazione del tubo di scarico sotto il lavello e sigillatura"
    sid = _make_specialist(spec, ["plumbing"], long_cap)
    sid2 = _make_specialist(spec_hvac, ["hvac", "appliances"], "Riparazione caldaia")
    c = {"spec": spec, "spec_hvac": spec_hvac, "client": client, "sid": sid, "sid2": sid2}
    yield c
    CTX.update({"sid": sid, "sid2": sid2, "client": {"email": client["email"], "token": client["token"]},
                "spec": {"email": spec["email"], "token": spec["token"]}})
    with open("/tmp/t3_ctx.json", "w") as f:
        json.dump(CTX, f)


class TestMembership:
    def test_membership_plans_prices(self, ctx):
        r = requests.get(f"{API}/membership/me", headers=ctx["spec"]["h"])
        assert r.status_code == 200
        d = r.json()
        print("MEMBERSHIP:", d)
        assert d["active"] is True
        assert d.get("plans", {}).get("monthly") == 19.99
        assert d.get("plans", {}).get("yearly") == 199.99

    def test_specialists_listed(self, ctx):
        r = requests.get(f"{API}/specialists?category=hvac", headers=ctx["client"]["h"])
        assert r.status_code == 200
        assert any(s["specialist_id"] == ctx["sid2"] for s in r.json())


class TestReviewFlow:
    def test_can_review_false_before_chat(self, ctx):
        r = requests.get(f"{API}/specialists/{ctx['sid']}", headers=ctx["client"]["h"])
        assert r.status_code == 200
        assert r.json()["can_review"] is False

    def test_review_forbidden_before_chat(self, ctx):
        r = requests.post(f"{API}/specialists/{ctx['sid']}/reviews", headers=ctx["client"]["h"], json={"rating": 5, "comment": "x"})
        assert r.status_code == 403

    def test_can_review_true_after_chat(self, ctx):
        r = requests.post(f"{API}/conversations", headers=ctx["client"]["h"], json={"specialist_id": ctx["sid"]})
        assert r.status_code == 200, r.text
        cid = r.json()["conversation_id"]
        r = requests.post(f"{API}/conversations/{cid}/messages", headers=ctx["client"]["h"], json={"text": "Hola, necesito ayuda"})
        assert r.status_code == 200, r.text
        r = requests.get(f"{API}/specialists/{ctx['sid']}", headers=ctx["client"]["h"])
        assert r.json()["can_review"] is True

    def test_review_comment_translated(self, ctx):
        r = requests.post(f"{API}/specialists/{ctx['sid']}/reviews", headers=ctx["client"]["h"],
                          json={"rating": 4, "comment": "Muy buen trabajo, rápido y limpio"}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        print("REVIEW:", d)
        assert "_id" not in d
        assert d.get("comment_es") and d.get("comment_it")
        assert d["comment_it"] != d["comment_es"]
        r = requests.get(f"{API}/specialists/{ctx['sid']}/reviews", headers=ctx["client"]["h"])
        rv = r.json()[0]
        assert rv["comment_it"] == d["comment_it"]

    def test_can_review_false_after_review(self, ctx):
        r = requests.get(f"{API}/specialists/{ctx['sid']}", headers=ctx["client"]["h"])
        d = r.json()
        assert d["can_review"] is False
        assert d["reviews_count"] == 1 and d["rating_avg"] is None  # avg hidden until 3 ratings (by design)
