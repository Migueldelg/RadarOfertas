# Búsqueda de Preórdenes - Canal PS4/PS5

## 📖 Cómo Funciona

La búsqueda de preórdenes es un sistema paralelo a la búsqueda de ofertas que:

1. **Se ejecuta cada 30 minutos** en el mismo ciclo que las ofertas
2. **Busca en 2 categorías**: "Próximos PS5" y "Próximos PS4"
3. **Publica hasta 3 preórdenes** por ciclo exitoso
4. **Respeta límite global de 7 días** compartido con ofertas

## 🔍 Cómo Se Detectan Preórdenes

### URLs de Búsqueda
```
https://www.amazon.es/s?k=juegos+ps5+proximamente
https://www.amazon.es/s?k=juegos+ps4+proximamente
```

### Patrones de Detección (en `_es_prereserva_item()`)

**Indicadores que detectan preórdenes:**
- `próximamente`
- `disponible el`
- `próxima`
- `pronto disponible`
- `preventa`, `pre-orden`, `preorder`
- `reservar`, `en reserva`
- `lanzamiento`, `fecha de lanzamiento`

**Filtros de falsos positivos:**
- Ignora "sin bono de reserva" a menos que haya indicadores fuertes

## 🛠️ Debugging y Ajustes

### Si no encuentras preórdenes:

```python
# 1. Verificar que las URLs devuelven resultados
python3 -c "
from shared.amazon_ofertas_core import obtener_pagina, BASE_URL
from bs4 import BeautifulSoup

url = BASE_URL + '/s?k=juegos+ps5+proximamente'
html = obtener_pagina(url)
soup = BeautifulSoup(html, 'html.parser')
items = soup.select('[data-component-type=\"s-search-result\"]')
print(f'Items encontrados: {len(items)}')
"

# 2. Ver qué patrones tiene el HTML real
python3 -c "
from shared.amazon_ofertas_core import obtener_pagina, BASE_URL
from bs4 import BeautifulSoup

url = BASE_URL + '/s?k=juegos+ps5+proximamente'
html = obtener_pagina(url)
soup = BeautifulSoup(html, 'html.parser')
items = soup.select('[data-component-type=\"s-search-result\"]')[:1]

for item in items:
    texto = item.get_text()[:200]
    print('Texto del primer item:')
    print(texto)
"
```

### Ajustar URLs de búsqueda:

Editar `ps/amazon_ps_ofertas.py` línea ~106:

```python
CATEGORIAS_PRERESERVAS = [
    {"nombre": "Próximos PS5", "emoji": "⏰", "url": "/s?k=juegos+ps5+AQUI"},
    {"nombre": "Próximos PS4", "emoji": "⏰", "url": "/s?k=juegos+ps4+AQUI"},
]
```

**URLs alternativas a probar:**
- `/s?k=juegos+ps5+proximamente` (actual, recomendado)
- `/s?k=juegos+ps5+proximo+lanzamiento`
- `/s?k=juegos+ps5+nuevo`
- `/s?k=ps5+preorder` (si Amazon.es la acepta)

### Ajustar patrones de detección:

Editar `ps/amazon_ps_ofertas.py` función `_es_prereserva_item()`:

```python
# Agregar nuevos indicadores en la lista:
indicadores_preorden = [
    'próximamente',
    'tu_nuevo_patrón_aquí',  # ← Agregar aquí
    'disponible el',
    # ...
]
```

## 📊 Información de Persistencia

### Archivo: `posted_ps_prereservas.json`

Estructura:
```json
{
    "B0EXAMPLE01": "2026-02-20T09:15:30.123456",
    "B0EXAMPLE02": "2026-02-20T09:16:45.654321"
}
```

- **Clave**: ASIN del preorden
- **Valor**: ISO timestamp de cuándo fue publicado
- **Ventana**: 48 horas (después expira y puede reciclarse)

### Límite Global

El timestamp `_ultima_publicacion_global` en `posted_ps_deals.json` bloquea ambos:
- Si ofertas publican → preórdenes bloqueadas 7 días
- Si preórdenes publican → ofertas bloqueadas 7 días

## 📋 Variables de Configuración

En `ps/amazon_ps_ofertas.py`:

```python
POSTED_PS_PRERESERVAS_FILE = "..."  # Ruta al archivo de persistencia
LIMITE_PRERESERVAS_HORAS = 48      # Ventana de dedup
MAX_PRERESERVAS_POR_CICLO = 3      # Máximo a publicar por ciclo
CATEGORIAS_PRERESERVAS = [...]     # URLs de búsqueda
```

## 🧪 Tests

```bash
# Todos los tests de preórdenes
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestBuscarPrereservasPS -v

# Test específico de detección
python3 -m pytest ps/tests/test_amazon_ps_ofertas.py::TestEsPrereservaItem -v

# Todos los tests (100 total)
python3 -m pytest ps/tests/ -v
```

## 📝 Notas Importantes

1. **Disponibilidad real**: La búsqueda solo funcionará si Amazon.es tiene preórdenes reales disponibles
2. **Patrones flexibles**: La función de detección es robusta y tolerante a variaciones en el HTML
3. **No bloqueante**: Si no hay preórdenes, simplemente retorna 0 (no afecta otras funciones)
4. **Coordinación automática**: El sistema de 7 días se coordina automáticamente sin necesidad de locks

## 🎯 Ejemplos de Formato Telegram

**Ejemplo de preorden publicado:**

```
⏰ PRÓXIMO LANZAMIENTO PRÓXIMOS PS5 ⏰

📦 Metal Gear Solid Delta: Snake Eater

💰 Precio de reserva: 69,99€

🛒 Reservar en Amazon
```

**Múltiples preórdenes en un ciclo:**
- Se publican hasta 3 mensajes separados en Telegram
- Cada uno con su propio enlace de compra
- Sin duplicar en 48 horas
