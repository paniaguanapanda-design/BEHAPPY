"""Nominatim (1 peticion por segundo): con mucha gente la fila no hace esperar a nadie y los lugares se guardan."""
import asyncio
import time

from test_preregistro import clean_db, server  # noqa: F401
from behappy import core, geo  # noqa: E402


async def test_full_queue_answers_at_once_instead_of_waiting(monkeypatch):
    async def slow(path, params):
        await asyncio.sleep(0.3)
        return {"ok": True}
    monkeypatch.setattr(geo, "_nominatim_in_line", slow)
    monkeypatch.setattr(geo, "NOMINATIM_MAX_QUEUE", 2)
    started = time.monotonic()
    results = await asyncio.gather(*[geo._nominatim("reverse", {}) for _ in range(5)])
    assert results.count({"ok": True}) == 2 and results.count(None) == 3
    assert time.monotonic() - started < 1  # nobody waited in a long line
    assert geo._nominatim_waiting == 0


async def test_reverse_place_is_cached(monkeypatch):
    calls = []

    async def fake(path, params):
        calls.append(params)
        return {"address": {"suburb": "Lingotto"}}
    monkeypatch.setattr(geo, "_nominatim", fake)
    assert await geo.reverse_place(45.0301, 7.6651) == "Lingotto"
    assert await geo.reverse_place(45.0302, 7.6652) == "Lingotto"  # ~10 m away: same cache cell
    assert len(calls) == 1
    assert await core.db.geo_cache.find_one({"_id": "place:45.030:7.665"})


async def test_reverse_place_without_data_is_not_cached(monkeypatch):
    async def none(path, params):
        return None
    monkeypatch.setattr(geo, "_nominatim", none)
    assert await geo.reverse_place(41.9, 12.5) is None
    assert not await core.db.geo_cache.find_one({"_id": "place:41.900:12.500"})
