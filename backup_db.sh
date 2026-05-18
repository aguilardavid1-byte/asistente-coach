#!/bin/bash
# Backup diario de la base de datos SQLite
# Conserva los últimos 7 backups

DEST="/home/coach/backups"
mkdir -p "$DEST"
FECHA=$(date +%Y%m%d_%H%M)
sqlite3 /home/coach/asistente_v2/asistente.db ".backup '$DEST/asistente_$FECHA.db'"

# Conservar solo los últimos 7 backups
ls -t "$DEST"/asistente_*.db 2>/dev/null | tail -n +8 | xargs -r rm
echo "✅ Backup: $DEST/asistente_$FECHA.db"
