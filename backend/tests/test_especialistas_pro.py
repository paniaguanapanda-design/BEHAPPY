"""Herramientas para especialistas: zona y horario, muro por zona, estadisticas, avisos, destacado, reportes y reseñas."""
from datetime import timedelta

import pytest

from test_preregistro import api, clean_db, make_profile, register, server  # noqa: F401

TORINO = (45.0703, 7.6869)
LINGOTTO = (45.0310, 7.6650)  # ~4,6 km del centro
IVREA = (45.4670, 7.8760)  # ~47 km, tambien provincia de Torino
MILANO = (45.4642, 9.1900)
ROMA = (41.9028, 12.4964)


@pytest.fixture
def pushes(monkeypatch):
    sent = []

    async def fake_push(user_id, title, body, data):
        sent.append({"user_id": user_id, "title": title, "body": body, "data": data})

    async def fake_place(lat, lng):
        return "San Salvario"

    async def fake_mail(*a):
        sent.append({"mail": a})
        return True

    monkeypatch.setattr(server, "send_push", fake_push)
    monkeypatch.setattr(server, "reverse_place", fake_place)
    monkeypatch.setattr(server, "send_email", fake_mail)
    return sent


async def pro(api, email, zone="TO", **extra):
    h = await register(api, email)
    s = await make_profile(api, h, zone=zone, **extra)
    await server.db.specialists.update_one({"specialist_id": s["specialist_id"]},
                                           {"$set": {"membership_expires_at": server.iso(server.now() + timedelta(days=30))}})
    return h, s


async def set_zone(api, h, at, radius=8, days=(1, 2, 3, 4, 5, 6, 7), frm="00:00", to="24:00", urgent=False):
    r = await api.put("/api/specialists/me/zone", headers=h, json={"lat": at[0], "lng": at[1], "radius_km": radius,
                                                                    "days": list(days), "from": frm, "to": to, "urgent": urgent})
    assert r.status_code == 200, r.text
    return r.json()


async def settle():
    import asyncio
    for _ in range(5):
        await asyncio.sleep(0.01)


async def test_wall_only_shows_specialists_of_the_client_province(api, pushes):
    h1, s1 = await pro(api, "centro@x.it")
    h2, s2 = await pro(api, "ivrea@x.it")
    h3, s3 = await pro(api, "milano@x.it")
    await set_zone(api, h1, TORINO, radius=8)
    await set_zone(api, h2, IVREA, radius=10)
    await set_zone(api, h3, MILANO, radius=50)
    c = await register(api, "cliente@x.it", at=None)
    # sin provincia no sale nadie
    assert (await api.get("/api/specialists?category=plumbing", headers=c)).json() == []
    # con su ubicacion: su provincia es Torino, salen los de Torino (Ivrea incluido) ordenados por distancia
    r = await api.get(f"/api/specialists?category=plumbing&lat={LINGOTTO[0]}&lng={LINGOTTO[1]}", headers=c)
    ids = [x["specialist_id"] for x in r.json()]
    assert ids == [s1["specialist_id"], s2["specialist_id"]]
    assert 4 <= r.json()[0]["distance_km"] <= 5.5
    assert r.json()[0]["zone"]["province"] == {"code": "TO", "name": "Torino"}
    # sin posicion se usa la provincia guardada
    r = await api.get("/api/specialists?category=plumbing", headers=c)
    assert [x["specialist_id"] for x in r.json()] == [s1["specialist_id"], s2["specialist_id"]]
    # elige Milano a mano: solo el de Milano
    assert (await api.put("/api/me/zone", headers=c, json={"lat": MILANO[0], "lng": MILANO[1]})).json()["province"]["code"] == "MI"
    r = await api.get(f"/api/specialists?category=plumbing&lat={LINGOTTO[0]}&lng={LINGOTTO[1]}", headers=c)
    assert [x["specialist_id"] for x in r.json()] == [s3["specialist_id"]]
    assert (await api.get("/api/me/zone", headers=c)).json()["province"]["code"] == "MI"


async def test_chat_only_within_the_same_province(api, pushes):
    hr, sr = await pro(api, "roma@x.it", zone="RM")
    ht, st = await pro(api, "torino@x.it")
    c = await register(api, "cliente@x.it")  # provincia de Torino
    r = await api.post("/api/conversations", headers=c, json={"specialist_id": sr["specialist_id"]})
    assert r.status_code == 403
    assert (await api.post("/api/conversations", headers=c, json={"specialist_id": st["specialist_id"]})).status_code == 200
    # sin provincia: primero tiene que elegirla
    nop = await register(api, "senza@x.it", at=None)
    assert (await api.post("/api/conversations", headers=nop, json={"specialist_id": st["specialist_id"]})).status_code == 409
    # una conversacion que ya existia se respeta aunque el cliente cambie de provincia
    await api.put("/api/me/zone", headers=c, json={"lat": ROMA[0], "lng": ROMA[1]})
    assert (await api.post("/api/conversations", headers=c, json={"specialist_id": st["specialist_id"]})).status_code == 200
    # un especialista sin zona no sale en el muro ni se le puede escribir
    hz, sz = await pro(api, "senzazona@x.it", zone=None)
    c2 = await register(api, "altro@x.it")
    assert sz["specialist_id"] not in [x["specialist_id"] for x in (await api.get("/api/specialists", headers=c2)).json()]
    assert (await api.post("/api/conversations", headers=c2, json={"specialist_id": sz["specialist_id"]})).status_code == 403


async def test_zone_outside_italy_is_rejected(api, pushes):
    h, s = await pro(api, "fuori@x.it", zone=None)
    r = await api.put("/api/specialists/me/zone", headers=h, json={"lat": 48.85, "lng": 2.35, "radius_km": 10,
                                                                    "days": [1], "from": "08:00", "to": "18:00"})
    assert r.status_code == 422
    c = await register(api, "c@x.it", at=None)
    assert (await api.put("/api/me/zone", headers=c, json={"lat": 48.85, "lng": 2.35})).status_code == 422


async def test_available_now_follows_the_schedule(api, pushes):
    h1, s1 = await pro(api, "sempre@x.it")
    h2, s2 = await pro(api, "mai@x.it")
    await set_zone(api, h1, TORINO)
    await set_zone(api, h2, TORINO, frm="00:00", to="00:01", days=(1,))
    c = await register(api, "cliente@x.it")
    r = await api.get("/api/specialists?available=true", headers=c)
    assert [x["specialist_id"] for x in r.json()] == [s1["specialist_id"]]
    assert r.json()[0]["schedule_label_it"].startswith("lun–dom")


async def test_featured_first_and_at_most_three_per_trade(api, pushes):
    specs = []
    for i in range(5):
        h, s = await pro(api, f"p{i}@x.it")
        specs.append(s)
    until = server.iso(server.now() + timedelta(days=7))
    for s in specs[1:]:
        await server.db.specialists.update_one({"specialist_id": s["specialist_id"]}, {"$set": {"featured_until": until}})
    c = await register(api, "cliente@x.it")
    out = (await api.get("/api/specialists?category=plumbing", headers=c)).json()
    assert [x["featured"] for x in out].count(True) == 3
    assert out[0]["featured"] and out[1]["featured"] and out[2]["featured"]
    assert "featured_until" not in out[0] and "quick_replies" not in out[0]


async def test_stats_views_clients_and_response_time(api, pushes):
    h, s = await pro(api, "stats@x.it")
    sid = s["specialist_id"]
    for i in range(3):
        c = await register(api, f"c{i}@x.it")
        await api.get(f"/api/specialists/{sid}", headers=c)
        await api.get(f"/api/specialists/{sid}", headers=c)  # la misma persona el mismo dia cuenta una vez
        conv = (await api.post("/api/conversations", headers=c, json={"specialist_id": sid})).json()
        await api.post(f"/api/conversations/{conv['conversation_id']}/messages", headers=c, json={"text": "Ciao, perde il rubinetto"})
        await api.post(f"/api/conversations/{conv['conversation_id']}/messages", headers=h, json={"text": "Arrivo"})
    await settle()
    st = (await api.get("/api/specialists/me/stats?days=7", headers=h)).json()
    assert st["views"] == 3 and st["clients"] == 3
    assert st["response_within_1h_pct"] == 100 and st["response_avg_min"] == 0
    assert len(st["daily"]) == 7 and st["daily"][-1]["views"] == 3
    me = await api.get(f"/api/specialists/{sid}", headers=h)
    assert me.json()["response_min"] == 0
    # visitar el propio perfil no cuenta
    assert (await api.get("/api/specialists/me/stats", headers=h)).json()["views"] == 3


async def test_push_to_specialist_on_first_message_and_to_client_on_reply(api, pushes):
    h, s = await pro(api, "push@x.it")
    c = await register(api, "giulia@x.it")
    await api.get(f"/api/specialists?lat={LINGOTTO[0]}&lng={LINGOTTO[1]}", headers=c)  # guarda su ultima posicion
    conv = (await api.post("/api/conversations", headers=c, json={"specialist_id": s["specialist_id"]})).json()
    await api.post(f"/api/conversations/{conv['conversation_id']}/messages", headers=c, json={"text": "Rubinetto che perde in cucina"})
    await settle()
    first = pushes[-1]
    assert first["title"]["it"].startswith("Nuovo cliente a ") and "Rispondi presto" in first["body"]["it"]
    await api.post(f"/api/conversations/{conv['conversation_id']}/messages", headers=h, json={"text": "Arrivo oggi"})
    await settle()
    assert pushes[-1]["body"]["it"] == "Arrivo oggi"


async def test_nearby_diagnosis_alert_respects_zone_trade_and_switch(api, pushes, monkeypatch):
    h, s = await pro(api, "vicino@x.it")
    await set_zone(api, h, TORINO, radius=8)
    h2, s2 = await pro(api, "lontano@x.it")
    await set_zone(api, h2, IVREA, radius=5)
    h3, s3 = await pro(api, "milano@x.it")
    await set_zone(api, h3, MILANO, radius=50)
    doc = {"diagnosis_id": "diag_x", "user_id": "u_cliente", "category": "plumbing", "title_it": "Scarico intasato"}
    await server.notify_nearby_diagnosis(doc, *LINGOTTO)
    assert len(pushes) == 1 and "a San Salvario" in pushes[0]["body"]["it"]
    # una diagnosis en Milano solo avisa al de Milano (aunque el radio de 50 km no llegue a Torino de todas formas)
    await server.notify_nearby_diagnosis({**doc, "diagnosis_id": "diag_m"}, *MILANO)
    assert len(pushes) == 2 and pushes[-1]["user_id"] != pushes[0]["user_id"]
    pushes.pop()
    assert pushes[0]["title"]["it"] == "Richiesta di idraulica vicino a te"
    await api.put("/api/specialists/me/alerts", headers=h, json={"enabled": False, "categories": ["plumbing"]})
    await server.notify_nearby_diagnosis(doc, *LINGOTTO)
    assert len(pushes) == 1


async def test_three_clients_who_talked_with_him_hide_the_profile(api, pushes):
    h, s = await pro(api, "cattivo@x.it")
    sid = s["specialist_id"]
    stranger = await register(api, "estraneo@x.it")
    await api.post("/api/reports", headers=stranger, json={"target_type": "specialist", "target_id": sid, "reason": "no_show"})
    for i in range(3):
        c = await register(api, f"r{i}@x.it")
        await api.post("/api/conversations", headers=c, json={"specialist_id": sid})
        r = await api.post("/api/reports", headers=c, json={"target_type": "specialist", "target_id": sid,
                                                            "reason": "broke_agreement", "details": "Non è venuto"})
        assert r.status_code == 200
        hidden = (await server.db.specialists.find_one({"specialist_id": sid}))["hidden"] if i == 2 else None
    assert hidden is True
    assert any("mail" in p for p in pushes)
    c = await register(api, "nuovo@x.it")
    assert (await api.get("/api/specialists", headers=c)).json() == []


async def test_review_prompt_two_days_after_first_reply(api, pushes):
    h, s = await pro(api, "rev@x.it")
    c = await register(api, "cli@x.it")
    conv = (await api.post("/api/conversations", headers=c, json={"specialist_id": s["specialist_id"]})).json()
    cid = conv["conversation_id"]
    await api.post(f"/api/conversations/{cid}/messages", headers=c, json={"text": "Ciao"})
    await api.post(f"/api/conversations/{cid}/messages", headers=h, json={"text": "Ciao!"})
    await settle()
    assert (await api.get(f"/api/conversations/{cid}", headers=c)).json()["review_prompt"] is False
    old = server.iso(server.now() - timedelta(days=3))
    await server.db.conversations.update_one({"conversation_id": cid}, {"$set": {"first_reply_at": old}})
    assert (await api.get(f"/api/conversations/{cid}", headers=c)).json()["review_prompt"] is True
    assert (await api.get(f"/api/conversations/{cid}", headers=h)).json()["review_prompt"] is False


async def test_diagnosis_travels_to_the_chat(api, pushes):
    h, s = await pro(api, "diag@x.it")
    c = await register(api, "cli@x.it")
    uid = (await api.get("/api/auth/me", headers=c)).json()["user_id"]
    await server.db.diagnoses.insert_one({"diagnosis_id": "diag_1", "user_id": uid, "category": "plumbing",
                                          "title_it": "Rubinetto che gocciola", "title_es": "Grifo que gotea",
                                          "image_path": "behappy/uploads/x/f.jpg",
                                          "materials": [{"name": "cartuccia 35 mm", "quantity": "1"}]})
    conv = (await api.post("/api/conversations", headers=c, json={"specialist_id": s["specialist_id"],
                                                                   "diagnosis_id": "diag_1"})).json()
    got = (await api.get(f"/api/conversations/{conv['conversation_id']}", headers=h)).json()
    assert got["diagnosis"]["title_it"] == "Rubinetto che gocciola"
    assert got["diagnosis"]["materials"] == ["cartuccia 35 mm"]
    assert got["stores_nearby"] == 0
    # una diagnosis de otra persona no se puede adjuntar
    other = await register(api, "altro@x.it")
    conv2 = (await api.post("/api/conversations", headers=other, json={"specialist_id": s["specialist_id"],
                                                                        "diagnosis_id": "diag_1"})).json()
    assert "diagnosis" not in conv2


async def test_settings_quick_replies_and_validation(api, pushes):
    h, s = await pro(api, "set@x.it", zone=None)
    st = (await api.get("/api/specialists/me/settings?lang=it", headers=h)).json()
    assert len(st["quick_replies"]) == 5 and st["zone"]["set"] is False
    r = await api.put("/api/specialists/me/quick-replies", headers=h, json={"items": ["  Arrivo   subito ", "", "Ok"]})
    assert r.json()["items"] == ["Arrivo subito", "Ok"]
    bad = await api.put("/api/specialists/me/zone", headers=h, json={"lat": 45, "lng": 7, "radius_km": 8, "days": [1],
                                                                      "from": "19:00", "to": "08:00"})
    assert bad.status_code == 400
    z = await set_zone(api, h, TORINO, radius=12, days=(1, 2, 3, 4, 5, 6), frm="08:00", to="19:00", urgent=True)
    assert z["zone"]["label"] == "San Salvario" and z["urgent"] is True
    assert z["zone"]["province"] == {"code": "TO", "name": "Torino"} and z["zone"]["set"] is True
    pub = (await api.get(f"/api/specialists/{s['specialist_id']}", headers=h)).json()
    assert pub["schedule_label_it"] == "lun–sab 8–19" and "lat" not in (pub["zone"] or {})


async def test_wall_only_lists_specialists_with_active_subscription(api, pushes):
    h, s = await pro(api, "attivo@x.it")
    h2 = await register(api, "nonpaga@x.it")
    await make_profile(api, h2, name="Senza Abbonamento")
    c = await register(api, "cliente@x.it")
    out = (await api.get("/api/specialists", headers=c)).json()
    assert [x["specialist_id"] for x in out] == [s["specialist_id"]]
