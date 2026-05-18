"""Google OAuth + Local (username/password) authentication."""

import os
import sys
import re
import sqlite3

from flask import Blueprint, redirect, request, session, url_for
from flask import current_app, render_template_string
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_db

# ── Flask-Login User ────────────────────────────────────────────────────────

class Usuario(UserMixin):
    def __init__(self, row):
        if isinstance(row, sqlite3.Row):
            row = dict(row)
        self.id = row["id"]
        self.google_id = row.get("google_id")
        self.username = row.get("username")
        self.email = row.get("email", "")
        self.nombre = row.get("nombre", "")
        self.avatar_url = row.get("avatar_url", "")

    def get_id(self):
        return str(self.id)


# ── LoginManager ────────────────────────────────────────────────────────────

login_manager = LoginManager()
login_manager.login_view = "auth.login_page"

@login_manager.user_loader
def load_user(user_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM usuarios WHERE id=?", (int(user_id),)).fetchone()
    conn.close()
    return Usuario(row) if row else None


# ── Auth Blueprint ──────────────────────────────────────────────────────────

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET"])
def login_page():
    return render_template_string(_LOGIN_HTML)


@auth_bp.route("/login", methods=["POST"])
def login_post():
    """POST /auth/login — login con username y contraseña."""
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return {"error": "Usuario y contraseña requeridos"}, 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE username=? AND password_hash != ''",
        (username,),
    ).fetchone()
    conn.close()

    if not row or not check_password_hash(row["password_hash"], password):
        return {"error": "Usuario o contraseña incorrectos"}, 401

    user = Usuario(row)
    login_user(user)
    return {"ok": True, "redirect": "/"}


@auth_bp.route("/register", methods=["GET"])
def register_page():
    return render_template_string(_REGISTER_HTML)


@auth_bp.route("/register", methods=["POST"])
def register_post():
    """POST /auth/register — crear cuenta local."""
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    nombre = (data.get("nombre") or username).strip()

    # Validaciones
    if not username or not password:
        return {"error": "Usuario y contraseña requeridos"}, 400
    if len(username) < 3:
        return {"error": "El usuario debe tener al menos 3 caracteres"}, 400
    if len(password) < 4:
        return {"error": "La contraseña debe tener al menos 4 caracteres"}, 400
    if not re.match(r"^[a-z0-9_]+$", username):
        return {"error": "Solo letras minúsculas, números y guión bajo"}, 400

    conn = get_db()
    exists = conn.execute("SELECT id FROM usuarios WHERE username=?", (username,)).fetchone()
    if exists:
        conn.close()
        return {"error": "El usuario ya existe"}, 409

    pwd_hash = generate_password_hash(password)
    conn.execute(
        "INSERT INTO usuarios (username, email, nombre, password_hash) VALUES (?, ?, ?, ?)",
        (username, f"{username}@local", nombre, pwd_hash),
    )
    conn.commit()
    uid = conn.execute("SELECT MAX(id) FROM usuarios").fetchone()[0]
    conn.close()

    # Auto-login después de registro
    user = Usuario({
        "id": uid,
        "google_id": None,
        "username": username,
        "email": f"{username}@local",
        "nombre": nombre,
        "avatar_url": "",
    })
    login_user(user)
    return {"ok": True, "redirect": "/"}


@auth_bp.route("/google/login")
def google_login():
    oauth = current_app.extensions.get("authlib.integrations.flask_client")
    if not oauth:
        return "Error: OAuth no configurado", 500
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    oauth = current_app.extensions.get("authlib.integrations.flask_client")
    if not oauth:
        return "Error: OAuth no configurado", 500
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or oauth.google.parse_id_token(token)

    google_id = userinfo["sub"]
    email = userinfo.get("email", "")
    nombre = userinfo.get("name", email.split("@")[0])
    avatar = userinfo.get("picture", "")

    conn = get_db()
    row = conn.execute("SELECT * FROM usuarios WHERE google_id=?", (google_id,)).fetchone()
    if row:
        user = Usuario(row)
    else:
        conn.execute(
            "INSERT INTO usuarios (google_id, email, nombre, avatar_url) VALUES (?, ?, ?, ?)",
            (google_id, email, nombre, avatar),
        )
        conn.commit()
        uid = conn.execute("SELECT MAX(id) FROM usuarios").fetchone()[0]
        user = Usuario({
            "id": uid,
            "google_id": google_id,
            "username": None,
            "email": email,
            "nombre": nombre,
            "avatar_url": avatar,
        })
    conn.close()

    login_user(user)
    return redirect(url_for("index"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/me")
@login_required
def me():
    return {
        "id": current_user.id,
        "nombre": current_user.nombre,
        "email": current_user.email,
        "avatar": current_user.avatar_url,
    }


# ── Login HTML ──────────────────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Iniciar sesión — Asistente Coach</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #efeae2; display: flex; align-items: center; justify-content: center; }
    .card { background: #fff; border-radius: 12px; padding: 32px; text-align: center; box-shadow: 0 2px 16px rgba(0,0,0,0.1); max-width: 380px; width: 90%; }
    .card h1 { font-size: 22px; color: #075e54; margin-bottom: 4px; }
    .card p.sub { color: #667781; font-size: 14px; margin-bottom: 24px; }
    .or-divider { display: flex; align-items: center; gap: 12px; margin: 20px 0; color: #8696a0; font-size: 13px; }
    .or-divider::before, .or-divider::after { content: ""; flex: 1; height: 1px; background: #e0d6cc; }
    .google-btn { display: inline-flex; align-items: center; justify-content: center; gap: 10px; width: 100%; background: #fff; border: 2px solid #ddd; border-radius: 8px; padding: 12px; font-size: 15px; font-weight: 600; cursor: pointer; transition: border-color 0.15s; text-decoration: none; color: #333; }
    .google-btn:hover { border-color: #075e54; }
    .form-group { text-align: left; margin-bottom: 14px; }
    .form-group label { display: block; font-size: 13px; font-weight: 600; color: #3b4a54; margin-bottom: 4px; }
    .form-group input { width: 100%; padding: 10px 12px; border: 2px solid #ddd; border-radius: 6px; font-size: 14px; outline: none; transition: border-color 0.15s; }
    .form-group input:focus { border-color: #075e54; }
    .btn-primary { width: 100%; padding: 12px; background: #075e54; color: #fff; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background 0.15s; }
    .btn-primary:hover { background: #054d44; }
    .error-msg { color: #c62828; font-size: 13px; margin-top: 8px; display: none; }
    .link { margin-top: 16px; font-size: 13px; color: #667781; }
    .link a { color: #075e54; text-decoration: none; font-weight: 600; }
    .link a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🤖 Asistente Coach</h1>
    <p class="sub">Inicia sesión para acceder</p>

    <!-- Google -->
    <a class="google-btn" href="/auth/google/login" id="google-btn">
      <svg viewBox="0 0 48 48" width="20" height="20"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.54 28.59A14.5 14.5 0 0 1 9.5 24c0-1.59.28-3.14.76-4.59l-7.98-6.19A23.99 23.99 0 0 0 0 24c0 3.77.87 7.35 2.56 10.56l7.98-5.97z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 5.97C6.51 42.62 14.62 48 24 48z"/></svg>
      Iniciar sesión con Google
    </a>

    <div class="or-divider">o</div>

    <!-- Login form -->
    <form id="login-form" onsubmit="return loginLocal(event)">
      <div class="form-group">
        <label>Usuario</label>
        <input type="text" id="username" placeholder="usuario" required autocomplete="username">
      </div>
      <div class="form-group">
        <label>Contraseña</label>
        <input type="password" id="password" placeholder="••••••••" required autocomplete="current-password">
      </div>
      <div id="login-error" class="error-msg"></div>
      <button type="submit" class="btn-primary">Entrar</button>
    </form>

    <div class="link">¿No tienes cuenta? <a href="/auth/register">Crear una</a></div>
  </div>

  <script>
  async function loginLocal(e) {
    e.preventDefault();
    const errEl = document.getElementById('login-error');
    errEl.style.display = 'none';
    const btn = e.target.querySelector('button');
    btn.disabled = true; btn.textContent = 'Entrando...';

    try {
      const r = await fetch('/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          username: document.getElementById('username').value,
          password: document.getElementById('password').value,
        }),
      });
      const data = await r.json();
      if (r.ok && data.redirect) {
        window.location.href = data.redirect;
      } else {
        errEl.textContent = data.error || 'Error al iniciar sesión';
        errEl.style.display = 'block';
      }
    } catch(e) {
      errEl.textContent = 'Error de conexión';
      errEl.style.display = 'block';
    }
    btn.disabled = false; btn.textContent = 'Entrar';
    return false;
  }
  </script>
</body>
</html>"""


_REGISTER_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Crear cuenta — Asistente Coach</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #efeae2; display: flex; align-items: center; justify-content: center; }
    .card { background: #fff; border-radius: 12px; padding: 32px; text-align: center; box-shadow: 0 2px 16px rgba(0,0,0,0.1); max-width: 380px; width: 90%; }
    .card h1 { font-size: 22px; color: #075e54; margin-bottom: 4px; }
    .card p.sub { color: #667781; font-size: 14px; margin-bottom: 24px; }
    .form-group { text-align: left; margin-bottom: 14px; }
    .form-group label { display: block; font-size: 13px; font-weight: 600; color: #3b4a54; margin-bottom: 4px; }
    .form-group input { width: 100%; padding: 10px 12px; border: 2px solid #ddd; border-radius: 6px; font-size: 14px; outline: none; transition: border-color 0.15s; }
    .form-group input:focus { border-color: #075e54; }
    .form-group .hint { font-size: 12px; color: #8696a0; margin-top: 2px; }
    .btn-primary { width: 100%; padding: 12px; background: #075e54; color: #fff; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background 0.15s; }
    .btn-primary:hover { background: #054d44; }
    .error-msg { color: #c62828; font-size: 13px; margin-top: 8px; display: none; }
    .link { margin-top: 16px; font-size: 13px; color: #667781; }
    .link a { color: #075e54; text-decoration: none; font-weight: 600; }
    .link a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🤖 Asistente Coach</h1>
    <p class="sub">Crear una cuenta nueva</p>

    <form id="register-form" onsubmit="return registerLocal(event)">
      <div class="form-group">
        <label>Nombre (opcional)</label>
        <input type="text" id="nombre" placeholder="Tu nombre" autocomplete="name">
      </div>
      <div class="form-group">
        <label>Usuario</label>
        <input type="text" id="username" placeholder="usuario" required autocomplete="username">
        <div class="hint">Mínimo 3 caracteres, solo minúsculas, números y _</div>
      </div>
      <div class="form-group">
        <label>Contraseña</label>
        <input type="password" id="password" placeholder="••••••••" required autocomplete="new-password" minlength="4">
        <div class="hint">Mínimo 4 caracteres</div>
      </div>
      <div id="register-error" class="error-msg"></div>
      <button type="submit" class="btn-primary">Crear cuenta</button>
    </form>

    <div class="link">¿Ya tienes cuenta? <a href="/auth/login">Iniciar sesión</a></div>
  </div>

  <script>
  async function registerLocal(e) {
    e.preventDefault();
    const errEl = document.getElementById('register-error');
    errEl.style.display = 'none';
    const btn = e.target.querySelector('button');
    btn.disabled = true; btn.textContent = 'Creando...';

    try {
      const r = await fetch('/auth/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          username: document.getElementById('username').value,
          password: document.getElementById('password').value,
          nombre: document.getElementById('nombre').value,
        }),
      });
      const data = await r.json();
      if (r.ok && data.redirect) {
        window.location.href = data.redirect;
      } else {
        errEl.textContent = data.error || 'Error al crear cuenta';
        errEl.style.display = 'block';
      }
    } catch(e) {
      errEl.textContent = 'Error de conexión';
      errEl.style.display = 'block';
    }
    btn.disabled = false; btn.textContent = 'Crear cuenta';
    return false;
  }
  </script>
</body>
</html>"""
