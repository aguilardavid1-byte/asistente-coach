#!/usr/bin/env python3
"""progreso_tarea.py — Actualiza el porcentaje de progreso de una tarea.

Uso: python scripts/progreso_tarea.py --tarea-id 29 --progreso 50

Salida:
  ✓ "Título" ahora está al 50%
  ✗ ERROR: La tarea ID X no existe
"""
import argparse
import sys

from db import get_db


def progreso(tarea_id: int, valor: int) -> tuple[bool, str]:
    if valor < 0 or valor > 100:
        return False, "✗ ERROR: El progreso debe ser entre 0 y 100"

    conn = get_db()
    tarea = conn.execute(
        "SELECT id, titulo FROM tareas WHERE id = ?", (tarea_id,)
    ).fetchone()
    if not tarea:
        conn.close()
        return False, f"✗ ERROR: La tarea ID {tarea_id} no existe"

    conn.execute("UPDATE tareas SET progreso = ? WHERE id = ?", (valor, tarea_id))
    conn.commit()
    conn.close()

    return True, f'✓ "{tarea["titulo"]}" ahora está al {valor}%'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Actualizar progreso de una tarea")
    parser.add_argument("--tarea-id", required=True, type=int, help="ID de la tarea")
    parser.add_argument("--progreso", required=True, type=int, help="Porcentaje 0-100")
    args = parser.parse_args()

    ok, msg = progreso(args.tarea_id, args.progreso)
    print(msg)
    sys.exit(0 if ok else 1)
