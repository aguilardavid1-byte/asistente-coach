# Scripts V3 — Automatización de Tareas

7 scripts Python atómicos para gestionar la base de datos de tareas.
Soporta **subgrupos** (jerarquía de carpetas).

## Requisitos

```bash
cd /home/david/Documentos/gestor_tareas/asistente_v2
source .venv/bin/activate
```

## Scripts

### `listar.py` — Ver estado actual (árbol jerárquico)

```bash
python scripts/listar.py
```
Salida: JSON con grupos anidados (subgrupos dentro de grupos padre), tareas y totales.
Los subgrupos aparecen dentro del campo `subgrupos` de su grupo padre.
Usar `--plano` para el formato plano original.

### `crear_grupo.py` — Crear grupo o subgrupo

```bash
# Grupo raíz (top-level)
python scripts/crear_grupo.py --nombre "Diseño de proyectos (MARCELA ALVAREZ)"
# ✓ Grupo creado: "Diseño de proyectos (MARCELA ALVAREZ)" (id=2)

# Subgrupo (anidado bajo un grupo padre)
python scripts/crear_grupo.py --nombre "Tareas pendientes" --parent-id 1
# ✓ Grupo creado: "Tareas pendientes" (id=3 → "Maestría")
```

### `crear_tarea.py` — Crear tarea

```bash
python scripts/crear_tarea.py --titulo "Encuesta AVA" --grupo-id 2 --fecha-limite "2026-06-14"
# ✓ Tarea creada: "Encuesta AVA" en "Diseño de proyectos (MARCELA ALVAREZ)" (id=3, vence: 2026-06-14)
```

### `buscar.py` — Buscar grupos o tareas

```bash
python scripts/buscar.py --texto "encuesta" --tipo "tarea"
# {"resultados": [{"tipo": "tarea", "id": 3, ...}]}
```

### `mover_tarea.py` — Mover tarea entre grupos

```bash
python scripts/mover_tarea.py --tarea-id 7 --grupo-id 5
# ✓ Tarea "Encuesta AVA" movida de "Maestría" a "Grupo Nuevo" (id=7)
```

### `eliminar_tarea.py` — Eliminar tarea

```bash
python scripts/eliminar_tarea.py --tarea-id 3
# ✓ Tarea "Encuesta AVA" eliminada (id=3, grupo_id=2)
```

### `eliminar_grupo.py` — Eliminar grupo (solo vacío)

```bash
python scripts/eliminar_grupo.py --grupo-id 2
# ✓ Grupo "Nombre" eliminado (id=2, estaba vacío)
# ✗ ERROR: Grupo "Nombre" no se puede eliminar (contiene 3 tareas)
```

### `migrar_subgrupos.py` — Anidar grupos existentes

```bash
# Por defecto: anida grupo 3 bajo grupo 1
python scripts/migrar_subgrupos.py

# O pasar reglas personalizadas por stdin
echo "5 2
6 2" | python scripts/migrar_subgrupos.py
```

## Subgrupos

Los grupos pueden anidarse usando `parent_id`:
```
General (chat)
└── Maestría (grupo padre, id=1)
    ├── Tareas propias de Maestría
    ├── Diseño de proyectos (MARCELA) [subgrupo, parent_id=1]
    │   └── Tareas de esta materia
    └── Gestión de proyectos (AURA) [subgrupo, parent_id=1]
        └── Tareas de esta materia
└── Películas por ver (grupo padre, id=2)
    └── Tareas
```

- `crear_grupo.py --parent-id X` crea un subgrupo bajo X
- `listar.py` muestra la jerarquía automáticamente
- `migrar_subgrupos.py` para anidar grupos ya existentes

## Exit codes

- `0` = operación exitosa
- `1` = error (grupo no existe, tarea no encontrada, grupo no vacío, etc.)
