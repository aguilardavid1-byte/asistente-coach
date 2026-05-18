#!/usr/bin/env python3
"""eliminar_tarea.py — Elimina una tarea por ID.

Uso: python scripts/eliminar_tarea.py --tarea-id 3

Salida:
  ✓ Tarea "Título" eliminada (id=X, grupo_id=Y)
  ✗ ERROR: La tarea ID X no existe
"""
import argparse
import sys

from db import get_db


def eliminar(tarea_id: int) -> tuple[bool, str]:
    conn = get_db()

    tarea = conn.execute(
        "SELECT id, titulo, grupo_id FROM tareas WHERE id = ?", (tarea_id,)
    ).fetchone()
    if not tarea:
        conn.close()
        return False, f"✗ ERROR: La tarea ID {tarea_id} no existe"

    # Eliminar chat asociado (si existe)
    chat = conn.execute(
        "SELECT id FROM chats WHERE tipo = 'tarea' AND ref_id = ?", (tarea_id,)
    ).fetchone()
    if chat:
        conn.execute("DELETE FROM mensajes WHERE chat_id = ?", (chat["id"],))
        conn.execute("DELETE FROM chats WHERE id = ?", (chat["id"],))

    conn.execute("DELETE FROM tareas WHERE id = ?", (tarea_id,))
    conn.commit()
    conn.close()

    return True, f'✓ Tarea "{tarea["titulo"]}" eliminada (id={tarea_id}, grupo_id={tarea["grupo_id"]})'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eliminar una tarea")
    parser.add_argument("--tarea-id", required=True, type=int, help="ID de la tarea a eliminar")
    args = parser.parse_args()

    ok, msg = eliminar(args.tarea_id)
    print(msg)
    sys.exit(0 if ok else 1)
