"""Codigo de referido (?ref=...): se guarda al crear la cuenta y el admin ve registrados/activos por codigo."""
from test_preregistro import api, clean_db, server  # noqa: F401
from behappy import admin, core, security  # noqa: E402

ADMIN = {"X-Admin-Token": "test-admin-token"}


async def signup(api, email, ref=None):
    body = {"email": email, "password": "secret123", "name": "Ana"}
    if ref is not None:
        body["ref"] = ref
    r = await api.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}, r.json()["user"]["user_id"]


async def google(api, monkeypatch, email, ref=None):
    from google.oauth2 import id_token
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *a, **k: {
        "aud": "test-client", "email": email, "email_verified": True, "name": "G"})
    body = {"id_token": "fake"}
    if ref is not None:
        body["ref"] = ref
    r = await api.post("/api/auth/google", json=body)
    assert r.status_code == 200, r.text
    return r.json()["user"]["user_id"]


async def stored(uid):
    return await core.db.users.find_one({"user_id": uid})


def test_clean_ref():
    assert security.clean_ref("  Silvano ") == "silvano"
    assert security.clean_ref("ferr-sansalvario_2") == "ferr-sansalvario_2"
    for bad in [None, "", "a", "-abc", "con espacio", "x" * 41, "<script>", "ref$1"]:
        assert security.clean_ref(bad) is None


async def test_register_saves_ref(api):
    _, uid = await signup(api, "a@example.com", ref="Silvano")
    u = await stored(uid)
    assert u["referido_por"] == "silvano" and u["referido_en"]


async def test_register_without_or_bad_ref(api):
    _, uid = await signup(api, "b@example.com")
    assert "referido_por" not in await stored(uid)
    _, uid = await signup(api, "c@example.com", ref="no valido!")
    assert "referido_por" not in await stored(uid)


async def test_google_new_user_saves_ref_existing_user_does_not_change(api, monkeypatch):
    uid = await google(api, monkeypatch, "g@example.com", ref="maria")
    assert (await stored(uid))["referido_por"] == "maria"
    again = await google(api, monkeypatch, "g@example.com", ref="otro")
    assert again == uid and (await stored(uid))["referido_por"] == "maria"  # no se puede cambiar despues


async def test_ref_not_exposed_to_user(api):
    h, _ = await signup(api, "d@example.com", ref="maria")
    assert "referido_por" not in (await api.get("/api/auth/me", headers=h)).json()


async def test_admin_report(api, monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_TOKEN", "test-admin-token")
    assert (await api.get("/api/admin/referidos")).status_code == 403
    _, u1 = await signup(api, "m1@example.com", ref="maria")
    _, u2 = await signup(api, "m2@example.com", ref="maria")
    _, u3 = await signup(api, "s1@example.com", ref="silvano")
    await signup(api, "x@example.com")
    for uid, status in ((u1, "ready"), (u1, "ready"), (u3, None)):  # activo = al menos 1 diagnostico terminado
        doc = {"diagnosis_id": core.new_id("diag"), "user_id": uid}
        if status:
            doc["status"] = status
        await core.db.diagnoses.insert_one(doc)
    for status in ("processing", "failed"):  # no cuentan
        await core.db.diagnoses.insert_one({"diagnosis_id": core.new_id("diag"), "user_id": u2, "status": status})
    r = await api.get("/api/admin/referidos", headers=ADMIN)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = {row["codigo"]: row for row in data["codigos"]}
    assert rows["maria"] == {"codigo": "maria", "registrados": 2, "activos": 1}
    assert rows["silvano"] == {"codigo": "silvano", "registrados": 1, "activos": 1}
    assert data["total_registrados"] == 3 and data["total_activos"] == 2
    hoy = core.now().strftime("%Y-%m-%d")
    assert (await api.get(f"/api/admin/referidos?desde={hoy}&hasta={hoy}", headers=ADMIN)).json()["total_registrados"] == 3
    assert (await api.get("/api/admin/referidos?desde=2099-01-01", headers=ADMIN)).json()["codigos"] == []
    assert (await api.get("/api/admin/referidos?desde=ayer", headers=ADMIN)).status_code == 400
