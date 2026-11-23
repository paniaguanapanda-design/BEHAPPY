"""Punto de entrada del servidor: Render lo arranca con `uvicorn server:app`.

El codigo vive en el paquete behappy/, un modulo por area (auth, diagnosis, specialists, chat, stores, web...).
"""
import os
import sys

# Tambien funciona si el servidor se arranca desde la raiz del repositorio (`uvicorn backend.server:app`):
# en ese caso la carpeta backend/ no esta en la ruta de Python y no se encontraria el paquete behappy.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from behappy.main import app  # noqa: E402,F401
