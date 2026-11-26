"""Codigo de invitacion propio: cada persona tiene su enlace y los registros con el quedan contados a su nombre."""
from test_preregistro import api, clean_db, server  # noqa: F401
from test_referidos import signup, stored  # noqa: F401
from behappy import core  # noqa: E402


async def test_invite_code_is_stable_and_attributes_signups(api):
    h, _uid = await signup(api, "invita@test.com")
    r = await api.get("/api/auth/invite", headers=h)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert code.startswith("u") and len(code) == 9
    assert r.json()["url"] == f"https://app.be-happyapp.com/?ref={code}"
    again = await api.get("/api/auth/invite", headers=h)
    assert again.json()["code"] == code  # no cambia al pedirlo otra vez

    _h2, uid2 = await signup(api, "invitado@test.com", ref=code)
    assert (await stored(uid2))["referido_por"] == code


async def test_invite_requires_login(api):
    r = await api.get("/api/auth/invite")
    assert r.status_code in (401, 403)


async def test_invite_code_not_in_public_user(api):
    h, uid = await signup(api, "publico@test.com")
    await api.get("/api/auth/invite", headers=h)
    doc = await core.db.users.find_one({"user_id": uid})
    assert doc.get("codigo_invitacion")
    me = await api.get("/api/auth/me", headers=h)
    assert "codigo_invitacion" not in me.json()
