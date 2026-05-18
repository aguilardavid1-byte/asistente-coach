#!/usr/bin/env python3
"""buscar.py — Busca grupos o tareas por texto parcial.

Uso: python scripts/buscar.py --texto "encuesta" [--tipo tarea|grupo|ambos]

Salida: JSON con resultados.
"""
import argparse
import json
import sys

from db import get_db


def buscar(texto: str, tipo: str = "ambos") -> list[dict]:
    conn = get_db()
    resultados = []
    patron = f"%{texto}%"

    if tipo in ("grupo", "ambos"):
        rows = conn.execute(
            "SELECT id, nombre FROM grupos WHERE nombre LIKE ?",
            (patron,),
        ).fetchall()
        for r in rows:
            resultados.append({
                "tipo": "grupo",
                "id": r["id"],
                "titulo": r["nombre"],
                "grupo_id": None,
                "grupo_nombre": None,
            })

    if tipo in ("tarea", "ambos"):
        rows = conn.execute(
            """SELECT t.id, t.titulo, t.grupo_id, g.nombre as grupo_nombre
               FROM tareas t
               LEFT JOIN grupos g ON g.id = t.grupo_id
               WHERE t.titulo LIKE ?""",
            (patron,),
        ).fetchall()
        for r in rows:
            resultados.append({
                "tipo": "tarea",
                "id": r["id"],
                "titulo": r["titulo"],
                "grupo_id": r["grupo_id"],
                "grupo_nombre": r["grupo_nombre"],
            })

    conn.close()
    return resultados


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Buscar grupos o tareas por texto")
    parser.add_argument("--texto", required=True, help="Texto a buscar")
    parser.add_argument("--tipo", default="ambos", choices=["tarea", "grupo", "ambos"], help="Tipo de búsqueda (default: ambos)")
    args = parser.parse_args()

    resultados = buscar(args.texto, args.tipo)
    print(json.dumps({"resultados": resultados}, indent=2, ensure_ascii=False))
    sys.exit(0)
