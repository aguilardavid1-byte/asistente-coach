"""Motor conversacional del coach — construye prompts, llama a DeepSeek, stremea."""

import os
import sys
from typing import Generator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

from config import DEEPSEEK_KEY, DEEPSEEK_MODEL, DEEPSEEK_ENDPOINT
from db import get_db

_IMAGEN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "imagenes")


def _get_perfil():
    """Retorna el perfil del usuario (primera fila de perfiles)."""
    conn = get_db()
    row = conn.execute("SELECT * FROM perfiles ORDER BY id LIMIT 1").fetchone()
    conn.close()
    if row:
        import json
        return {
            "nombre": row["nombre"] or "",
            "metas": (json.loads(row["metas"]) if row["metas"] else []) if isinstance(row["metas"], str) else [],
            "estado": row["estado"] or "",
        }
    return {"nombre": "", "metas": [], "estado": ""}


def _get_chat_info(chat_id: int) -> dict:
    """Retorna info del chat: tipo, ref_id, nombre."""
    conn = get_db()
    row = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "tipo": row["tipo"], "ref_id": row["ref_id"], "nombre": row["nombre"]}
    return {"id": chat_id, "tipo": "general", "ref_id": None, "nombre": "General"}


def _get_grupo_info(grupo_id: int) -> dict:
    """Retorna info del grupo + lista de tareas."""
    conn = get_db()
    grupo = conn.execute("SELECT * FROM grupos WHERE id = ?", (grupo_id,)).fetchone()
    tareas = conn.execute(
        "SELECT titulo, prioridad, estado FROM tareas WHERE grupo_id = ? ORDER BY prioridad",
        (grupo_id,),
    ).fetchall()
    conn.close()
    if grupo:
        return {
            "nombre": grupo["nombre"],
            "tareas": [{"titulo": t["titulo"], "prioridad": t["prioridad"], "estado": t["estado"]} for t in tareas],
        }
    return {"nombre": "", "tareas": []}


def _get_tarea_info(tarea_id: int) -> dict:
    """Retorna info de una tarea."""
    conn = get_db()
    row = conn.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,)).fetchone()
    conn.close()
    if row:
        return {
            "titulo": row["titulo"],
            "descripcion": row["descripcion"],
            "prioridad": row["prioridad"],
            "estado": row["estado"],
            "fecha_limite": row["fecha_limite"],
        }
    return {}


def get_historial(chat_id: int, limit: int = 50) -> list[dict]:
    """Retorna los últimos N mensajes del chat como lista de {"role": ..., "content": ...}."""
    conn = get_db()
    rows = conn.execute(
        "SELECT rol, contenido FROM mensajes WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    conn.close()
    rows.reverse()
    return [{"role": r["rol"], "content": r["contenido"]} for r in rows]


def _get_recordatorios() -> str:
    """Retorna recordatorios de tareas recurrentes según el día."""
    from datetime import datetime
    conn = get_db()
    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    hoy_idx = datetime.now().weekday()
    hoy = dias[hoy_idx]
    manana = dias[(hoy_idx + 1) % 7]
    dia_mes = datetime.now().day

    rows = conn.execute(
        "SELECT t.titulo, t.recurrencia, g.nombre as grupo FROM tareas t LEFT JOIN grupos g ON g.id=t.grupo_id WHERE t.recurrencia IS NOT NULL"
    ).fetchall()
    conn.close()

    hoy_list = []
    pronto_list = []
    for r in rows:
        rec = r["recurrencia"].lower()
        if hoy in rec:
            hoy_list.append(f'  - {r["titulo"]} ({r["grupo"]}) — **HOY**')
        elif manana in rec:
            pronto_list.append(f'  - {r["titulo"]} ({r["grupo"]}) — MANANA')
        elif "mes" in rec and dia_mes <= 3:
            pronto_list.append(f'  - {r["titulo"]} ({r["grupo"]}) — {r["recurrencia"]} (principio de mes)')
        elif "semana" in rec and hoy_idx == 0:
            pronto_list.append(f'  - {r["titulo"]} ({r["grupo"]}) — {r["recurrencia"]} (esta semana)')

    partes = []
    if hoy_list:
        partes.append("\n".join(hoy_list))
    if pronto_list:
        tag = "PROXIMOS" if not hoy_list else "TAMBIEN PROXIMOS"
        partes.append("\n".join(pronto_list))

    if partes:
        titulo = f"RECORDATORIOS DEL DIA ({hoy.capitalize()}):"
        return f"\n{titulo}\n" + "\n".join(partes) + "\n"
    return ""


def construir_system_prompt(chat_id: int, descripcion_imagen: str = "") -> str:
    """Construye system prompt según el contexto del chat (general / grupo / tarea)."""
    perfil = _get_perfil()
    chat = _get_chat_info(chat_id)

    nombre = perfil["nombre"] or "amigo"
    metas = ", ".join(perfil["metas"]) if perfil["metas"] else "aún no definidas"
    estado = perfil["estado"] or "desconocido"
    recordatorios = _get_recordatorios()

    base = f"""Eres un coach de vida empático. Hablas en español natural y cálido.
Conoces a {nombre}. Sus metas: {metas}. Su estado actual: {estado}.

OBJETIVOS DE VIDA DE {nombre.upper()}:
El sistema organiza las tareas por estos GRANDES OBJETIVOS (grupos raíz):
1. "Maestría al día" — trabajos, materias, tareas de la maestría
2. "Casa en orden" — labores domésticas, limpieza, organización del hogar
3. "Docencia eficiente" — planear clases, preparar material, ser organizado como docente
4. "Películas por ver" — entretenimiento, series, películas
5. "Presentación personal" — cuidado personal, barba, cabeza, ropa, zapatos, compras de vestimenta
6. "Salud y ejercicio" — calistenia, ejercicio, rutinas, salud física, bienestar

REGLAS:
- Sé natural, como un amigo que escucha y orienta
- Adapta tu tono al estado de {nombre}
- Respuestas concisas: 2-4 párrafos, usa **negritas** para énfasis
- CLASIFICA automáticamente lo que {nombre} menciona en su objetivo correcto
- No esperes a que pida organización explícitamente — actúa cuando sea obvio
- Si menciona algo de la universidad/maestría/materias → agéndalo en "Maestría al día"
- Si menciona limpieza, desorden, casa, lavar, cocinar → agéndalo en "Casa en orden"  
- Si menciona planear clases, estudiantes, enseñanza, colegio → agéndalo en "Docencia eficiente"
- Si menciona barba, cabeza, calvo, zapatos, ropa, presentación, compras de vestimenta → agéndalo en "Presentación personal"
- Si menciona ejercicio, calistenia, rutina, salud, deporte → agéndalo en "Salud y ejercicio"
	- Si menciona silla, monitor, escritorio, espacio de trabajo, equipos → agéndalo en "Espacio de trabajo"
- Siempre di en qué objetivo quedó registrado: "Listo, te lo dejé agendado en [objetivo]"

CAPACIDADES DE ORGANIZACIÓN:
Puedes crear tareas, grupos, mover y eliminar. El sistema ejecuta los cambios automáticamente al detectar tus instrucciones.

IMPORTANTE — Cuando indiques que ya ejecutaste una acción, USA SIEMPRE PASADO para que el sistema la detecte:
- "He creado la tarea..." (no "voy a crear" ni "creo")
- "He movido las tareas a..." (no "voy a mover")
- "He eliminado la tarea..." / "La tarea ha sido eliminada" / "Ya quedó eliminada"

{recordatorios}"""

    if chat["tipo"] == "general" or (chat["tipo"] != "grupo" and chat["tipo"] != "tarea"):
        conn = get_db()
        grupos = conn.execute("SELECT id, nombre FROM grupos ORDER BY nombre").fetchall()
        grupos_info = []
        for g in grupos:
            count = conn.execute(
                "SELECT COUNT(*) FROM tareas WHERE grupo_id=? AND estado != 'completada'", (g["id"],)
            ).fetchone()[0]
            grupos_info.append(f'"{g["nombre"]}" ({count} tarea(s) activa(s))')
        conn.close()
        grupos_str = ", ".join(grupos_info) if grupos_info else "(ningún grupo creado aún)"

        base += f"""

Contexto actual: estás en el chat GENERAL.
Este espacio es abierto a CUALQUIER idea, tarea o pensamiento.

OBJETIVOS DE VIDA activos:
{grupos_str}

REGLAS para el chat General:
1. Escucha y CLASIFICA todo en uno de los 4 objetivos automáticamente
2. SE PROACTIVO: cuando {nombre} mencione algo pendiente, responde confirmando donde lo agendaste
3. Ejemplo: "manana tengo que planear clase" → "Listo, te lo agende en Docencia eficiente"
4. Ejemplo: "tengo el desorden de la casa" → "Lo deje en Casa en orden para que no se te olvide"
5. No preguntes "quieres que lo cree?" — si es obvio, hazlo y avisa
6. El sistema se encarga de crear las tareas automaticamente

ESPIRITU:
Eres un coach que escucha, clasifica y actua. No esperes instrucciones explicitas para lo obvio."No seas pasivo. Si ves que algo le importa, ayuda a organizarlo."""

    elif chat["tipo"] == "grupo" and chat["ref_id"]:
        info = _get_grupo_info(chat["ref_id"])
        tareas_str = "\n".join(
            f"  - {t['titulo']} ({t['prioridad']}, {t['estado']})"
            for t in info["tareas"]
        ) or "  (sin tareas aún)"
        # Obtener subgrupos
        conn2 = get_db()
        subgrupos = conn2.execute(
            "SELECT id, nombre FROM grupos WHERE parent_id=?", (chat["ref_id"],)
        ).fetchall()
        conn2.close()
        subgrupos_str = "\n".join(
            f"  📁 {s['nombre']}" for s in subgrupos
        ) or "  (sin subgrupos)"
        base += f"""

Contexto actual: estás en el grupo "{chat["nombre"]}".

Tareas directas de este grupo:
{tareas_str}

Subgrupos (materias dentro de este grupo):
{subgrupos_str}

Ayuda a priorizar, hacer seguimiento y organizar el trabajo de este grupo.

Si el usuario menciona una MATERIA o PROFESOR, sugiere crear un subgrupo para organizar sus tareas dentro de este grupo. El sistema creará automáticamente el subgrupo si el usuario acepta.

	PROPAGACIÓN AUTOMÁTICA: Si el usuario comparte información (horario, fechas, instrucciones) que sea relevante para alguna tarea específica de este grupo, menciónalo en tu respuesta para que el sistema lo propague automáticamente al chat de cada tarea afectada."""

    elif chat["tipo"] == "tarea" and chat["ref_id"]:
        info = _get_tarea_info(chat["ref_id"])
        if info:
            base += f"""

Contexto actual: estás hablando de la tarea específica "{info["titulo"]}".
Estado: {info["estado"]}. Prioridad: {info["prioridad"]}.
Vence: {info.get("fecha_limite") or "sin fecha"}.

Ayuda a avanzar en esta tarea, desglosarla y hacer seguimiento."""

    if descripcion_imagen:
        base += f"""

Contexto visual: el usuario adjuntó una imagen.
{descripcion_imagen}

Usa esta información como si hubieras visto la imagen."""

    return base


def _guardar_mensaje(chat_id: int, rol: str, contenido: str, imagen_path: str | None = None) -> None:
    conn = get_db()
    img_filename = os.path.basename(imagen_path) if imagen_path else None
    conn.execute(
        "INSERT INTO mensajes (chat_id, rol, contenido, tiene_imagen) VALUES (?, ?, ?, ?)",
        (chat_id, rol, contenido, img_filename),
    )
    conn.commit()
    conn.close()


def stream_respuesta(
    chat_id: int,
    mensaje: str,
    imagen_path: str | None = None,
) -> Generator[str, None, str]:
    """Stremea respuesta de DeepSeek y la persiste en DB.

    Yields: chunks de texto.
    Returns: texto completo de la respuesta.

    La función también guarda el mensaje del usuario y la respuesta
    final del asistente en la base de datos.
    """
    # 1. Guardar mensaje del usuario (con imagen si aplica)
    _guardar_mensaje(chat_id, "user", mensaje, imagen_path)

    # 2. Procesar imagen si hay
    descripcion_imagen = ""
    if imagen_path:
        from core.gemini import analizar_imagen
        descripcion_imagen = analizar_imagen(imagen_path)

    # 3. Construir prompt e historial
    system_prompt = construir_system_prompt(chat_id, descripcion_imagen)
    historial = get_historial(chat_id)

    messages = [{"role": "system", "content": system_prompt}, *historial]

    # 4. Llamar a DeepSeek con streaming
    client = OpenAI(base_url=DEEPSEEK_ENDPOINT, api_key=DEEPSEEK_KEY)
    respuesta_completa = ""

    try:
        stream = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=2048,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                respuesta_completa += delta
                yield delta
    except Exception as e:
        error_msg = f"\n\n[Error de conexión con DeepSeek: {e}]"
        respuesta_completa += error_msg
        yield error_msg

    # 5. Guardar respuesta del asistente
    _guardar_mensaje(chat_id, "assistant", respuesta_completa)

    return respuesta_completa
