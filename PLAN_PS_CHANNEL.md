# Plan: Canal de Ofertas PS4/PS5 (Opción A)

## Contexto

El proyecto actual tiene un único script monolítico (`amazon_bebe_ofertas.py`) que busca ofertas en Amazon.es y las publica en un canal de Telegram. El objetivo es añadir un segundo canal independiente para ofertas de juegos y accesorios de PS4/PS5, reutilizando la lógica genérica mediante refactorización en un módulo compartido.

---

## Enfoque: Módulo compartido + 2 scripts especializados

```
amazon_ofertas_core.py      ← ✅ CREADO: funciones genéricas compartidas
amazon_bebe_ofertas.py      ← ✅ MODIFICADO: usa core + config de bebé
amazon_ps_ofertas.py        ← PENDIENTE: usa core + config de PS4/PS5
.github/workflows/
  ofertas.yml               ← PENDIENTE: añadir git pull --rebase
  ofertas-ps.yml            ← PENDIENTE: workflow para PS4/PS5
posted_ps_deals.json        ← PENDIENTE: estado anti-repetición de PS
```

---

## ✅ Fase 1 — Crear `amazon_ofertas_core.py` — COMPLETADA

Funciones extraídas de `amazon_bebe_ofertas.py` al módulo compartido:

| Función | Cambio aplicado |
|---|---|
| `setup_logging()` | Sin cambios |
| `HEADERS`, `BASE_URL`, `PARTNER_TAG` | Sin cambios (constantes globales) |
| `obtener_pagina(url)` | Sin cambios |
| `extraer_productos_busqueda(html)` | Sin cambios |
| `normalizar_titulo(titulo)` | Sin cambios |
| `titulos_similares(t1, t2, umbral)` | Sin cambios |
| `titulo_similar_a_recientes(titulo, lista)` | Sin cambios |
| `obtener_prioridad_marca(titulo, marcas)` | Añadido parámetro `marcas: list` |
| `send_telegram_message(message, token, chat_id)` | Añadidos params `token`, `chat_id` |
| `send_telegram_photo(photo_url, caption, token, chat_id)` | Añadidos params `token`, `chat_id` |
| `format_telegram_message(producto, cat)` | Sin cambios |
| `load_posted_deals(filepath)` | Añadido param `filepath` |
| `save_posted_deals(deals_dict, filepath, ...)` | Añadido param `filepath` |

> **Nota de diseño:** `buscar_y_publicar_ofertas()` **no** se movió al core. Permanece en cada script especializado para mantener compatibilidad con los tests (que hacen monkeypatch sobre funciones del módulo `bot`).

---

## ✅ Fase 2 — Refactorizar `amazon_bebe_ofertas.py` — COMPLETADA

- Eliminadas las funciones movidas al core
- Importa desde `amazon_ofertas_core` con alias `_*_core` para funciones parametrizadas
- Define **wrappers sin-args** con los nombres originales (necesario para que el monkeypatching de los tests siga funcionando):
  - `obtener_prioridad_marca(titulo)` → llama al core con `MARCAS_PRIORITARIAS`
  - `send_telegram_message(message)` → llama al core con token/chat_id de bebe
  - `send_telegram_photo(photo_url, caption)` → ídem
  - `load_posted_deals()` → llama al core con `POSTED_BEBE_DEALS_FILE`
  - `save_posted_deals(deals_dict, ...)` → ídem
- `buscar_y_publicar_ofertas()` sin cambios de firma: llama a los wrappers del módulo
- Constantes de configuración propias intactas: `CATEGORIAS_BEBE`, `MARCAS_PRIORITARIAS`, etc.
- **64/64 tests en verde** tras la refactorización

---

## ✅ Fase 3 — Crear `amazon_ps_ofertas.py` — COMPLETADA

Script independiente con configuración específica de PS4/PS5. Mismo patrón que bebe:
importar utilidades del core, definir wrappers con credenciales PS, y tener
`buscar_y_publicar_ofertas()` propio que use los wrappers locales.

### Características implementadas

✅ **Priorización de videojuegos** - Juegos PS4/PS5 siempre por delante de accesorios
✅ **Anti-duplicados 48h** - No repite el mismo ASIN en 48 horas
✅ **Anti-títulos similares** - Para Juegos PS4/PS5, evita títulos similares a los recientes
✅ **Modo DEV** - Publica en canal de pruebas sin modificar `posted_ps_deals.json`
✅ **59 tests** - Cobertura completa de lógica, parsing, I/O y priorización
✅ **README.md** - Documentación completa de uso y configuración

### Configuración

```python
# Archivo de estado
POSTED_PS_DEALS_FILE = "posted_ps_deals.json"

# Categorías con campo 'tipo' para priorizar videojuegos
CATEGORIAS_PS = [
    # Videojuegos (priorizados)
    {"nombre": "Juegos PS5",        "emoji": "🎮", "url": "/s?k=juegos+ps5",           "tipo": "videojuego"},
    {"nombre": "Juegos PS4",        "emoji": "🎮", "url": "/s?k=juegos+ps4",           "tipo": "videojuego"},
    # Accesorios
    {"nombre": "Mandos PS5",        "emoji": "🕹️", "url": "/s?k=mando+dualsense+ps5",  "tipo": "accesorio"},
    {"nombre": "Mandos PS4",        "emoji": "🕹️", "url": "/s?k=mando+dualshock+ps4",  "tipo": "accesorio"},
    {"nombre": "Auriculares gaming","emoji": "🎧", "url": "/s?k=auriculares+gaming...", "tipo": "accesorio"},
    {"nombre": "Tarjetas PSN",      "emoji": "💳", "url": "/s?k=tarjeta+psn+play...",  "tipo": "accesorio"},
    {"nombre": "Accesorios PS5",    "emoji": "⚙️",  "url": "/s?k=accesorios+ps5",      "tipo": "accesorio"},
    {"nombre": "Accesorios PS4",    "emoji": "⚙️",  "url": "/s?k=accesorios+ps4",      "tipo": "accesorio"},
]

MARCAS_PRIORITARIAS = ["sony", "playstation", "nacon", "thrustmaster", "razer", "hyperx"]

CATEGORIAS_VERIFICAR_TITULOS = ["Juegos PS5", "Juegos PS4"]  # Evitar juegos similares
CATEGORIAS_LIMITE_SEMANAL = []                                 # Sin límite semanal (no aplica en PS)

# Secrets específicos del canal PS
TELEGRAM_PS_BOT_TOKEN = os.getenv('TELEGRAM_PS_BOT_TOKEN')
TELEGRAM_PS_CHAT_ID   = os.getenv('TELEGRAM_PS_CHAT_ID')
DEV_TELEGRAM_PS_BOT_TOKEN = os.getenv('DEV_TELEGRAM_PS_BOT_TOKEN')
DEV_TELEGRAM_PS_CHAT_ID = os.getenv('DEV_TELEGRAM_PS_CHAT_ID')
```

### Archivos creados

```
ps/
├── amazon_ps_ofertas.py           ← Script principal con priorización de videojuegos
├── posted_ps_deals.json           ← Estado anti-duplicados (vacío inicialmente)
├── ofertas_ps.log                 ← Logs de ejecución (generado tras primera ejecución)
├── README.md                      ← Documentación completa
├── __init__.py                    ← Módulo Python
└── tests/
    ├── test_amazon_ps_ofertas.py  ← 59 tests (todos en verde ✅)
    └── __init__.py
```

### Ejecución manual para pruebas

```bash
# Modo desarrollo (no modifica JSON, publica en canal dev)
export DEV_TELEGRAM_PS_BOT_TOKEN=...
export DEV_TELEGRAM_PS_CHAT_ID=...
python3 ps/amazon_ps_ofertas.py --dev

# Ver logs
tail -f ps/ofertas_ps.log
```

---

## ✅ Fase 4 — Crear `.github/workflows/ofertas-ps.yml` — COMPLETADA

Copia de `ofertas.yml` con:
- ✅ `name: Ofertas PS4/PS5`
- ✅ Secrets: `TELEGRAM_PS_BOT_TOKEN`, `TELEGRAM_PS_CHAT_ID`
- ✅ `run: python ps/amazon_ps_ofertas.py`
- ✅ `git add ps/posted_ps_deals.json`
- ✅ Mensaje de commit: `"chore: actualizar estado ofertas PS [skip ci]"`

### ✅ Fix de concurrencia (aplicado en AMBOS workflows)

Cuando los dos workflows se ejecutan simultáneamente y ambos hacen push, el segundo fallará porque el remote ya avanzó. Solución implementada:

```yaml
- name: Guardar estado (commit del JSON)
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add posted_bebe_deals.json   # o posted_ps_deals.json según el workflow
    git diff --staged --quiet || git commit -m "chore: ..."
    git pull --rebase origin main    # ← Evita conflicto de push concurrente
    git push
```

### Archivos creados/modificados

- ✅ `.github/workflows/ofertas-ps.yml` - Nuevo workflow para PS4/PS5
- ✅ `.github/workflows/ofertas.yml` - Actualizado con `git pull --rebase`

---

## Fase 5 — Agregar Secrets en GitHub (MANUAL)

Acceder a: `https://github.com/Migueldelg/RadarOfertas/settings/secrets/actions`

Agregar los siguientes secrets:
- `TELEGRAM_PS_BOT_TOKEN` = `8542903683:AAFcIbXqweq8b4Sqo2c7eaKsgkneZcivfio`
- `TELEGRAM_PS_CHAT_ID` = `-1001003885398555`

Una vez agregados, el workflow `Ofertas PS4/PS5` se ejecutará automáticamente cada 30 minutos.

---

## Archivos a crear/modificar

| Archivo | Acción | Estado |
|---|---|---|
| `amazon_ofertas_core.py` | CREAR | ✅ Hecho (Fase 1) |
| `amazon_bebe_ofertas.py` | MODIFICAR (importar desde core, mismo comportamiento) | ✅ Hecho (Fase 2) |
| `amazon_ps_ofertas.py` | CREAR | ✅ Hecho (Fase 3) |
| `ps/posted_ps_deals.json` | CREAR (vacío `{}`) | ✅ Hecho (Fase 3) |
| `ps/tests/test_amazon_ps_ofertas.py` | CREAR (59 tests) | ✅ Hecho (Fase 3) |
| `ps/README.md` | CREAR (documentación) | ✅ Hecho (Fase 3) |
| `.github/workflows/ofertas-ps.yml` | CREAR | ✅ Hecho (Fase 4) |
| `.github/workflows/ofertas.yml` | MODIFICAR (añadir `git pull --rebase`) | ✅ Hecho (Fase 4) |
| **GitHub Secrets** | AGREGAR `TELEGRAM_PS_BOT_TOKEN`, `TELEGRAM_PS_CHAT_ID` | ⏳ Fase 5 (MANUAL) |

---

## Pasos manuales requeridos (por el usuario)

1. **Crear bot de Telegram para PS** en @BotFather → obtener token
2. **Crear/vincular el canal PS** en Telegram → obtener chat_id
3. **Añadir secrets en GitHub** → Settings → Secrets:
   - `TELEGRAM_PS_BOT_TOKEN`
   - `TELEGRAM_PS_CHAT_ID`

---

## Verificación

1. Ejecutar localmente:
   ```bash
   TELEGRAM_PS_BOT_TOKEN=xxx TELEGRAM_PS_CHAT_ID=yyy python amazon_ps_ofertas.py
   ```
2. Verificar que `posted_ps_deals.json` se actualiza con el ASIN publicado
3. Verificar que `amazon_bebe_ofertas.py` sigue funcionando igual:
   ```bash
   TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python amazon_bebe_ofertas.py
   ```
4. Lanzar manualmente el workflow PS desde GitHub Actions:
   ```bash
   gh workflow run "Ofertas PS4/PS5"
   gh run watch
   ```
