# RadarOfertas — Plataforma Multi-Canal

Plataforma para crear **N canales independientes de ofertas en Telegram**, cada uno publicando automáticamente las mejores ofertas de Amazon.es en su nicho. Todos comparten el mismo motor (`amazon_ofertas_core.py`) y solo requieren un script de configuración propio.

Corre en **GitHub Actions** sin necesidad de servidor propio.

---

## Canales activos

| Canal | Carpeta | Status | Workflow |
|-------|---------|--------|----------|
| 🍼 Ofertas de Bebé | `bebe/` | ✅ En producción | Cada 30 min |
| 🎮 Ofertas PS4/PS5 | `ps/` | ✅ En producción* | Cada 30 min |

*Necesita agregar secrets en GitHub (TELEGRAM_PS_BOT_TOKEN, TELEGRAM_PS_CHAT_ID)

## Próximos canales (en desarrollo)

| Canal | Carpeta | Estado |
|-------|---------|--------|
| 🟢 Ofertas Nintendo Switch | `switch/` | Planificado |
| ✈️ Ofertas Viajes | `viajes/` | Planificado |

---

## ¿Cómo funciona?

### Búsqueda de Ofertas

```
1. Busca ofertas en Amazon en las categorías del canal
                          ↓
2. De cada categoría, selecciona la mejor oferta (mayor descuento, valoraciones altas)
                          ↓
3. Agrupa variantes del mismo producto (ej: FIFA 26 PS4 ↔ FIFA 26 PS5)
                          ↓
4. De todas las mejores, elige la de MAYOR DESCUENTO (con prioridad a marcas conocidas)
                          ↓
5. Publica en Telegram con links paralelos para cada variante:
   - PS5: 39,99€ → enlace Amazon PS5
   - PS4: 34,99€ → enlace Amazon PS4 (PS4)
```

### Búsqueda de Preórdenes (Canal PS — Nueva 🆕)

```
En paralelo, cada 30 min el canal PS ejecuta:

1. Busca próximos lanzamientos en Amazon.es (PS4/PS5)
                          ↓
2. Detecta preórdenes por patrones: "próximamente", "disponible el", "preventa"
                          ↓
3. Ordena por popularidad (valoraciones + ventas)
                          ↓
4. Publica hasta 3 preórdenes por ciclo
                          ↓
5. Respeta límite global de 7 días (solo UNA publicación cada 7 días: oferta O preorden)
```

**Sistema de Agrupamiento de Variantes:**
- Detecta automáticamente variantes usando normalización de títulos (ej: colores, plataformas)
- Una sola publicación en Telegram con **múltiples links clicables** (no "También disponible")
- Representante seleccionado por mayor descuento, variantes identificadas automáticamente
- Ambos ASINs guardados en anti-duplicados (evita re-publicar cualquier variante)

Cada canal tiene su propio estado anti-duplicados (`posted_*.json`) y sus propios secrets de Telegram, por lo que funcionan de forma completamente independientes.

---

## Arquitectura

El proyecto se estructura en un **core genérico** y **scripts especializados** por canal:

```
shared/
└── amazon_ofertas_core.py      ← Motor compartido: scraping, Telegram, utilidades

bebe/                           ← Canal bebé
├── amazon_bebe_ofertas.py      ← Config + lógica del canal
├── posted_bebe_deals.json      ← Estado anti-duplicados
└── tests/

ps/                             ← Canal PlayStation (futuro)
└── amazon_ps_ofertas.py

switch/                         ← Canal Nintendo Switch (futuro)
└── ...
```

Para **crear un nuevo canal** basta con una carpeta que contenga:
1. Un script que importe las utilidades del core
2. Sus categorías, marcas prioritarias y credenciales de Telegram
3. Su propio workflow de GitHub Actions

---

## Sistema Anti-Repetición

Cada canal aplica de forma independiente 5 filtros:

- **Anti-ASIN (48h):** No repite el mismo producto en 48 horas
- **Anti-Variante:** Cuando agrupa variantes, guarda todos los ASINs para evitar re-publicar
- **Anti-Categoría:** Evita las últimas 4 categorías publicadas
- **Anti-Título Similar:** En categorías configuradas, evita títulos con >50% palabras comunes
- **Límite Semanal:** Categorías configurables para publicarse solo 1 vez por semana

---

## Archivos del Proyecto

```
RadarOfertas/
├── shared/
│   └── amazon_ofertas_core.py      ← Motor genérico compartido
│
├── bebe/
│   ├── amazon_bebe_ofertas.py      ← Canal bebé
│   ├── posted_bebe_deals.json      ← Estado anti-duplicados del canal bebé
│   ├── README.md                   ← Documentación del canal bebé
│   └── tests/
│       └── test_amazon_bebe_ofertas.py ← 84 tests automatizados (+ 20 tests de variantes)
│
├── ps/
│   ├── amazon_ps_ofertas.py        ← Canal PS4/PS5 (Fase 3 ✅) + Preórdenes (Nueva 🆕)
│   ├── posted_ps_deals.json        ← Estado anti-duplicados del canal PS (ofertas)
│   ├── posted_ps_prereservas.json  ← Estado anti-duplicados del canal PS (preórdenes) 🆕
│   ├── PRERESERVAS_README.md       ← Documentación de preórdenes 🆕
│   ├── README.md                   ← Documentación del canal PS
│   └── tests/
│       └── test_amazon_ps_ofertas.py ← 100 tests (59 ofertas + 17 preórdenes + 24 variantes)
│
├── requirements.txt                ← Dependencias Python (producción)
├── requirements-dev.txt            ← Dependencias de desarrollo (pytest)
├── pytest.ini                      ← Config de pytest (testpaths, pythonpath)
│
├── .github/workflows/
│   ├── ofertas.yml                 ← Workflow del canal bebé (cada 30 min)
│   └── ofertas-ps.yml              ← Workflow del canal PS (cada 30 min)
│
├── .gitignore
├── README.md
├── CLAUDE.md                       ← Referencia rápida para Claude
├── AGENTS.md                       ← Referencia técnica para IA
├── PLAN_PS_CHANNEL.md              ← Plan de desarrollo del canal PS (Fases 1-4 ✅)
└── .env.sample                     ← Plantilla de credenciales
```

---

## GitHub Actions

Cada canal tiene su propio workflow que corre de forma independiente cada **30 minutos**. Al final de cada run, si se publicó una oferta nueva, el workflow hace commit del JSON de estado de vuelta al repo para persistir el historial.

Los logs de cada run están disponibles en la pestaña *Actions* del repo durante 90 días.

### Workflows disponibles

```bash
gh workflow run "Ofertas de Bebé"        # Canal bebé
gh workflow run "Ofertas PS4/PS5"        # Canal PS (requiere secrets)
gh run watch                             # Seguir progreso en tiempo real
```

### Configuración de nuevos canales

Al agregar un nuevo canal, necesitas:
1. Crear la carpeta y script (`canal/amazon_canal_ofertas.py`)
2. Crear el workflow (`.github/workflows/ofertas-canal.yml`)
3. Agregar los secrets en GitHub
4. El workflow se ejecutará automáticamente cada 30 minutos

---

## Ejecución y configuración local

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Configurar credenciales

Copia `.env.sample` a `.env` y rellena los valores (`.env` nunca se sube al repo, está en `.gitignore`):

```bash
cp .env.sample .env
# edita .env con tu editor y rellena los valores
```

**Variables de entorno necesarias:**

```bash
# Canal de Bebé
export TELEGRAM_BOT_TOKEN=tu_token_aqui
export TELEGRAM_CHAT_ID=tu_chat_id_aqui
export DEV_TELEGRAM_BOT_TOKEN=tu_token_dev
export DEV_TELEGRAM_CHAT_ID=tu_chat_id_dev

# Canal PS4/PS5 (nuevo)
export TELEGRAM_PS_BOT_TOKEN=tu_token_ps
export TELEGRAM_PS_CHAT_ID=tu_chat_id_ps
export DEV_TELEGRAM_PS_BOT_TOKEN=tu_token_ps_dev
export DEV_TELEGRAM_PS_CHAT_ID=tu_chat_id_ps_dev
```

**¿Cómo obtener estos valores?**
- **Token:** abre [@BotFather](https://t.me/BotFather) en Telegram → `/newbot` → sigue los pasos
- **Chat ID:** una vez el bot esté en el canal, llama a `https://api.telegram.org/bot<TOKEN>/getUpdates` tras enviar un mensaje al canal

### 3. Ejecutar

**Canal de Bebé:**
```bash
# Producción: publica en el canal real y actualiza el JSON de estado
source .env && python3 bebe/amazon_bebe_ofertas.py

# Desarrollo: publica en el canal de pruebas; el JSON de prod no se toca
source .env && python3 bebe/amazon_bebe_ofertas.py --dev
```

**Canal PS4/PS5:**
```bash
# Producción
source .env && python3 ps/amazon_ps_ofertas.py

# Desarrollo
source .env && python3 ps/amazon_ps_ofertas.py --dev

# Modo continuo (cada 15 minutos)
source .env && python3 ps/amazon_ps_ofertas.py --continuo
```

### 4. Ejecutar los tests (sin necesidad de credenciales)

```bash
pip install -r requirements-dev.txt

# Todos los tests (184 tests totales: 84 bebe + 100 PS)
python3 -m pytest -v

# Solo tests del canal bebé (84 tests: 64 originales + 20 de variantes)
python3 -m pytest bebe/tests/ -v

# Solo tests del canal PS (100 tests: 59 ofertas + 17 preórdenes + 24 variantes)
python3 -m pytest ps/tests/ -v

# Con cobertura
python3 -m pytest --cov=ps.amazon_ps_ofertas --cov-report=term-missing
```

---

## Solución de Problemas

### El bot no encuentra ofertas
- Revisar que las URLs de categorías sean válidas en Amazon.es
- Comprobar si Amazon ha cambiado los selectores CSS (ver AGENTS.md)

### No llega mensaje a Telegram
- Verificar que los secrets del canal estén correctamente configurados en *Settings → Secrets*
- Revisar los logs del último run en GitHub Actions

### Resetear el estado de un canal
```bash
# El bot volverá a publicar desde cero
echo "{}" > bebe/posted_bebe_deals.json
git add bebe/posted_bebe_deals.json && git commit -m "chore: resetear estado" && git push
```

---

## Precauciones

- No eliminar los delays entre requests (Amazon bloqueará las peticiones)
- No cambiar selectores CSS sin saber qué haces (Amazon cambia su HTML frecuentemente)
- Las credenciales van en GitHub Secrets, nunca en el código

---

**Canales activos:**
- 🍼 [@ofertasparaelbebe](https://t.me/ofertasparaelbebe) - Bebé
- 🎮 PS4/PS5 - En producción (secrets pendientes)
