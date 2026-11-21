"""Concorso «Natale senza guasti»: el usuario marca un diagnostico como resuelto y el admin saca la lista de Torino."""
from test_preregistro import PROVINCES, api, clean_db, make_profile, register, server  # noqa: F401

ADMIN = {"X-Admin-Token": "test-admin-token"}


async def diag(uid, status="ready", created=None):
    did = server.new_id("diag")
    await server.db.diagnoses.insert_one({"diagnosis_id": did, "user_id": uid, "status": status,
                                          "created_at": created or server.iso(server.now())})
    return did


async def me(api, h):
    return (await api.get("/api/auth/me", headers=h)).json()["user_id"]


async def test_mark_resolved_saves_once_with_province(api):
    h = await register(api, "ana@example.com")  # zona en Torino
    did = await diag(await me(api, h))
    r = await api.post(f"/api/diagnoses/{did}/resolved", headers=h)
    assert r.status_code == 200, r.text
    first = r.json()["resolved_at"]
    again = await api.post(f"/api/diagnoses/{did}/resolved", headers=h)
    assert again.json()["resolved_at"] == first  # la primera vez manda
    d = await server.db.diagnoses.find_one({"diagnosis_id": did})
    assert d["resolved_province"] == "TO"
    assert (await api.get(f"/api/diagnoses/{did}", headers=h)).json()["resolved_at"] == first


async def test_cannot_resolve_others_or_unfinished(api):
    a = await register(api, "a@example.com")
    b = await register(api, "b@example.com")
    did = await diag(await me(api, a))
    assert (await api.post(f"/api/diagnoses/{did}/resolved", headers=b)).status_code == 403
    pending = await diag(await me(api, a), status="processing")
    assert (await api.post(f"/api/diagnoses/{pending}/resolved", headers=a)).status_code == 409
    assert (await api.post("/api/diagnoses/nope/resolved", headers=a)).status_code == 404


async def test_admin_list_only_torino_users_resolved_in_period(api, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_TOKEN", "test-admin-token")
    assert (await api.get("/api/admin/concorso?desde=2026-01-01&hasta=2099-01-01")).status_code == 403
    ok = await register(api, "ok@example.com")
    for _ in range(2):  # dos diagnosticos resueltos cuentan como una sola participacion
        await api.post(f"/api/diagnoses/{await diag(await me(api, ok))}/resolved", headers=ok)
    not_resolved = await register(api, "nores@example.com")
    await diag(await me(api, not_resolved))
    milano_lat, milano_lng = PROVINCES["MI"][1], PROVINCES["MI"][2]
    milano = await register(api, "mi@example.com", at=(milano_lat, milano_lng))
    await api.post(f"/api/diagnoses/{await diag(await me(api, milano))}/resolved", headers=milano)
    spec = await register(api, "spec@example.com")
    await make_profile(api, spec)  # los especialistas quedan fuera
    await api.post(f"/api/diagnoses/{await diag(await me(api, spec))}/resolved", headers=spec)
    old = await register(api, "old@example.com")
    await api.post(f"/api/diagnoses/{await diag(await me(api, old), created='2020-01-01T00:00:00+00:00')}/resolved", headers=old)

    hoy = server.now().strftime("%Y-%m-%d")
    r = await api.get(f"/api/admin/concorso?desde={hoy}&hasta={hoy}", headers=ADMIN)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["partecipanti"] == 1
    row = data["lista"][0]
    assert row["email"] == "ok@example.com" and row["diagnosi_risolte"] == 2 and row["n"] == 1
    csv_r = await api.get(f"/api/admin/concorso?desde={hoy}&hasta={hoy}&formato=csv", headers=ADMIN)
    assert csv_r.status_code == 200 and "ok@example.com" in csv_r.text and csv_r.text.startswith("n,user_id")
    assert (await api.get("/api/admin/concorso?desde=ieri&hasta=oggi", headers=ADMIN)).status_code == 400
