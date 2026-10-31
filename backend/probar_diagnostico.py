"""Prueba el diagnostico de Gemini con una foto, sin abrir la app.

Uso (desde la carpeta backend, con el entorno activado):
    python probar_diagnostico.py ruta\\a\\la\\foto.jpg it "nota opcional"

Usa el mismo prompt y las mismas reglas de seguridad que /api/diagnose. No guarda nada en la base de datos.
"""
import asyncio
import base64
import json
import sys

import server


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    foto = sys.argv[1]
    lang_code = sys.argv[2] if len(sys.argv) > 2 else "it"
    nota = sys.argv[3] if len(sys.argv) > 3 else ""
    raw = server.shrink_image(open(foto, "rb").read())
    b64 = base64.b64encode(raw).decode()
    lang = server.LANG_NAME.get(lang_code, "Italian")
    extra = f"User note: {nota}" if nota else ""
    prompt = server.DIAG_PROMPT.format(lang=lang, cats=server.CATEGORIES, extra=extra)
    r = server.normalize_diagnosis(await server.gemini_json(prompt, b64))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print("\n--- RESUMEN ---")
    print("Objeto:     ", r.get("object"))
    print("Se ve:      ", r.get("observed"))
    print("Accion:     ", r.get("recommended_action"), "-", r.get("action_reason"))
    print("Titulo:     ", r.get(f"title_{lang_code}"))
    print("Dificultad: ", r.get("difficulty"))
    print("Especialista:", r.get("when_to_call_pro"))


asyncio.run(main())
