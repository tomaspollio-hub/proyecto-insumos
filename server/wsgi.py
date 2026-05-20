"""Punto de entrada para gunicorn (Railway / producción)."""

from server.app import app, init_db, UPLOADS_DIR, PRODUCTOS_IMG_DIR

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PRODUCTOS_IMG_DIR.mkdir(parents=True, exist_ok=True)
init_db()
