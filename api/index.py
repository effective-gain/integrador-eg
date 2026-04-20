"""Entrypoint para Vercel — re-exporta o app FastAPI."""
from api.webhook import app

__all__ = ["app"]
