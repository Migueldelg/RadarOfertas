#!/usr/bin/env python3
"""
Script para obtener ofertas de videojuegos y accesorios PS4/PS5 de Amazon.es
y publicarlas en Telegram
"""

import argparse
import time
import os
import sys
import logging
from datetime import datetime, timedelta

# Add project root to path so shared/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.amazon_ofertas_core import (
    setup_logging,
    BASE_URL,
    PARTNER_TAG,
    obtener_pagina,
    extraer_productos_busqueda,
    normalizar_titulo,
    titulos_similares,
    titulo_similar_a_recientes,
    format_telegram_message,
    obtener_prioridad_marca as _obtener_prioridad_marca_core,
    send_telegram_message as _send_telegram_message_core,
    send_telegram_photo as _send_telegram_photo_core,
    load_posted_deals as _load_posted_deals_core,
    save_posted_deals as _save_posted_deals_core,
)

_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ofertas_ps.log")
setup_logging(_LOG_FILE)
log = logging.getLogger(__name__)

# --- Configuracion de Telegram ---
# Bot y canal (ofertas PS) — produccion:
TELEGRAM_PS_BOT_TOKEN = os.getenv('TELEGRAM_PS_BOT_TOKEN')
TELEGRAM_PS_CHAT_ID = os.getenv('TELEGRAM_PS_CHAT_ID')

# Bot y canal — desarrollo (--dev):
DEV_TELEGRAM_PS_BOT_TOKEN = os.getenv('DEV_TELEGRAM_PS_BOT_TOKEN')
DEV_TELEGRAM_PS_CHAT_ID = os.getenv('DEV_TELEGRAM_PS_CHAT_ID')

# Flag de modo dev (se activa via --dev en CLI)
DEV_MODE = False

# Archivo para guardar ofertas ya publicadas
POSTED_PS_DEALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posted_ps_deals.json")


def _effective_token():
    return DEV_TELEGRAM_PS_BOT_TOKEN if DEV_MODE and DEV_TELEGRAM_PS_BOT_TOKEN else TELEGRAM_PS_BOT_TOKEN


def _effective_chat_id():
    return DEV_TELEGRAM_PS_CHAT_ID if DEV_MODE and DEV_TELEGRAM_PS_CHAT_ID else TELEGRAM_PS_CHAT_ID

# Categorias que requieren verificacion de titulos similares
# (para evitar publicar el mismo tipo de producto repetidamente)
CATEGORIAS_VERIFICAR_TITULOS = ["Juegos PS5", "Juegos PS4"]

# Categorias que solo se publican una vez por semana (no aplica en PS)
CATEGORIAS_LIMITE_SEMANAL = []

# Marcas prioritarias (se prefieren cuando hay igualdad de descuento)
MARCAS_PRIORITARIAS = ["sony", "playstation", "nacon", "thrustmaster", "razer", "hyperx"]

# Categorias de productos PS4/PS5 para buscar
# Videojuegos se buscan primero y tienen prioridad
CATEGORIAS_PS = [
    {"nombre": "Juegos PS5", "emoji": "🎮", "url": "/s?k=juegos+ps5", "tipo": "videojuego"},
    {"nombre": "Juegos PS4", "emoji": "🎮", "url": "/s?k=juegos+ps4", "tipo": "videojuego"},
    {"nombre": "Mandos PS5", "emoji": "🕹️", "url": "/s?k=mando+dualsense+ps5", "tipo": "accesorio"},
    {"nombre": "Mandos PS4", "emoji": "🕹️", "url": "/s?k=mando+dualshock+ps4", "tipo": "accesorio"},
    {"nombre": "Auriculares gaming", "emoji": "🎧", "url": "/s?k=auriculares+gaming+ps4+ps5", "tipo": "accesorio"},
    {"nombre": "Tarjetas PSN", "emoji": "💳", "url": "/s?k=tarjeta+psn+playstation", "tipo": "accesorio"},
    {"nombre": "Accesorios PS5", "emoji": "⚙️", "url": "/s?k=accesorios+ps5", "tipo": "accesorio"},
    {"nombre": "Accesorios PS4", "emoji": "⚙️", "url": "/s?k=accesorios+ps4", "tipo": "accesorio"},
]


# --- Wrappers de funciones parametrizadas del core ---
# Estas definiciones en el namespace del módulo permiten que los tests
# hagan monkeypatch sobre bot.send_telegram_photo, bot.obtener_prioridad_marca, etc.

def obtener_prioridad_marca(titulo):
    return _obtener_prioridad_marca_core(titulo, MARCAS_PRIORITARIAS)


def send_telegram_message(message):
    """Envia un mensaje al canal de Telegram de PS."""
    return _send_telegram_message_core(message, _effective_token(), _effective_chat_id())


def send_telegram_photo(photo_url, caption):
    """Envia una foto con caption al canal de Telegram de PS."""
    return _send_telegram_photo_core(photo_url, caption, _effective_token(), _effective_chat_id())


def load_posted_deals():
    """
    Carga las ofertas publicadas (ultimas 48h) desde un archivo JSON.
    Retorna tupla: (dict_ofertas, ultimas_categorias, ultimos_titulos, categorias_semanales)
    """
    return _load_posted_deals_core(POSTED_PS_DEALS_FILE)


def save_posted_deals(deals_dict, ultimas_categorias=None, ultimos_titulos=None, categorias_semanales=None):
    """Guarda el diccionario de ofertas publicadas en un archivo JSON."""
    return _save_posted_deals_core(deals_dict, POSTED_PS_DEALS_FILE, ultimas_categorias, ultimos_titulos, categorias_semanales)


def buscar_y_publicar_ofertas():
    """
    Busca la mejor oferta de cada categoria y publica la de mayor descuento.
    Prioriza siempre videojuegos sobre accesorios.
    """
    if not _effective_token() or not _effective_chat_id():
        if DEV_MODE:
            log.error(
                "DEV_MODE activo pero credenciales dev no configuradas. "
                "Establece DEV_TELEGRAM_PS_BOT_TOKEN y DEV_TELEGRAM_PS_CHAT_ID."
            )
        else:
            log.error(
                "Credenciales de Telegram no configuradas. "
                "Establece las variables de entorno TELEGRAM_PS_BOT_TOKEN y TELEGRAM_PS_CHAT_ID."
            )
        return 0

    log.info("=" * 60)
    if DEV_MODE:
        log.info("INICIO [DEV MODE] - BUSCADOR DE OFERTAS PS4/PS5 | Amazon.es -> Telegram (canal de pruebas)")
    else:
        log.info("INICIO - BUSCADOR DE OFERTAS PS4/PS5 | Amazon.es -> Telegram")
    log.info("Tag de afiliado: %s | Hora: %s", PARTNER_TAG, datetime.now().strftime('%d/%m/%Y %H:%M'))
    log.info("=" * 60)

    # Cargar ofertas ya publicadas (ultimas 48h), ultimas categorias y titulos
    # En DEV_MODE se ignora el historial para no contaminar el JSON de produccion
    if DEV_MODE:
        posted_deals, ultimas_categorias, ultimos_titulos, categorias_semanales = {}, [], [], {}
        log.info("DEV_MODE: historial de publicaciones ignorado (posted_ps_deals.json no se leerá ni escribirá)")
    else:
        posted_deals, ultimas_categorias, ultimos_titulos, categorias_semanales = load_posted_deals()
    posted_asins = set(posted_deals.keys())

    if ultimas_categorias:
        log.info(
            "Anti-repeticion de categoria: se evitaran las ultimas %d categorias [%s]",
            len(ultimas_categorias), ", ".join(ultimas_categorias)
        )
    if ultimos_titulos:
        log.info(
            "Anti-titulo-similar activo para categorias %s (%d titulos recientes guardados)",
            ", ".join(CATEGORIAS_VERIFICAR_TITULOS), len(ultimos_titulos)
        )

    now = datetime.now()
    una_semana = timedelta(days=7)

    # Recopilar la mejor oferta de cada categoria
    mejores_por_categoria = []
    mejores_videojuegos = []  # Separar videojuegos para priorizarlos

    for categoria in CATEGORIAS_PS:
        log.info("")
        log.info("--- Categoria: %s ---", categoria['nombre'])

        # Verificar limite semanal para ciertas categorias
        if categoria['nombre'] in CATEGORIAS_LIMITE_SEMANAL:
            ultima_pub_str = categorias_semanales.get(categoria['nombre'])
            if ultima_pub_str:
                try:
                    ultima_pub = datetime.fromisoformat(ultima_pub_str)
                    tiempo_transcurrido = now - ultima_pub
                    if tiempo_transcurrido < una_semana:
                        dias_restantes = (una_semana - tiempo_transcurrido).days + 1
                        log.info(
                            "  SALTADA por limite semanal: ultima publicacion el %s (hace %d dias, faltan ~%d dias)",
                            ultima_pub.strftime('%d/%m %H:%M'), tiempo_transcurrido.days, dias_restantes
                        )
                        continue
                    else:
                        log.debug(
                            "  Limite semanal OK: ultima publicacion hace %d dias (supera los 7 requeridos)",
                            tiempo_transcurrido.days
                        )
                except (ValueError, TypeError):
                    pass

        url = BASE_URL + categoria['url']
        html_content = obtener_pagina(url)

        if not html_content:
            log.warning("  No se pudo obtener la pagina, saltando categoria")
            continue

        productos = extraer_productos_busqueda(html_content)
        ofertas = [p for p in productos if p['tiene_oferta']]
        sin_oferta = len(productos) - len(ofertas)
        log.info(
            "  Scraped: %d productos (%d con oferta, %d sin descuento)",
            len(productos), len(ofertas), sin_oferta
        )

        if not ofertas:
            log.info("  No hay productos con descuento en esta categoria")
            continue

        # Ordenar ofertas: primero por mayor descuento, luego marca prioritaria, luego valoraciones, luego ventas
        ofertas_ordenadas = sorted(
            ofertas,
            key=lambda x: (x['descuento'], obtener_prioridad_marca(x['titulo']), x['valoraciones'], x['ventas']),
            reverse=True
        )

        # Log de los top candidatos antes de filtrar
        log.debug("  Top candidatos antes de filtros anti-duplicacion:")
        for i, p in enumerate(ofertas_ordenadas[:5], 1):
            marca_flag = " [MARCA PRIO]" if obtener_prioridad_marca(p['titulo']) else ""
            log.debug(
                "    %d. [%s] %s | %.0f%% dto | %d vals | %d ventas%s",
                i, p['asin'], p['titulo'][:50], p['descuento'],
                p['valoraciones'], p['ventas'], marca_flag
            )

        # Buscar la mejor oferta no publicada en esta categoria
        verificar_titulos = categoria['nombre'] in CATEGORIAS_VERIFICAR_TITULOS
        candidato_elegido = None

        for producto in ofertas_ordenadas:
            asin = producto['asin']
            titulo_corto = producto['titulo'][:45]

            if asin in posted_asins:
                log.info(
                    "  DESCARTADO [ya publicado en <48h] %s... (%.0f%% dto, ASIN: %s)",
                    titulo_corto, producto['descuento'], asin
                )
                continue

            if verificar_titulos and titulo_similar_a_recientes(producto['titulo'], ultimos_titulos):
                log.info(
                    "  DESCARTADO [titulo similar a reciente] %s... (%.0f%% dto)",
                    titulo_corto, producto['descuento']
                )
                continue

            candidato_elegido = producto
            marca_flag = " [marca prioritaria]" if obtener_prioridad_marca(producto['titulo']) else ""
            log.info(
                "  ELEGIDO para categoria: %s... (%.0f%% dto, %d valoraciones, ASIN: %s)%s",
                titulo_corto, producto['descuento'], producto['valoraciones'], asin, marca_flag
            )

            # Separar videojuegos de accesorios para priorizar videojuegos
            entrada = {
                'producto': producto,
                'categoria': categoria
            }
            if categoria['tipo'] == 'videojuego':
                mejores_videojuegos.append(entrada)
            else:
                mejores_por_categoria.append(entrada)
            break

        if candidato_elegido is None:
            log.info("  Sin candidatos validos: todos descartados por duplicacion o similitud de titulo")

    # Priorizar videojuegos: agregar los videojuegos ordenados antes que accesorios
    # Combinar: primero videojuegos ordenados por descuento, luego accesorios
    mejores_videojuegos.sort(
        key=lambda x: (x['producto']['descuento'], obtener_prioridad_marca(x['producto']['titulo'])),
        reverse=True
    )
    mejores_por_categoria = mejores_videojuegos + mejores_por_categoria

    # De entre las mejores ofertas, seleccionar la de mayor descuento
    if not mejores_por_categoria:
        log.info("")
        log.info("=" * 60)
        log.info("RESULTADO: No hay ofertas nuevas para publicar en este ciclo")
        log.info("=" * 60)
        return 0

    # Ordenar por descuento y marca prioritaria, seleccionar la mejor
    mejores_por_categoria.sort(
        key=lambda x: (x['producto']['descuento'], obtener_prioridad_marca(x['producto']['titulo'])),
        reverse=True
    )

    log.info("")
    log.info("--- Seleccion global (ranking de mejores por categoria) ---")
    for i, entrada in enumerate(mejores_por_categoria, 1):
        p = entrada['producto']
        cat = entrada['categoria']['nombre']
        tipo_cat = entrada['categoria']['tipo']
        marca_flag = " [marca prio]" if obtener_prioridad_marca(p['titulo']) else ""
        en_ultimas = " [cat. reciente]" if cat in ultimas_categorias else ""
        log.info(
            "  %d. [%s] %s... | %.0f%% dto | cat: %s (%s)%s%s",
            i, p['asin'], p['titulo'][:40], p['descuento'], cat, tipo_cat, marca_flag, en_ultimas
        )

    # Evitar repetir categorias de las ultimas 4 publicaciones
    mejor_oferta = None
    categorias_excluidas_repeticion = []  # En PS no excluimos ninguna categoria de repeticion

    for oferta in mejores_por_categoria:
        nombre_categoria = oferta['categoria']['nombre']
        if nombre_categoria not in ultimas_categorias or nombre_categoria in categorias_excluidas_repeticion:
            mejor_oferta = oferta
            break

    if mejor_oferta is None:
        log.info(
            "Todas las categorias candidatas estan en el historial reciente [%s], "
            "publicando la mejor disponible igualmente",
            ", ".join(ultimas_categorias)
        )
        mejor_oferta = mejores_por_categoria[0]
    elif mejor_oferta != mejores_por_categoria[0]:
        primera_cat = mejores_por_categoria[0]['categoria']['nombre']
        log.info(
            "Anti-repeticion: la #1 global (%s) fue descartada porque su categoria '%s' "
            "aparece en las recientes [%s]. Se elige la siguiente valida.",
            mejores_por_categoria[0]['producto']['titulo'][:35],
            primera_cat,
            ", ".join(ultimas_categorias)
        )

    producto = mejor_oferta['producto']
    categoria = mejor_oferta['categoria']

    log.info("")
    log.info(">>> OFERTA SELECCIONADA PARA PUBLICAR:")
    log.info("    Titulo:    %s", producto['titulo'])
    log.info("    Categoria: %s | Descuento: %.0f%%", categoria['nombre'], producto['descuento'])
    log.info("    Precio:    %s (antes: %s)", producto['precio'], producto.get('precio_anterior', 'N/A'))
    log.info("    ASIN:      %s | Valoraciones: %d | Ventas: %d",
             producto['asin'], producto['valoraciones'], producto['ventas'])
    log.info("    URL:       %s", producto['url'])

    # Formatear mensaje
    mensaje = format_telegram_message(producto, categoria)

    # Enviar a Telegram (con foto si disponible)
    if producto['imagen']:
        log.debug("    Enviando con foto: %s", producto['imagen'])
        exito = send_telegram_photo(producto['imagen'], mensaje)
    else:
        log.debug("    Enviando sin foto (no disponible)")
        exito = send_telegram_message(mensaje)

    ofertas_publicadas = 0
    if exito:
        posted_deals[producto['asin']] = datetime.now().isoformat()
        # Añadir categoria al inicio de la lista y mantener solo las ultimas 4
        ultimas_categorias.insert(0, categoria['nombre'])
        ultimas_categorias = ultimas_categorias[:4]
        log.debug("Historial de categorias actualizado: %s", ", ".join(ultimas_categorias))

        # Si es categoria con verificacion de titulos, guardar el titulo
        if categoria['nombre'] in CATEGORIAS_VERIFICAR_TITULOS:
            ultimos_titulos.insert(0, producto['titulo'])
            ultimos_titulos = ultimos_titulos[:4]
            log.debug("Titulo guardado en anti-similitud (total: %d)", len(ultimos_titulos))

        # Si es categoria con limite semanal, guardar el timestamp
        if categoria['nombre'] in CATEGORIAS_LIMITE_SEMANAL:
            categorias_semanales[categoria['nombre']] = datetime.now().isoformat()
            log.debug("Timestamp de limite semanal actualizado para categoria '%s'", categoria['nombre'])

        ofertas_publicadas = 1
    else:
        log.error("Fallo al enviar a Telegram, no se guarda el ASIN en el historial")

    # Guardar ofertas publicadas, ultimas categorias y titulos
    # En DEV_MODE no se escribe para no contaminar el historial de produccion
    if DEV_MODE:
        log.info("DEV_MODE: historial no guardado (posted_ps_deals.json sin cambios)")
    else:
        save_posted_deals(posted_deals, ultimas_categorias, ultimos_titulos, categorias_semanales)

    log.info("")
    log.info("=" * 60)
    log.info("FIN - %s oferta publicada en Telegram", ofertas_publicadas)
    log.info("=" * 60)

    return ofertas_publicadas


def main(modo_continuo=False):
    """
    Funcion principal.
    - modo_continuo=False: ejecuta una vez y termina (para cron)
    - modo_continuo=True: ejecuta cada 15 minutos en bucle infinito
    """
    if modo_continuo:
        log.info("Modo continuo activado - Ejecutando cada 15 minutos (Ctrl+C para detener)")
        while True:
            try:
                buscar_y_publicar_ofertas()
                log.info("Proxima ejecucion en 15 minutos...")
                log.info("-" * 60)
                time.sleep(900)  # 15 minutos = 900 segundos
            except KeyboardInterrupt:
                log.info("Detenido por el usuario (Ctrl+C)")
                break
    else:
        # Ejecutar una sola vez (ideal para cron)
        buscar_y_publicar_ofertas()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Buscador de ofertas PS4/PS5 en Amazon.es')
    parser.add_argument('--dev', action='store_true', help='Modo desarrollo: publica en canal de pruebas y no modifica el JSON de produccion')
    parser.add_argument('--continuo', '-c', action='store_true', help='Ejecuta en bucle cada 15 minutos')
    args = parser.parse_args()

    if args.dev:
        globals()['DEV_MODE'] = True
        log.info("CLI: DEV_MODE activado (canal de pruebas, JSON de prod intacto)")

    main(modo_continuo=args.continuo)
