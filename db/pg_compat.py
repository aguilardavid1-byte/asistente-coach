"""Adaptador PostgreSQL → interfaz compatible con sqlite3 (dict Row + ? placeholders)."""

import re

import psycopg2
import psycopg2.extras
import psycopg2.errors
import sqlite3

_RE_INTEGER_PK = re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\b", re.IGNORECASE)


class PGRow(dict):
    """Compatible con sqlite3.Row: acceso por clave string o índice."""
    def __getitem__(self, key):
        if isinstance(key, int):
            keys = list(self.keys())
            return super().__getitem__(keys[key])
        return super().__getitem__(key)


class PGCursor:
    """Envuelve un cursor psycopg2 para que parezca un cursor sqlite3."""

    def __init__(self, cur):
        self._cur = cur
        self.description = None

    def _fix_sql(self, sql: str) -> str:
        sql = sql.replace("?", "%s")
        sql = _RE_INTEGER_PK.sub("SERIAL PRIMARY KEY", sql)
        return sql

    def execute(self, sql: str, params=None):
        sql = self._fix_sql(sql)
        try:
            self._cur.execute(sql, params)
        except psycopg2.errors.DuplicateColumn:
            raise sqlite3.OperationalError("duplicate column") from None
        except psycopg2.errors.UndefinedColumn:
            raise sqlite3.OperationalError("no such column") from None
        self.description = self._cur.description
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return PGRow(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        return [PGRow(r) for r in rows]

    def __iter__(self):
        return iter(self.fetchall())


class PGConnection:
    """Envuelve una conexión psycopg2 con interfaz similar a sqlite3.Connection."""

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        return cur.execute(sql, params)

    def cursor(self):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return PGCursor(cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def executescript(self, sql: str):
        """Ejecuta múltiples statements separados por ;"""
        cur = self._conn.cursor()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                fixed = stmt.replace("?", "%s")
                fixed = _RE_INTEGER_PK.sub("SERIAL PRIMARY KEY", fixed)
                try:
                    cur.execute(fixed)
                except (psycopg2.errors.DuplicateColumn, psycopg2.errors.UndefinedColumn):
                    pass  # misma columna existe
        cur.close()
