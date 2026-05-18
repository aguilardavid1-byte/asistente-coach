"""Conexión a base de datos — función get_db().

Usa SQLite localmente o PostgreSQL si DATABASE_URL está definida.
"""

import os
import sqlite3

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DB_PATH") or os.path.join(_BASE, "asistente.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_db():
    """Retorna conexión SQLite o PostgreSQL según el entorno."""
    if DATABASE_URL:
        from db.pg_compat import PGConnection
        return PGConnection(DATABASE_URL)

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
