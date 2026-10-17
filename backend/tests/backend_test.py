"""FixAI backend regression tests - full flow."""
import os
import io
import base64
import time
import uuid
import requests
import pytest
from PIL import Image

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://fixmyhome-cam.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

SPEC_EMAIL = "specialist1@fixai.app"
SPEC_PWD = "specialist123"


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    r.raise_for_status()
    return r.json()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def specialist_sess():
    return _login(SPEC_EMAIL, SPEC_PWD)


@pytest.fixture(scope="module")
def client_sess():
    # fresh client per run
    email = f"TEST_client_{uuid.uuid4().hex[:8]}@fixai.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "test123", "name": "Test Client"}, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------- Auth ----------
class TestAuth:
    def test_register_login_me(self):
        email = f"test_u_{uuid.uuid4().hex[:8]}@fixai.app"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "test123", "name": "T"})
        assert r.status_code == 200, r.text
        tok = r.json()["session_token"]
        assert r.json()["user"]["email"] == email.lower()
        # login
        r2 = requests.post(f"{API}/auth/login", json={"email": email, "password": "test123"})
        assert r2.status_code == 200
        # me
        r3 = requests.get(f"{API}/auth/me", headers=_hdr(tok))
        assert r3.status_code == 200
        assert r3.json()["email"] == email

    def test_login_bad(self):
        r = requests.post(f"{API}/auth/login", json={"email": "nope@x.com", "password": "x"})
        assert r.status_code == 401

    def test_register_short_pwd(self):
        r = requests.post(f"{API}/auth/register", json={"email": "a@b.com", "password": "123", "name": "x"})
        assert r.status_code == 400

    def test_me_unauth(self):
        assert requests.get(f"{API}/auth/me").status_code == 401


# ---------- Specialists ----------
class TestSpecialists:
    def test_list_seeded(self, client_sess):
        r = requests.get(f"{API}/specialists", headers=_hdr(client_sess["session_token"]))
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 4
        # verified ordered first
        emails_cats = {i["category"] for i in items}
        assert "plumbing" in emails_cats

    def test_filter_category(self, client_sess):
        r = requests.get(f"{API}/specialists?category=electrical", headers=_hdr(client_sess["session_token"]))
        assert r.status_code == 200
        for s in r.json():
            assert s["category"] == "electrical"

    def test_search_q(self, client_sess):
        r = requests.get(f"{API}/specialists?q=Marco", headers=_hdr(client_sess["session_token"]))
        assert r.status_code == 200
        assert any("Marco" in s["name"] for s in r.json())

    def test_get_one(self, client_sess, specialist_sess):
        sid = specialist_sess["user"]["specialist_id"]
        r = requests.get(f"{API}/specialists/{sid}", headers=_hdr(client_sess["session_token"]))
        assert r.status_code == 200
        assert r.json()["specialist_id"] == sid

    def test_reviews_list(self, client_sess, specialist_sess):
        sid = specialist_sess["user"]["specialist_id"]
        r = requests.get(f"{API}/specialists/{sid}/reviews", headers=_hdr(client_sess["session_token"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_add_review_and_agg(self, client_sess, specialist_sess):
        sid = specialist_sess["user"]["specialist_id"]
        tok = client_sess["session_token"]
        r = requests.post(f"{API}/specialists/{sid}/reviews", json={"rating": 5, "comment": "Great", "recommend": True}, headers=_hdr(tok))
        assert r.status_code == 200
        # check aggregation updated
        r2 = requests.get(f"{API}/specialists/{sid}", headers=_hdr(tok))
        assert r2.json()["reviews_count"] >= 1

    def test_self_review_forbidden(self, specialist_sess):
        sid = specialist_sess["user"]["specialist_id"]
        tok = specialist_sess["session_token"]
        r = requests.post(f"{API}/specialists/{sid}/reviews", json={"rating": 5}, headers=_hdr(tok))
        assert r.status_code == 400

    def test_register_as_specialist(self):
        # fresh user becomes specialist
        email = f"TEST_sp_{uuid.uuid4().hex[:8]}@fixai.app"
        reg = requests.post(f"{API}/auth/register", json={"email": email, "password": "test123", "name": "SpecX"}).json()
        tok = reg["session_token"]
        payload = {"name": "SpecX", "category": "painting", "bio": "pro", "phone": "+391234", "city": "Milano", "years_experience": 3}
        r = requests.post(f"{API}/specialists", json=payload, headers=_hdr(tok))
        assert r.status_code == 200, r.text
        sid = r.json()["specialist_id"]
        # me endpoint reflects role
        me = requests.get(f"{API}/auth/me", headers=_hdr(tok)).json()
        assert me["role"] == "specialist"
        assert me["specialist_id"] == sid
        # portfolio add/delete
        pf = requests.post(f"{API}/specialists/me/portfolio", json={"image": "x.jpg", "caption": "a"}, headers=_hdr(tok))
        assert pf.status_code == 200
        item_id = pf.json()["item_id"]
        rd = requests.delete(f"{API}/specialists/me/portfolio/{item_id}", headers=_hdr(tok))
        assert rd.status_code == 200
        # verify
        rv = requests.post(f"{API}/specialists/me/verify", json={"document_image": "doc.jpg", "document_number": "ABC12345"}, headers=_hdr(tok))
        assert rv.status_code == 200
        assert rv.json()["verified"] is True


# ---------- Upload / Files ----------
def _make_jpeg_bytes():
    img = Image.new("RGB", (120, 80), (100, 150, 200))
    for x in range(120):
        for y in range(80):
            img.putpixel((x, y), ((x * 2) % 255, (y * 3) % 255, (x + y) % 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


class TestUpload:
    def test_upload_and_fetch(self, client_sess):
        tok = client_sess["session_token"]
        data = _make_jpeg_bytes()
        r = requests.post(f"{API}/upload", headers=_hdr(tok),
                          files={"file": ("test.jpg", data, "image/jpeg")})
        assert r.status_code == 200, r.text
        path = r.json()["path"]
        # fetch with query token
        rf = requests.get(f"{API}/files/{path}?token={tok}")
        assert rf.status_code == 200
        assert len(rf.content) > 0

    def test_upload_unauth(self):
        r = requests.post(f"{API}/upload", files={"file": ("a.jpg", b"x", "image/jpeg")})
        assert r.status_code == 401


# ---------- Diagnose (slow AI call) ----------
class TestDiagnose:
    def test_diagnose_and_list(self, client_sess):
        tok = client_sess["session_token"]
        img_b64 = base64.b64encode(_make_jpeg_bytes()).decode()
        r = requests.post(f"{API}/diagnose", json={"image_base64": img_b64, "language": "es"},
                          headers=_hdr(tok), timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["title", "category", "difficulty", "steps", "materials", "diagnosis_id"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["steps"], list)
        did = d["diagnosis_id"]
        # list
        lst = requests.get(f"{API}/diagnoses", headers=_hdr(tok))
        assert lst.status_code == 200
        assert any(x["diagnosis_id"] == did for x in lst.json())
        # get one
        one = requests.get(f"{API}/diagnoses/{did}", headers=_hdr(tok))
        assert one.status_code == 200
        assert one.json()["diagnosis_id"] == did

    def test_diagnose_bad_image(self, client_sess):
        tok = client_sess["session_token"]
        r = requests.post(f"{API}/diagnose", json={"image_base64": "@@@notb64@@@", "language": "es"},
                          headers=_hdr(tok), timeout=30)
        assert r.status_code == 400


# ---------- Conversations / messages / requests ----------
class TestChatAndRequests:
    def test_create_conv_and_message(self, client_sess, specialist_sess):
        tok = client_sess["session_token"]
        sid = specialist_sess["user"]["specialist_id"]
        r = requests.post(f"{API}/conversations", json={"specialist_id": sid}, headers=_hdr(tok))
        assert r.status_code == 200
        cid = r.json()["conversation_id"]
        # send msg
        m = requests.post(f"{API}/conversations/{cid}/messages", json={"text": "hello"}, headers=_hdr(tok))
        assert m.status_code == 200
        # list
        lst = requests.get(f"{API}/conversations/{cid}/messages", headers=_hdr(tok))
        assert lst.status_code == 200
        assert any(x["text"] == "hello" for x in lst.json())
        # conversations list
        cl = requests.get(f"{API}/conversations", headers=_hdr(tok))
        assert cl.status_code == 200
        assert any(c["conversation_id"] == cid for c in cl.json())

    def test_empty_message_rejected(self, client_sess, specialist_sess):
        tok = client_sess["session_token"]
        sid = specialist_sess["user"]["specialist_id"]
        conv = requests.post(f"{API}/conversations", json={"specialist_id": sid}, headers=_hdr(tok)).json()
        r = requests.post(f"{API}/conversations/{conv['conversation_id']}/messages", json={"text": "  "}, headers=_hdr(tok))
        assert r.status_code == 400

    def test_create_request_and_status_flow(self, client_sess, specialist_sess):
        ctok = client_sess["session_token"]
        stok = specialist_sess["session_token"]
        sid = specialist_sess["user"]["specialist_id"]
        r = requests.post(f"{API}/requests", json={"specialist_id": sid, "description": "fix leak", "address": "street 1"}, headers=_hdr(ctok))
        assert r.status_code == 200, r.text
        rid = r.json()["request_id"]
        cid = r.json()["conversation_id"]
        # [REQUEST] message auto-pushed
        msgs = requests.get(f"{API}/conversations/{cid}/messages", headers=_hdr(ctok)).json()
        assert any("[REQUEST]" in m["text"] for m in msgs)
        # list requests both sides
        assert any(x["request_id"] == rid for x in requests.get(f"{API}/requests", headers=_hdr(ctok)).json())
        assert any(x["request_id"] == rid for x in requests.get(f"{API}/requests", headers=_hdr(stok)).json())
        # specialist accepts
        p = requests.patch(f"{API}/requests/{rid}", json={"status": "accepted"}, headers=_hdr(stok))
        assert p.status_code == 200
        assert p.json()["status"] == "accepted"
        # client cannot accept
        bad = requests.patch(f"{API}/requests/{rid}", json={"status": "accepted"}, headers=_hdr(ctok))
        assert bad.status_code == 403
        # client cancels
        c = requests.patch(f"{API}/requests/{rid}", json={"status": "cancelled"}, headers=_hdr(ctok))
        assert c.status_code == 200
        # specialist completes -> jobs_completed inc
        before = requests.get(f"{API}/specialists/{sid}", headers=_hdr(ctok)).json()["jobs_completed"]
        comp = requests.patch(f"{API}/requests/{rid}", json={"status": "completed"}, headers=_hdr(stok))
        assert comp.status_code == 200
        after = requests.get(f"{API}/specialists/{sid}", headers=_hdr(ctok)).json()["jobs_completed"]
        assert after == before + 1
