# 🎮 Canal PS4/PS5 - Buscador de Ofertas

Script para obtener las mejores ofertas de videojuegos y accesorios PS4/PS5 de Amazon.es y publicarlas en un canal de Telegram.

## Estructura

```
ps/
├── amazon_ps_ofertas.py           ← Script principal (ofertas + preórdenes)
├── posted_ps_deals.json           ← Estado anti-duplicados (ofertas)
├── posted_ps_prereservas.json     ← Estado anti-duplicados (preórdenes) 🆕
├── ofertas_ps.log                 ← Logs de ejecución
├── README.md                      ← Este archivo
├── PRERESERVAS_README.md          ← Documentación de preórdenes 🆕
└── tests/
    └── test_amazon_ps_ofertas.py  ← 100 tests automatizados (59 ofertas + 17 preórdenes + 24 variantes)
```

## Características

### Búsqueda de Ofertas
✅ **Videojuegos priorizados** - Siempre publica juegos PS4/PS5 antes que accesorios
✅ **Agrupamiento de variantes** - Automáticamente agrupa PS4/PS5 en un solo mensaje con links paralelos
✅ **Anti-duplicados 96h** - No repite el mismo ASIN en 96 horas (incluyendo variantes)
✅ **Anti-títulos similares** - Evita publicar juegos similares repetidamente
✅ **Límite global 7 días** - Una publicación cada 7 días (oferta o preorden)

### Búsqueda de Preórdenes 🆕
✅ **Ejecución paralela** - Se ejecuta cada 30 min junto con ofertas
✅ **Detección automática** - Identifica preórdenes por patrones HTML ("próximamente", "preventa", etc.)
✅ **Hasta 3 por ciclo** - Publica máximo 3 preórdenes cuando están disponibles
✅ **Anti-duplicados 48h** - Ventana independiente de ofertas (puede reciclar cada 2 días)
✅ **Formato diferente** - Mensajes con ⏰ emoji, sin precios tachados, enlace "Reservar"

### General
✅ **Modo desarrollo** - Publica en canal de pruebas sin modificar los JSONs
✅ **Tests completos** - 100 tests que cubren ofertas, preórdenes y variantes

## Configuración

### Credenciales de Telegram

Necesitas dos conjuntos de credenciales:

1. **Producción** (publicar en el canal real):
   ```bash
   export TELEGRAM_PS_BOT_TOKEN=8542903683:AAFcIbXqweq8b4Sqo2c7eaKsgkneZcivfio
   export TELEGRAM_PS_CHAT_ID=1003885398555
   ```

2. **Desarrollo** (publicar en canal de pruebas, sin modificar JSON):
   ```bash
   export DEV_TELEGRAM_PS_BOT_TOKEN=...
   export DEV_TELEGRAM_PS_CHAT_ID=...
   ```

Guarda estas variables en tu `.env` local:
```bash
source .env
```

## Ejecución

### Modo Manual (una sola vez)

```bash
# Publicar en el canal de producción
source .env && python3 ps/amazon_ps_ofertas.py

# Publicar en canal de pruebas (no modifica posted_ps_deals.json)
source .env && python3 ps/amazon_ps_ofertas.py --dev
```

### Modo Continuo (cada 15 minutos)

```bash
source .env && python3 ps/amazon_ps_ofertas.py --continuo
```

### Tests

```bash
# Ejecutar todos los tests (100 tests: 59 ofertas + 17 preórdenes + 24 variantes)
python3 -m pytest ps/tests/ -v

# Ver cobertura
python3 -m pytest ps/tests/ --cov=ps.amazon_ps_ofertas --cov-report=term-missing

# Solo tests de preórdenes
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestBuscarPrereservasPS -v
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestEsPrereservaItem -v
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestFormatPrereservaMessage -v

# Ejecutar un test específico
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestObtenerPrioridadMarca -v
```

## Lógica de Selección

```
1. Para cada categoría (videojuegos primero, luego accesorios):
   ├─ Obtener productos de Amazon
   ├─ Filtrar solo los que tienen descuento
   └─ Elegir el mejor según: descuento ↓ → marca_prioritaria ↓ → valoraciones ↓ → ventas ↓

2. Agrupar variantes del mismo producto (ej: FIFA 26 PS4 ↔ FIFA 26 PS5)
   ├─ Representante: producto con mayor descuento
   └─ Variantes adicionales: guardadas para mostrar en Telegram

3. De todos los mejores por categoría:
   ├─ Prefiere videojuegos sobre accesorios
   ├─ Evita repetir las últimas 4 categorías (si hay alternativas)
   ├─ No republica ASINs en <48h (incluyendo variantes)
   └─ Para Juegos PS4/PS5: evita títulos similares a los últimos publicados

4. Publicar en Telegram con formato especial si hay variantes
5. Guardar estado (ASINs de todas las variantes)
```

### Formato Telegram con Variantes

Cuando se detectan variantes (ej: PS5 vs PS4), el mensaje muestra **múltiples links paralelos**:

```
🎮 OFERTA JUEGOS PS5 🎮

📦 FIFA 26 PS5

💰 39,99€ <s>69,99€</s> (-43%)
💰 34,99€ <s>58,99€</s> (-40%) (PS4)
```

**Características:**
- ✅ Ambos precios son **clickeables** (no hay "También disponible")
- ✅ Identificadores automáticos: `(PS4)`, `(PS5)`, `(AZUL)`, etc.
- ✅ Precios anteriores tachados en ambas opciones
- ✅ Descuentos mostrados en ambas variantes

**Formato original sin variantes (preservado):**
```
🎮 OFERTA JUEGOS PS5 🎮

📦 Mando DualSense

💰 Precio: 74,99€ → 59,99€ (-20%)

🛒 Ver en Amazon
```

## Búsqueda de Preórdenes 🆕

El canal PS incluye una búsqueda paralela de **próximos lanzamientos y preórdenes** que:

- Se ejecuta **en el mismo ciclo** de 30 minutos
- Busca en `/s?k=juegos+ps5+proximamente` y `/s?k=juegos+ps4+proximamente`
- Detecta preórdenes por patrones HTML: "próximamente", "disponible el", "preventa", "preorder"
- Publica **hasta 3 preórdenes** por ciclo (si están disponibles)
- **No repite en 48 horas** (ventana independiente de ofertas)
- **Respeta límite global de 7 días** (solo UNA publicación cada 7 días: oferta O preorden)

### Formato de Preorden

```
⏰ PRÓXIMO LANZAMIENTO PRÓXIMOS PS5 ⏰

📦 Metal Gear Solid Delta: Snake Eater

💰 Precio de reserva: 69,99€

🛒 Reservar en Amazon
```

**Características:**
- ⏰ Emoji de reloj para identificar preórdenes
- Sin precios tachados (no hay descuento conocido)
- Botón "Reservar" en lugar de "Ver en Amazon"
- Enlace directo a la página de reserva del producto

### Archivo de Persistencia: `posted_ps_prereservas.json`

Almacena los preórdenes publicados con una **ventana de 48 horas** (separada de las ofertas):

```json
{
  "B0EXAMPLE01": "2026-02-20T09:15:30.123456",
  "B0EXAMPLE02": "2026-02-20T09:16:45.654321"
}
```

**Coordinación con ofertas:**
- Ambos comparten el timestamp `_ultima_publicacion_global` en `posted_ps_deals.json`
- Si ofertas publican → preórdenes bloqueadas 7 días
- Si preórdenes publican → ofertas bloqueadas 7 días
- Sistema automático sin locks manuales

Para más detalles sobre debugging y ajustes, ver **`PRERESERVAS_README.md`**.

## Categorías

### Videojuegos (Priorizados ⭐)
- 🎮 Juegos PS5 → `/s?k=juegos+ps5`
- 🎮 Juegos PS4 → `/s?k=juegos+ps4`

### Accesorios
- 🕹️ Mandos PS5 → `/s?k=mando+dualsense+ps5`
- 🕹️ Mandos PS4 → `/s?k=mando+dualshock+ps4`
- 🎧 Auriculares gaming → `/s?k=auriculares+gaming+ps4+ps5`
- 💳 Tarjetas PSN → `/s?k=tarjeta+psn+playstation`
- ⚙️ Accesorios PS5 → `/s?k=accesorios+ps5`
- ⚙️ Accesorios PS4 → `/s?k=accesorios+ps4`

## Marcas Prioritarias

Cuando hay igualdad de descuento, se prefieren estas marcas:
- `sony`
- `playstation`
- `nacon`
- `thrustmaster`
- `razer`
- `hyperx`

## Archivo de Estado: `posted_ps_deals.json`

Estructura del JSON que mantiene el historial:

```json
{
  "_ultimas_categorias": ["Juegos PS5", "Mandos PS5", "Accesorios PS5", "Juegos PS4"],
  "_ultimos_titulos": ["Juego PS5 Elden Ring...", "Juego PS5 The Last..."],
  "_categorias_semanales": {},
  "B08XYZ123": "2025-02-17T10:30:00",
  "B07ABC456": "2025-02-16T18:45:00"
}
```

- **`_ultimas_categorias`**: Últimas 4 categorías publicadas (para evitar repetir)
- **`_ultimos_titulos`**: Últimos 4 títulos de juegos (para evitar similares)
- **`_categorias_semanales`**: Timestamps de últimas publicaciones por categoría (no aplica en PS)
- **`ASIN`**: Timestamp ISO de cuándo se publicó (expirado después de 48h)

## Modo DEV vs PROD

| Comportamiento | Producción | Dev (`--dev`) |
|---|---|---|
| Canal Telegram | `TELEGRAM_PS_CHAT_ID` | `DEV_TELEGRAM_PS_CHAT_ID` |
| Bot token | `TELEGRAM_PS_BOT_TOKEN` | `DEV_TELEGRAM_PS_BOT_TOKEN` |
| Lee historial JSON | ✅ Sí | ❌ No (vacío) |
| Escribe historial JSON | ✅ Sí | ❌ No (sin cambios) |
| Deduplicación | ✅ Sí | ❌ No (puede repetir) |

Ideal para **probar cambios sin contaminar el historial de producción**.

## Resetear Estado

```bash
# Resetear TODO el historial (volverá a publicar desde cero)
rm ps/posted_ps_deals.json
git add ps/posted_ps_deals.json && git commit -m "chore: resetear estado PS" && git push

# Resetear solo las últimas categorías: editar JSON manualmente
# Resetear solo los títulos recientes: editar JSON manualmente
```

## Logs

Los logs se guardan en `ps/ofertas_ps.log` con rotación diaria (conserva últimos 5 días).

```bash
# Ver logs en tiempo real
tail -f ps/ofertas_ps.log

# Ver último ciclo
tail -50 ps/ofertas_ps.log
```

## Diferencias con el canal de Bebé

| Aspecto | Bebé | PS |
|---|---|---|
| Priorización | Categórica (Pañales/Toallitas sin repetición) | Videojuegos siempre |
| Límite semanal | ✅ Tronas, Cámaras, Chupetes, Vajilla | ❌ Ninguno |
| Videojuegos | ❌ No aplica | ✅ Priorizados |
| Anti-títulos similares | Chupetes, Juguetes | Juegos PS5, Juegos PS4 |
| Agrupamiento de variantes | ✅ Ambos canales | ✅ Ambos canales |
| Tests | 84 tests | 79 tests |

## Próximos Pasos (GitHub Actions)

Cuando estés listo para programar automáticamente:

1. Crear `.github/workflows/ofertas-ps.yml` (similar a `ofertas.yml`)
2. Añadir secrets en GitHub:
   - `TELEGRAM_PS_BOT_TOKEN`
   - `TELEGRAM_PS_CHAT_ID`
3. Configurar schedule: `0 */30 * * *` (cada 30 minutos)
4. Git pull --rebase para evitar conflictos de concurrencia

## Testing

Todos los tests usan mocks y fixtures, sin acceder a Amazon ni Telegram:

- ✅ **Funciones puras**: normalización, similitud, prioridades
- ✅ **I/O con mocks**: Telegram, archivos JSON
- ✅ **Parsing HTML**: extracción de productos
- ✅ **Lógica de selección**: priorización de videojuegos, anti-duplicados

```bash
# Cobertura detallada
python3 -m pytest ps/tests/ -v --cov=ps.amazon_ps_ofertas --cov-report=html
# Abrir htmlcov/index.html
```

## Troubleshooting

### Error: "Credenciales de Telegram no configuradas"
```bash
# Asegúrate de que las variables están en el entorno:
echo $TELEGRAM_PS_BOT_TOKEN
echo $TELEGRAM_PS_CHAT_ID

# O en modo dev:
echo $DEV_TELEGRAM_PS_BOT_TOKEN
echo $DEV_TELEGRAM_PS_CHAT_ID
```

### Amazon bloqueó la IP
Si obtiene errores de conexión, intenta:
```bash
# Limpiar historial de reintentos
rm ps/ofertas_ps.log
```

### Los tests fallan
```bash
# Asegúrate de que el módulo se importa correctamente
python3 -c "import ps.amazon_ps_ofertas; print('OK')"

# Ejecuta en verbose para más detalles
python3 -m pytest ps/tests/ -vv
```

---

## Roadmap

- ✅ **Fase 1:** Búsqueda de ofertas (videojuegos priorizados)
- ✅ **Fase 2:** Agrupamiento de variantes (PS4 + PS5)
- ✅ **Fase 3:** Límite global de 7 días entre publicaciones
- ✅ **Fase 4:** Búsqueda paralela de preórdenes 🆕

---

**Creado con ❤️ en Fase 4 del Plan PS** (Preórdenes 🆕)
