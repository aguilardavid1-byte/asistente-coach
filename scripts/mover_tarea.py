#!/usr/bin/env python3
"""mover_tarea.py — Mueve una tarea de un grupo a otro.

Uso: python scripts/mover_tarea.py --tarea-id 3 --grupo-id 5

Salida:
  ✓ Tarea "Título" movida de "Grupo A" a "Grupo B" (id=X)
  ✗ ERROR: ...
"""
import argparse
import sys

from db import get_db


def mover(tarea_id: int, grupo_destino_id: int) -> tuple[bool, str]:
    conn = get_db()

    tarea = conn.execute(
        "SELECT t.id, t.titulo, t.grupo_id, g.nombre as grupo_nombre FROM tareas t LEFT JOIN grupos g ON g.id = t.grupo_id WHERE t.id = ?",
        (tarea_id,),
    ).fetchone()
    if not tarea:
        conn.close()
        return False, f"✗ ERROR: La tarea ID {tarea_id} no existe"

    destino = conn.execute(
        "SELECT id, nombre FROM grupos WHERE id = ?", (grupo_destino_id,)
    ).fetchone()
    if not destino:
        conn.close()
        return False, f"✗ ERROR: El grupo destino ID {grupo_destino_id} no existe"

    grupo_origen_nombre = tarea["grupo_nombre"] or "(sin grupo)"
    conn.execute("UPDATE tareas SET grupo_id = ? WHERE id = ?", (grupo_destino_id, tarea_id))
    conn.commit()
    conn.close()

    return True, f'✓ Tarea "{tarea["titulo"]}" movida de "{grupo_origen_nombre}" a "{destino["nombre"]}" (id={tarea_id})'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mover una tarea a otro grupo")
    parser.add_argument("--tarea-id", required=True, type=int, help="ID de la tarea")
    parser.add_argument("--grupo-id", required=True, type=int, help="ID del grupo destino")
    args = parser.parse_args()

    ok, msg = mover(args.tarea_id, args.grupo_id)
    print(msg)
    sys.exit(0 if ok else 1)
