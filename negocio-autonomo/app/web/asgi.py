"""Punto de entrada ASGI: uvicorn app.web.asgi:app"""
from ..config import load_settings
from .app import create_app

app = create_app(load_settings())
