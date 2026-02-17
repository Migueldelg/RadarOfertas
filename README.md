# Amazon Ofertas Bot — Plataforma Multi-Canal

Plataforma para crear **N canales independientes de ofertas en Telegram**, cada uno publicando automáticamente las mejores ofertas de Amazon.es en su nicho. Todos comparten el mismo motor (`amazon_ofertas_core.py`) y solo requieren un script de configuración propio.

Corre en **GitHub Actions** sin necesidad de servidor propio.

---

## Canales activos

| Canal | Script | Telegram | Workflow |
|-------|--------|----------|----------|
| 🍼 Ofertas de Bebé | `amazon_bebe_ofertas.py` | [@ofertasparaelbebe](https://t.me/ofertasparaelbebe) | Cada 30 min |

## Próximos canales (en desarrollo)

| Canal | Script |
|-------|--------|
| 🎮 Ofertas PlayStation | `amazon_ps_ofertas.py` |
| 🟢 Ofertas Nintendo Switch | *(pendiente)* |

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
amazon_ofertas_core.py          ← Motor compartido: scraping, Telegram, utilidades
        │
        ├── amazon_bebe_ofertas.py      ← Canal bebé (categorías, marcas, credenciales)
        ├── amazon_ps_ofertas.py        ← Canal PlayStation (en desarrollo)
        └── amazon_switch_ofertas.py    ← Canal Switch (futuro)
```

Para **crear un nuevo canal** basta con un script que:
1. Importe las utilidades del core
2. Defina sus categorías, marcas prioritarias y credenciales de Telegram
3. Tenga su propio workflow de GitHub Actions

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
├── amazon_ofertas_core.py          ← Motor genérico compartido
│
├── amazon_bebe_ofertas.py          ← Canal bebé
├── posted_bebe_deals.json          ← Estado anti-duplicados del canal bebé
│
├── requirements.txt                ← Dependencias Python (producción)
├── requirements-dev.txt            ← Dependencias de desarrollo (pytest)
├── tests/
│   └── test_amazon_bebe_ofertas.py ← 64 tests automatizados
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
export TELEGRAM_BOT_TOKEN=tu_token_aqui
export TELEGRAM_CHAT_ID=tu_chat_id_aqui
```

**¿Cómo obtener estos valores?**
- **Token:** abre [@BotFather](https://t.me/BotFather) en Telegram → `/newbot` → sigue los pasos
- **Chat ID:** una vez el bot esté en el canal, llama a `https://api.telegram.org/bot<TOKEN>/getUpdates` tras enviar un mensaje al canal

### 3. Ejecutar

```bash
# Cargar variables y ejecutar
source .env && python3 amazon_bebe_ofertas.py
```

### 4. Ejecutar los tests (sin necesidad de credenciales)

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
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
echo "{}" > posted_bebe_deals.json
git add posted_bebe_deals.json && git commit -m "chore: resetear estado" && git push
```

---

## Precauciones

- No eliminar los delays entre requests (Amazon bloqueará las peticiones)
- No cambiar selectores CSS sin saber qué haces (Amazon cambia su HTML frecuentemente)
- Las credenciales van en GitHub Secrets, nunca en el código

---

*Canales activos: [@ofertasparaelbebe](https://t.me/ofertasparaelbebe)*
