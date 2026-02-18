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


def load_posted_deals(filepath, horas_ventana=48):
    """
    Carga las ofertas publicadas desde un archivo JSON, filtrando por ventana de tiempo.

    Args:
        filepath: Ruta al archivo JSON de ofertas publicadas
        horas_ventana: Número de horas a considerar como "reciente" (default 48)

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
    cutoff_time = now - timedelta(hours=horas_ventana)

    for deal_id, timestamp_str in data.items():
        try:
            post_time = datetime.fromisoformat(timestamp_str)
            if post_time > cutoff_time:
                recent_deals[deal_id] = timestamp_str
            else:
                expired_count += 1
        except (ValueError, TypeError):
            continue

    log.info(
        "Historial cargado: %d ASINs en ventana de %dh (ignorados %d expirados)",
        len(recent_deals), horas_ventana, expired_count
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


# Constante para detectar variantes (colores, tamaños, etc.)
PALABRAS_VARIANTE = {
    'rojo', 'roja', 'azul', 'verde', 'rosa', 'negro', 'negra',
    'blanco', 'blanca', 'amarillo', 'amarilla', 'naranja',
    'morado', 'morada', 'violeta', 'gris', 'beige', 'marron',
    'dorado', 'dorada', 'plateado', 'plateada', 'lila', 'turquesa',
    'mini', 'maxi',
}


def son_variantes(titulo1, titulo2):
    """
    Determina si dos productos son variantes del mismo producto base.
    Dos productos son variantes si sus títulos normalizados comparten
    una base común y solo difieren en palabras de variante (colores, etc.).

    Nota: identificadores de plataforma como PS4/PS5 son automáticamente
    invisibles porque el regex de normalizar_titulo extrae solo letras.
    """
    palabras1 = normalizar_titulo(titulo1)
    palabras2 = normalizar_titulo(titulo2)

    if not palabras1 or not palabras2:
        return False

    comunes = palabras1 & palabras2
    if not comunes:
        return False

    solo_en_1 = palabras1 - palabras2
    solo_en_2 = palabras2 - palabras1

    return solo_en_1.issubset(PALABRAS_VARIANTE) and solo_en_2.issubset(PALABRAS_VARIANTE)


def agrupar_variantes(mejores_por_categoria):
    """
    Agrupa productos variantes en la lista de mejores por categoría.

    Input/Output: lista de dicts {'producto': ..., 'categoria': ...}
    El representante es el de mayor descuento (desempate: valoraciones).
    El dict del representante recibe 'variantes_adicionales': lista de
    {asin, titulo, url, precio, precio_anterior, descuento}.
    Se usa .copy() para no mutar el dict original.
    """
    if not mejores_por_categoria:
        return []

    n = len(mejores_por_categoria)
    padre = list(range(n))

    def encontrar(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unir(x, y):
        px, py = encontrar(x), encontrar(y)
        if px != py:
            padre[px] = py

    for i in range(n):
        t_i = mejores_por_categoria[i]['producto']['titulo']
        for j in range(i + 1, n):
            t_j = mejores_por_categoria[j]['producto']['titulo']
            if son_variantes(t_i, t_j):
                unir(i, j)
                log.info(
                    "Variantes detectadas: '%s' ↔ '%s'",
                    t_i[:40], t_j[:40]
                )

    grupos = {}
    for i in range(n):
        grupos.setdefault(encontrar(i), []).append(i)

    resultado = []
    for indices in grupos.values():
        if len(indices) == 1:
            resultado.append(mejores_por_categoria[indices[0]])
            continue

        indices_ord = sorted(
            indices,
            key=lambda i: (
                mejores_por_categoria[i]['producto']['descuento'],
                mejores_por_categoria[i]['producto']['valoraciones'],
            ),
            reverse=True,
        )
        idx_rep = indices_ord[0]
        entrada_rep = mejores_por_categoria[idx_rep]
        producto_rep = entrada_rep['producto'].copy()

        producto_rep['variantes_adicionales'] = [
            {
                'asin': mejores_por_categoria[k]['producto']['asin'],
                'titulo': mejores_por_categoria[k]['producto']['titulo'],
                'url': mejores_por_categoria[k]['producto']['url'],
                'precio': mejores_por_categoria[k]['producto']['precio'],
                'precio_anterior': mejores_por_categoria[k]['producto'].get('precio_anterior'),
                'descuento': mejores_por_categoria[k]['producto']['descuento'],
            }
            for k in indices_ord[1:]
        ]

        log.info(
            "Grupo de variantes: representante '%s' + %d variante(s): %s",
            producto_rep['titulo'][:35],
            len(producto_rep['variantes_adicionales']),
            ", ".join(v['titulo'][:25] for v in producto_rep['variantes_adicionales']),
        )
        resultado.append({'producto': producto_rep, 'categoria': entrada_rep['categoria']})

    return resultado


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
        # Usar data en lugar de json para mayor compatibilidad con Telegram
        response = requests.post(url, data=payload)
        response.raise_for_status()
        log.info("Mensaje enviado a Telegram correctamente (solo texto)")
        return True
    except requests.exceptions.RequestException as e:
        log.critical("❌ ERROR CRÍTICO: No se pudo enviar mensaje a Telegram: %s", e)
        raise  # Relanzar la excepción para que el workflow falle


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
        # Usar data en lugar de json para mayor compatibilidad con Telegram
        response = requests.post(url, data=payload)
        response.raise_for_status()
        log.info("Mensaje enviado a Telegram correctamente (con foto)")
        return True
    except requests.exceptions.RequestException as e:
        log.warning("⚠️  Error al enviar foto a Telegram (%s), reintentando solo con texto...", e)
        try:
            return send_telegram_message(caption, token, chat_id)
        except requests.exceptions.RequestException as e2:
            log.critical("❌ ERROR CRÍTICO: Falló foto Y mensaje de texto. Error foto: %s | Error texto: %s", e, e2)
            raise  # Relanzar para marcar el workflow como error


def format_telegram_message(producto, categoria):
    """Formatea un producto para enviarlo a Telegram."""
    titulo = html.escape(producto['titulo'])
    precio = producto['precio']
    precio_anterior = producto.get('precio_anterior')
    url = html.escape(producto['url'])  # Escapar URL para HTML válido
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

    variantes = producto.get('variantes_adicionales', [])

    message = f"{emoji} <b>OFERTA {categoria_nombre.upper()}</b> {emoji}\n\n"
    message += f"📦 <b>{titulo}</b>\n\n"

    # Si hay variantes, mostrar todas las opciones de forma paralela
    if variantes:
        # Función auxiliar para extraer identificador de variante (ej: 'PS5', 'Azul')
        def extraer_variante_id(titulo_completo, titulo_base):
            """
            Extrae identificador que diferencia las variantes.
            Busca plataformas (PS5, PS4, etc.) o colores no presentes en la base.
            """
            # Buscar primero palabras con patrón PSX, GenX, etc. (letra+números)
            # Usar patrón más específico: 1-2 letras seguidas de números
            palabras_plataforma = re.findall(r'\b([a-záéíóúñü]{1,3}\d+)\b', titulo_completo, re.IGNORECASE)
            if palabras_plataforma:
                return palabras_plataforma[0].upper()

            # Fallback: extraer palabras del título que no estén en la base
            palabras_base = normalizar_titulo(titulo_base)
            palabras_completo = normalizar_titulo(titulo_completo)
            diferencia = palabras_completo - palabras_base
            if diferencia:
                return list(diferencia)[0].upper()

            return ""

        # Producto principal
        if precio_anterior:
            message += f"💰 <a href=\"{url}\"><b>{precio}</b></a> <s>{precio_anterior}</s>{descuento_texto}\n"
        else:
            message += f"💰 <a href=\"{url}\"><b>{precio}</b></a>\n"

        # Variantes adicionales (todas con link y su identificador)
        for variante in variantes:
            var_url = html.escape(variante['url'])
            var_titulo = variante['titulo']
            var_precio = variante.get('precio', '')
            var_precio_anterior = variante.get('precio_anterior')
            var_desc = variante.get('descuento', 0)
            var_desc_texto = f" (-{int(var_desc)}%)" if var_desc else ""

            # Extraer identificador de esta variante
            var_id_label = extraer_variante_id(var_titulo, titulo)
            var_id_texto = f" ({var_id_label})" if var_id_label else ""

            if var_precio_anterior:
                message += f"💰 <a href=\"{var_url}\"><b>{var_precio}</b></a> <s>{var_precio_anterior}</s>{var_desc_texto}{var_id_texto}\n"
            else:
                message += f"💰 <a href=\"{var_url}\"><b>{var_precio}</b></a>{var_id_texto}\n"
    else:
        # Sin variantes: formato original
        if precio_anterior:
            message += f"💰 Precio: <s>{precio_anterior}</s> → <b>{precio}</b>{descuento_texto}\n"
        else:
            message += f"💰 Precio: <b>{precio}</b>\n"

        message += f'\n🛒 <a href="{url}">Ver en Amazon</a>'

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
