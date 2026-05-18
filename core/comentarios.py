"""Inyección de comentarios entre niveles de chat (general → grupo → tarea)."""

from db import get_db


def _hijos_de(chat_id: int, user_id: int) -> list[int]:
    """Retorna los chat_ids hijos de un chat padre.

    - Si el padre es el chat General (tipo='general'): retorna todos los chats
      de grupo y tareas sueltas del usuario.
    - Si el padre es un chat de grupo (tipo='grupo'): retorna los chats de
      tareas pertenecientes a ese grupo del usuario.
    """
    conn = get_db()
    padre = conn.execute("SELECT tipo, ref_id FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id)).fetchone()
    if not padre:
        conn.close()
        return []

    hijos = []

    if padre["tipo"] == "general":
        # Chats de grupo del usuario
        rows = conn.execute("SELECT id FROM chats WHERE tipo = 'grupo' AND user_id = ?", (user_id,)).fetchall()
        hijos.extend(r["id"] for r in rows)
        # Tareas sueltas (sin grupo) del usuario
        rows = conn.execute(
            """SELECT c.id FROM chats c
               JOIN tareas t ON t.id = c.ref_id
               WHERE c.tipo = 'tarea' AND t.grupo_id IS NULL AND t.user_id = ? AND c.user_id = ?""",
            (user_id, user_id),
        ).fetchall()
        hijos.extend(r["id"] for r in rows)

    elif padre["tipo"] == "grupo":
        grupo_id = padre["ref_id"]
        rows = conn.execute(
            """SELECT c.id FROM chats c
               JOIN tareas t ON t.id = c.ref_id
               WHERE c.tipo = 'tarea' AND t.grupo_id = ? AND t.user_id = ? AND c.user_id = ?""",
            (grupo_id, user_id, user_id),
        ).fetchall()
        hijos.extend(r["id"] for r in rows)

    conn.close()
    return hijos


def inyectar_comentario(chat_id_padre: int, texto: str, user_id: int) -> int:
    """Inyecta un mensaje en todos los chats hijos del padre.

    Args:
        chat_id_padre: ID del chat padre.
        texto: Texto a inyectar (se prefija con 📌).
        user_id: ID del usuario propietario.

    Returns:
        Número de hijos en los que se inyectó.
    """
    # Obtener nombre del chat padre para el prefijo
    conn = get_db()
    padre = conn.execute("SELECT nombre FROM chats WHERE id = ? AND user_id = ?", (chat_id_padre, user_id)).fetchone()
    conn.close()
    origen = padre["nombre"] if padre else "nivel superior"

    hijos = _hijos_de(chat_id_padre, user_id)
    inyectados = 0

    conn = get_db()
    for hijo_id in hijos:
        conn.execute(
            "INSERT INTO mensajes (chat_id, rol, contenido) VALUES (?, 'assistant', ?)",
            (hijo_id, f"📌 *{origen}:* {texto}"),
        )
        inyectados += 1

    if inyectados:
        conn.commit()
    conn.close()

    print(f"  📌 Comentario propagado a {inyectados} chat(s) hijo(s) desde '{origen}'")
    return inyectados
