#!/usr/bin/env python3
"""crear_grupo.py — Crea un grupo nuevo.

Uso: python scripts/crear_grupo.py --nombre "Nombre del grupo"

Salida:
  ✓ Grupo creado: "Nombre" (id=X)
  ✗ ERROR: El grupo "Nombre" ya existe (id=X)
"""
import argparse
import sys

from db import get_db


def crear(nombre: str, parent_id: int | None = None) -> tuple[bool, str]:
    conn = get_db()

    # Validar padre si se especifica
    if parent_id is not None:
        padre = conn.execute(
            "SELECT id, nombre FROM grupos WHERE id = ?", (parent_id,)
        ).fetchone()
        if not padre:
            conn.close()
            return False, f"✗ ERROR: El grupo padre ID {parent_id} no existe"

    slug = nombre.lower().strip()
    existente = conn.execute(
        "SELECT id FROM grupos WHERE slug = ?", (slug,)
    ).fetchone()

    if existente:
        conn.close()
        return False, f'✗ ERROR: El grupo "{nombre}" ya existe (id={existente["id"]})'

    if parent_id is not None:
        conn.execute(
            "INSERT INTO grupos (slug, nombre, parent_id) VALUES (?, ?, ?)",
            (slug, nombre.strip(), parent_id),
        )
    else:
        conn.execute(
            "INSERT INTO grupos (slug, nombre) VALUES (?, ?)",
            (slug, nombre.strip()),
        )
    conn.commit()
    nuevo_id = conn.execute("SELECT MAX(id) FROM grupos").fetchone()[0]

    # Nombre del padre para el mensaje
    ctx = ""
    if parent_id is not None:
        ctx = f' → "{padre["nombre"]}"'

    conn.close()
    return True, f'✓ Grupo creado: "{nombre}" (id={nuevo_id}{ctx})'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crear un grupo nuevo")
    parser.add_argument("--nombre", required=True, help="Nombre del grupo")
    parser.add_argument("--parent-id", type=int, default=None, help="ID del grupo padre (para subgrupos)")
    args = parser.parse_args()

    ok, msg = crear(args.nombre, args.parent_id)
    print(msg)
    sys.exit(0 if ok else 1)
