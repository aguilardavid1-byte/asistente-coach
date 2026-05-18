#!/usr/bin/env python3
"""eliminar_grupo.py — Elimina un grupo (solo si está vacío).

Uso: python scripts/eliminar_grupo.py --grupo-id 2

Salida:
  ✓ Grupo "Nombre" eliminado (id=X, estaba vacío)
  ✗ ERROR: Grupo "Nombre" no se puede eliminar (contiene N tareas)
  ✗ ERROR: El grupo ID X no existe
"""
import argparse
import sys

from db import get_db


def eliminar(grupo_id: int) -> tuple[bool, str]:
    conn = get_db()

    grupo = conn.execute(
        "SELECT id, nombre FROM grupos WHERE id = ?", (grupo_id,)
    ).fetchone()
    if not grupo:
        conn.close()
        return False, f"✗ ERROR: El grupo ID {grupo_id} no existe"

    count = conn.execute(
        "SELECT COUNT(*) FROM tareas WHERE grupo_id = ?", (grupo_id,)
    ).fetchone()[0]

    if count > 0:
        conn.close()
        return False, f'✗ ERROR: Grupo "{grupo["nombre"]}" no se puede eliminar (contiene {count} tareas)'

    # Eliminar chat del grupo (si existe)
    chat = conn.execute(
        "SELECT id FROM chats WHERE tipo = 'grupo' AND ref_id = ?", (grupo_id,)
    ).fetchone()
    if chat:
        conn.execute("DELETE FROM mensajes WHERE chat_id = ?", (chat["id"],))
        conn.execute("DELETE FROM chats WHERE id = ?", (chat["id"],))

    conn.execute("DELETE FROM grupos WHERE id = ?", (grupo_id,))
    conn.commit()
    conn.close()

    return True, f'✓ Grupo "{grupo["nombre"]}" eliminado (id={grupo_id}, estaba vacío)'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Eliminar un grupo (solo si está vacío)")
    parser.add_argument("--grupo-id", required=True, type=int, help="ID del grupo a eliminar")
    args = parser.parse_args()

    ok, msg = eliminar(args.grupo_id)
    print(msg)
    sys.exit(0 if ok else 1)
