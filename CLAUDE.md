# CLAUDE.md - Referencia Rápida para Claude AI

**Ver documentación completa:**
- 📖 **README.md** → Guía general "¿Cómo funciona?"
- 🔧 **AGENTS.md** → Referencia técnica completa (estructura de datos, funciones, selectores CSS, líneas exactas)

---

## Resumen Ejecutivo

**Plataforma multi-canal** que busca las mejores ofertas de Amazon.es y las publica en Telegram.

### Canal 🍼 Bebé (en producción)
- **Config:** `bebe/amazon_bebe_ofertas.py`
- **Categorías:** 12 (Pañales, Toallitas, Juguetes, etc.)
- **Tests:** 64 tests

### Canal 🎮 PS4/PS5 (en producción + Preórdenes 🆕)
- **Config:** `ps/amazon_ps_ofertas.py` — **Prioriza videojuegos sobre accesorios + Búsqueda de preórdenes**
- **Categorías (Ofertas):** 8 (Juegos PS5/PS4, Mandos, Accesorios)
- **Categorías (Preórdenes):** 2 (Próximos PS5, Próximos PS4) 🆕
- **Tests:** 100 tests (59 ofertas + 17 preórdenes + 24 variantes)
- **Workflow:** `.github/workflows/ofertas-ps.yml`

### Core Compartido
- `shared/amazon_ofertas_core.py` — Motor genérico (scraping, Telegram, utilidades)

---

## Estructura de carpetas

```
shared/
└── amazon_ofertas_core.py       ← Motor compartido (scraping, Telegram, utilidades)

bebe/                           ← 🍼 Canal bebé (producción ✅)
├── amazon_bebe_ofertas.py
├── posted_bebe_deals.json
├── README.md
└── tests/ (64 tests)

ps/                             ← 🎮 Canal PS4/PS5 (producción ✅ + Preórdenes 🆕)
├── amazon_ps_ofertas.py        ← Prioriza videojuegos sobre accesorios + Búsqueda de preórdenes
├── posted_ps_deals.json        ← Estado anti-duplicados (ofertas)
├── posted_ps_prereservas.json  ← Estado anti-duplicados (preórdenes) 🆕
├── README.md
├── PRERESERVAS_README.md       ← Documentación de preórdenes 🆕
└── tests/ (100 tests)

.github/workflows/
├── ofertas.yml                 ← Bebé (cada 30 min)
└── ofertas-ps.yml              ← PS4/PS5 (cada 30 min)

switch/                         ← Canal futuro
viajes/                         ← Canal futuro
```

---

## Constantes de Configuración (en `bebe/amazon_bebe_ofertas.py`)

```python
CATEGORIAS_BEBE                    # Línea ~70 - Categorías a buscar
CATEGORIAS_VERIFICAR_TITULOS       # Línea ~61 - Evitar títulos similares
CATEGORIAS_LIMITE_SEMANAL          # Línea ~64 - Solo 1x por semana
MARCAS_PRIORITARIAS                # Línea ~67 - Marcas en igualdad de descuento
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID      # Línea ~35-36 - Credenciales producción (env vars / GitHub Secrets)
DEV_TELEGRAM_BOT_TOKEN, DEV_TELEGRAM_CHAT_ID  # Línea ~39-40 - Credenciales dev (env vars / .env local)
DEV_MODE                           # Línea ~46 - Flag de modo dev (activado via --dev)
```

---

## Preórdenes - Canal PS (Nuevo 🆕)

El canal PS incluye una **búsqueda paralela de preórdenes** ejecutada en el mismo ciclo de 30 min:

### Constantes (en `ps/amazon_ps_ofertas.py`)
```python
CATEGORIAS_PRERESERVAS              # Línea ~106 - URLs de búsqueda (/s?k=juegos+ps5+proximamente)
LIMITE_PRERESERVAS_HORAS = 48       # Ventana de deduplicación (separada de ofertas)
MAX_PRERESERVAS_POR_CICLO = 3       # Máximo a publicar por ciclo
```

### Funciones Principales
```python
buscar_prereservas_ps()             # Función principal (línea ~178)
_es_prereserva_item(item)           # Detección de preórdenes (línea ~145)
format_prereserva_message()         # Formato Telegram (línea ~162)
load_posted_prereservas()           # Cargar estado (línea ~140)
save_posted_prereservas()           # Guardar estado (línea ~143)
```

### Coordinación con Ofertas
- **Límite global de 7 días:** Ambas funciones comparten `_ultima_publicacion_global` en `posted_ps_deals.json`
- **Si ofertas publican:** Preórdenes bloqueadas 7 días
- **Si preórdenes publican:** Ofertas bloqueadas 7 días
- **Persistencia separada:** Cada una tiene su propio JSON con ventana independiente

### Cambios Comunes - Preórdenes
| Tarea | Ubicación |
|-------|-----------|
| Ajustar URLs de búsqueda | `CATEGORIAS_PRERESERVAS` línea ~106 en `ps/amazon_ps_ofertas.py` |
| Cambiar patrones de detección | `indicadores_preorden` en función `_es_prereserva_item()` línea ~145 |
| Ver documentación completa | `ps/PRERESERVAS_README.md` |
| Ejecutar tests de preórdenes | `python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestBuscarPrereservasPS -v` |

---

## Sistema Anti-Repetición (5 Mecanismos)

1. **Anti-ASIN (48h):** No repite el mismo producto en 48 horas (ofertas)
2. **Anti-ASIN Preórdenes (48h):** No repite preórdenes en 48 horas (ventana independiente) 🆕
3. **Anti-Categoría:** Evita las últimas 4 categorías (excepto Pañales/Toallitas)
4. **Anti-Título Similar:** Para Chupetes/Juguetes, evita títulos con >50% palabras comunes
5. **Límite Global 7 días:** Ambas funciones (ofertas + preórdenes) respetan límite compartido

---

## Prioridad de Marcas

Cuando **igual descuento**, prefiere: `dodot`, `suavinex`, `baby sebamed`, `mustela`, `waterwipes`

---

## Lógica de Selección

```
Para cada categoría:
  1. Obtener ofertas de Amazon
  2. Ordenar: descuento ↓ → marca_prioritaria ↓ → valoraciones ↓ → ventas ↓
  3. Tomar la mejor no duplicada

De todas las mejores:
  1. Ordenar por: descuento ↓ → marca_prioritaria ↓
  2. Evitar últimas 4 categorías (si hay alternativas)
  3. Publicar en Telegram
```

---

## Ejecución

Los bots corre en **GitHub Actions** cada 30 minutos automáticamente.

### Lanzamiento manual
```bash
gh workflow run "Ofertas de Bebé"        # Canal bebé
gh workflow run "Ofertas PS4/PS5"        # Canal PS
gh run watch                             # Ver progreso en tiempo real
```

### Ejecución local - Canal Bebé
```bash
source .env && python3 bebe/amazon_bebe_ofertas.py            # Producción
source .env && python3 bebe/amazon_bebe_ofertas.py --dev      # Desarrollo (no modifica JSON)
source .env && python3 bebe/amazon_bebe_ofertas.py --continuo # Bucle cada 15 min
```

### Ejecución local - Canal PS4/PS5
```bash
source .env && python3 ps/amazon_ps_ofertas.py                # Producción
source .env && python3 ps/amazon_ps_ofertas.py --dev          # Desarrollo
source .env && python3 ps/amazon_ps_ofertas.py --continuo     # Bucle cada 15 min
```

### Tests
```bash
python3 -m pytest -v                                          # Todos los tests (184 total)
python3 -m pytest bebe/tests/ -v                              # Solo bebé (84 tests)
python3 -m pytest ps/tests/ -v                                # Solo PS (100 tests)

# Tests específicos de preórdenes
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestBuscarPrereservasPS -v
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestEsPrereservaItem -v
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestFormatPrereservaMessage -v
```

---

## Cambios Comunes

### Canal Bebé

| Tarea | Ubicación |
|-------|-----------|
| Añadir categoría | `CATEGORIAS_BEBE` línea ~72 en `bebe/amazon_bebe_ofertas.py` |
| Cambiar marcas prioritarias | `MARCAS_PRIORITARIAS` línea ~69 |
| Activar límite semanal en categoría | `CATEGORIAS_LIMITE_SEMANAL` línea ~66 |

### Canal PS4/PS5

| Tarea | Ubicación |
|-------|-----------|
| Cambiar priorización (siempre videojuegos) | Campo `tipo` en `CATEGORIAS_PS` línea ~71 en `ps/amazon_ps_ofertas.py` |
| Cambiar marcas prioritarias | `MARCAS_PRIORITARIAS` línea ~68 |
| Añadir categoría | `CATEGORIAS_PS` línea ~71 |

### Ambos canales

| Tarea | Ubicación |
|-------|-----------|
| Cambiar ventana anti-duplicados | `timedelta(hours=48)` en `load_posted_deals()` de `shared/amazon_ofertas_core.py` |
| Cambiar frecuencia del schedule | `cron:` en `.github/workflows/ofertas.yml` o `ofertas-ps.yml` |
| Cambiar formato Telegram | Función `format_telegram_message()` en `shared/amazon_ofertas_core.py` |
| Cambiar selectores CSS | Función `extraer_productos_busqueda()` en `shared/amazon_ofertas_core.py` |

### Secretos

| Credencial | Ubicación |
|---|---|
| Bebé Producción | GitHub Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Bebé Desarrollo | `.env` local: `DEV_TELEGRAM_BOT_TOKEN`, `DEV_TELEGRAM_CHAT_ID` |
| PS Producción | GitHub Secrets: `TELEGRAM_PS_BOT_TOKEN`, `TELEGRAM_PS_CHAT_ID` ✅ |
| PS Desarrollo | `.env` local: `DEV_TELEGRAM_PS_BOT_TOKEN`, `DEV_TELEGRAM_PS_CHAT_ID` |

---

**Más detalles técnicos:** Ver **AGENTS.md**
