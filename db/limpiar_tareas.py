"""
Script de limpieza puntual: deja el grupo Maestría solo con tareas reales.
Las materias (Diseño, Gestión, IAP, Pasantía) pasan a ser contexto en el chat del grupo.

Ejecutar una sola vez:
    python db/limpiar_tareas.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db

TITULOS_NO_TAREA = [
    "Diseño de proyectos de aula para educación inclusiva",
    "Gestión de proyectos transversales para la educación",
    "Investigación acción participativa",
    "Pasantía",
    "Ir pasando las imágenes de las materias y tareas pendientes",
    "Identificar la materia o tarea que más pesa",
    "retomar una de las cuatro materias activas",
]

CONTEXTO_MATERIAS = """📚 **Materias activas de la maestría** (referencia — aún sin tareas asignadas):

• Diseño de proyectos de aula para educación inclusiva (23%)
• Gestión de proyectos transversales para la educación (24%)
• Investigación acción participativa (26%)
• Pasantía (21%)

Las tareas concretas de cada materia se agregarán cuando se comparta el detalle de cada una."""

def limpiar():
    conn = get_db()

    # Buscar chat del grupo Maestría (tipo='grupo', ref_id del grupo con slug='maestría')
    grupo = conn.execute("SELECT id FROM grupos WHERE slug = 'maestría'").fetchone()
    if not grupo:
        print("⚠ Grupo 'maestría' no encontrado.")
        conn.close()
        return

    grupo_id = grupo["id"]
    chat_grupo = conn.execute(
        "SELECT id FROM chats WHERE tipo='grupo' AND ref_id=?", (grupo_id,)
    ).fetchone()

    eliminadas = 0
    duplicados = set()

    for titulo in TITULOS_NO_TAREA:
        # Buscar todas las tareas que coincidan (incluyendo duplicados)
        rows = conn.execute(
            "SELECT id FROM tareas WHERE titulo LIKE ?", (f"%{titulo}%",)
        ).fetchall()
        for row in rows:
            tid = row["id"]
            # Eliminar mensajes del chat de esta tarea
            conn.execute(
                "DELETE FROM mensajes WHERE chat_id IN "
                "(SELECT id FROM chats WHERE tipo='tarea' AND ref_id=?)", (tid,)
            )
            # Eliminar el chat de esta tarea
            conn.execute("DELETE FROM chats WHERE tipo='tarea' AND ref_id=?", (tid,))
            # Eliminar la tarea
            conn.execute("DELETE FROM tareas WHERE id=?", (tid,))
            eliminadas += 1
            print(f"  🗑 Eliminada: {titulo[:60]}")

    # Inyectar mensaje de contexto en el chat del grupo Maestría
    if chat_grupo:
        conn.execute(
            "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, 'assistant', ?)",
            (chat_grupo["id"], CONTEXTO_MATERIAS),
        )
        print(f"  💬 Contexto de materias inyectado en chat del grupo Maestría")
    else:
        print("  ⚠ Chat del grupo Maestría no encontrado, no se inyectó contexto.")

    conn.commit()
    conn.close()
    print(f"\n✅ Listo. {eliminadas} tareas eliminadas.")
    print("   Tareas que quedan son acciones reales pendientes.")

if __name__ == "__main__":
    limpiar()
