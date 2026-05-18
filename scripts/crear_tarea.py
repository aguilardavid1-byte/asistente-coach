#!/usr/bin/env python3
"""crear_tarea.py — Crea una tarea dentro de un grupo.

Uso: python scripts/crear_tarea.py --titulo "Título" --grupo-id 2 [--prioridad media] [--fecha-limite "2026-06-14"]

Salida:
  ✓ Tarea creada: "Título" en "Grupo" (id=X, vence: YYYY-MM-DD)
  ✗ ERROR: El grupo ID X no existe
"""
import argparse
import sys

from db import get_db


def crear(titulo: str, grupo_id: int, prioridad: str = "media", fecha_limite: str = "", recurrencia: str = "", progreso: int = 0) -> tuple[bool, str]:
    conn = get_db()

    grupo = conn.execute("SELECT id, nombre FROM grupos WHERE id = ?", (grupo_id,)).fetchone()
    if not grupo:
        conn.close()
        return False, f'✗ ERROR: El grupo ID {grupo_id} no existe'

    conn.execute(
        "INSERT INTO tareas (grupo_id, titulo, prioridad, fecha_limite, recurrencia, progreso) VALUES (?, ?, ?, ?, ?, ?)",
        (grupo_id, titulo.strip(), prioridad, fecha_limite or None, recurrencia or None, progreso),
    )
    conn.commit()
    nuevo_id = conn.execute("SELECT MAX(id) FROM tareas").fetchone()[0]
    conn.close()

    vence = f", vence: {fecha_limite}" if fecha_limite else ""
    recur = f", recurrencia: {recurrencia}" if recurrencia else ""
    prog = f", progreso: {progreso}%" if progreso else ""
    return True, f'✓ Tarea creada: "{titulo}" en "{grupo["nombre"]}" (id={nuevo_id}{vence}{recur}{prog})'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crear una tarea en un grupo")
    parser.add_argument("--titulo", required=True, help="Título de la tarea")
    parser.add_argument("--grupo-id", required=True, type=int, help="ID del grupo")
    parser.add_argument("--prioridad", default="media", choices=["alta", "media", "baja"], help="Prioridad (default: media)")
    parser.add_argument("--fecha-limite", default="", help="Fecha límite (YYYY-MM-DD)")
    parser.add_argument("--recurrencia", default="", help="Recurrencia (ej: cada miercoles, diario, cada mes)")
    parser.add_argument("--progreso", type=int, default=0, help="Porcentaje de avance 0-100")
    args = parser.parse_args()

    ok, msg = crear(args.titulo, args.grupo_id, args.prioridad, args.fecha_limite, args.recurrencia, args.progreso)
    print(msg)
    sys.exit(0 if ok else 1)
