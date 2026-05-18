"""Conexión compartida a la base de datos para scripts V3.

La DB está en ../asistente.db (relativo a este directorio).
"""
import os
import sqlite3

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_SCRIPTS_DIR, "..", "asistente.db")


def _migrar(conn: sqlite3.Connection) -> None:
    """Agrega columnas faltantes (migración automática)."""
    cols_g = [r["name"] for r in conn.execute("PRAGMA table_info(grupos)").fetchall()]
    if "parent_id" not in cols_g:
        conn.execute("ALTER TABLE grupos ADD COLUMN parent_id INTEGER REFERENCES grupos(id)")
        conn.commit()

    cols_t = [r["name"] for r in conn.execute("PRAGMA table_info(tareas)").fetchall()]
    if "recurrencia" not in cols_t:
        conn.execute("ALTER TABLE tareas ADD COLUMN recurrencia TEXT DEFAULT NULL")
        conn.commit()
    if "progreso" not in cols_t:
        conn.execute("ALTER TABLE tareas ADD COLUMN progreso INTEGER DEFAULT 0")
        conn.commit()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrar(conn)
    return conn
