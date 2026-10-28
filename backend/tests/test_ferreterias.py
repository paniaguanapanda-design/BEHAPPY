"""Ferreterias: inscripcion desde la web, verificacion automatica (VIES + Google Maps) y mapa en la app."""
import re

import pytest

from test_preregistro import api, clean_db, register, server  # noqa: F401


def make_piva(base="0123456789"):
    total = 0
    for i, ch in enumerate(base):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
    return base + str((10 - total % 10) % 10)


PIVA = make_piva()
TORINO = {"lat": 45.0703, "lng": 7.6869}


def form(**extra):
    return {"name": "Ferramenta Rossi", "owner_name": "Mario Rossi", "email": "mario@ferramenta.it",
            "phone": "+39 011 123456", "whatsapp": "+39 333 1234567", "address": "Via Roma 10", "cap": "10121",
            "city": "Torino", "province": "TO", "piva": PIVA, "hours": "Lun-Sab 8:30-19:30",
            "categories": ["plumbing", "electrical"], "accept_terms": True, "language": "it", **extra}


@pytest.fixture
def world(monkeypatch):
    """Simula correo, VIES, Google Maps y geocodificacion."""
    state = {"mail": [], "vies": {"ok": True, "name": "ROSSI MARIO", "address": "VIA ROMA 10 10121 TORINO TO"},
             "google": {"ok": True, "place_id": "p1", "types": ["hardware_store"], "location": TORINO},
             "geo": TORINO}

    async def fake_send(to, subject, text, html):
        state["mail"].append({"to": to, "subject": subject, "text": text})
        return True

    async def fake_vies(piva):
        return dict(state["vies"])

    async def fake_places(*a):
        return dict(state["google"])

    async def fake_geo(*a):
        return state["geo"]

    monkeypatch.setenv("RESEND_API_KEY", "test")
    monkeypatch.setenv("EMAIL_FROM", "Be Happy <no-reply@be-happyapp.com>")
    monkeypatch.delenv("WEB_PROXY_KEY", raising=False)
    monkeypatch.setattr(server, "send_email", fake_send)
    monkeypatch.setattr(server, "vies_check", fake_vies)
    monkeypatch.setattr(server, "places_check", fake_places)
    monkeypatch.setattr(server, "geocode", fake_geo)
    server._store_maint_last = 1e18  # el mantenimiento automatico no corre durante las pruebas
    return state


def last_code(state):
    return re.search(r"\b(\d{6})\b", state["mail"][-1]["text"]).group(1)


async def apply_and_confirm(api, state, **extra):
    r = await api.post("/api/stores/apply", json=form(**extra))
    assert r.status_code == 200, r.text
    sid = r.json()["store_id"]
    r = await api.post(f"/api/stores/{sid}/confirm", json={"code": last_code(state)})
    assert r.status_code == 200, r.text
    return sid, r.json()["status"]


async def nearby(api, **params):
    r = await api.get("/api/stores/nearby", params={"lat": 45.07, "lng": 7.68, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_piva_checksum():
    assert server.piva_valid(PIVA)
    assert not server.piva_valid(PIVA[:-1] + str((int(PIVA[-1]) + 1) % 10))
    assert not server.piva_valid("00000000000")
    assert not server.piva_valid("123")


async def test_all_checks_pass_store_goes_on_map(api, world):
    sid, status = await apply_and_confirm(api, world)
    assert status == "approved"
    items = await nearby(api)
    assert [s["store_id"] for s in items] == [sid]
    s = items[0]
    assert s["name"] == "Ferramenta Rossi" and s["distance_km"] < 2 and "piva" not in s and "email" not in s
    assert "sulla mappa" in world["mail"][-1]["subject"]


async def test_not_on_map_before_email_code(api, world):
    r = await api.post("/api/stores/apply", json=form())
    assert r.status_code == 200
    assert await nearby(api) == []


async def test_wrong_code_and_attempt_limit(api, world):
    r = await api.post("/api/stores/apply", json=form())
    sid, code = r.json()["store_id"], last_code(world)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert (await api.post(f"/api/stores/{sid}/confirm", json={"code": wrong})).status_code == 400
    assert (await api.post(f"/api/stores/{sid}/confirm", json={"code": code})).status_code == 400


async def test_not_a_hardware_store_goes_to_review(api, world):
    world["google"] = {"ok": False, "found": [["bar", "restaurant"]]}
    sid, status = await apply_and_confirm(api, world)
    assert status == "in_review"
    assert await nearby(api) == []
    s = await server.db.stores.find_one({"store_id": sid})
    assert s["review_reasons"] == ["google_not_hardware_store"]


async def test_inactive_vat_goes_to_review(api, world):
    world["vies"] = {"ok": False}
    _, status = await apply_and_confirm(api, world)
    assert status == "in_review"


async def test_vat_in_other_city_goes_to_review(api, world):
    world["vies"] = {"ok": True, "name": "X", "address": "VIA MILANO 1 20121 MILANO MI"}
    sid, status = await apply_and_confirm(api, world)
    assert status == "in_review"
    assert (await server.db.stores.find_one({"store_id": sid}))["review_reasons"] == ["vies_address_mismatch"]


async def test_invalid_form_rejected(api, world):
    r = await api.post("/api/stores/apply", json=form(piva="12345678901", accept_terms=False, cap="1012", categories=[]))
    assert r.status_code == 400
    fields = r.json()["detail"]["fields"]
    assert {"piva", "accept_terms", "cap", "categories"} <= set(fields)
    assert world["mail"] == []


async def test_duplicate_store_rejected(api, world):
    await apply_and_confirm(api, world)
    r = await api.post("/api/stores/apply", json=form(email="otro@ferramenta.it"))
    assert r.status_code == 409


async def test_requires_web_proxy_key_when_configured(api, world, monkeypatch):
    monkeypatch.setenv("WEB_PROXY_KEY", "k" * 32)
    assert (await api.post("/api/stores/apply", json=form())).status_code == 403
    r = await api.post("/api/stores/apply", json=form(), headers={"X-BeHappy-Proxy-Key": "k" * 32})
    assert r.status_code == 200


async def test_three_reports_hide_store(api, world):
    sid, _ = await apply_and_confirm(api, world)
    for i in range(3):
        h = await register(api, f"cliente{i}@example.com")
        r = await api.post("/api/reports", headers=h, json={"target_type": "store", "target_id": sid, "reason": "fraud"})
        assert r.status_code == 200
        if i < 2:
            assert len(await nearby(api)) == 1
    assert await nearby(api) == []


async def test_category_first_then_distance(api, world):
    near_sid, _ = await apply_and_confirm(api, world, categories=["electrical"])
    world["google"] = {**world["google"], "location": {"lat": 45.10, "lng": 7.70}}
    far_sid, _ = await apply_and_confirm(api, world, name="Idraulica Bianchi", address="Via Po 3", categories=["plumbing"])
    assert [s["store_id"] for s in await nearby(api)] == [near_sid, far_sid]
    assert [s["store_id"] for s in await nearby(api, category="plumbing")] == [far_sid, near_sid]


async def test_admin_digest_and_one_click_decision(api, world, monkeypatch):
    world["google"] = {"ok": False, "found": []}
    sid, _ = await apply_and_confirm(api, world)
    monkeypatch.setenv("ADMIN_EMAIL", "admin@be-happyapp.com")
    await server.store_maintenance(force=True)
    digest = world["mail"][-1]
    assert digest["to"] == "admin@be-happyapp.com" and "Ferramenta Rossi" in digest["text"]
    link = re.search(r"Aprobar: \S*(/api/admin/stores/\S+)", digest["text"]).group(1)
    page = await api.get(link)
    assert page.status_code == 200 and "<form" in page.text
    assert await nearby(api) == []  # abrir el enlace no aprueba nada
    token = re.search(r"t=([0-9a-f]+)", link).group(1)
    r = await api.post(link.split("?")[0] + "?d=approve", data={"t": token})
    assert r.status_code == 200
    assert [s["store_id"] for s in await nearby(api)] == [sid]
    bad = await api.post(link.split("?")[0] + "?d=approve", data={"t": "0" * 64})
    assert bad.status_code == 403


async def test_unavailable_checks_are_retried(api, world):
    world["vies"] = {"ok": None}
    sid, status = await apply_and_confirm(api, world)
    assert status == "in_review"
    world["vies"] = {"ok": True, "name": "X", "address": "VIA ROMA 10 10121 TORINO"}
    await server.store_maintenance(force=True)
    assert (await server.db.stores.find_one({"store_id": sid}))["status"] == "approved"
