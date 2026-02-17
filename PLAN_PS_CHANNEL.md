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

## Fase 3 — Crear `amazon_ps_ofertas.py`

Script independiente con configuración específica de PS4/PS5. Mismo patrón que bebe:
importar utilidades del core, definir wrappers con credenciales PS, y tener
`buscar_y_publicar_ofertas()` propio que use los wrappers locales.

```python
# Archivo de estado
POSTED_PS_DEALS_FILE = "posted_ps_deals.json"

# Categorías propuestas (ajustable)
CATEGORIAS_PS = [
    {"nombre": "Juegos PS5",        "emoji": "🎮", "url": "/s?k=juegos+ps5"},
    {"nombre": "Juegos PS4",        "emoji": "🎮", "url": "/s?k=juegos+ps4"},
    {"nombre": "Mandos PS5",        "emoji": "🕹️", "url": "/s?k=mando+dualsense+ps5"},
    {"nombre": "Mandos PS4",        "emoji": "🕹️", "url": "/s?k=mando+dualshock+ps4"},
    {"nombre": "Auriculares gaming","emoji": "🎧", "url": "/s?k=auriculares+gaming+ps4+ps5"},
    {"nombre": "Tarjetas PSN",      "emoji": "💳", "url": "/s?k=tarjeta+psn+playstation"},
    {"nombre": "Accesorios PS5",    "emoji": "⚙️",  "url": "/s?k=accesorios+ps5"},
    {"nombre": "Accesorios PS4",    "emoji": "⚙️",  "url": "/s?k=accesorios+ps4"},
]

MARCAS_PRIORITARIAS_PS = ["sony", "playstation", "nacon", "thrustmaster", "razer", "hyperx"]

CATEGORIAS_VERIFICAR_TITULOS_PS = ["Juegos PS5", "Juegos PS4"]  # Evitar juegos similares
CATEGORIAS_LIMITE_SEMANAL_PS = []                                 # Sin límite semanal
CATEGORIAS_EXCLUIDAS_REPETICION_PS = []                           # Sin excepciones

# Secrets específicos del canal PS
TELEGRAM_PS_BOT_TOKEN = os.getenv('TELEGRAM_PS_BOT_TOKEN')
TELEGRAM_PS_CHAT_ID   = os.getenv('TELEGRAM_PS_CHAT_ID')
```

---

## Fase 4 — Crear `.github/workflows/ofertas-ps.yml`

Copia de `ofertas.yml` con:
- `name: Ofertas PS4/PS5`
- Secrets: `TELEGRAM_PS_BOT_TOKEN`, `TELEGRAM_PS_CHAT_ID`
- `run: python amazon_ps_ofertas.py`
- `git add posted_ps_deals.json`
- Mensaje de commit: `"chore: actualizar estado ofertas PS [skip ci]"`

### Fix de concurrencia (aplicar en AMBOS workflows)

Cuando los dos workflows se ejecutan simultáneamente y ambos hacen push, el segundo fallará porque el remote ya avanzó. Solución en el step de commit:

```yaml
- name: Guardar estado (commit del JSON)
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add posted_bebe_deals.json   # o posted_ps_deals.json según el workflow
    git diff --staged --quiet || git commit -m "chore: ..."
    git pull --rebase origin main    # ← NUEVO: evita conflicto de push concurrente
    git push
```

---

## Fase 5 — Crear `posted_ps_deals.json` vacío

```json
{}
```

Será el archivo de estado inicial del canal PS.

---

## Archivos a crear/modificar

| Archivo | Acción | Estado |
|---|---|---|
| `amazon_ofertas_core.py` | CREAR | ✅ Hecho |
| `amazon_bebe_ofertas.py` | MODIFICAR (importar desde core, mismo comportamiento) | ✅ Hecho |
| `amazon_ps_ofertas.py` | CREAR | Pendiente |
| `.github/workflows/ofertas-ps.yml` | CREAR | Pendiente |
| `.github/workflows/ofertas.yml` | MODIFICAR (añadir `git pull --rebase`) | Pendiente |
| `posted_ps_deals.json` | CREAR (vacío `{}`) | Pendiente |

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
