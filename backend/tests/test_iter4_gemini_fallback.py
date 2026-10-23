"""Iteration 4 retest: Gemini own-key -> EMERGENT_LLM_KEY fallback.
Covers: /api/diagnose (200 + title_es/title_it/difficulty), GET /api/diagnoses/{id}?lang=it translation,
review comment translation (comment_es/comment_it), portfolio caption translation (caption_es/caption_it).
Cleanup: python tests/cleanup_iter3.py"""
import os
import base64
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
API = f"{BASE_URL}/api"
IMG = "/tmp/leak.jpg"


def _register(prefix):
    email = f"test_{prefix}_{uuid.uuid4().hex[:6]}@fixai.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "test123", "name": f"TEST {prefix}"})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"email": email, "user": d["user"], "h": {"Authorization": f"Bearer {d['session_token']}"}}


@pytest.fixture(scope="module")
def ctx():
    return {"spec": _register("i4spec"), "client": _register("i4client")}


# ---- Diagnosis (core AI feature) ----
class TestDiagnose:
    def test_diagnose_200(self, ctx):
        with open(IMG, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        r = requests.post(f"{API}/diagnose", headers=ctx["client"]["h"],
                          json={"image_base64": b64, "language": "es"}, timeout=120)
        print("DIAG status", r.status_code, r.text[:600])
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "_id" not in d
        assert d.get("title_es") and d.get("title_it")
        assert d["title_es"] != d["title_it"]
        assert d.get("difficulty")
        assert d.get("description")
        ctx["diag"] = d

    def test_diagnosis_lang_it(self, ctx):
        if "diag" not in ctx:
            pytest.skip("no diagnosis")
        d0 = ctx["diag"]
        r = requests.get(f"{API}/diagnoses/{d0['diagnosis_id']}?lang=it", headers=ctx["client"]["h"], timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        print("IT description:", d.get("description"))
        print("ES description:", d0.get("description"))
        assert d["view_language"] == "it"
        assert d["title"] == d0["title_it"]
        assert d["description"] and d["description"] != d0["description"]
        assert "i18n" not in d

    def test_diagnosis_lang_it_cached(self, ctx):
        if "diag" not in ctx:
            pytest.skip("no diagnosis")
        r = requests.get(f"{API}/diagnoses/{ctx['diag']['diagnosis_id']}?lang=it", headers=ctx["client"]["h"], timeout=30)
        assert r.status_code == 200
        assert r.json()["description"] != ctx["diag"]["description"]

    def test_diagnose_invalid_image_400(self, ctx):
        r = requests.post(f"{API}/diagnose", headers=ctx["client"]["h"], json={"image_base64": "notanimage", "language": "es"})
        assert r.status_code == 400


# ---- Specialist portfolio + review translations ----
class TestTranslations:
    def test_specialist_portfolio_caption(self, ctx):
        u = ctx["spec"]
        r = requests.post(f"{API}/specialists", headers=u["h"], json={"name": u["user"]["name"], "categories": ["plumbing"],
                                                                      "bio": "TEST bio", "phone": "+390111234567"})
        assert r.status_code == 200, r.text
        ctx["sid"] = r.json()["specialist_id"]
        r = requests.post(f"{API}/membership/revenuecat-sync", headers=u["h"], json={"plan": "yearly"})
        assert r.status_code == 200 and r.json()["active"] is True, r.text
        with open(IMG, "rb") as f:
            r = requests.post(f"{API}/upload", headers=u["h"], files={"file": ("leak.jpg", f, "image/jpeg")})
        assert r.status_code == 200, r.text
        cap = "Riparazione della perdita sotto il lavello della cucina"
        r = requests.post(f"{API}/specialists/me/portfolio", headers=u["h"], json={"image": r.json()["path"], "caption": cap}, timeout=120)
        assert r.status_code == 200, r.text
        r = requests.get(f"{API}/specialists/{ctx['sid']}", headers=ctx["client"]["h"])
        item = r.json()["portfolio"][0]
        print("CAPTION:", item)
        assert item["caption_it"] and item["caption_es"]
        assert item["caption_es"] != item["caption_it"]
        assert item["caption_es"] != cap

    def test_review_comment_translated(self, ctx):
        if "sid" not in ctx:
            pytest.skip("no specialist")
        c = ctx["client"]
        r = requests.post(f"{API}/conversations", headers=c["h"], json={"specialist_id": ctx["sid"]})
        assert r.status_code == 200, r.text
        cid = r.json()["conversation_id"]
        r = requests.post(f"{API}/conversations/{cid}/messages", headers=c["h"], json={"text": "Hola, necesito ayuda"})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/specialists/{ctx['sid']}", headers=c["h"]).json()["can_review"] is True
        comment = "Muy buen trabajo, rápido y limpio"
        r = requests.post(f"{API}/specialists/{ctx['sid']}/reviews", headers=c["h"], json={"rating": 5, "comment": comment}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        print("REVIEW:", d)
        assert "_id" not in d
        assert d["comment_es"] and d["comment_it"]
        assert d["comment_it"] != d["comment_es"]
        assert d["comment_it"] != comment
        rv = requests.get(f"{API}/specialists/{ctx['sid']}/reviews", headers=c["h"]).json()[0]
        assert rv["comment_it"] == d["comment_it"]
