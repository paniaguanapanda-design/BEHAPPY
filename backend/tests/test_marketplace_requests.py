from datetime import timedelta
from io import BytesIO

from PIL import Image

from test_preregistro import TORINO_POINT, api, clean_db, make_profile, register, server  # noqa: F401


async def specialist_account(api, email, zone="TO", categories=None):
    headers = await register(api, email)
    profile = await make_profile(api, headers, zone=zone, categories=categories or ["plumbing"])
    await server.db.specialists.update_one(
        {"specialist_id": profile["specialist_id"]},
        {"$set": {"membership_expires_at": server.iso(server.now() + timedelta(days=30))}},
    )
    return headers, profile


async def publish_request(api, headers, **values):
    payload = {
        "title": "Renovar el baño",
        "description": "Quiero cambiar los azulejos y actualizar el lavabo.",
        "category": "plumbing",
        "photos": [],
        **values,
    }
    return await api.post("/api/requests/board", headers=headers, json=payload)


async def test_marketplace_quote_is_private_until_client_accepts(api, monkeypatch):
    client_headers = await register(api, "market-client@example.com")
    spec_headers, _ = await specialist_account(api, "market-spec@example.com")
    second_headers, _ = await specialist_account(api, "market-spec-two@example.com")
    monkeypatch.setattr(server, "reverse_place", lambda *_: _async_value("Torino"))
    monkeypatch.setattr(server, "send_push", lambda *_args, **_kwargs: _async_value(None))
    monkeypatch.setattr(server, "after_message", lambda *_args, **_kwargs: _async_value(None))

    created = await publish_request(api, client_headers)
    assert created.status_code == 200, created.text
    request_id = created.json()["request_id"]

    feed = await api.get("/api/requests/board", headers=spec_headers)
    assert feed.status_code == 200, feed.text
    public_request = next(item for item in feed.json() if item["request_id"] == request_id)
    assert public_request["distance_km"] == 0
    assert not {"client_id", "address", "lat", "lng", "zone", "phone", "email"} & public_request.keys()
    assert await server.db.conversations.count_documents({}) == 0

    first_quote = await api.post(
        f"/api/requests/board/{request_id}/quotes",
        headers=spec_headers,
        json={"price": 480, "description": "Materiales y mano de obra", "estimated_time": "3 días"},
    )
    assert first_quote.status_code == 200, first_quote.text
    second_quote = await api.post(
        f"/api/requests/board/{request_id}/quotes",
        headers=second_headers,
        json={"price": 510, "description": "Oferta alternativa", "estimated_time": "5 días"},
    )
    assert second_quote.status_code == 200, second_quote.text
    duplicate_quote = await api.post(
        f"/api/requests/board/{request_id}/quotes",
        headers=spec_headers,
        json={"price": 500, "description": "Otro presupuesto", "estimated_time": "4 días"},
    )
    assert duplicate_quote.status_code == 409

    client_feed = (await api.get("/api/requests/board", headers=client_headers)).json()
    offers = next(item for item in client_feed if item["request_id"] == request_id)["quotes"]
    assert len(offers) == 2
    assert all(offer["status"] == "pending" for offer in offers)
    assert all("conversation_id" not in offer for offer in offers)
    assert await server.db.conversations.count_documents({}) == 0

    accepted = await api.patch(
        f"/api/quotes/{first_quote.json()['quote_id']}",
        headers=client_headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["conversation_id"]
    assert await server.db.conversations.count_documents({}) == 1
    stored_request = await server.db.service_requests.find_one({"request_id": request_id}, {"_id": 0})
    assert stored_request["status"] == "accepted"
    assert stored_request["accepted_quote_id"] == first_quote.json()["quote_id"]
    stored_quote = await server.db.quotes.find_one({"quote_id": first_quote.json()["quote_id"]}, {"_id": 0})
    assert stored_quote["status"] == "accepted"
    assert stored_quote["conversation_id"] == accepted.json()["conversation_id"]
    rejected_quote = await server.db.quotes.find_one({"quote_id": second_quote.json()["quote_id"]}, {"_id": 0})
    assert rejected_quote["status"] == "rejected"


async def test_marketplace_feed_filters_by_membership_trade_province_and_radius(api, monkeypatch):
    client_headers = await register(api, "market-filter-client@example.com")
    eligible_headers, eligible = await specialist_account(api, "eligible@example.com")
    wrong_trade_headers, wrong_trade = await specialist_account(api, "wrong-trade@example.com", categories=["electrical"])
    wrong_province_headers, wrong_province = await specialist_account(api, "wrong-province@example.com", zone="MI")
    outside_headers, outside_radius = await specialist_account(api, "outside-radius@example.com")
    inactive_headers, inactive = await specialist_account(api, "inactive@example.com")
    await server.db.specialists.update_one(
        {"specialist_id": outside_radius["specialist_id"]},
        {"$set": {"zone.lat": TORINO_POINT[0] + 1, "zone.lng": TORINO_POINT[1], "zone.radius_km": 1}},
    )
    await server.db.specialists.update_one(
        {"specialist_id": inactive["specialist_id"]},
        {"$set": {"membership_expires_at": server.iso(server.now() - timedelta(days=1))}},
    )
    monkeypatch.setattr(server, "reverse_place", lambda *_: _async_value("Torino"))
    created = await publish_request(api, client_headers)
    assert created.status_code == 200, created.text
    rid = created.json()["request_id"]

    assert [item["request_id"] for item in (await api.get("/api/requests/board", headers=eligible_headers)).json()] == [rid]
    assert (await api.get("/api/requests/board", headers=wrong_trade_headers)).json() == []
    assert (await api.get("/api/requests/board", headers=wrong_province_headers)).json() == []
    assert (await api.get("/api/requests/board", headers=outside_headers)).json() == []
    assert (await api.get("/api/requests/board", headers=inactive_headers)).json() == []


async def test_marketplace_rejection_and_cancellation_do_not_open_chat(api, monkeypatch):
    client_headers = await register(api, "market-cancel-client@example.com")
    spec_headers, _ = await specialist_account(api, "market-cancel-spec@example.com")
    monkeypatch.setattr(server, "reverse_place", lambda *_: _async_value("Torino"))
    request_response = await publish_request(api, client_headers)
    rid = request_response.json()["request_id"]
    quote_response = await api.post(
        f"/api/requests/board/{rid}/quotes",
        headers=spec_headers,
        json={"price": 100, "description": "Instalación", "estimated_time": "1 día"},
    )
    quote_id = quote_response.json()["quote_id"]
    rejected = await api.patch(f"/api/quotes/{quote_id}", headers=client_headers, json={"status": "rejected"})
    assert rejected.status_code == 200
    assert await server.db.conversations.count_documents({}) == 0

    cancelled_response = await publish_request(api, client_headers, title="Cambiar grifo")
    cancelled_id = cancelled_response.json()["request_id"]
    await api.post(
        f"/api/requests/board/{cancelled_id}/quotes",
        headers=spec_headers,
        json={"price": 40, "description": "Cambio de grifo", "estimated_time": "1 hora"},
    )
    cancelled = await api.patch(
        f"/api/requests/{cancelled_id}", headers=client_headers, json={"status": "cancelled"}
    )
    assert cancelled.status_code == 200, cancelled.text
    pending = await server.db.quotes.find_one({"request_id": cancelled_id}, {"_id": 0})
    assert pending["status"] == "rejected"
    assert await server.db.conversations.count_documents({}) == 0


async def test_marketplace_photos_are_only_available_to_owner_or_matching_specialists(api, monkeypatch):
    client_headers = await register(api, "market-photo-client@example.com")
    spec_headers, _ = await specialist_account(api, "market-photo-spec@example.com")
    outsider_headers, _ = await specialist_account(api, "market-photo-outsider@example.com", zone="MI")
    monkeypatch.setattr(server, "reverse_place", lambda *_: _async_value("Torino"))
    monkeypatch.setattr(server, "get_object", lambda _path: (b"image-bytes", "image/jpeg"))
    monkeypatch.setattr(server, "put_object", lambda *_args, **_kwargs: None)
    image = BytesIO()
    Image.new("RGB", (4, 4), "red").save(image, format="JPEG")
    upload = await api.post(
        "/api/requests/photos",
        headers=client_headers,
        files={"file": ("request.jpg", image.getvalue(), "image/jpeg")},
    )
    assert upload.status_code == 200, upload.text
    path = upload.json()["path"]
    assert "/uploads/" not in path
    created = await publish_request(api, client_headers, photos=[path])
    assert created.status_code == 200, created.text

    own_photo = await api.get(f"/api/files/{path}", headers=client_headers)
    matched_photo = await api.get(f"/api/files/{path}", headers=spec_headers)
    outsider_photo = await api.get(f"/api/files/{path}", headers=outsider_headers)
    assert own_photo.status_code == 200
    assert matched_photo.status_code == 200
    assert outsider_photo.status_code == 404


async def _async_value(value):
    return value
