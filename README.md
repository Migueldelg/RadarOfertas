# Amazon Ofertas Bot — Plataforma Multi-Canal

Plataforma para crear **N canales independientes de ofertas en Telegram**, cada uno publicando automáticamente las mejores ofertas de Amazon.es en su nicho. Todos comparten el mismo motor (`amazon_ofertas_core.py`) y solo requieren un script de configuración propio.

Corre en **GitHub Actions** sin necesidad de servidor propio.

---

## Canales activos

| Canal | Carpeta | Telegram | Workflow |
|-------|---------|----------|----------|
| 🍼 Ofertas de Bebé | `bebe/` | [@ofertasparaelbebe](https://t.me/ofertasparaelbebe) | Cada 30 min |

## Próximos canales (en desarrollo)

| Canal | Carpeta |
|-------|---------|
| 🎮 Ofertas PlayStation | `ps/` *(pendiente)* |
| 🟢 Ofertas Nintendo Switch | `switch/` *(pendiente)* |

---

## ¿Cómo funciona?

```
1. Busca ofertas en Amazon en las categorías del canal
                          ↓
2. De cada categoría, selecciona la mejor oferta (mayor descuento, valoraciones altas)
                          ↓
3. De todas las mejores, elige la de MAYOR DESCUENTO (con prioridad a marcas conocidas)
                          ↓
4. Publica 1 oferta en Telegram con foto y enlace de afiliado
```

Cada canal tiene su propio estado anti-duplicados (`posted_*.json`) y sus propios secrets de Telegram, por lo que funcionan de forma completamente independiente.

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

Cada canal aplica de forma independiente 4 filtros:

- **Anti-ASIN (48h):** No repite el mismo producto en 48 horas
- **Anti-Categoría:** Evita las últimas 4 categorías publicadas
- **Anti-Título Similar:** En categorías configuradas, evita títulos con >50% palabras comunes
- **Límite Semanal:** Categorías configurables para publicarse solo 1 vez por semana

---

## Archivos del Proyecto

```
OfertasDeBebe/
├── shared/
│   └── amazon_ofertas_core.py      ← Motor genérico compartido
│
├── bebe/
│   ├── amazon_bebe_ofertas.py      ← Canal bebé
│   ├── posted_bebe_deals.json      ← Estado anti-duplicados del canal bebé
│   └── tests/
│       └── test_amazon_bebe_ofertas.py ← 64 tests automatizados
│
├── requirements.txt                ← Dependencias Python (producción)
├── requirements-dev.txt            ← Dependencias de desarrollo (pytest)
├── pytest.ini                      ← Config de pytest (testpaths, pythonpath)
│
├── .github/workflows/
│   └── ofertas.yml                 ← Workflow del canal bebé (cada 30 min)
│
├── .gitignore
├── README.md
├── AGENTS.md                       ← Referencia técnica para IA
└── CLAUDE.md                       ← Referencia rápida para Claude
```

---

## GitHub Actions

Cada canal tiene su propio workflow que corre de forma independiente. Al final de cada run, si se publicó una oferta nueva, el workflow hace commit del JSON de estado de vuelta al repo para persistir el historial.

Los logs de cada run están disponibles en la pestaña *Actions* del repo durante 90 días.

### Ejecución manual

```bash
gh workflow run "Ofertas de Bebé"
gh run watch  # Seguir progreso en tiempo real
```

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

```bash
export TELEGRAM_BOT_TOKEN=tu_token_aqui       # Bot y canal de producción
export TELEGRAM_CHAT_ID=tu_chat_id_aqui
export DEV_TELEGRAM_BOT_TOKEN=tu_token_dev    # Bot y canal de pruebas (para --dev)
export DEV_TELEGRAM_CHAT_ID=tu_chat_id_dev
```

**¿Cómo obtener estos valores?**
- **Token:** abre [@BotFather](https://t.me/BotFather) en Telegram → `/newbot` → sigue los pasos
- **Chat ID:** una vez el bot esté en el canal, llama a `https://api.telegram.org/bot<TOKEN>/getUpdates` tras enviar un mensaje al canal

### 3. Ejecutar

```bash
# Producción: publica en el canal real y actualiza el JSON de estado
source .env && python3 bebe/amazon_bebe_ofertas.py

# Desarrollo: publica en el canal de pruebas; el JSON de prod no se toca
source .env && python3 bebe/amazon_bebe_ofertas.py --dev
```

### 4. Ejecutar los tests (sin necesidad de credenciales)

```bash
pip install -r requirements-dev.txt
python3 -m pytest -v
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

*Canales activos: [@ofertasparaelbebe](https://t.me/ofertasparaelbebe)*
