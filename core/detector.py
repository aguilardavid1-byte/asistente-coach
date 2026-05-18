"""Detector automático — analiza respuestas del coach y extrae tareas/cambios."""

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

from config import DEEPSEEK_KEY, DEEPSEEK_MODEL, DEEPSEEK_ENDPOINT
from db import get_db

_DETECTOR_PROMPT = """Analiza el siguiente texto (del usuario o del coach). Extrae TAREAS mencionadas y CONTEXTO.

Texto:
"{texto}"

Extrae en formato JSON (sin explicaciones, solo JSON válido):
{{
  "tareas_nuevas": [
    {{"titulo": "texto", "prioridad": "alta|media|baja", "grupo": "nombre_del_grupo_basado_en_contexto"}}
  ],
  "tareas_actualizadas": [
    {{"titulo": "texto", "nuevo_estado": "completada|en_progreso|cancelada", "nueva_prioridad": "alta|media|baja"}}
  ],
  "perfil": {{
    "nombre": "solo si el usuario dijo su nombre",
    "estado_animo": "solo si se infiere claramente"
  }},
  "acciones": [
    {{
      "tipo": "eliminar_tarea",
      "titulo": "título parcial de la tarea a eliminar"
    }},
    {{
      "tipo": "mover_tareas_a_grupo",
      "grupo_origen": "nombre del grupo a vaciar (o null si no aplica)",
      "grupo_destino": "nombre del grupo destino",
      "titulos": ["solo si especificó tareas individuales, si es todo el grupo dejar vacío"]
    }},
    {{
      "tipo": "eliminar_grupo",
      "grupo": "nombre del grupo a eliminar (solo si está vacío)"
    }},
    {{
      "tipo": "comentar_en_chat",
      "chat_destino_tipo": "grupo|tarea",
      "chat_destino_nombre": "nombre del grupo o tarea",
      "comentario": "texto del comentario a inyectar (autoexplicativo, quién lo generó y qué pasó)"
    }}
  ]
}}

REGLAS CRÍTICAS - LEE EL CONTEXTO:
- Si el usuario menciona "de la materia X" o "PROFESOR NAME", USA ESE NOMBRE COMO GRUPO
  * Ejemplo: "estas son de la materia Diseño de proyectos (MARCELA)" → grupo: "Diseño de proyectos (MARCELA)"
  * Ejemplo: "Gestión de proyectos (AURA GARCIA)" → grupo: "Gestión de proyectos (AURA GARCIA)"
- Si el contexto indica que es una materia dentro de un grupo mayor, el sistema la creará como subgrupo automáticamente
- Si no hay contexto de materia, infiere el grupo por el OBJETIVO DE VIDA:
  * Universidad, maestría, trabajos → "Maestría al día"
  * Limpieza, cocina, desorden, casa → "Casa en orden"
  * Clases, planear, estudiantes, enseñanza, colegio → "Docencia eficiente"
  * Entretenimiento, series, películas → "Películas por ver"
  * Barba, cabeza, zapatos, ropa, presentación personal → "Presentación personal"
  * Ejercicio, calistenia, rutina, salud, deporte → "Salud y ejercicio"
  * Silla, monitor, escritorio, espacio de trabajo, equipos → "Espacio de trabajo"
- NUNCA dejes "grupo" vacío — SIEMPRE clasifica en uno de los 7 objetivos
- "tareas_nuevas": SOLO si hay NUEVAS tareas listadas (no si solo habla de existentes), O si el coach dice haber creado una tarea nueva
- NO trates actividades con nombres diferentes como duplicados — cada materia tiene sus propias actividades
- Sin texto adicional, SOLO JSON"""


def _parsear_json(texto: str) -> dict[str, Any]:
    """Extrae y parsea el primer objeto JSON del texto."""
    texto = texto.strip()
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio == -1 or fin == -1:
        return {"tareas_nuevas": [], "tareas_actualizadas": [], "perfil": {}, "acciones": []}
    try:
        return json.loads(texto[inicio : fin + 1])
    except json.JSONDecodeError:
        return {"tareas_nuevas": [], "tareas_actualizadas": [], "perfil": {}, "acciones": []}


def detectar_entidades(texto_respuesta: str, chat_id: int = 0, user_id: int = 0) -> dict[str, Any]:
    """Analiza el texto del coach y extrae tareas, cambios, perfil y acciones.

    Args:
        texto_respuesta: texto del coach.
        chat_id: ID del chat donde ocurre (para contexto de subgrupos).
        user_id: ID del usuario propietario.

    Retorna:
        dict con claves: tareas_nuevas, tareas_actualizadas, perfil, acciones
    """
    if not texto_respuesta.strip():
        return {"tareas_nuevas": [], "tareas_actualizadas": [], "perfil": {}, "acciones": []}

    # Obtener contexto del chat para subgrupos
    contexto_chat = ""
    if chat_id:
        try:
            conn = get_db()
            chat = conn.execute("SELECT tipo, ref_id, nombre FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).fetchone()
            if chat and chat["tipo"] == "grupo" and chat["ref_id"]:
                padre = conn.execute("SELECT id, nombre FROM grupos WHERE id=? AND user_id=?", (chat["ref_id"], user_id)).fetchone()
                if padre:
                    contexto_chat = f'\nCONTEXTO: El usuario está en el grupo "{padre["nombre"]}".\nLas nuevas materias que mencionen deben crearse como SUBGRUPOS de este grupo.\n'
            conn.close()
        except Exception:
            pass

    prompt_base = _DETECTOR_PROMPT.format(texto=texto_respuesta[:2000])
    prompt = prompt_base + contexto_chat

    try:
        client = OpenAI(base_url=DEEPSEEK_ENDPOINT, api_key=DEEPSEEK_KEY)
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        raw = resp.choices[0].message.content or ""
        return _parsear_json(raw)
    except Exception as e:
        print(f"  ⚠ Detector falló: {e}", flush=True)
        return {"tareas_nuevas": [], "tareas_actualizadas": [], "perfil": {}}


def _slug(titulo: str) -> str:
    safe = "".join(c for c in titulo.lower() if c.isalnum() or c == " ")[:40].strip()
    return safe.replace(" ", "-")


def _get_parent_id(conn, chat_id: int, user_id: int) -> int | None:
    """Si el chat es de tipo 'grupo', retorna su ref_id como posible parent_id para subgrupos.
    Filtra por user_id."""
    try:
        chat = conn.execute(
            "SELECT tipo, ref_id FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)
        ).fetchone()
        if chat and chat["tipo"] == "grupo" and chat["ref_id"]:
            return chat["ref_id"]
    except Exception:
        pass
    return None


def aplicar_detecciones(detecciones: dict[str, Any], chat_id: int, user_id: int) -> dict:
    """Guarda en DB lo detectado.

    Args:
        detecciones: salida de detectar_entidades()
        chat_id: ID del chat donde ocurrió
        user_id: ID del usuario propietario

    Returns:
        dict con reportes detallados:
        {
            "tareas_creadas": [{"titulo": ..., "id": ..., "grupo": ...}],
            "grupos_creados": [{"nombre": ..., "id": ...}],
            "tareas_actualizadas": [{"titulo": ..., "cambio": ...}],
        }
    """
    conn = get_db()
    reporte = {
        "tareas_creadas": [],
        "grupos_creados": [],
        "tareas_actualizadas": [],
    }

    parent_id = _get_parent_id(conn, chat_id, user_id)

    # ── Perfil ────────────────────────────────────────────────────────────
    perfil = detecciones.get("perfil") or {}
    if perfil.get("nombre") or perfil.get("estado_animo"):
        updates = []
        params = []
        if perfil.get("nombre"):
            updates.append("nombre = ?")
            params.append(perfil["nombre"])
        if perfil.get("estado_animo"):
            updates.append("estado = ?")
            params.append(perfil["estado_animo"])
        if updates:
            params.append(user_id)
            conn.execute(
                f"UPDATE perfiles SET {', '.join(updates)} WHERE user_id = ?",
                params,
            )

    # ── Tareas nuevas ─────────────────────────────────────────────────────
    for t in detecciones.get("tareas_nuevas") or []:
        titulo = (t.get("titulo") or "").strip()
        if not titulo:
            continue

        grupo_nombre = (t.get("grupo") or "").strip().lower()
        grupo_id = None
        grupo_nombre_real = None

        if grupo_nombre:
            row = conn.execute(
                "SELECT id, nombre FROM grupos WHERE slug = ? AND user_id = ?", (grupo_nombre, user_id)
            ).fetchone()
            if row:
                grupo_id = row["id"]
                grupo_nombre_real = row["nombre"]
            else:
                # Crear como subgrupo si hay parent_id
                if parent_id is not None:
                    conn.execute(
                        "INSERT INTO grupos (slug, nombre, parent_id, user_id) VALUES (?, ?, ?, ?)",
                        (grupo_nombre, t["grupo"].strip(), parent_id, user_id),
                    )
                else:
                    conn.execute(
                        "INSERT INTO grupos (slug, nombre, user_id) VALUES (?, ?, ?)",
                        (grupo_nombre, t["grupo"].strip(), user_id),
                    )
                grupo_id = conn.execute(
                    "SELECT id FROM grupos WHERE slug = ? AND user_id = ?", (grupo_nombre, user_id)
                ).fetchone()["id"]
                grupo_nombre_real = t["grupo"].strip()
                from core.chats import asegurar_chat_grupo
                asegurar_chat_grupo(grupo_id, grupo_nombre, grupo_nombre_real, user_id)
                parent_str = f" → (subgrupo de grupo {parent_id})" if parent_id is not None else ""
                reporte["grupos_creados"].append({"nombre": grupo_nombre_real, "id": grupo_id})

        conn.execute(
            """INSERT INTO tareas (grupo_id, titulo, prioridad, user_id)
               VALUES (?, ?, ?, ?)""",
            (grupo_id, titulo, t.get("prioridad", "media"), user_id),
        )
        tarea_id = conn.execute("SELECT MAX(id) FROM tareas").fetchone()[0]
        reporte["tareas_creadas"].append({
            "titulo": titulo,
            "id": tarea_id,
            "grupo": grupo_nombre_real,
        })

        # Crear chat para la tarea
        task_slug = _slug(titulo)
        conn.execute(
            "INSERT INTO chats (tipo, ref_id, nombre, user_id) VALUES (?, ?, ?, ?)",
            ("tarea", tarea_id, titulo, user_id),
        )

    # ── Tareas actualizadas ───────────────────────────────────────────────
    for t in detecciones.get("tareas_actualizadas") or []:
        titulo = (t.get("titulo") or "").strip()
        if not titulo:
            continue
        if t.get("nuevo_estado"):
            conn.execute(
                "UPDATE tareas SET estado = ? WHERE id = ("
                "SELECT id FROM tareas WHERE titulo LIKE ? AND user_id = ? ORDER BY id DESC LIMIT 1)",
                (t["nuevo_estado"], f"%{titulo}%", user_id),
            )
            reporte["tareas_actualizadas"].append({
                "titulo": titulo,
                "cambio": f"estado → {t['nuevo_estado']}"
            })
        if t.get("nueva_prioridad"):
            conn.execute(
                "UPDATE tareas SET prioridad = ? WHERE id = ("
                "SELECT id FROM tareas WHERE titulo LIKE ? AND user_id = ? ORDER BY id DESC LIMIT 1)",
                (t["nueva_prioridad"], f"%{titulo}%", user_id),
            )
            reporte["tareas_actualizadas"].append({
                "titulo": titulo,
                "cambio": f"prioridad → {t['nueva_prioridad']}"
            })

    conn.commit()
    conn.close()
    return reporte


# ── Detector de acciones estructurales por ID ─────────────────────────────────

_ACCIONES_PROMPT = """Eres un procesador de instrucciones de un sistema de gestión de tareas.

El usuario dijo: "{mensaje_usuario}"
El coach respondió: "{respuesta_coach}"

═══ ESTADO REAL DE LA BASE DE DATOS ═══
{estado_db}
═══════════════════════════════════════

Tu tarea: generar JSON con las operaciones de DB a ejecutar SOLO si el usuario O el coach LO PIDEN EXPLÍCITAMENTE.

Tipos disponibles (usa EXACTAMENTE estos nombres):
[
  {{"tipo": "crear_grupo", "nombre": "...", "parent_id": N}},
  {{"tipo": "crear_tarea", "titulo": "...", "grupo_id": N o null, "prioridad": "alta|media|baja"}},
  {{"tipo": "eliminar_tarea", "id": N}},
  {{"tipo": "eliminar_grupo", "id": N}},
  {{"tipo": "mover_tarea", "tarea_id": N, "grupo_id": N, "grupo_nombre": "nombre del grupo (alternativa si no sabes el ID)"}},
  {{"tipo": "comentar_en_chat", "chat_destino_tipo": "grupo|tarea", "chat_destino_nombre": "nombre exacto", "comentario": "texto del comentario"}}
]

REGLAS CRÍTICAS (NUNCA VIOLAR):
1. Si el coach USA PASADO ("he creado", "he eliminado", "he movido", "quedó eliminada", "ya eliminé", "creé", "moví") → genera la acción correspondiente. El coach solo dice esto cuando la acción DEBE ejecutarse.
2. Si el usuario pide "elimina", "borra", "quita", "mueve", "pasa", "crea" o similar → genera la acción.
3. Excepción: si el coach solo repite/confirma sin indicar nueva acción ("la misma", "como dices"), no generar.
4. Si el usuario solo pega contenido sin pedir nada → retorna [].
5. Si no hay ninguna señal de acción → retorna [].
6. Responde SOLO el array JSON, sin explicaciones.


	FUNCIONALIDAD CLAVE — PROPAGAR CONTEXTO A TAREAS:
	Cuando el usuario está en un chat de GRUPO y comparte información útil para una o más tareas de ese grupo, DEBES generar un "comentar_en_chat" por cada tarea afectada para que el contexto llegue al chat individual de cada tarea.

	Ejemplo: usuario está en "Docencia eficiente" y pega el horario de clases. El coach responde relacionándolo con "Planear clase de mañana". Entonces debes generar:
	[{{"tipo": "comentar_en_chat", "chat_destino_tipo": "tarea", "chat_destino_nombre": "Planear clase de mañana", "comentario": "Contexto desde Docencia eficiente: [resumen de la información compartida]"}}]

CONTEXTO DE SUBGRUPOS:
- Si el chat está dentro de un grupo, crear_grupo debe usar parent_id del grupo activo
	- parent_id = id del grupo padre (null si es grupo raiz)"""


def _obtener_estado_db(chat_id: int, user_id: int) -> tuple[str, int | None]:
    """Retorna descripción textual del estado DB relevante al chat y el grupo_id si aplica.
    Filtra por user_id."""
    conn = get_db()
    chat = conn.execute("SELECT tipo, ref_id, nombre FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).fetchone()

    lineas = []
    grupo_activo_id = None

    if chat and chat["tipo"] == "grupo" and chat["ref_id"]:
        grupo_activo_id = chat["ref_id"]
        g = conn.execute("SELECT id, nombre, parent_id FROM grupos WHERE id=? AND user_id=?", (grupo_activo_id, user_id)).fetchone()
        if g:
            # Mostrar info de padre si es subgrupo
            if g["parent_id"]:
                padre = conn.execute("SELECT nombre FROM grupos WHERE id=? AND user_id=?", (g["parent_id"], user_id)).fetchone()
                if padre:
                    lineas.append(f'  Subgrupo de: "{padre["nombre"]}"')
            lineas.append(f'Grupo activo: "{g["nombre"]}" (id={g["id"]})')
            tareas = conn.execute(
                "SELECT id, titulo, estado FROM tareas WHERE grupo_id=? AND user_id=?", (g["id"], user_id)
            ).fetchall()
            for t in tareas:
                lineas.append(f'  - Tarea id={t["id"]}: "{t["titulo"]}" ({t["estado"]})')
    else:
        grupos = conn.execute("SELECT id, nombre, parent_id FROM grupos WHERE user_id=?", (user_id,)).fetchall()
        for g in grupos:
            prefix = "Subgrupo ─ " if g["parent_id"] else "Grupo ─ "
            lineas.append(f'{prefix}"{g["nombre"]}" (id={g["id"]}):')
            tareas = conn.execute(
                "SELECT id, titulo, estado FROM tareas WHERE grupo_id=? AND user_id=?", (g["id"], user_id)
            ).fetchall()
            for t in tareas:
                lineas.append(f'  - Tarea id={t["id"]}: "{t["titulo"]}" ({t["estado"]})')

        # Mostrar tareas sueltas (sin grupo)
        tareas_sueltas = conn.execute(
            "SELECT id, titulo, estado FROM tareas WHERE grupo_id IS NULL AND user_id=?", (user_id,)
        ).fetchall()
        if tareas_sueltas:
            lineas.append("Tareas sueltas (sin grupo):")
            for t in tareas_sueltas:
                lineas.append(f'  - Tarea id={t["id"]}: "{t["titulo"]}" ({t["estado"]})')

    conn.close()
    return "\n".join(lineas) or "(sin grupos ni tareas)", grupo_activo_id


def ejecutar_acciones_por_id(acciones: list[dict], chat_id: int, user_id: int) -> list[dict]:
    """Ejecuta acciones estructurales usando IDs exactos de DB.
    Filtra todas las operaciones por user_id.

    Retorna lista de reportes: [{"accion": "...", "exito": bool, "detalle": "..."}]
    """
    if not acciones:
        return []
    reportes = []
    conn = get_db()
    try:
        for accion in acciones:
            tipo = accion.get("tipo")

            if tipo == "crear_grupo":
                nombre = (accion.get("nombre") or "").strip()
                parent_id = accion.get("parent_id")
                if not nombre:
                    reportes.append({"accion": "crear_grupo", "exito": False, "detalle": "falta nombre"})
                    continue
                slug = nombre.lower()
                # Verificar si ya existe (solo dentro del usuario)
                exists = conn.execute(
                    "SELECT id FROM grupos WHERE (lower(slug)=? OR lower(nombre)=?) AND user_id=?",
                    (slug, slug, user_id),
                ).fetchone()
                if exists:
                    reportes.append({
                        "accion": "crear_grupo",
                        "exito": False,
                        "detalle": f"Grupo \"{nombre}\" ya existe",
                    })
                    continue
                if parent_id:
                    conn.execute("INSERT INTO grupos (slug, nombre, parent_id, user_id) VALUES (?, ?, ?, ?)", (slug, nombre, parent_id, user_id))
                else:
                    conn.execute("INSERT INTO grupos (slug, nombre, user_id) VALUES (?, ?, ?)", (slug, nombre, user_id))
                gid = conn.execute("SELECT MAX(id) FROM grupos").fetchone()[0]
                # Crear chat del grupo usando la MISMA conexión (evitar lock anidado)
                conn.execute(
                    "INSERT INTO chats (tipo, ref_id, nombre, user_id) VALUES ('grupo', ?, ?, ?)",
                    (gid, nombre, user_id),
                )
                chat_id_grupo = conn.execute("SELECT MAX(id) FROM chats").fetchone()[0]
                conn.execute(
                    "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, 'assistant', ?)",
                    (chat_id_grupo, f"## 📁 {nombre}\n\nEste es el espacio del grupo **{nombre}**. ¿Por dónde empezamos?"),
                )
                reportes.append({
                    "accion": "crear_grupo",
                    "exito": True,
                    "detalle": f"Grupo creado: \"{nombre}\"",
                })

            elif tipo == "crear_tarea":
                titulo = (accion.get("titulo") or "").strip()
                if not titulo:
                    reportes.append({"accion": "crear_tarea", "exito": False, "detalle": "falta título"})
                    continue
                gid = accion.get("grupo_id")
                prioridad = accion.get("prioridad", "media")
                # Validar grupo_id si se pasó
                grupo_nombre = None
                if gid:
                    g = conn.execute("SELECT nombre FROM grupos WHERE id=? AND user_id=?", (gid, user_id)).fetchone()
                    if not g:
                        reportes.append({
                            "accion": "crear_tarea",
                            "exito": False,
                            "detalle": f"grupo id={gid} no existe",
                        })
                        continue
                    grupo_nombre = g["nombre"]
                conn.execute(
                    "INSERT INTO tareas (grupo_id, titulo, prioridad, user_id) VALUES (?, ?, ?, ?)",
                    (gid, titulo, prioridad, user_id),
                )
                tid = conn.execute("SELECT MAX(id) FROM tareas").fetchone()[0]
                conn.execute(
                    "INSERT INTO chats (tipo, ref_id, nombre, user_id) VALUES (?, ?, ?, ?)",
                    ("tarea", tid, titulo, user_id),
                )
                grupo_str = f" en \"{grupo_nombre}\"" if grupo_nombre else ""
                reportes.append({
                    "accion": "crear_tarea",
                    "exito": True,
                    "detalle": f"Tarea creada: \"{titulo}\"{grupo_str}",
                })

            elif tipo == "eliminar_tarea":
                tid = accion.get("id")
                if not tid:
                    reportes.append({"accion": "eliminar_tarea", "exito": False, "detalle": "falta id"})
                    continue
                row = conn.execute("SELECT titulo FROM tareas WHERE id=? AND user_id=?", (tid, user_id)).fetchone()
                if not row:
                    reportes.append({"accion": "eliminar_tarea", "exito": False, "detalle": f"tarea id={tid} no existe"})
                    continue
                titulo = row["titulo"]
                conn.execute(
                    "DELETE FROM mensajes WHERE chat_id IN "
                    "(SELECT id FROM chats WHERE tipo='tarea' AND ref_id=? AND user_id=?)", (tid, user_id)
                )
                conn.execute("DELETE FROM chats WHERE tipo='tarea' AND ref_id=? AND user_id=?", (tid, user_id))
                conn.execute("DELETE FROM tareas WHERE id=? AND user_id=?", (tid, user_id))
                reportes.append({"accion": "eliminar_tarea", "exito": True, "detalle": f"Tarea eliminada: \"{titulo}\""})

            elif tipo == "eliminar_grupo":
                gid = accion.get("id")
                if not gid:
                    reportes.append({"accion": "eliminar_grupo", "exito": False, "detalle": "falta id"})
                    continue
                total = _eliminar_grupo_recursivo(conn, gid, user_id)
                if total is None:
                    reportes.append({"accion": "eliminar_grupo", "exito": False, "detalle": f"grupo id={gid} no existe"})
                else:
                    reportes.append({
                        "accion": "eliminar_grupo", "exito": True,
                        "detalle": f"Grupo eliminado (liberadas {total} tarea(s))"
                    })

            elif tipo == "mover_tarea":
                tid = accion.get("tarea_id")
                gid = accion.get("grupo_id")
                gnombre = (accion.get("grupo_nombre") or "").strip()
                if not tid:
                    reportes.append({"accion": "mover_tarea", "exito": False, "detalle": "falta tarea_id"})
                    continue
                # Resolver grupo: si no existe grupo_id o el grupo no se encuentra,
                # intentar por nombre (útil cuando el grupo se creó en el mismo lote)
                g = None
                if gid:
                    g = conn.execute("SELECT id, nombre FROM grupos WHERE id=? AND user_id=?", (gid, user_id)).fetchone()
                if not g and gnombre:
                    g = conn.execute(
                        "SELECT id, nombre FROM grupos WHERE nombre LIKE ? AND user_id=? ORDER BY id DESC LIMIT 1",
                        (f"%{gnombre}%", user_id),
                    ).fetchone()
                if not g:
                    reportes.append({"accion": "mover_tarea", "exito": False, "detalle": "grupo destino no encontrado"})
                    continue
                t = conn.execute("SELECT titulo, grupo_id FROM tareas WHERE id=? AND user_id=?", (tid, user_id)).fetchone()
                if not t:
                    reportes.append({"accion": "mover_tarea", "exito": False, "detalle": "tarea no existe"})
                    continue
                if t["grupo_id"] == g["id"]:
                    reportes.append({
                        "accion": "mover_tarea", "exito": True,
                        "detalle": f"Tarea \"{t['titulo']}\" ya está en \"{g['nombre']}\""
                    })
                    continue
                conn.execute("UPDATE tareas SET grupo_id=? WHERE id=? AND user_id=?", (g["id"], tid, user_id))
                reportes.append({
                    "accion": "mover_tarea",
                    "exito": True,
                    "detalle": f"Tarea \"{t['titulo']}\" movida a \"{g['nombre']}\""
                })
            elif tipo == "comentar_en_chat":
                c_tipo = accion.get("chat_destino_tipo")
                c_nombre = (accion.get("chat_destino_nombre") or "").strip()
                comentario = (accion.get("comentario") or "").strip()
                if not all([c_tipo, c_nombre, comentario]):
                    reportes.append({"accion": "comentar_en_chat", "exito": False, "detalle": "faltan campos"})
                    continue
                if c_tipo == "grupo":
                    row = conn.execute(
                        "SELECT c.id FROM chats c JOIN grupos g ON g.id=c.ref_id "
                        "WHERE c.tipo='grupo' AND (lower(g.slug)=? OR lower(g.nombre)=?) AND g.user_id=? AND c.user_id=?",
                        (c_nombre.lower(), c_nombre.lower(), user_id, user_id),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT c.id FROM chats c JOIN tareas t ON t.id=c.ref_id "
                        "WHERE c.tipo='tarea' AND t.titulo LIKE ? AND t.user_id=? AND c.user_id=?",
                        ("%" + c_nombre + "%", user_id, user_id),
                    ).fetchone()
                if row:
                    conn.execute(
                        "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, 'assistant', ?)",
                        (row["id"], "Contexto compartido desde grupo: " + comentario),
                    )
                    reportes.append({"accion": "comentar_en_chat", "exito": True, "detalle": "Comentario inyectado en '" + c_nombre + "'"})
                else:
                    reportes.append({"accion": "comentar_en_chat", "exito": False, "detalle": "Chat '" + c_nombre + "' no encontrado"})
            else:
                reportes.append({"accion": tipo, "exito": False, "detalle": f"tipo desconocido: {tipo}"})

        conn.commit()
    except Exception as e:
        reportes.append({"accion": "error", "exito": False, "detalle": str(e)})
    finally:
        conn.close()
    return reportes


def detectar_acciones_estructurales(
    mensaje_usuario: str,
    respuesta_coach: str,
    chat_id: int,
    user_id: int = 0,
) -> list[dict]:
    """Detecta acciones estructurales usando IDs exactos de DB.

    A diferencia de detectar_entidades(), esta función recibe el estado real
    de la DB y pide al LLM que mapee la intención a IDs concretos.
    """
    estado_db, _ = _obtener_estado_db(chat_id, user_id)

    prompt = _ACCIONES_PROMPT.format(
        mensaje_usuario=mensaje_usuario[:500],
        respuesta_coach=respuesta_coach[:500],
        estado_db=estado_db,
    )

    print(f"  [ACCIONES] Prompt:\n{prompt[:300]}...", flush=True)

    try:
        client = OpenAI(base_url=DEEPSEEK_ENDPOINT, api_key=DEEPSEEK_KEY)
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=1024,
        )
        raw = (resp.choices[0].message.content or "").strip()
        print(f"  [ACCIONES] Raw response: {raw}", flush=True)

        inicio = raw.find("[")
        fin = raw.rfind("]")
        if inicio == -1 or fin == -1:
            print(f"  [ACCIONES] No JSON array found in response", flush=True)
            return []

        acciones = json.loads(raw[inicio:fin + 1])
        print(f"  [ACCIONES] Parsed: {acciones}", flush=True)
        # Filtrar acciones con IDs inválidos (LLM puede alucinar)
        acciones = _filtrar_acciones_validas(acciones, user_id)
        print(f"  [ACCIONES] Filtradas: {acciones}", flush=True)

        # Fallback: si el LLM no detectó nada, intentar por patrones en el texto del coach
        if not acciones:
            acciones = _detectar_por_patron(respuesta_coach, chat_id, user_id)
            if acciones:
                print(f"  [ACCIONES] Detectadas por patrón: {acciones}", flush=True)

        return acciones
    except Exception as e:
        print(f"  [ACCIONES] ERROR: {e}", flush=True)
        return []


def _detectar_por_patron(respuesta_coach: str, chat_id: int, user_id: int) -> list[dict]:
    """Detecta acciones por patrones textuales cuando el LLM falla."""
    import re
    acciones = []
    conn = get_db()
    try:
        # Obtener grupo activo (filtrado por user_id)
        chat = conn.execute("SELECT tipo, ref_id FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).fetchone()
        grupo_id = None
        if chat and chat["tipo"] == "grupo" and chat["ref_id"]:
            grupo_id = chat["ref_id"]
        elif chat and chat["tipo"] == "tarea" and chat["ref_id"]:
            # Si es chat de tarea, obtener grupo de la tarea (filtrado por user_id)
            t = conn.execute("SELECT grupo_id FROM tareas WHERE id=? AND user_id=?", (chat["ref_id"], user_id)).fetchone()
            if t:
                grupo_id = t["grupo_id"]
        else:
            # Chat general o chat_id no encontrado
            conn.close()
            return []

        # Obtener tareas del grupo activo (filtrado por user_id)
        tareas = conn.execute(
            "SELECT id, titulo FROM tareas WHERE grupo_id=? AND user_id=?", (grupo_id, user_id)
        ).fetchall()

        text = respuesta_coach.lower()

        # --- Detectar ELIMINAR ---
        if any(p in text for p in ["eliminad", "eliminé", "borr", "quit", "ya no existe", "ya no aparece", "está borrad"]):
            for t in tareas:
                titulo_lower = t["titulo"].lower()
                if titulo_lower in text:
                    acciones.append({"tipo": "eliminar_tarea", "id": t["id"]})

        # --- Detectar MOVER ---
        if "he movido" in text or "moví" in text or "quedaron en" in text:
            gnombre = None
            m = re.search(r'(?:subgrupo|grupo)\s*[""]?([^""\n]+?)[""]?', text)
            if m:
                gnombre = m.group(1).strip()
            for t in tareas:
                titulo_lower = t["titulo"].lower()
                if titulo_lower in text:
                    acc = {"tipo": "mover_tarea", "tarea_id": t["id"]}
                    if gnombre:
                        acc["grupo_nombre"] = gnombre
                    acciones.append(acc)

    finally:
        conn.close()

    return acciones


def _filtrar_acciones_validas(acciones: list[dict], user_id: int) -> list[dict]:
    """Elimina acciones que referencian IDs que no existen en DB (filtrados por user_id)."""
    if not acciones:
        return []
    conn = get_db()
    try:
        # Recopilar IDs reales del usuario
        ids_tareas = {r["id"] for r in conn.execute("SELECT id FROM tareas WHERE user_id=?", (user_id,)).fetchall()}
        ids_grupos = {r["id"] for r in conn.execute("SELECT id FROM grupos WHERE user_id=?", (user_id,)).fetchall()}
    finally:
        conn.close()

    validas = []
    for a in acciones:
        tipo = a.get("tipo")
        if tipo in ("eliminar_tarea",):
            if a.get("id") in ids_tareas:
                validas.append(a)
            else:
                print(f"  [FILTER] Ignorada {tipo} id={a.get('id')} (no existe para este usuario)", flush=True)
        elif tipo in ("eliminar_grupo",):
            if a.get("id") in ids_grupos:
                validas.append(a)
            else:
                print(f"  [FILTER] Ignorada {tipo} id={a.get('id')} (no existe para este usuario)", flush=True)
        elif tipo == "mover_tarea":
            tid = a.get("tarea_id")
            gid = a.get("grupo_id")
            gnombre = (a.get("grupo_nombre") or "").strip()
            if tid in ids_tareas and (gid in ids_grupos or gnombre):
                validas.append(a)
            else:
                print(f"  [FILTER] Ignorada {tipo} (IDs no existen para este usuario)", flush=True)
        elif tipo == "crear_tarea":
            # grupo_id puede ser None, pero si está debe existir
            gid = a.get("grupo_id")
            if gid is None or gid in ids_grupos:
                validas.append(a)
            else:
                print(f"  [FILTER] Ignorada crear_tarea: grupo_id={gid} no existe para este usuario", flush=True)
        else:
            # crear_grupo y otros sin IDs: pasan
            validas.append(a)
    return validas


def _eliminar_grupo_recursivo(conn, gid: int, user_id: int) -> int | None:
    """Elimina grupo recursivamente (subgrupos + tareas + chats).
    Filtra todas las operaciones por user_id.
    Retorna cantidad total de tareas eliminadas o None si no existe."""
    g = conn.execute("SELECT nombre FROM grupos WHERE id=? AND user_id=?", (gid, user_id)).fetchone()
    if not g:
        return None
    total = 0
    hijos = conn.execute("SELECT id FROM grupos WHERE parent_id=? AND user_id=?", (gid, user_id)).fetchall()
    for h in hijos:
        total += _eliminar_grupo_recursivo(conn, h["id"], user_id)
    tids = conn.execute("SELECT id FROM tareas WHERE grupo_id=? AND user_id=?", (gid, user_id)).fetchall()
    for t in tids:
        chat = conn.execute(
            "SELECT id FROM chats WHERE tipo='tarea' AND ref_id=? AND user_id=?", (t["id"], user_id)
        ).fetchone()
        if chat:
            conn.execute("DELETE FROM mensajes WHERE chat_id=?", (chat["id"],))
            conn.execute("DELETE FROM chats WHERE id=? AND user_id=?", (chat["id"], user_id))
    conn.execute("DELETE FROM tareas WHERE grupo_id=? AND user_id=?", (gid, user_id))
    total += len(tids)
    chat = conn.execute(
        "SELECT id FROM chats WHERE tipo='grupo' AND ref_id=? AND user_id=?", (gid, user_id)
    ).fetchone()
    if chat:
        conn.execute("DELETE FROM mensajes WHERE chat_id=?", (chat["id"],))
        conn.execute("DELETE FROM chats WHERE id=? AND user_id=?", (chat["id"], user_id))
    conn.execute("DELETE FROM grupos WHERE id=? AND user_id=?", (gid, user_id))
    return total
