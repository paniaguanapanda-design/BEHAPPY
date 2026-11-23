"""Prueba el diagnostico con una o varias fotos, sin abrir la app: Grok y Gemini, con el tiempo de cada uno.

Uso (desde la carpeta backend, con el entorno activado):
    python probar_diagnostico.py ruta\\a\\la\\foto.jpg [otra.jpg ...] --lang it --nota "nota opcional"
    python probar_diagnostico.py foto.jpg --solo grok      (o --solo gemini)

Usa el mismo prompt y las mismas reglas de seguridad que /api/diagnose. No guarda nada en la base de datos.
Cada foto gasta una llamada de cada proveedor (creditos de xAI y cuota de Gemini).
"""
import argparse
import asyncio
import base64
import time

from behappy import ai, diagnosis

PROVIDERS = {"grok": ai.xai_json, "gemini": ai.gemini_json}


async def run(name, prompt, b64, lang_code):
    started = time.monotonic()
    try:
        r = diagnosis.normalize_diagnosis(await PROVIDERS[name](prompt, b64))
    except Exception as e:
        print(f"  {name:7} FALLO tras {time.monotonic() - started:5.1f}s: {str(e)[:150]}")
        return
    print(f"  {name:7} {time.monotonic() - started:5.1f}s  objeto: {r.get('object')}")
    print(f"          accion: {r.get('recommended_action')} - {r.get('action_reason')}")
    print(f"          titulo: {r.get(f'title_{lang_code}')} | dificultad: {r.get('difficulty')}"
          f" | oficio: {r.get('category')}")


async def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fotos", nargs="+")
    p.add_argument("--lang", default="it", choices=sorted(diagnosis.LANG_NAME))
    p.add_argument("--nota", default="")
    p.add_argument("--solo", choices=sorted(PROVIDERS))
    a = p.parse_args()
    names = [a.solo] if a.solo else list(PROVIDERS)
    if "grok" in names and not ai.xai_configured():
        print("Falta XAI_API_KEY en backend/.env: solo se prueba Gemini.\n")
        names = [n for n in names if n != "grok"]
    extra = f"User note: {a.nota}" if a.nota else ""
    prompt = diagnosis.DIAG_PROMPT.format(lang=diagnosis.LANG_NAME[a.lang], cats=diagnosis.CATEGORIES, extra=extra)
    for foto in a.fotos:
        print(f"\n{foto}")
        b64 = base64.b64encode(diagnosis.shrink_image(open(foto, "rb").read())).decode()
        for name in names:
            await run(name, prompt, b64, a.lang)


asyncio.run(main())
