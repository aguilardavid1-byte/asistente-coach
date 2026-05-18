"""Inicializa la base de datos: crea tablas e inserta datos iniciales.

Uso:
    python db/init_db.py
"""

import sqlite3
import sys

# Permitir importar desde el directorio raíz del proyecto
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db, DB_PATH
from db.schema import crear_tablas


def _init_datos(conn: sqlite3.Connection) -> None:
    """Inserta datos semilla si están vacíos."""
    cur = conn.execute("SELECT COUNT(*) FROM chats")
    if cur.fetchone()[0] > 0:
        return  # ya hay datos, no duplicar

    conn.execute(
        "INSERT INTO perfiles (nombre, metas, estado, user_id) VALUES (?, ?, ?, ?)",
        ("", "[]", "", 1),
    )

    conn.execute(
        "INSERT INTO chats (tipo, ref_id, nombre, user_id) VALUES (?, ?, ?, ?)",
        ("general", None, "General", 1),
    )

    conn.execute(
        "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, ?, ?)",
        (1, "assistant", "¡Hola! Soy tu coach personal. ¿En qué puedo ayudarte hoy?"),
    )

    conn.commit()


def main() -> None:
    print(f"📦 DB: {DB_PATH}")
    conn = get_db()
    crear_tablas(conn)
    _init_datos(conn)
    conn.close()

    # Asegurar chats de grupos existentes
    from core.chats import asegurar_chats_grupos
    n = asegurar_chats_grupos()
    if n:
        print(f"  → {n} chat(s) de grupo creado(s)")

    # Verificación
    conn = get_db()
    rows = conn.execute("SELECT tipo, nombre FROM chats").fetchall()
    conn.close()
    print(f"✅ Tablas creadas. Chats: {[dict(r) for r in rows]}")


if __name__ == "__main__":
    main()
