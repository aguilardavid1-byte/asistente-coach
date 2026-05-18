"""Endpoint de tareas — GET /api/tareas, PATCH /api/tareas/<id>."""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from db import get_db

tareas_bp = Blueprint("tareas", __name__)


@tareas_bp.route("/tareas", methods=["GET"])
def listar_tareas():
    """GET /api/tareas — lista todas las tareas del usuario actual."""
    conn = get_db()
    rows = conn.execute(
        """SELECT t.*, g.nombre as grupo_nombre, g.slug as grupo_slug
           FROM tareas t
           LEFT JOIN grupos g ON g.id = t.grupo_id
           WHERE t.user_id = ?
           ORDER BY
             CASE t.prioridad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,
             t.creado_en DESC""",
        (current_user.id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@tareas_bp.route("/tareas/<int:tarea_id>", methods=["PATCH"])
def actualizar_tarea(tarea_id):
    """PATCH /api/tareas/<id> — actualiza campos de una tarea.

    Request JSON (todos opcionales):
        estado: "pendiente" | "en_progreso" | "completada"
        prioridad: "alta" | "media" | "baja"
        fecha_limite: "YYYY-MM-DD" | null
        titulo: str
        descripcion: str
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Body requerido"}), 400

    conn = get_db()

    existente = conn.execute("SELECT id FROM tareas WHERE id = ? AND user_id = ?", (tarea_id, current_user.id)).fetchone()
    if not existente:
        conn.close()
        return jsonify({"error": "Tarea no encontrada"}), 404

    campos_permitidos = {"estado", "prioridad", "fecha_limite", "titulo", "descripcion"}
    updates = []
    params = []
    for key in campos_permitidos:
        if key in data:
            updates.append(f"{key} = ?")
            params.append(data[key])

    if updates:
        params.append(tarea_id)
        params.append(current_user.id)
        conn.execute(
            f"UPDATE tareas SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
            params,
        )
        conn.commit()

    tarea = conn.execute("SELECT * FROM tareas WHERE id = ? AND user_id = ?", (tarea_id, current_user.id)).fetchone()
    conn.close()

    return jsonify(dict(tarea) if tarea else {})
