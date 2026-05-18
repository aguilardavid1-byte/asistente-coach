#!/usr/bin/env python3
"""listar.py — Muestra el estado actual completo de la DB en forma de árbol.

Uso: python scripts/listar.py [--arbol]  (--arbol es el default)
      python scripts/listar.py --plano     (formato plano original)

Salida: JSON con grupos jerárquicos, tareas y totales.
"""
import argparse
import json
import sys

sys.path.insert(0, __file__)
from db import get_db


def _build_tree(conn) -> dict:
    """Construye el árbol de grupos con subgrupos y tareas anidadas."""
    grupos_raw = conn.execute("""
        SELECT g.id, g.nombre, g.parent_id,
               (SELECT COUNT(*) FROM tareas WHERE grupo_id = g.id) AS tareas_count
        FROM grupos g ORDER BY g.id
    """).fetchall()

    # Todas las tareas
    tareas_raw = conn.execute("""
        SELECT t.id, t.titulo, t.grupo_id, g.nombre as grupo_nombre,
               t.prioridad, t.estado, t.fecha_limite, t.recurrencia, t.progreso
        FROM tareas t LEFT JOIN grupos g ON g.id = t.grupo_id
        ORDER BY t.id
    """).fetchall()

    tareas_flat = [
        {"id": t["id"], "titulo": t["titulo"], "grupo_id": t["grupo_id"],
         "grupo_nombre": t["grupo_nombre"], "prioridad": t["prioridad"],
         "estado": t["estado"], "fecha_limite": t["fecha_limite"], "recurrencia": t["recurrencia"], "progreso": t["progreso"]}
        for t in tareas_raw
    ]

    # Organizar grupos: top-level (parent_id IS NULL) y subgrupos
    tops = []
    subs = []

    # Build lookup for subgrupos
    hijos: dict[int, list] = {}
    grupo_info: dict[int, dict] = {}

    for g in grupos_raw:
        entry = {"id": g["id"], "nombre": g["nombre"], "parent_id": g["parent_id"],
                 "tareas_count": g["tareas_count"]}
        grupo_info[g["id"]] = entry

        if g["parent_id"] is None:
            tops.append(entry)
        else:
            subs.append(entry)
            hijos.setdefault(g["parent_id"], []).append(entry)

    # Nest subgrupos
    for t in tops + subs:
        t["subgrupos"] = hijos.get(t["id"], [])

    # Attach tareas to each group
    for g in grupos_raw:
        g_tareas = [t for t in tareas_flat if t["grupo_id"] == g["id"]]
        grupo_info[g["id"]]["tareas"] = g_tareas

    return {
        "grupos": tops,
        "tareas": tareas_flat,
        "total_grupos": len(grupos_raw),
        "total_tareas": len(tareas_flat),
    }


def _build_flat(conn) -> dict:
    """Formato plano original (sin jerarquía)."""
    grupos_raw = conn.execute(
        "SELECT id, nombre, parent_id FROM grupos ORDER BY id"
    ).fetchall()

    grupos = []
    for g in grupos_raw:
        count = conn.execute(
            "SELECT COUNT(*) FROM tareas WHERE grupo_id = ?", (g["id"],)
        ).fetchone()[0]
        entry = {"id": g["id"], "nombre": g["nombre"], "tareas_count": count}
        if g["parent_id"] is not None:
            entry["parent_id"] = g["parent_id"]
        grupos.append(entry)

    tareas_raw = conn.execute("""
        SELECT t.id, t.titulo, t.grupo_id, g.nombre as grupo_nombre,
               t.prioridad, t.estado, t.fecha_limite, t.recurrencia, t.progreso
        FROM tareas t LEFT JOIN grupos g ON g.id = t.grupo_id
        ORDER BY t.id
    """).fetchall()

    tareas = [
        {"id": t["id"], "titulo": t["titulo"], "grupo_id": t["grupo_id"],
         "grupo_nombre": t["grupo_nombre"], "prioridad": t["prioridad"],
         "estado": t["estado"], "fecha_limite": t["fecha_limite"], "recurrencia": t["recurrencia"], "progreso": t["progreso"]}
        for t in tareas_raw
    ]

    conn.close()
    return {"grupos": grupos, "tareas": tareas,
            "total_grupos": len(grupos), "total_tareas": len(tareas)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Listar estado de la base de datos")
    parser.add_argument("--plano", action="store_true", help="Formato plano (sin árbol)")
    args = parser.parse_args()

    conn = get_db()
    data = _build_flat(conn) if args.plano else _build_tree(conn)
    conn.close()
    print(json.dumps(data, indent=2, ensure_ascii=False))
