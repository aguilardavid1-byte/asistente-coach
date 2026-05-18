"""Gestión de chats por nivel — asegura que cada grupo tenga su chat."""

from db import get_db


def asegurar_chat_grupo(grupo_id: int, slug: str, nombre: str, user_id: int) -> int | None:
    """Crea el chat de un grupo si no existe. Retorna el chat_id."""
    conn = get_db()
    existente = conn.execute(
        "SELECT id FROM chats WHERE tipo = 'grupo' AND ref_id = ? AND user_id = ?",
        (grupo_id, user_id),
    ).fetchone()
    if existente:
        conn.close()
        return existente["id"]

    conn.execute(
        "INSERT INTO chats (tipo, ref_id, nombre, user_id) VALUES ('grupo', ?, ?, ?)",
        (grupo_id, nombre, user_id),
    )
    chat_id = conn.execute("SELECT MAX(id) FROM chats").fetchone()[0]

    # Mensaje de bienvenida
    conn.execute(
        "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, 'assistant', ?)",
        (chat_id, f"## 📁 {nombre}\n\nEste es el espacio del grupo **{nombre}**. Aquí podemos organizar, priorizar y hacer seguimiento de todas las tareas de esta área. ¿Por dónde empezamos?"),
    )
    conn.commit()
    conn.close()
    return chat_id


def asegurar_chats_grupos(user_id: int = 1) -> int:
    """Crea chats para todos los grupos que no tengan uno. Retorna cuantos creó."""
    conn = get_db()
    grupos = conn.execute("SELECT id, slug, nombre FROM grupos WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()

    creados = 0
    for g in grupos:
        cid = asegurar_chat_grupo(g["id"], g["slug"], g["nombre"], user_id)
        if cid is not None:
            creados += 1
    return creados
