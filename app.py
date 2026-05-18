"""Entry point Flask — registra blueprints y sirve frontend."""

import os
import sys

from flask import Flask, send_from_directory, redirect, url_for, request
from flask_login import current_user
from authlib.integrations.flask_client import OAuth

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.chat import chat_bp
from api.nav import nav_bp
from api.tareas import tareas_bp
from auth import auth_bp, login_manager
from config import PORT, SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from db.init_db import main as init_db
from db.schema import crear_tablas
from db import get_db

_appdir = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(os.path.join(_appdir, "asistente.db")):
    print("📦 Inicializando base de datos...")
    init_db()

# Siempre asegurar esquema actualizado (CREATE IF NOT EXISTS para nuevas tablas)
conn = get_db()
crear_tablas(conn)
conn.close()

app = Flask(__name__, static_folder="frontend", static_url_path="")
app.secret_key = SECRET_KEY

# ── OAuth ───────────────────────────────────────────────────────────────────
oauth = OAuth(app)
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ── Auth ────────────────────────────────────────────────────────────────────
login_manager.init_app(app)
login_manager.login_view = "auth.login_page"
app.register_blueprint(auth_bp)

# ── Imágenes ────────────────────────────────────────────────────────────────
_IMAGEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imagenes")
os.makedirs(_IMAGEN_DIR, exist_ok=True)

@app.route("/imagenes/<path:filename>")
def servir_imagen(filename):
    return send_from_directory(_IMAGEN_DIR, filename)

# ── API endpoints ───────────────────────────────────────────────────────────
app.register_blueprint(chat_bp, url_prefix="/api")
app.register_blueprint(nav_bp, url_prefix="/api")
app.register_blueprint(tareas_bp, url_prefix="/api")

# ── Auth check for all /api/* routes ───────────────────────────────────────
@app.before_request
def require_auth():
    if request.path.startswith("/api/") and not current_user.is_authenticated:
        return {"error": "No autorizado"}, 401

@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login_page"))
    return send_from_directory("frontend", "index.html")


if __name__ == "__main__":
    debug = os.environ.get("FLASK_ENV") == "development"
    print(f"🚀 Servidor en http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=debug)
