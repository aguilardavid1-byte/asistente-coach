"""Análisis de imágenes con Gemini 2.5 Flash vía httpx."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import base64

from config import GEMINI_KEY, GEMINI_ENDPOINT


def analizar_imagen(ruta_imagen: str) -> str:
    """Envía una imagen a Gemini y retorna la descripción textual."""
    if not GEMINI_KEY:
        return "[Análisis de imagen no disponible: falta GEMINI_API_KEY]"

    if not os.path.exists(ruta_imagen):
        return "[Error: archivo de imagen no encontrado]"

    with open(ruta_imagen, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    ext = os.path.splitext(ruta_imagen)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")

    payload = {
        "contents": [{
            "parts": [
                {"text": "Describe esta imagen en detalle, en español."},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]
        }]
    }

    url = f"{GEMINI_ENDPOINT}?key={GEMINI_KEY}"
    try:
        resp = httpx.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        partes = data["candidates"][0]["content"]["parts"]
        return " ".join(p["text"] for p in partes if "text" in p)
    except Exception as e:
        return f"[Error analizando imagen: {e}]"
