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
import html
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

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
    agrupar_variantes,
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

# Archivo para guardar preórdenes ya publicadas (ventana separada de 48h)
POSTED_PS_PRERESERVAS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posted_ps_prereservas.json")

# Límite de 48 horas para no repetir el mismo preorden
LIMITE_PRERESERVAS_HORAS = 48

# Máximo de preórdenes a publicar por ciclo
MAX_PRERESERVAS_POR_CICLO = 3


def _effective_token():
    return DEV_TELEGRAM_PS_BOT_TOKEN if DEV_MODE and DEV_TELEGRAM_PS_BOT_TOKEN else TELEGRAM_PS_BOT_TOKEN


def _effective_chat_id():
    return DEV_TELEGRAM_PS_CHAT_ID if DEV_MODE and DEV_TELEGRAM_PS_CHAT_ID else TELEGRAM_PS_CHAT_ID

# Categorias que requieren verificacion de titulos similares
# (para evitar publicar el mismo tipo de producto repetidamente)
CATEGORIAS_VERIFICAR_TITULOS = ["Juegos PS5", "Juegos PS4"]

# Categorias que solo se publican una vez por semana (no aplica en PS)
CATEGORIAS_LIMITE_SEMANAL = []

# Límite de 3 días para cualquier accesorio (solo una categoría de accesorios cada 3 días)
LIMITE_ACCESORIOS_DIAS = 3

# Límite global de 7 días entre publicaciones (videojuegos o accesorios)
LIMITE_GLOBAL_DIAS = 7

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

# Categorias de preórdenes (búsqueda semántica)
# Nota: Las URLs buscan "próximos lanzamientos" y productos con señales de preorden
# en el HTML (disponible el, próximamente, preventa, etc.)
CATEGORIAS_PRERESERVAS = [
    {"nombre": "Próximos PS5", "emoji": "⏰", "url": "/s?k=juegos+ps5+proximamente"},
    {"nombre": "Próximos PS4", "emoji": "⏰", "url": "/s?k=juegos+ps4+proximamente"},
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
    Carga las ofertas publicadas (ultimas 4 dias/96h) desde un archivo JSON.
    Retorna tupla: (dict_ofertas, ultimas_categorias, ultimos_titulos, categorias_semanales)
    """
    return _load_posted_deals_core(POSTED_PS_DEALS_FILE, horas_ventana=96)


def save_posted_deals(deals_dict, ultimas_categorias=None, ultimos_titulos=None, categorias_semanales=None):
    """Guarda el diccionario de ofertas publicadas en un archivo JSON."""
    return _save_posted_deals_core(deals_dict, POSTED_PS_DEALS_FILE, ultimas_categorias, ultimos_titulos, categorias_semanales)


def load_posted_prereservas():
    """
    Carga las preórdenes publicadas (ultimas 48h) desde un archivo JSON.
    Retorna: dict de ASINs -> timestamps
    """
    return _load_posted_deals_core(POSTED_PS_PRERESERVAS_FILE, horas_ventana=LIMITE_PRERESERVAS_HORAS)[0]


def save_posted_prereservas(deals_dict):
    """Guarda el diccionario de preórdenes publicadas en un archivo JSON."""
    return _save_posted_deals_core(deals_dict, POSTED_PS_PRERESERVAS_FILE)


def _es_prereserva_item(item_html):
    """
    Detecta si un item de búsqueda de Amazon es un preorden o próximo lanzamiento.
    Busca patrones de:
    - Disponibilidad futura: "disponible el", "próximamente", "próxima semana"
    - Preorden: "preventa", "pre-orden", "preorder", "reservar"
    - Fechas futuras: referencias a meses (febrero, marzo, etc.) o años (2026, 2027)
    """
    try:
        texto = item_html.get_text(strip=True).lower()
    except (AttributeError, TypeError):
        return False

    # Indicadores de preorden/próximo lanzamiento
    indicadores_preorden = [
        'disponible el ',
        'disponible a partir',
        'próximamente',
        'próxima',
        'pronto disponible',
        'preventa',
        'pre-orden',
        'preorden',
        'preorder',
        'reservar',
        'reserva',
        'en reserva',
        'fecha de lanzamiento',
        'lanzamiento',
        'nuevo lanzamiento',
    ]

    # Si contiene indicador de preorden, es preorden
    if any(ind in texto for ind in indicadores_preorden):
        # Pero filtrar falsos positivos como "sin bono de reserva"
        if 'sin bono' in texto or 'no recomendada' in texto:
            # Aquí estamos en el título/descripción normal, probablemente falso positivo
            # Solo aceptar si hay un indicador fuerte adicional
            if not any(ind in texto for ind in ['disponible el', 'próximamente', 'pronto disponible', 'fecha de lanzamiento']):
                return False
        return True

    return False


def format_prereserva_message(producto, categoria):
    """Formatea un preorden para enviarlo a Telegram."""
    titulo = html.escape(producto['titulo'])
    precio = producto['precio']
    url = html.escape(producto['url'])
    emoji = categoria.get('emoji', '⏰')
    plataforma = categoria.get('nombre', '').upper()

    message = f"{emoji} <b>PRÓXIMO LANZAMIENTO {plataforma}</b> {emoji}\n\n"
    message += f"📦 <b>{titulo}</b>\n\n"
    if precio and precio != "N/A":
        message += f"💰 Precio de reserva: <b>{precio}</b>\n\n"
    message += f'🛒 <a href="{url}">Reservar en Amazon</a>'
    return message


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
    tres_dias = timedelta(days=LIMITE_ACCESORIOS_DIAS)
    siete_dias = timedelta(days=LIMITE_GLOBAL_DIAS)

    # Verificar límite global de 7 días entre publicaciones
    ultima_pub_global_str = categorias_semanales.get("_ultima_publicacion_global")
    if ultima_pub_global_str:
        try:
            ultima_pub_global = datetime.fromisoformat(ultima_pub_global_str)
            tiempo_transcurrido = now - ultima_pub_global
            if tiempo_transcurrido < siete_dias:
                dias_restantes = (siete_dias - tiempo_transcurrido).days + 1
                log.info(
                    "LÍMITE GLOBAL: última publicación el %s (hace %d días, faltan ~%d días). No se publica.",
                    ultima_pub_global.strftime('%d/%m %H:%M'), tiempo_transcurrido.days, dias_restantes
                )
                log.info("=" * 60)
                return 0
        except (ValueError, TypeError):
            pass

    # Verificar si se publicó un accesorio en los últimos 3 días
    accesorios_bloqueados = False
    ultima_pub_accesorio_str = categorias_semanales.get("_accesorios_ultima_pub")
    if ultima_pub_accesorio_str:
        try:
            ultima_pub_accesorio = datetime.fromisoformat(ultima_pub_accesorio_str)
            tiempo_transcurrido = now - ultima_pub_accesorio
            if tiempo_transcurrido < tres_dias:
                accesorios_bloqueados = True
                dias_restantes = (tres_dias - tiempo_transcurrido).days + 1
                log.info(
                    "Límite de 3 días para accesorios: última publicación de accesorio el %s (hace %d días, faltan ~%d días)",
                    ultima_pub_accesorio.strftime('%d/%m %H:%M'), tiempo_transcurrido.days, dias_restantes
                )
        except (ValueError, TypeError):
            pass

    # Recopilar la mejor oferta de cada categoria
    mejores_por_categoria = []
    mejores_videojuegos = []  # Separar videojuegos para priorizarlos

    for categoria in CATEGORIAS_PS:
        log.info("")
        log.info("--- Categoria: %s ---", categoria['nombre'])

        # Verificar límite de 3 días para accesorios
        if accesorios_bloqueados and categoria['tipo'] == 'accesorio':
            log.info("  SALTADA por límite de 3 días para accesorios")
            continue

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

    # Agrupar variantes (ej: FIFA 26 PS4 + FIFA 26 PS5 → un solo grupo)
    mejores_por_categoria = agrupar_variantes(mejores_por_categoria)

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
        # Guardar también ASINs de variantes agrupadas para evitar republicarlas
        for variante in producto.get('variantes_adicionales', []):
            posted_deals[variante['asin']] = datetime.now().isoformat()
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

        # Si es un accesorio, guardar el timestamp de última publicación de accesorio
        if categoria['tipo'] == 'accesorio':
            categorias_semanales["_accesorios_ultima_pub"] = datetime.now().isoformat()
            log.debug("Timestamp de límite de 3 días para accesorios actualizado")

        # Guardar timestamp de última publicación global
        categorias_semanales["_ultima_publicacion_global"] = datetime.now().isoformat()
        log.debug("Timestamp de límite global de 7 días actualizado")

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


def buscar_prereservas_ps():
    """
    Busca juegos en preorden para PS4/PS5 y publica hasta MAX_PRERESERVAS_POR_CICLO.
    Respeta el límite global de 7 días compartido con las ofertas normales.
    """
    if not _effective_token() or not _effective_chat_id():
        return 0

    log.info("=" * 60)
    log.info("INICIO BÚSQUEDA PRERESERVAS PS4/PS5")
    log.info("=" * 60)

    # Cargar estado de offers para verificar límite global de 7 días
    if DEV_MODE:
        posted_deals, _, _, categorias_semanales = {}, [], [], {}
    else:
        posted_deals, _, _, categorias_semanales = load_posted_deals()

    # Verificar límite global de 7 días
    now = datetime.now()
    siete_dias = timedelta(days=LIMITE_GLOBAL_DIAS)
    ultima_pub_global_str = categorias_semanales.get("_ultima_publicacion_global")
    if ultima_pub_global_str:
        try:
            ultima_pub_global = datetime.fromisoformat(ultima_pub_global_str)
            if now - ultima_pub_global < siete_dias:
                dias_restantes = (siete_dias - (now - ultima_pub_global)).days + 1
                log.info("LÍMITE GLOBAL activo (faltan ~%d días). Sin prereservas.", dias_restantes)
                log.info("=" * 60)
                return 0
        except (ValueError, TypeError):
            pass

    # Cargar ASINs de prereservas publicadas (ventana 48h)
    if DEV_MODE:
        posted_prereservas = {}
    else:
        posted_prereservas = load_posted_prereservas()
    posted_prereservas_asins = set(posted_prereservas.keys())

    # Recopilar candidatos de todas las URLs de búsqueda de preórdenes
    candidatos = []
    for categoria in CATEGORIAS_PRERESERVAS:
        url = BASE_URL + categoria['url']
        log.info("Buscando preórdenes: %s", categoria['nombre'])
        html_content = obtener_pagina(url)
        if not html_content:
            log.warning("  No se pudo obtener la página, saltando")
            continue

        soup = BeautifulSoup(html_content, 'html.parser')
        items = soup.select('[data-component-type="s-search-result"]')

        log.info("  Encontrados %d items, verificando si son preórdenes...", len(items))
        items_descartados = 0
        for item in items[:20]:
            asin = item.get('data-asin', '')
            if not asin or asin in posted_prereservas_asins:
                continue
            if not _es_prereserva_item(item):
                items_descartados += 1
                # DEBUG: mostrar texto del item para investigar por qué se descarta
                texto_item = item.get_text(strip=True)[:100]
                log.debug("    [DESCARTADO] ASIN %s: %s...", asin, texto_item)
                continue

            # Extraer datos básicos del producto del item individual
            # Convertir el item BeautifulSoup a string para que extraer_productos_busqueda lo procese
            productos = extraer_productos_busqueda(str(item))
            if productos:
                producto = productos[0]
                candidatos.append({'producto': producto, 'categoria': categoria})
                log.info("    [PREORDEN] %s (ASIN: %s)", producto['titulo'][:50], asin)

        if items_descartados > 0:
            log.info("  %d items descartados por no tener señales de preorden", items_descartados)

    if not candidatos:
        log.info("No hay candidatos de preórdenes en este ciclo")
        log.info("=" * 60)
        return 0

    # Ordenar por popularidad (valoraciones + ventas como proxy)
    candidatos.sort(
        key=lambda x: (x['producto']['valoraciones'], x['producto']['ventas']),
        reverse=True
    )

    log.info("")
    log.info("--- Top candidatos de preórdenes (ordenados por popularidad) ---")
    for i, entrada in enumerate(candidatos[:MAX_PRERESERVAS_POR_CICLO], 1):
        p = entrada['producto']
        log.info(
            "  %d. %s... | %d vals | ASIN: %s",
            i, p['titulo'][:40], p['valoraciones'], p['asin']
        )

    # Publicar hasta MAX_PRERESERVAS_POR_CICLO
    publicadas = 0
    nuevos_asins = {}
    for entrada in candidatos[:MAX_PRERESERVAS_POR_CICLO]:
        producto = entrada['producto']
        categoria = entrada['categoria']
        mensaje = format_prereserva_message(producto, categoria)

        log.info("Publicando preorden: %s (ASIN: %s)", producto['titulo'][:50], producto['asin'])

        if producto['imagen']:
            exito = send_telegram_photo(producto['imagen'], mensaje)
        else:
            exito = send_telegram_message(mensaje)

        if exito:
            nuevos_asins[producto['asin']] = datetime.now().isoformat()
            publicadas += 1

    if publicadas > 0:
        # Guardar ASINs de prereservas publicadas
        posted_prereservas.update(nuevos_asins)
        if not DEV_MODE:
            save_posted_prereservas(posted_prereservas)

        # Actualizar límite global de 7 días en posted_ps_deals.json
        categorias_semanales["_ultima_publicacion_global"] = datetime.now().isoformat()
        if not DEV_MODE:
            save_posted_deals(posted_deals, None, None, categorias_semanales)

    log.info("")
    log.info("=" * 60)
    log.info("FIN PRERESERVAS - %d publicadas", publicadas)
    log.info("=" * 60)

    return publicadas


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
                buscar_prereservas_ps()
                log.info("Proxima ejecucion en 15 minutos...")
                log.info("-" * 60)
                time.sleep(900)  # 15 minutos = 900 segundos
            except KeyboardInterrupt:
                log.info("Detenido por el usuario (Ctrl+C)")
                break
    else:
        # Ejecutar una sola vez (ideal para cron)
        buscar_y_publicar_ofertas()
        buscar_prereservas_ps()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Buscador de ofertas PS4/PS5 en Amazon.es')
    parser.add_argument('--dev', action='store_true', help='Modo desarrollo: publica en canal de pruebas y no modifica el JSON de produccion')
    parser.add_argument('--continuo', '-c', action='store_true', help='Ejecuta en bucle cada 15 minutos')
    args = parser.parse_args()

    if args.dev:
        globals()['DEV_MODE'] = True
        log.info("CLI: DEV_MODE activado (canal de pruebas, JSON de prod intacto)")

    main(modo_continuo=args.continuo)
