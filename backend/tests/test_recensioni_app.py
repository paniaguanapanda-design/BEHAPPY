"""Reseñas de la app en la web: solo con cuenta, una por persona, estadisticas y ocultar desde el correo."""
import re

import pytest

from test_preregistro import api, clean_db, make_profile, register, server  # noqa: F401


@pytest.fixture
def mail(monkeypatch):
    sent = []

    async def fake_mail(to, subject, text, html):
        sent.append({"to": to, "subject": subject, "text": text})
        return True

    monkeypatch.delenv("WEB_PROXY_KEY", raising=False)
    monkeypatch.setattr(server, "send_email", fake_mail)
    return sent


async def web_login(api, mail, email):
    await api.post("/api/web/login/start", json={"email": email})
    code = re.search(r"\b(\d{6})\b", [m for m in mail if m["to"] == email][-1]["text"]).group(1)
    r = await api.post("/api/web/login/confirm", json={"email": email, "code": code})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def settle():
    import asyncio
    for _ in range(5):
        await asyncio.sleep(0.01)


async def test_needs_account_and_one_review_per_person(api, mail):
    r = await api.post("/api/web/app-reviews", json={"stars": 5, "satisfaction": 5, "recommend": True})
    assert r.status_code == 401
    await api.post("/api/auth/register", json={"email": "giulia@x.it", "password": "secret123", "name": "Giulia Bianchi"})
    w = await web_login(api, mail, "giulia@x.it")
    r = await api.post("/api/web/app-reviews", headers=w, json={"stars": 5, "satisfaction": 4, "recommend": True,
                                                                  "comment": "  Utile   e veloce "})
    assert r.status_code == 200 and r.json()["name"] == "Giulia B." and r.json()["comment"] == "Utile e veloce"
    await api.post("/api/web/app-reviews", headers=w, json={"stars": 3, "satisfaction": 3, "recommend": False})
    out = (await api.get("/api/web/app-reviews")).json()
    assert out["count"] == 1 and out["items"][0]["stars"] == 3 and out["recommend_pct"] == 0
    assert (await api.get("/api/web/app-reviews/mine", headers=w)).json()["review"]["stars"] == 3


async def test_stats_and_specialist_role(api, mail):
    h = await register(api, "mario@x.it")
    await make_profile(api, h)
    await api.post("/api/auth/register", json={"email": "anna@x.it", "password": "secret123", "name": "Anna"})
    for email, stars, sat, rec in (("mario@x.it", 4, 4, True), ("anna@x.it", 2, 2, False)):
        w = await web_login(api, mail, email)
        await api.post("/api/web/app-reviews", headers=w, json={"stars": stars, "satisfaction": sat, "recommend": rec})
    out = (await api.get("/api/web/app-reviews")).json()
    assert out["count"] == 2 and out["stars_avg"] == 3.0 and out["recommend_pct"] == 50
    assert out["satisfaction"] == [0, 1, 0, 1, 0]
    roles = {i["name"]: i["role"] for i in out["items"]}
    assert roles["Anna"] == "client" and "specialist" in roles.values()


async def test_admin_link_hides_review(api, mail):
    await api.post("/api/auth/register", json={"email": "troll@x.it", "password": "secret123", "name": "Troll"})
    w = await web_login(api, mail, "troll@x.it")
    rid = (await api.post("/api/web/app-reviews", headers=w, json={"stars": 1, "satisfaction": 1, "recommend": False,
                                                                     "comment": "spam spam"})).json()["id"]
    await settle()
    link = re.search(r"/api/admin/app-reviews/\S+", [m for m in mail if "recensione" in m["subject"]][-1]["text"]).group(0)
    t = link.split("t=")[1]
    assert (await api.post(f"/api/admin/app-reviews/{rid}/hide", data={"t": "bad"})).status_code == 403
    assert (await api.post(f"/api/admin/app-reviews/{rid}/hide", data={"t": t})).status_code == 200
    assert (await api.get("/api/web/app-reviews")).json()["count"] == 0
