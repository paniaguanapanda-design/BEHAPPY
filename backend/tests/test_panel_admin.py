"""Panel de administracion: /api/admin/stats con la clave de admin, y registro de actividad diaria."""
import pytest

from test_preregistro import api, clean_db, make_profile, register, server  # noqa: F401
from behappy import admin, core  # noqa: E402

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setattr(admin, "ADMIN_TOKEN", "test-admin-token")


async def stats(api):
    r = await api.get("/api/admin/stats", headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


async def test_needs_admin_token(api):
    assert (await api.get("/api/admin/stats")).status_code == 403
    assert (await api.get("/api/admin/stats", headers={"X-Admin-Token": "nope"})).status_code == 403


async def test_counts_users_activity_diagnoses_and_ai(api):
    a = await register(api, "a@example.com")
    b = await register(api, "b@example.com")
    await register(api, "c@example.com", at=None)
    pro = await register(api, "pro@example.com")
    await make_profile(api, pro)
    for h in (a, b, a, a):  # a uses the app several times today: counted once
        assert (await api.get("/api/auth/me", headers=h)).status_code == 200
    me = (await api.get("/api/auth/me", headers=a)).json()
    today = core.now().strftime("%Y-%m-%d")
    for cat, status in (("plumbing", "ready"), ("plumbing", "ready"), ("electrical", "failed")):
        await core.db.diagnoses.insert_one({"diagnosis_id": core.new_id("diag"), "user_id": me["user_id"],
                                            "category": cat, "status": status, "created_at": core.iso(core.now())})
    await core.db.usage.insert_many([{"_id": f"xai:{today}", "count": 7}, {"_id": f"gemini:{today}", "count": 2}])

    s = await stats(api)
    u = s["users"]
    assert u["total"] == 4 and u["new_today"] == 4 and u["new_7d"] == 4 and u["specialists"] == 1
    assert u["active_today"] >= 2 and u["active_7d"] == u["active_today"]  # register + zone also count as use
    assert s["diagnoses"]["today"] == 3 and s["diagnoses"]["failed_7d"] == 1
    assert s["diagnoses"]["top_categories_30d"][0] == {"category": "plumbing", "count": 2}
    assert s["ai"]["grok_today"] == 7 and s["ai"]["gemini_today"] == 2 and s["ai"]["grok_daily_cap"] == 1000
    assert s["specialists"]["total"] == 1
    last = s["series"][-1]
    assert len(s["series"]) == 30 and last["day"] == today
    assert last["new_users"] == 4 and last["diagnoses"] == 3 and last["ai_grok"] == 7


async def test_activity_is_written_once_per_person_and_day(api):
    h = await register(api, "once@example.com", at=None)
    for _ in range(5):
        await api.get("/api/auth/me", headers=h)
    uid = (await api.get("/api/auth/me", headers=h)).json()["user_id"]
    rows = await core.db.activity_days.find({"user_id": uid}).to_list(10)
    assert len(rows) == 1 and rows[0]["day"] == core.now().strftime("%Y-%m-%d")


async def test_days_parameter_is_limited(api):
    r = await api.get("/api/admin/stats?days=500", headers=ADMIN)
    assert len(r.json()["series"]) == 90
    r = await api.get("/api/admin/stats?days=1", headers=ADMIN)
    assert len(r.json()["series"]) == 7
