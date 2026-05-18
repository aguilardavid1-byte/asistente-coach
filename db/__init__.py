"""Conexión a base de datos — función get_db()."""

import os
import sqlite3

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DB_PATH") or os.path.join(_BASE, "asistente.db")


def get_db() -> sqlite3.Connection:
    """Retorna conexión SQLite con row_factory = sqlite3.Row.

    Configurada para tolerar acceso concurrente:
    - timeout=30s: espera hasta 30s si la DB está bloqueada
    - WAL mode: múltiples lectores + 1 escritor concurrente
    - busy_timeout=30000: igual al timeout, garantiza espera
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
