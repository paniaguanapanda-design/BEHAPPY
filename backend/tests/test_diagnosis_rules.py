"""Reglas del diagnóstico: qué es un electrodoméstico, qué va al especialista y qué acción se recomienda."""
from test_preregistro import server  # noqa: F401


def norm(**r):
    base = {"category": "plumbing", "difficulty": "medium", "steps": [{"title": "x", "detail": "y"}]}
    return server.normalize_diagnosis({**base, **r})


def test_water_heater_is_not_an_appliance_and_goes_to_a_specialist():
    r = norm(is_appliance=True, category="appliance", object="Calentador de agua eléctrico",
             title_es="Calentador descolgado de la pared – volver a fijar", recommended_action="reposition")
    assert r["is_appliance"] is False and r["category"] == "plumbing"
    assert r["difficulty"] == "expert" and r["steps"] == []
    assert r["recommended_action"] == "reposition"


def test_washing_machine_is_an_appliance_but_keeps_the_ai_decision():
    r = norm(is_appliance=True, object="Lavatrice", title_it="Guarnizione dell'oblò rotta", recommended_action="repair")
    assert r["is_appliance"] is True and r["category"] == "appliance" and r["steps"] == []
    assert r["recommended_action"] == "repair"


def test_thermostat_is_not_mistaken_for_a_water_heater():
    r = norm(category="hvac", object="Termostato", title_es="Termostato sin pantalla", difficulty="easy")
    assert r.get("is_appliance") is not True and r["category"] == "hvac" and r["difficulty"] == "easy"


def test_unknown_action_becomes_inspect():
    assert norm(title_es="Grifo que gotea", recommended_action="tirar")["recommended_action"] == "inspect"
