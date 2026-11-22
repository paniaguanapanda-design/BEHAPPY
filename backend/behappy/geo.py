"""Lugares y provincias (Nominatim) y zona del usuario."""
import asyncio
import re
import httpx
import time as _time
from fastapi import Request, APIRouter
from pydantic import BaseModel, Field
from typing import Optional
from . import pro
from .core import db, iso, logger, now
from .security import current_user, rate_limit


router = APIRouter(prefix="/api")


async def reverse_place(lat: float, lng: float) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "BeHappy/1.0 (info@be-happyapp.com)"}) as hc:
            r = await hc.get("https://nominatim.openstreetmap.org/reverse",
                             params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 14, "accept-language": "it"})
        a = r.json().get("address") or {}
        return a.get("suburb") or a.get("quarter") or a.get("neighbourhood") or a.get("city_district") or a.get("city")
    except Exception:
        return None


# --- Provincias: cliente y especialista solo se encuentran dentro de la misma provincia ---
# Toda Italia, sectorizada por provincia: un especialista de Roma no ve ni recibe trabajos de Milan.
# La provincia sale del punto en el mapa (OpenStreetMap / Nominatim) y se guarda: {"code": "TO", "name": "Torino"}.
_nominatim_lock = asyncio.Lock()
_nominatim_last = 0.0


async def _nominatim(path: str, params: dict) -> Optional[object]:
    """Nominatim pide como maximo 1 peticion por segundo: las ponemos en fila."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = 1.05 - (_time.monotonic() - _nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "BeHappy/1.0 (info@be-happyapp.com)"}) as hc:
                r = await hc.get(f"https://nominatim.openstreetmap.org/{path}",
                                 params={**params, "format": "jsonv2", "addressdetails": 1, "accept-language": "it"})
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            logger.warning("nominatim %s: %s", path, e)
            return None
        finally:
            _nominatim_last = _time.monotonic()


def province_from_address(a: dict) -> Optional[dict]:
    """De la direccion de Nominatim a un area legible: en Italia {"code": "TO", "name": "Torino"}; en otros paises
    {"code": "ES-M", "name": "Madrid"} (region/condado). Solo sirve para mostrar la zona: quien llega a quien se decide
    por distancia (radio del especialista), en cualquier pais."""
    cc = (a.get("country_code") or "it").lower()
    if cc != "it":
        name = a.get("county") or a.get("state_district") or a.get("state") or a.get("city") or a.get("town") or ""
        iso_code = a.get("ISO3166-2-lvl6") or a.get("ISO3166-2-lvl4") or ""
        if not name and not iso_code:
            return {"code": cc.upper(), "name": a.get("country") or cc.upper()}
        return {"code": iso_code.upper() or f"{cc.upper()}-{name.upper()}", "name": name or iso_code}
    iso_code = a.get("ISO3166-2-lvl6") or ""
    code = iso_code.split("-", 1)[1].upper() if iso_code.upper().startswith("IT-") else ""
    name = a.get("county") or a.get("province") or ""
    name = re.sub(r"^(citt[aà] metropolitana d[i'] ?|provincia (di|del|della|dell') ?|libero consorzio comunale di )", "",
                  name.strip(), flags=re.I).strip()
    if not code and not name and "aosta" in (a.get("state") or "").lower():
        code, name = "AO", "Aosta"  # la Valle d'Aosta no tiene provincia: cuenta como una
    if not code and not name:
        return None
    return {"code": code or name.upper(), "name": name or code}


async def province_at(lat: float, lng: float) -> Optional[dict]:
    """Provincia de un punto (con cache de ~1 km)."""
    key = f"rev:{lat:.2f}:{lng:.2f}"
    hit = await db.geo_cache.find_one({"_id": key})
    if hit:
        return hit.get("province")
    data = await _nominatim("reverse", {"lat": lat, "lon": lng, "zoom": 10})
    if not isinstance(data, dict) or data.get("error"):
        return None
    prov = province_from_address(data.get("address") or {})
    if prov:
        await db.geo_cache.update_one({"_id": key}, {"$set": {"province": prov, "at": iso(now())}}, upsert=True)
    return prov


async def place_search(q: str) -> list:
    """Busca una ciudad por nombre en cualquier pais y devuelve su punto y su area (para quien no da la ubicacion)."""
    q = " ".join(q.split())[:80]
    key = f"q:{q.lower()}"
    hit = await db.geo_cache.find_one({"_id": key})
    if hit:
        return hit.get("results") or []
    data = await _nominatim("search", {"q": q, "featureType": "settlement", "limit": 8, "addressdetails": 1})
    if not isinstance(data, list):
        return []
    out, seen = [], set()
    for it in data:
        a = it.get("address") or {}
        prov = province_from_address(a)
        name = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("hamlet") \
            or (it.get("name") or "")
        if not prov or not name or (name, prov["code"]) in seen:
            continue
        seen.add((name, prov["code"]))
        out.append({"name": name, "province": prov, "lat": float(it["lat"]), "lng": float(it["lon"])})
    await db.geo_cache.update_one({"_id": key}, {"$set": {"results": out[:6], "at": iso(now())}}, upsert=True)
    return out[:6]


async def zone_from_city(city: str) -> Optional[dict]:
    """Zona inicial del especialista a partir del comune que escribio en la web ('settimo-torinese' o texto libre)."""
    name = " ".join(city.replace("-", " ").split())
    if len(name) < 2:
        return None
    results = await place_search(name)
    if not results:
        return None
    best = next((r for r in results if r["name"].lower() == name.lower()), results[0])
    return {"lat": best["lat"], "lng": best["lng"], "radius_km": pro.DEFAULT_RADIUS_KM, "label": best["name"],
            "province": best["province"]}


def prov_code(doc: Optional[dict]) -> Optional[str]:
    return ((doc or {}).get("province") or {}).get("code")


def zone_point(doc: Optional[dict]) -> Optional[tuple]:
    """Punto (lat, lng) de una zona de usuario o especialista, o None si aun no la eligio."""
    z = doc or {}
    return (z["lat"], z["lng"]) if z.get("lat") is not None and z.get("lng") is not None else None


def in_reach(point: Optional[tuple], spec: dict) -> bool:
    """El cliente (point) esta dentro del radio de trabajo del especialista. Vale en cualquier pais."""
    if not point or not zone_point(spec.get("zone")):
        return False
    center, radius = pro.spec_zone(spec)
    return pro.km_between(point, center) <= radius


async def set_user_province(user: dict, lat: float, lng: float, source: str) -> Optional[dict]:
    """Guarda la zona del usuario (su punto, en cualquier pais) y el nombre de su area para mostrarla."""
    prov = await province_at(lat, lng) or {"code": "", "name": ""}
    zone = {"province": prov, "lat": round(lat, 3), "lng": round(lng, 3), "source": source, "at": iso(now())}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"zone": zone}})
    user["zone"] = zone
    return prov


class MyZoneIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@router.get("/me/zone")
async def get_my_zone(request: Request):
    user = await current_user(request)
    zone = user.get("zone") or {}
    return {"province": zone.get("province"), "lat": zone.get("lat"), "lng": zone.get("lng")}


@router.put("/me/zone")
async def put_my_zone(body: MyZoneIn, request: Request):
    """El cliente elige su provincia: con su ubicacion o con el comune que escribe."""
    user = await current_user(request)
    rate_limit(f"zone:{user['user_id']}", 10, 60)
    prov = await set_user_province(user, body.lat, body.lng, "manual")
    return {"province": prov}


@router.get("/places/search")
async def search_places(q: str, request: Request):
    user = await current_user(request)
    if len(q.strip()) < 2:
        return []
    rate_limit(f"places:{user['user_id']}", 10, 60)
    return await place_search(q)
