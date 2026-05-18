"""Endpoint de chat — POST /api/chat/send (SSE streaming) y GET /api/chat/<id>."""

import base64
import json
import os
import re
import tempfile
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_login import current_user

from config import BASE_DIR
from core.coach import get_historial, stream_respuesta
from core.detector import (
    detectar_entidades,
    aplicar_detecciones,
    detectar_acciones_estructurales,
    ejecutar_acciones_por_id,
)
from db import get_db

_LOG_FILE = os.path.join(BASE_DIR, "debug.log")


def _log(msg: str):
    """Escribe a archivo de log para diagnóstico."""
    with open(_LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")


def _construir_confirmacion(reportes_estruct: list[dict], reporte_creacion: dict) -> list[dict]:
    """Construye lista de confirmaciones legibles para mostrar en UI.

    Cada item: {"exito": bool, "texto": "..."}
    """
    items = []

    # Reportes de acciones estructurales (eliminar, mover)
    for r in reportes_estruct:
        items.append({
            "exito": r.get("exito", False),
            "texto": r.get("detalle", "(sin detalle)"),
        })

    # Reportes de creación
    for g in reporte_creacion.get("grupos_creados", []):
        items.append({"exito": True, "texto": f"Grupo creado: \"{g['nombre']}\""})
    for t in reporte_creacion.get("tareas_creadas", []):
        grupo_str = f" en \"{t['grupo']}\"" if t.get("grupo") else ""
        items.append({"exito": True, "texto": f"Tarea creada: \"{t['titulo']}\"{grupo_str}"})
    for u in reporte_creacion.get("tareas_actualizadas", []):
        items.append({"exito": True, "texto": f"Tarea actualizada: \"{u['titulo']}\" ({u['cambio']})"})

    return items

chat_bp = Blueprint("chat", __name__)
_IMAGEN_DIR = os.path.join(BASE_DIR, "imagenes")


def _salvar_imagen(base64_str: str) -> str | None:
    """Convierte base64 a archivo temporal y retorna la ruta."""
    if not base64_str:
        return None
    try:
        os.makedirs(_IMAGEN_DIR, exist_ok=True)
        header, _, data = base64_str.partition(",")
        raw = base64.b64decode(data)
        ext = ".png"
        if "png" in header:
            ext = ".png"
        elif "jpeg" in header or "jpg" in header:
            ext = ".jpg"
        elif "gif" in header:
            ext = ".gif"
        elif "webp" in header:
            ext = ".webp"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(_IMAGEN_DIR, f"img_{stamp}{ext}")
        with open(path, "wb") as f:
            f.write(raw)
        return path
    except Exception as e:
        print(f"  ⚠ Error salvando imagen: {e}", flush=True)
        return None


_BLOQUE_ACCIONES = re.compile(r'\[ACCIONES_COACH\]:\s*(\[.*?\])\s*$', re.MULTILINE | re.DOTALL)


def _extraer_acciones(texto: str) -> tuple[str, list]:
    """Extrae el bloque [ACCIONES_COACH] del texto. Retorna (texto_limpio, acciones)."""
    # Log últimas 3 líneas para diagnóstico
    ultimas = texto.strip().splitlines()[-3:]
    print(f"  🔍 Últimas líneas del coach: {ultimas}", flush=True)

    m = _BLOQUE_ACCIONES.search(texto)
    if not m:
        return texto, []
    try:
        acciones = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON inválido en [ACCIONES_COACH]: {e}", flush=True)
        return texto, []
    texto_limpio = texto[:m.start()].rstrip()
    return texto_limpio, acciones


def _ejecutar_acciones(acciones: list, chat_id: int, user_id: int) -> None:
    """Ejecuta acciones estructurales directamente en DB."""
    if not acciones:
        return
    conn = get_db()
    try:
        for accion in acciones:
            tipo = accion.get("tipo")

            if tipo == "eliminar_tarea":
                titulo = (accion.get("titulo") or "").strip()
                if not titulo:
                    continue
                row = conn.execute(
                    "SELECT id FROM tareas WHERE user_id = ? AND (titulo = ? OR titulo LIKE ?) LIMIT 1",
                    (user_id, titulo, f"%{titulo}%"),
                ).fetchone()
                if row:
                    tid = row["id"]
                    conn.execute(
                        "DELETE FROM mensajes WHERE chat_id IN "
                        "(SELECT id FROM chats WHERE tipo='tarea' AND ref_id=? AND user_id=?)", (tid, user_id)
                    )
                    conn.execute("DELETE FROM chats WHERE tipo='tarea' AND ref_id=? AND user_id=?", (tid, user_id))
                    conn.execute("DELETE FROM tareas WHERE id=? AND user_id=?", (tid, user_id))
                    print(f"  🗑 Tarea eliminada: '{titulo}'", flush=True)
                else:
                    print(f"  ⚠ Tarea no encontrada: '{titulo}'", flush=True)

            elif tipo == "mover_tareas_a_grupo":
                origen_nombre = (accion.get("grupo_origen") or "").strip().lower()
                destino_nombre = (accion.get("grupo_destino") or "").strip().lower()
                if not destino_nombre:
                    continue
                destino = conn.execute(
                    "SELECT id FROM grupos WHERE user_id = ? AND (lower(slug) = ? OR lower(nombre) = ?)",
                    (user_id, destino_nombre, destino_nombre),
                ).fetchone()
                if not destino:
                    continue
                dest_id = destino["id"]
                titulos = accion.get("titulos") or []
                if titulos:
                    for t in titulos:
                        conn.execute(
                            "UPDATE tareas SET grupo_id=? WHERE user_id=? AND (titulo=? OR titulo LIKE ?)",
                            (dest_id, user_id, t, f"%{t}%"),
                        )
                elif origen_nombre:
                    origen = conn.execute(
                        "SELECT id FROM grupos WHERE user_id = ? AND (lower(slug) = ? OR lower(nombre) = ?)",
                        (user_id, origen_nombre, origen_nombre),
                    ).fetchone()
                    if origen:
                        conn.execute(
                            "UPDATE tareas SET grupo_id=? WHERE user_id=? AND grupo_id=?",
                            (dest_id, user_id, origen["id"]),
                        )
                print(f"  🔄 Tareas movidas a '{accion.get('grupo_destino', '')}'", flush=True)

            elif tipo == "eliminar_grupo":
                grupo_nombre = (accion.get("grupo") or "").strip().lower()
                if not grupo_nombre:
                    continue
                g = conn.execute(
                    "SELECT id, nombre FROM grupos WHERE user_id = ? AND (lower(slug) = ? OR lower(nombre) = ?)",
                    (user_id, grupo_nombre, grupo_nombre),
                ).fetchone()
                if g:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM tareas WHERE user_id=? AND grupo_id=?", (user_id, g["id"])
                    ).fetchone()[0]
                    if count == 0:
                        chat = conn.execute(
                            "SELECT id FROM chats WHERE tipo='grupo' AND ref_id=? AND user_id=?", (g["id"], user_id)
                        ).fetchone()
                        if chat:
                            conn.execute("DELETE FROM mensajes WHERE chat_id=?", (chat["id"],))
                            conn.execute("DELETE FROM chats WHERE id=? AND user_id=?", (chat["id"], user_id))
                        conn.execute("DELETE FROM grupos WHERE id=? AND user_id=?", (g["id"], user_id))
                        print(f"  🗑 Grupo eliminado: '{g['nombre']}'", flush=True)
                    else:
                        print(f"  ⚠ Grupo '{g['nombre']}' tiene {count} tareas, no se eliminó", flush=True)

            elif tipo == "comentar_en_chat":
                c_tipo = accion.get("chat_destino_tipo")
                c_nombre = (accion.get("chat_destino_nombre") or "").strip()
                comentario = (accion.get("comentario") or "").strip()
                if not all([c_tipo, c_nombre, comentario]):
                    continue
                if c_tipo == "grupo":
                    chat = conn.execute(
                        """SELECT c.id FROM chats c JOIN grupos g ON g.id=c.ref_id
                           WHERE c.tipo='grupo' AND (lower(g.slug)=? OR lower(g.nombre)=?)
                           AND g.user_id=? AND c.user_id=?""",
                        (c_nombre.lower(), c_nombre.lower(), user_id, user_id),
                    ).fetchone()
                else:
                    chat = conn.execute(
                        """SELECT c.id FROM chats c JOIN tareas t ON t.id=c.ref_id
                           WHERE c.tipo='tarea' AND t.titulo LIKE ?
                           AND t.user_id=? AND c.user_id=?""",
                        (f"%{c_nombre}%", user_id, user_id),
                    ).fetchone()
                if chat:
                    conn.execute(
                        "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, 'assistant', ?)",
                        (chat["id"], f"📌 *Nota del coach:* {comentario}"),
                    )
                    print(f"  💬 Comentario inyectado en '{c_nombre}'", flush=True)

        conn.commit()
    finally:
        conn.close()


def _propagar_si_aplica(chat_id: int, respuesta: str, user_id: int):
    """Si el coach menciona mover/organizar tareas, inyecta nota en hijos."""
    PALABRAS_CLAVE = [
        "moviendo", "moví", "organicé", "asigné",
        "quedó en", "lo puse en", "cambié a", "actualicé",
        "trasladé", "reorganicé", "pasé al grupo", "pasé a",
    ]
    if any(p in respuesta.lower() for p in PALABRAS_CLAVE):
        resumen = respuesta[:200].strip()
        from core.comentarios import inyectar_comentario
        inyectar_comentario(chat_id, resumen, user_id)


@chat_bp.route("/chat/<int:chat_id>", methods=["GET"])
def obtener_chat(chat_id):
    """GET /api/chat/<id> → historial completo + metadatos del chat."""
    conn = get_db()
    chat = conn.execute("SELECT * FROM chats WHERE id = ? AND user_id = ?", (chat_id, current_user.id)).fetchone()
    if not chat:
        conn.close()
        return jsonify({"error": "Chat no encontrado"}), 404

    mensajes = conn.execute(
        "SELECT id, rol, contenido, tiene_imagen, creado_en FROM mensajes WHERE chat_id = ? ORDER BY id",
        (chat_id,),
    ).fetchall()
    conn.close()

    return jsonify({
        "id": chat["id"],
        "tipo": chat["tipo"],
        "ref_id": chat["ref_id"],
        "nombre": chat["nombre"],
        "mensajes": [dict(m) for m in mensajes],
    })


@chat_bp.route("/chat/send", methods=["POST"])
def enviar_mensaje():
    """POST /api/chat/send → SSE stream con la respuesta del coach.

    Request JSON:
        chat_id: int
        mensaje: str
        imagen_base64: str | null (opcional)

    Response: SSE (text/event-stream)
        data: {"tipo": "chunk", "texto": "..."}
        data: {"tipo": "fin", "tareas_nuevas": 3}
    """
    data = request.get_json(force=True)
    chat_id = data.get("chat_id")
    mensaje = (data.get("mensaje") or "").strip()

    if not chat_id or not mensaje:
        return jsonify({"error": "chat_id y mensaje requeridos"}), 400

    user_id = current_user.id
    imagen_path = _salvar_imagen(data.get("imagen_base64") or "")

    # Verificar que el chat pertenece al usuario
    conn = get_db()
    chat = conn.execute("SELECT id FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id)).fetchone()
    conn.close()
    if not chat:
        return jsonify({"error": "Chat no encontrado"}), 404

    def generar_stream():
        texto_completo = ""
        chunks = []
        try:
            # 1. Obtener respuesta completa del coach (acumular chunks sin enviar aún)
            for chunk in stream_respuesta(chat_id, mensaje, imagen_path, user_id):
                texto_completo += chunk
                chunks.append(chunk)

            # 2. Detectar y ejecutar acciones ANTES de enviar la respuesta del coach
            _log(f">>> Usuario (chat_id={chat_id}): {mensaje[:100]}")
            _log(f">>> Coach respondió: {texto_completo[:150]}")

            acciones = detectar_acciones_estructurales(mensaje, texto_completo, chat_id, user_id)
            _log(f">>> Acciones detectadas: {acciones}")

            reportes_estructurales = []
            if acciones:
                reportes_estructurales = ejecutar_acciones_por_id(acciones, chat_id, user_id)
                _log(f">>> Reportes: {reportes_estructurales}")

            # 3. Detector para tareas_nuevas y perfil
            detecciones = detectar_entidades(texto_completo, chat_id, user_id)
            reporte_creacion = aplicar_detecciones(detecciones, chat_id, user_id)
            _log(f">>> Reporte creación: {reporte_creacion}")

            _propagar_si_aplica(chat_id, texto_completo, user_id)

            # 4. Construir confirmaciones
            confirmaciones = _construir_confirmacion(reportes_estructurales, reporte_creacion)

            # 5. ENVIAR PRIMERO las confirmaciones de acciones ejecutadas
            if confirmaciones:
                yield f"data: {json.dumps({'tipo': 'confirmaciones', 'confirmaciones': confirmaciones})}\n\n"

            # 6. DESPUÉS enviar la respuesta del coach
            for chunk in chunks:
                yield f"data: {json.dumps({'tipo': 'chunk', 'texto': chunk})}\n\n"

            # 7. Terminar
            yield f"data: {json.dumps({'tipo': 'fin', 'tareas_nuevas': len(reporte_creacion.get('tareas_creadas', []))})}\n\n"

        except Exception as e:
            _log(f"!!! ERROR: {e}")
            yield f"data: {json.dumps({'tipo': 'error', 'texto': str(e)})}\n\n"
        finally:
            # No eliminar imágenes — se conservan para el historial del chat
            pass

    return Response(
        stream_with_context(generar_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
