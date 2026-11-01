from test_preregistro import api, clean_db, register, server  # noqa: F401


async def test_text_only_home_request_creates_specialist_diagnosis(api, monkeypatch):
    headers = await register(api, "home-request@example.com")
    received = {}

    async def fake_gemini_json(prompt, image_b64=None):
        received["prompt"] = prompt
        received["image_b64"] = image_b64
        return {
            "is_home_problem": True,
            "is_appliance": False,
            "title_es": "Pintar una habitación",
            "title_it": "Dipingere una stanza",
            "category": "masonry",
            "description": "Solicitud para pintar una habitación.",
            "difficulty": "expert",
            "safety_warnings": [],
            "materials": [],
            "tools": [],
            "steps": [],
        }

    monkeypatch.setattr(server, "gemini_json", fake_gemini_json)
    response = await api.post(
        "/api/diagnose",
        headers=headers,
        json={"note": "Quiero pintar el dormitorio de azul", "language": "es"},
    )

    assert response.status_code == 200, response.text
    diagnosis = response.json()
    assert diagnosis["category"] == "masonry"
    assert diagnosis["image_path"] is None
    assert received["image_b64"] is None
    assert "Quiero pintar el dormitorio de azul" in received["prompt"]
    stored = await server.db.diagnoses.find_one({"diagnosis_id": diagnosis["diagnosis_id"]})
    assert stored["image_path"] is None
    assert server.diagnosis_summary(stored)["user_note"] == "Quiero pintar el dormitorio de azul"


async def test_diagnose_requires_photo_or_description(api):
    headers = await register(api, "empty-request@example.com")
    response = await api.post("/api/diagnose", headers=headers, json={"language": "es"})
    assert response.status_code == 422
