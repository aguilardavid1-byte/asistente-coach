"""Endpoint de navegación — GET /api/nav (sidebar).

Auto-crea chats faltantes para grupos y tareas que no tengan.
"""

from flask import Blueprint, jsonify
from flask_login import current_user

from db import get_db

nav_bp = Blueprint("nav", __name__)


def _asegurar_chat_grupo(conn, grupo_id: int, nombre: str, user_id: int) -> int:
    """Retorna el chat_id del grupo, creándolo si no existe."""
    chat = conn.execute(
        "SELECT id FROM chats WHERE tipo='grupo' AND ref_id=? AND user_id=?", (grupo_id, user_id)
    ).fetchone()
    if chat:
        return chat["id"]
    conn.execute(
        "INSERT INTO chats (tipo, ref_id, nombre, user_id) VALUES ('grupo', ?, ?, ?)",
        (grupo_id, nombre, user_id),
    )
    cid = conn.execute("SELECT MAX(id) FROM chats").fetchone()[0]
    conn.execute(
        "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, 'assistant', ?)",
        (cid, f"## 📁 {nombre}\n\nEste es el espacio del grupo **{nombre}**. ¿Por dónde empezamos?"),
    )
    return cid


def _asegurar_chat_tarea(conn, tarea_id: int, titulo: str, user_id: int) -> int | None:
    """Retorna el chat_id de la tarea, creándolo si no existe."""
    chat = conn.execute(
        "SELECT id FROM chats WHERE tipo='tarea' AND ref_id=? AND user_id=?", (tarea_id, user_id)
    ).fetchone()
    if chat:
        return chat["id"]
    conn.execute(
        "INSERT INTO chats (tipo, ref_id, nombre, user_id) VALUES ('tarea', ?, ?, ?)",
        (tarea_id, titulo, user_id),
    )
    return conn.execute("SELECT MAX(id) FROM chats").fetchone()[0]


def _build_grupo(conn, g: dict, user_id: int) -> dict:
    """Construye la respuesta JSON para un grupo, incluyendo subgrupos anidados."""
    chat_id = _asegurar_chat_grupo(conn, g["id"], g["nombre"], user_id)

    tareas_pendientes = conn.execute(
        "SELECT COUNT(*) FROM tareas WHERE grupo_id = ? AND estado = 'pendiente' AND user_id = ?",
        (g["id"], user_id),
    ).fetchone()[0]

    # Tareas directas de este grupo (incluye crear chats si faltan)
    tareas_raw = conn.execute(
        "SELECT id, titulo, prioridad, estado FROM tareas WHERE grupo_id = ? AND user_id = ? ORDER BY prioridad, creado_en",
        (g["id"], user_id),
    ).fetchall()

    chats = []
    for t in tareas_raw:
        ctid = _asegurar_chat_tarea(conn, t["id"], t["titulo"], user_id)
        chats.append({
            "id": ctid,
            "nombre": t["titulo"],
            "tipo": "tarea",
            "estado": t["estado"],
            "prioridad": t["prioridad"],
        })

    resultado = {
        "id": g["id"],
        "slug": g["slug"],
        "nombre": g["nombre"],
        "icono": g["icono"] or "📁",
        "chat_id": chat_id,
        "tareas_pendientes": tareas_pendientes,
        "parent_id": g["parent_id"],
        "chats": chats,
        "subgrupos": [],
    }

    # Subgrupos (hijos)
    hijos = conn.execute(
        "SELECT id, slug, nombre, icono, parent_id FROM grupos WHERE parent_id = ? AND user_id = ? ORDER BY orden, nombre",
        (g["id"], user_id),
    ).fetchall()
    for h in hijos:
        resultado["subgrupos"].append(_build_grupo(conn, h, user_id))

    return resultado


@nav_bp.route("/nav", methods=["GET"])
def obtener_nav():
    """Retorna estructura completa del sidebar con jerarquía de subgrupos.

    Response JSON:
    {
        "chats_directos": [{"id": 1, "nombre": "General", "tipo": "general"}],
        "grupos": [...],
        "tareas_sueltas": [...]
    }
    """
    conn = get_db()
    user_id = current_user.id

    directos = conn.execute(
        "SELECT id, nombre, tipo FROM chats WHERE tipo = 'general' AND user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()

    # Solo grupos raíz (parent_id IS NULL) — los subgrupos se anidan dentro
    grupos_raiz = conn.execute(
        "SELECT id, slug, nombre, icono, parent_id FROM grupos WHERE parent_id IS NULL AND user_id = ? ORDER BY orden, nombre",
        (user_id,),
    ).fetchall()

    grupos = []
    for g in grupos_raiz:
        grupos.append(_build_grupo(conn, g, user_id))

    # Tareas sin grupo (sueltas)
    sueltas_raw = conn.execute(
        "SELECT id, titulo, prioridad, estado FROM tareas WHERE grupo_id IS NULL AND user_id = ? ORDER BY prioridad, creado_en",
        (user_id,),
    ).fetchall()

    sueltas = []
    for t in sueltas_raw:
        ctid = _asegurar_chat_tarea(conn, t["id"], t["titulo"], user_id)
        sueltas.append({
            "id": ctid,
            "nombre": t["titulo"],
            "tipo": "tarea",
            "estado": t["estado"],
            "prioridad": t["prioridad"],
        })

    conn.commit()
    conn.close()

    return jsonify({
        "chats_directos": [dict(c) for c in directos],
        "grupos": grupos,
        "tareas_sueltas": sueltas,
    })
