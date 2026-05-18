"""Esquema SQLite — definición de tablas y creación."""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS perfiles (
    id          INTEGER PRIMARY KEY,
    nombre      TEXT DEFAULT '',
    metas       TEXT DEFAULT '[]',
    estado      TEXT DEFAULT '',
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usuarios (
    id             INTEGER PRIMARY KEY,
    google_id      TEXT UNIQUE,
    username       TEXT UNIQUE,
    email          TEXT NOT NULL DEFAULT '',
    nombre         TEXT NOT NULL,
    password_hash  TEXT DEFAULT '',
    avatar_url     TEXT DEFAULT '',
    creado_en      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS grupos (
    id          INTEGER PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    nombre      TEXT NOT NULL,
    icono       TEXT DEFAULT '📁',
    orden       INTEGER DEFAULT 0,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tareas (
    id           INTEGER PRIMARY KEY,
    grupo_id     INTEGER REFERENCES grupos(id),
    titulo       TEXT NOT NULL,
    descripcion  TEXT DEFAULT '',
    prioridad    TEXT DEFAULT 'media',
    estado       TEXT DEFAULT 'pendiente',
    fecha_limite TEXT,
    creado_en    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chats (
    id          INTEGER PRIMARY KEY,
    tipo        TEXT NOT NULL,
    ref_id      INTEGER,
    nombre      TEXT NOT NULL,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mensajes (
    id           INTEGER PRIMARY KEY,
    chat_id      INTEGER NOT NULL REFERENCES chats(id),
    rol          TEXT NOT NULL,
    contenido    TEXT NOT NULL,
    tiene_imagen INTEGER DEFAULT 0,
    creado_en    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mensajes_chat ON mensajes(chat_id);
CREATE INDEX IF NOT EXISTS idx_tareas_grupo ON tareas(grupo_id);
CREATE INDEX IF NOT EXISTS idx_chats_tipo ON chats(tipo);
"""

# Migraciones para tablas existentes (columnas nuevas)
MIGRATIONS_SQL = [
    "ALTER TABLE usuarios ADD COLUMN username TEXT UNIQUE",
    "ALTER TABLE usuarios ADD COLUMN password_hash TEXT DEFAULT ''",
]


def crear_tablas(conn: sqlite3.Connection) -> None:
    """Ejecuta el DDL de creación de tablas y migraciones."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    # Migraciones: ignorar error si la columna ya existe
    for sql in MIGRATIONS_SQL:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass
