"""BE HAPPY iteration: diagnosis difficulty/translation, specialists showcase, portfolio captions, reviews rules.
Test data is saved to /tmp/t1_ctx.json for UI testing; run tests/cleanup_test_data.py afterwards."""
import os
import io
import json
import base64
import uuid
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
API = f"{BASE_URL}/api"
CTX = {}
CATS = ["plumbing", "electrical", "carpentry", "hvac", "appliances"]


def _img_b64(size=800):
    im = Image.open("/tmp/leak.jpg").convert("RGB")
    im.thumbnail((size, size))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=70)
    return base64.b64encode(b.getvalue()).decode()


def _register(prefix):
    email = f"test_{prefix}_{uuid.uuid4().hex[:6]}@fixai.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "test123", "name": f"TEST {prefix}"})
    assert r.status_code == 200, r.text
    d = r.json()
    CTX.setdefault("emails", []).append(email)
    return {"email": email, "token": d["session_token"], "user": d["user"],
            "h": {"Authorization": f"Bearer {d['session_token']}"}}


@pytest.fixture(scope="module")
def users():
    spec = _register("spec")
    client = _register("client")
    spec2 = _register("spec2")
    yield {"spec": spec, "client": client, "spec2": spec2}
    CTX["spec"] = {"email": spec["email"], "token": spec["token"]}
    CTX["client"] = {"email": client["email"], "token": client["token"], "user_id": client["user"]["user_id"]}
    with open("/tmp/t1_ctx.json", "w") as f:
        json.dump(CTX, f)


# --- Diagnosis ---
class TestDiagnosis:
    def test_diagnose_real_image(self, users):
        r = requests.post(f"{API}/diagnose", headers=users["client"]["h"],
                          json={"image_base64": _img_b64(), "language": "es"}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        print("DIAG:", d.get("difficulty"), d.get("category"), d.get("title_es"), d.get("title_it"))
        assert d["difficulty"] in ("easy", "medium", "expert")
        assert d["category"] in CATS
        assert d["title_es"] and d["title_it"]
        assert "_id" not in d
        if d["difficulty"] == "expert":
            assert d["steps"] == [] and d["materials"] == [] and d["tools"] == []
        CTX["diag_id"] = d["diagnosis_id"]
        CTX["diag_desc_es"] = d["description"]

    def test_get_diagnosis_translated_it(self, users):
        if "diag_id" not in CTX:
            pytest.skip("no diagnosis")
        r = requests.get(f"{API}/diagnoses/{CTX['diag_id']}?lang=it", headers=users["client"]["h"], timeout=120)
        assert r.status_code == 200
        d = r.json()
        print("IT desc:", d["description"][:120])
        assert d["view_language"] == "it"
        assert d["title"] == d["title_it"]
        assert d["description"] != CTX["diag_desc_es"]
        assert "i18n" not in d

    def test_get_diagnosis_es_original(self, users):
        if "diag_id" not in CTX:
            pytest.skip("no diagnosis")
        r = requests.get(f"{API}/diagnoses/{CTX['diag_id']}?lang=es", headers=users["client"]["h"], timeout=60)
        assert r.status_code == 200
        assert r.json()["description"] == CTX["diag_desc_es"]

    def test_diagnosis_forbidden_other_user(self, users):
        if "diag_id" not in CTX:
            pytest.skip("no diagnosis")
        r = requests.get(f"{API}/diagnoses/{CTX['diag_id']}", headers=users["spec"]["h"])
        assert r.status_code == 403


# --- Specialists ---
class TestSpecialists:
    def test_categories_exact_5(self):
        r = requests.get(f"{API}/categories")
        assert r.status_code == 200
        assert sorted(r.json()) == sorted(CATS)

    def test_create_requires_valid_categories(self, users):
        r = requests.post(f"{API}/specialists", headers=users["spec"]["h"],
                          json={"name": "TEST Bad", "categories": ["general"], "phone": "+39111"})
        assert r.status_code == 400
        r = requests.post(f"{API}/specialists", headers=users["spec"]["h"], json={"name": "TEST Bad", "phone": "+39111"})
        assert r.status_code == 422

    def test_create_specialist_multi_trade(self, users):
        r = requests.post(f"{API}/specialists", headers=users["spec"]["h"],
                          json={"name": "TEST Zorro Fontaniere", "categories": ["plumbing", "hvac", "plumbing"],
                                "bio": "Riparo tubi e caldaie a Torino", "phone": "+393331112222"})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["categories"] == ["plumbing", "hvac"]
        for k in ("city", "years_experience", "hourly_rate", "lat", "lng"):
            assert k not in s, k
        assert s["rating_avg"] is None
        CTX["spec_id"] = s["specialist_id"]

    def test_not_listed_without_membership_or_photo(self, users):
        r = requests.get(f"{API}/specialists", headers=users["client"]["h"])
        assert CTX["spec_id"] not in [s["specialist_id"] for s in r.json()]
        r = requests.post(f"{API}/membership/revenuecat-sync", headers=users["spec"]["h"], json={"plan": "yearly"})
        assert r.status_code == 200, r.text
        r = requests.get(f"{API}/specialists", headers=users["client"]["h"])
        assert CTX["spec_id"] not in [s["specialist_id"] for s in r.json()], "listed without portfolio photo"

    def test_portfolio_requires_caption(self, users):
        r = requests.post(f"{API}/specialists/me/portfolio", headers=users["spec"]["h"],
                          json={"image": "data:image/jpeg;base64," + _img_b64(300), "caption": "  "})
        assert r.status_code == 400

    def test_portfolio_caption_both_langs(self, users):
        r = requests.post(f"{API}/specialists/me/portfolio", headers=users["spec"]["h"],
                          json={"image": "data:image/jpeg;base64," + _img_b64(300), "caption": "Riparazione perdita sotto il lavandino"},
                          timeout=60)
        assert r.status_code == 200, r.text
        it = r.json()
        print("captions:", it["caption_es"], "|", it["caption_it"])
        assert it["caption_es"] and it["caption_it"]
        assert it["caption_es"] != it["caption_it"]

    def test_listed_after_photo_and_filters(self, users):
        h = users["client"]["h"]
        ids = lambda p: [s["specialist_id"] for s in requests.get(f"{API}/specialists", headers=h, params=p).json()]
        assert CTX["spec_id"] in ids({})
        assert CTX["spec_id"] in ids({"category": "hvac"})
        assert CTX["spec_id"] in ids({"category": "plumbing"})
        assert CTX["spec_id"] not in ids({"category": "electrical"})
        assert CTX["spec_id"] in ids({"q": "zorro"})
        assert CTX["spec_id"] not in ids({"q": "caldaie"}), "q matched bio"
        assert CTX["spec_id"] not in ids({"q": "Torino"}), "q matched city"

    def test_list_item_shape(self, users):
        items = requests.get(f"{API}/specialists", headers=users["client"]["h"]).json()
        s = [x for x in items if x["specialist_id"] == CTX["spec_id"]][0]
        assert s["rating_avg"] is None
        assert s["membership_active"] is True
        assert "verification_document" not in s and "document_number" not in s


# --- Reviews ---
class TestReviews:
    def test_review_forbidden_before_message(self, users):
        sid = CTX["spec_id"]
        prof = requests.get(f"{API}/specialists/{sid}", headers=users["client"]["h"]).json()
        assert prof["can_review"] is False
        r = requests.post(f"{API}/specialists/{sid}/reviews", headers=users["client"]["h"], json={"rating": 5})
        assert r.status_code == 403

    def test_review_forbidden_conv_without_message(self, users):
        sid = CTX["spec_id"]
        r = requests.post(f"{API}/conversations", headers=users["client"]["h"], json={"specialist_id": sid})
        assert r.status_code == 200, r.text
        CTX["conv_id"] = r.json()["conversation_id"]
        r = requests.post(f"{API}/specialists/{sid}/reviews", headers=users["client"]["h"], json={"rating": 5})
        assert r.status_code == 403

    def test_self_review_400(self, users):
        r = requests.post(f"{API}/specialists/{CTX['spec_id']}/reviews", headers=users["spec"]["h"], json={"rating": 5})
        assert r.status_code == 400

    def test_review_after_message_then_duplicate(self, users):
        sid, h = CTX["spec_id"], users["client"]["h"]
        r = requests.post(f"{API}/conversations/{CTX['conv_id']}/messages", headers=h, json={"text": "Ciao, perdita in cucina"})
        assert r.status_code == 200
        assert requests.get(f"{API}/specialists/{sid}", headers=h).json()["can_review"] is True
        r = requests.post(f"{API}/specialists/{sid}/reviews", headers=h, json={"rating": 4, "comment": "Molto gentile"})
        assert r.status_code == 200, r.text
        assert r.json()["rating"] == 4
        r = requests.post(f"{API}/specialists/{sid}/reviews", headers=h, json={"rating": 5})
        assert r.status_code == 400
        prof = requests.get(f"{API}/specialists/{sid}", headers=h).json()
        assert prof["reviews_count"] == 1
        assert prof["rating_avg"] is None
        assert prof["can_review"] is False

    def test_rating_out_of_range(self, users):
        r = requests.post(f"{API}/specialists/{CTX['spec_id']}/reviews", headers=users["spec2"]["h"], json={"rating": 6})
        assert r.status_code == 422
