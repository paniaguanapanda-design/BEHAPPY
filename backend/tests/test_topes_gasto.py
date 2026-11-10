"""Topes diarios de gasto: Gemini y Google Maps no pasan del maximo del dia aunque haya muchas cuentas."""
import pytest

from test_preregistro import api, clean_db, register, server  # noqa: F401


@pytest.fixture
def mail(monkeypatch):
    sent = []

    async def fake_mail(to, subject, text, html):
        sent.append(subject)
        return True

    monkeypatch.setattr(server, "send_email", fake_mail)
    return sent


async def test_gemini_cap_blocks_diagnosis_and_warns_admin(api, mail, monkeypatch):
    monkeypatch.setitem(server.DAILY_CAPS, "gemini", 5)
    for _ in range(5):
        await server.spend_daily("gemini")
    import asyncio
    await asyncio.sleep(0.01)
    assert any("80%" in s for s in mail) and any("alcanzado" in s for s in mail)
    h = await register(api, "a@x.it")
    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "JPEG")
    r = await api.post("/api/diagnose", headers=h, json={"image_base64": base64.b64encode(buf.getvalue()).decode()})
    assert r.status_code == 200
    did = r.json()["diagnosis_id"]
    for _ in range(50):  # the analysis runs in the background
        d = (await api.get(f"/api/diagnoses/{did}", headers=h)).json()
        if d.get("status") != "processing":
            break
        await asyncio.sleep(0.02)
    assert d["status"] == "failed" and "domani" in d["error"]


async def test_maps_cap_falls_back_without_spending(api, mail, monkeypatch):
    monkeypatch.setitem(server.DAILY_CAPS, "maps", 0)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    out = await server.places_check("Ferramenta", "Via Roma 1", "10121", "Torino")
    assert out == {"ok": None}
