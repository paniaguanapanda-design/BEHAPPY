"""Punto de entrada del servidor: Render lo arranca con `uvicorn server:app`.

El codigo vive en el paquete behappy/, un modulo por area (auth, diagnosis, specialists, chat, stores, web...).
"""
from behappy.main import app  # noqa: F401
