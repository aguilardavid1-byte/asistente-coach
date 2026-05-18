"""Configuración — variables de entorno con soporte .env."""

import os
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cargar .env si existe (Python 3 nativo, sin dotenv)
_env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if not os.environ.get(key):
                os.environ.setdefault(key, val)

DB_PATH = os.path.join(BASE_DIR, "asistente.db")

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

PORT = int(os.environ.get("PORT") or os.environ.get("ASISTENTE_PORT") or 7860)

# Auth
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
