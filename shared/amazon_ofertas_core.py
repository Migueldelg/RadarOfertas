#!/usr/bin/env python3
"""
Funciones genéricas compartidas para los scripts de ofertas de Amazon.es.
Importar desde aquí en amazon_bebe_ofertas.py y amazon_ps_ofertas.py.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
import json
import os
import html
import logging
import logging.handlers
import sys
from datetime import datetime, timedelta

# --- Configuracion de Logging ---

def setup_logging(log_file):
    """Configura logging con rotacion diaria y limpieza automatica de logs mayores a 5 dias.

    Args:
        log_file: Ruta absoluta al archivo de log (cada canal usa el suyo propio).
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)-7s] %(message)s',
        datefmt='%d/%m/%Y %H:%M:%S'
    )

    # Handler de consola: solo si hay terminal interactiva (evita duplicados cuando
    # cron/launchd redirige stdout al mismo fichero de log)
    if sys.stdout.isatty() or os.getenv('CI'):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Handler de archivo con rotacion a medianoche, conserva 5 dias
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when='midnight',
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


# --- Configuracion de Amazon ---
PARTNER_TAG = "juegosenoferta-21"
BASE_URL = "https://www.amazon.es"

# Headers para simular un navegador moderno
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'Cache-Control': 'max-age=0',
}

# Sesion global para mantener cookies
session = requests.Session()

log = logging.getLogger(__name__)


def load_posted_deals(filepath):
    """
    Carga las ofertas publicadas (ultimas 48h) desde un archivo JSON.
    Retorna tupla: (dict_ofertas, ultimas_categorias, ultimos_titulos, categorias_semanales)
    """
    if not os.path.exists(filepath):
        log.info("No existe historial previo de ofertas publicadas, empezando desde cero")
        return {}, [], [], {}

    with open(filepath, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            log.warning("El archivo de historial esta corrupto, ignorando y empezando desde cero")
            return {}, [], [], {}

    if not isinstance(data, dict):
        log.warning("Formato de historial inesperado, ignorando y empezando desde cero")
        return {}, [], [], {}

    # Extraer ultimas categorias publicadas (lista de hasta 4)
    ultimas_categorias = data.pop('_ultimas_categorias', [])
    # Compatibilidad con formato anterior (string simple)
    if not ultimas_categorias:
        ultima_cat = data.pop('_ultima_categoria', None)
        ultimas_categorias = [ultima_cat] if ultima_cat else []

    # Extraer ultimos titulos publicados (para verificacion de similitud)
    ultimos_titulos = data.pop('_ultimos_titulos', [])

    # Extraer timestamps de ultima publicacion de categorias con limite semanal
    categorias_semanales = data.pop('_categorias_semanales', {})

    recent_deals = {}
    expired_count = 0
    now = datetime.now()
    forty_eight_hours_ago = now - timedelta(hours=48)

    for deal_id, timestamp_str in data.items():
        try:
            post_time = datetime.fromisoformat(timestamp_str)
            if post_time > forty_eight_hours_ago:
                recent_deals[deal_id] = timestamp_str
            else:
                expired_count += 1
        except (ValueError, TypeError):
            continue

    log.info(
        "Historial cargado: %d ASINs en ventana de 48h (ignorados %d expirados)",
        len(recent_deals), expired_count
    )
    if ultimas_categorias:
        log.info("Ultimas categorias publicadas (anti-repeticion): %s", ", ".join(ultimas_categorias))
    if ultimos_titulos:
        log.debug("Ultimos titulos guardados para anti-similitud: %d titulos", len(ultimos_titulos))
    if categorias_semanales:
        for cat, ts in categorias_semanales.items():
            try:
                ultima = datetime.fromisoformat(ts)
                dias = (now - ultima).days
                log.debug("  Categoria '%s' con limite semanal: ultima publicacion hace %d dias (%s)", cat, dias, ultima.strftime('%d/%m %H:%M'))
            except (ValueError, TypeError):
                pass

    return recent_deals, ultimas_categorias, ultimos_titulos, categorias_semanales


def save_posted_deals(deals_dict, filepath, ultimas_categorias=None, ultimos_titulos=None, categorias_semanales=None):
    """Guarda el diccionario de ofertas publicadas en un archivo JSON."""
    data = deals_dict.copy()
    if ultimas_categorias:
        data['_ultimas_categorias'] = ultimas_categorias
    if ultimos_titulos:
        data['_ultimos_titulos'] = ultimos_titulos
    if categorias_semanales:
        data['_categorias_semanales'] = categorias_semanales
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)


def normalizar_titulo(titulo):
    """Normaliza un titulo para comparacion: minusculas, sin palabras comunes."""
    palabras_ignorar = {
        'de', 'para', 'con', 'sin', 'el', 'la', 'los', 'las', 'un', 'una',
        'unos', 'unas', 'y', 'o', 'a', 'en', 'del', 'al', 'bebe', 'bebé',
        'pack', 'set', 'unidades', 'meses', 'años', 'mese', 'ano',
    }
    titulo_lower = titulo.lower()
    # Extraer solo palabras alfanumericas
    palabras = re.findall(r'\b[a-záéíóúñü]+\b', titulo_lower)
    # Filtrar palabras comunes y muy cortas
    palabras_clave = [p for p in palabras if p not in palabras_ignorar and len(p) > 2]
    return set(palabras_clave)


def titulos_similares(titulo1, titulo2, umbral=0.5):
    """
    Compara dos titulos y determina si son similares.
    Retorna True si comparten mas del umbral (50%) de palabras clave.
    """
    palabras1 = normalizar_titulo(titulo1)
    palabras2 = normalizar_titulo(titulo2)

    if not palabras1 or not palabras2:
        return False

    # Calcular similitud: palabras en comun / total de palabras unicas
    comunes = palabras1 & palabras2
    total = palabras1 | palabras2

    if not total:
        return False

    similitud = len(comunes) / len(total)
    return similitud >= umbral


def titulo_similar_a_recientes(titulo, ultimos_titulos):
    """Verifica si un titulo es similar a alguno de los titulos recientes."""
    for titulo_reciente in ultimos_titulos:
        if titulos_similares(titulo, titulo_reciente):
            return True
    return False


def obtener_prioridad_marca(titulo, marcas):
    """
    Extrae la marca del titulo y retorna su prioridad según la lista de marcas.
    - 1: marca prioritaria encontrada
    - 0: sin marca prioritaria
    """
    titulo_lower = titulo.lower()
    for marca in marcas:
        if marca.lower() in titulo_lower:
            return 1
    return 0


def send_telegram_message(message, token, chat_id):
    """Envia un mensaje al canal de Telegram especificado."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        log.info("Mensaje enviado a Telegram correctamente (solo texto)")
        return True
    except requests.exceptions.RequestException as e:
        log.error("Error al enviar mensaje a Telegram: %s", e)
        return False


def send_telegram_photo(photo_url, caption, token, chat_id):
    """Envia una foto con caption al canal de Telegram especificado."""
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {
        'chat_id': chat_id,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        log.info("Mensaje enviado a Telegram correctamente (con foto)")
        return True
    except requests.exceptions.RequestException as e:
        log.warning("Error al enviar foto a Telegram (%s), reintentando solo con texto...", e)
        return send_telegram_message(caption, token, chat_id)


def format_telegram_message(producto, categoria):
    """Formatea un producto para enviarlo a Telegram."""
    titulo = html.escape(producto['titulo'])
    precio = producto['precio']
    precio_anterior = producto.get('precio_anterior')
    url = producto['url']
    emoji = categoria.get('emoji', '🛍️')
    categoria_nombre = categoria.get('nombre', 'Bebe')

    # Calcular descuento si hay precio anterior
    descuento_texto = ""
    if precio_anterior:
        try:
            precio_num = float(precio.replace('€', '').replace(',', '.').strip())
            precio_ant_num = float(precio_anterior.replace('€', '').replace(',', '.').strip())
            descuento = ((precio_ant_num - precio_num) / precio_ant_num) * 100
            descuento_texto = f" (-{descuento:.0f}%)"
        except:
            descuento_texto = ""

    message = f"{emoji} <b>OFERTA {categoria_nombre.upper()}</b> {emoji}\n\n"
    message += f"📦 <b>{titulo}</b>\n\n"

    if precio_anterior:
        message += f"💰 Precio: <s>{precio_anterior}</s> → <b>{precio}</b>{descuento_texto}\n"
    else:
        message += f"💰 Precio: <b>{precio}</b>\n"

    message += f"\n🛒 <a href='{url}'>Ver en Amazon</a>"

    return message


def obtener_pagina(url, reintentos=3):
    """Obtiene el contenido HTML de una pagina con reintentos."""
    headers = HEADERS.copy()
    headers['Referer'] = 'https://www.amazon.es/'

    for intento in range(reintentos):
        try:
            # Delay aleatorio más largo para parecer humano
            time.sleep(random.uniform(2, 4))
            response = session.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            if intento < reintentos - 1:
                wait_time = random.uniform(5, 10) * (intento + 1)
                log.warning(
                    "Error al obtener pagina (intento %d/%d): %s - Reintentando en %.0fs",
                    intento + 1, reintentos, e, wait_time
                )
                time.sleep(wait_time)
            else:
                log.error("Fallo definitivo al obtener pagina tras %d intentos: %s | URL: %s", reintentos, e, url)
                return None


def extraer_productos_busqueda(html_content):
    """Extrae productos de una pagina de busqueda de Amazon."""
    productos = []
    soup = BeautifulSoup(html_content, 'html.parser')
    items = soup.select('[data-component-type="s-search-result"]')

    for item in items[:20]:  # Mas productos para encontrar ofertas
        try:
            asin = item.get('data-asin', '')
            if not asin:
                continue

            titulo_elem = item.select_one('h2 a span') or item.select_one('h2 span')
            titulo = titulo_elem.get_text(strip=True) if titulo_elem else "Sin titulo"

            precio = "N/A"
            precio_elem = item.select_one('.a-price .a-offscreen')
            if precio_elem:
                precio = precio_elem.get_text(strip=True)

            precio_anterior = None
            precio_anterior_elem = item.select_one('.a-price[data-a-strike="true"] .a-offscreen')
            if precio_anterior_elem:
                precio_anterior = precio_anterior_elem.get_text(strip=True)

            # Calcular descuento
            descuento = 0
            if precio_anterior and precio != "N/A":
                try:
                    precio_num = float(precio.replace('€', '').replace(',', '.').strip())
                    precio_ant_num = float(precio_anterior.replace('€', '').replace(',', '.').strip())
                    if precio_ant_num > 0:
                        descuento = ((precio_ant_num - precio_num) / precio_ant_num) * 100
                except:
                    descuento = 0

            # Extraer numero de valoraciones
            valoraciones = 0
            valoraciones_elem = item.select_one('.a-size-base.s-underline-text') or item.select_one('[aria-label*="estrellas"] + span')
            if valoraciones_elem:
                try:
                    val_text = valoraciones_elem.get_text(strip=True).replace('.', '').replace(',', '')
                    valoraciones = int(re.sub(r'[^\d]', '', val_text) or 0)
                except:
                    valoraciones = 0

            # Extraer ventas (ej: "10K+ comprados el mes pasado")
            ventas = 0
            ventas_elem = item.select_one('.a-size-base.a-color-secondary')
            if ventas_elem:
                ventas_text = ventas_elem.get_text(strip=True).lower()
                if 'compra' in ventas_text or 'vendido' in ventas_text:
                    try:
                        match = re.search(r'(\d+)[kK]?\+?', ventas_text)
                        if match:
                            ventas = int(match.group(1))
                            if 'k' in ventas_text.lower():
                                ventas *= 1000
                    except:
                        ventas = 0

            imagen = ""
            img_elem = item.select_one('img.s-image')
            if img_elem:
                imagen = img_elem.get('src', '')

            url_afiliado = f"{BASE_URL}/dp/{asin}?tag={PARTNER_TAG}"

            productos.append({
                'asin': asin,
                'titulo': titulo[:100] + "..." if len(titulo) > 100 else titulo,
                'precio': precio,
                'precio_anterior': precio_anterior,
                'descuento': descuento,
                'valoraciones': valoraciones,
                'ventas': ventas,
                'imagen': imagen,
                'url': url_afiliado,
                'tiene_oferta': precio_anterior is not None
            })

        except Exception:
            continue

    return productos
