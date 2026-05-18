#!/usr/bin/env python3
"""migrar_subgrupos.py — Migración única: agrega parent_id y anida grupos existentes.

Uso: python scripts/migrar_subgrupos.py

Lee una lista de asignaciones desde standard input (una por línea, formato: hijo_id padre_id):
  echo "3 1" | python scripts/migrar_subgrupos.py

O usa las reglas hardcodeadas si no se pasa input.
"""
import re
import sys

sys.path.insert(0, __file__)
from db import get_db


def _col_exists(conn, table: str, col: str) -> bool:
    return col in [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def migrar(reglas: list[tuple[int, int]]) -> list[str]:
    """Aplica migraciones. Devuelve lista de mensajes informativos."""
    conn = get_db()
    msgs = []

    # 1. Asegurar columna parent_id
    if not _col_exists(conn, "grupos", "parent_id"):
        conn.execute("ALTER TABLE grupos ADD COLUMN parent_id INTEGER REFERENCES grupos(id)")
        msgs.append("✓ Columna parent_id agregada a grupos")
        conn.commit()

    # 2. Aplicar reglas de anidación
    for hijo_id, padre_id in reglas:
        hijo = conn.execute("SELECT id, nombre, parent_id FROM grupos WHERE id=?", (hijo_id,)).fetchone()
        if not hijo:
            msgs.append(f"✗ Grupo hijo ID {hijo_id} no existe — ignorado")
            continue
        padre = conn.execute("SELECT id, nombre FROM grupos WHERE id=?", (padre_id,)).fetchone()
        if not padre:
            msgs.append(f"✗ Grupo padre ID {padre_id} no existe — ignorado")
            continue
        if hijo["parent_id"] == padre_id:
            msgs.append(f'~ Ya anidado: "{hijo["nombre"]}" → "{padre["nombre"]}"')
            continue
        conn.execute("UPDATE grupos SET parent_id=? WHERE id=?", (padre_id, hijo_id))
        msgs.append(f'✓ "{hijo["nombre"]}" (id={hijo_id}) → "{padre["nombre"]}" (id={padre_id})')

    conn.commit()
    conn.close()
    return msgs


if __name__ == "__main__":
    # Leer reglas desde stdin (formato: "hijo_id padre_id" por línea)
    reglas: list[tuple[int, int]] = []
    if not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"(\d+)\s+(\d+)", line)
            if m:
                reglas.append((int(m.group(1)), int(m.group(2))))

    # Si no hay input, usar regla por defecto
    if not reglas:
        reglas = [(3, 1)]  # Gestión de proyectos transversales → Maestría

    msgs = migrar(reglas)
    for m in msgs:
        print(m)
    sys.exit(0 if not any(m.startswith("✗") for m in msgs) else 1)
