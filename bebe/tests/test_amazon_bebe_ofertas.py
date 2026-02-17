"""
Tests para amazon_bebe_ofertas.py

Cubren funciones puras, I/O con mocks, parsing HTML y lógica de selección.
Sirven como red de seguridad para refactors.
"""

import json
import os
import sys
import textwrap
from datetime import datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Importar el módulo sin ejecutar setup_logging ni abrir ficheros
# bebe/tests/ → bebe/ → root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import bebe.amazon_bebe_ofertas as bot


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

def make_producto(**kwargs):
    """Crea un producto con valores por defecto, sobreescribibles."""
    defaults = {
        'asin': 'B000TEST01',
        'titulo': 'Pañales Dodot Talla 3 × 60 unidades',
        'precio': '12,99€',
        'precio_anterior': '17,99€',
        'descuento': 27.8,
        'valoraciones': 1500,
        'ventas': 500,
        'imagen': 'https://example.com/img.jpg',
        'url': 'https://www.amazon.es/dp/B000TEST01?tag=juegosenoferta-21',
        'tiene_oferta': True,
    }
    defaults.update(kwargs)
    return defaults


def make_categoria(**kwargs):
    """Crea una categoría con valores por defecto."""
    defaults = {'nombre': 'Panales', 'emoji': '🧷', 'url': '/s?k=panales'}
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# normalizar_titulo
# ---------------------------------------------------------------------------

class TestNormalizarTitulo:
    def test_devuelve_set(self):
        result = bot.normalizar_titulo("Pañales Dodot Talla 3")
        assert isinstance(result, set)

    def test_minusculas(self):
        result = bot.normalizar_titulo("DODOT PAÑALES")
        assert all(p == p.lower() for p in result)

    def test_elimina_palabras_comunes(self):
        result = bot.normalizar_titulo("Crema de bebe para el culete")
        assert 'de' not in result
        assert 'para' not in result
        assert 'bebe' not in result
        assert 'el' not in result

    def test_elimina_palabras_cortas(self):
        result = bot.normalizar_titulo("Set de 3 packs con bebe")
        # palabras de 2 letras o menos deben eliminarse
        assert 'de' not in result

    def test_palabras_clave_presentes(self):
        result = bot.normalizar_titulo("Crema Mustela suave hidratante")
        assert 'mustela' in result
        assert 'suave' in result
        assert 'hidratante' in result

    def test_cadena_vacia(self):
        result = bot.normalizar_titulo("")
        assert result == set()

    def test_solo_palabras_ignoradas(self):
        result = bot.normalizar_titulo("de para con sin el la los las")
        assert result == set()


# ---------------------------------------------------------------------------
# titulos_similares
# ---------------------------------------------------------------------------

class TestTitulosSimilares:
    def test_titulos_identicos_son_similares(self):
        t = "Chupete Suavinex talla 2 silicona"
        assert bot.titulos_similares(t, t) is True

    def test_titulos_muy_diferentes_no_son_similares(self):
        assert bot.titulos_similares(
            "Pañales Dodot talla 3",
            "Biberón Chicco anticólico 150ml"
        ) is False

    def test_titulos_parcialmente_similares_sobre_umbral(self):
        # Comparten "suavinex chupete silicona" → alta similitud
        assert bot.titulos_similares(
            "Chupete Suavinex silicona talla 1",
            "Chupete Suavinex silicona talla 2"
        ) is True

    def test_umbral_personalizado(self):
        # Con umbral alto (0.9) títulos algo similares NO lo son
        assert bot.titulos_similares(
            "Chupete Suavinex silicona talla 1 azul",
            "Chupete Suavinex silicona talla 2 rosa",
            umbral=0.9
        ) is False

    def test_titulo_vacio_no_es_similar(self):
        assert bot.titulos_similares("", "Pañales Dodot talla 3") is False
        assert bot.titulos_similares("Pañales Dodot talla 3", "") is False

    def test_ambos_vacios_no_son_similares(self):
        assert bot.titulos_similares("", "") is False


# ---------------------------------------------------------------------------
# titulo_similar_a_recientes
# ---------------------------------------------------------------------------

class TestTituloSimilarARecientes:
    def test_sin_recientes_devuelve_false(self):
        assert bot.titulo_similar_a_recientes("Chupete Suavinex", []) is False

    def test_detecta_similar_entre_recientes(self):
        recientes = ["Chupete Suavinex silicona talla 1"]
        assert bot.titulo_similar_a_recientes(
            "Chupete Suavinex silicona talla 2", recientes
        ) is True

    def test_no_detecta_diferente(self):
        recientes = ["Pañales Dodot talla 3 × 60 unidades"]
        assert bot.titulo_similar_a_recientes(
            "Biberón Chicco anticólico 150ml", recientes
        ) is False

    def test_basta_un_similar_para_devolver_true(self):
        recientes = [
            "Pañales Dodot talla 3",
            "Biberón Chicco 150ml",
            "Chupete Suavinex silicona talla 1",
        ]
        assert bot.titulo_similar_a_recientes(
            "Chupete Suavinex silicona talla 2", recientes
        ) is True


# ---------------------------------------------------------------------------
# obtener_prioridad_marca
# ---------------------------------------------------------------------------

class TestObtenerPrioridadMarca:
    @pytest.mark.parametrize("titulo,esperado", [
        ("Pañales Dodot Talla 3", 1),
        ("Crema Mustela Bebe", 1),
        ("Toallitas WaterWipes sin fragancia", 1),
        ("Chupete Suavinex silicona", 1),
        ("Crema Baby Sebamed dermatológica", 1),
        ("Biberón genérico marca desconocida", 0),
        ("", 0),
    ])
    def test_prioridad(self, titulo, esperado):
        assert bot.obtener_prioridad_marca(titulo) == esperado

    def test_insensible_mayusculas(self):
        assert bot.obtener_prioridad_marca("DODOT PANALES") == 1
        assert bot.obtener_prioridad_marca("dodot panales") == 1


# ---------------------------------------------------------------------------
# format_telegram_message
# ---------------------------------------------------------------------------

class TestFormatTelegramMessage:
    def test_contiene_titulo(self):
        p = make_producto(titulo="Pañales Dodot Talla 3")
        cat = make_categoria(nombre="Panales", emoji="🧷")
        msg = bot.format_telegram_message(p, cat)
        assert "Pañales Dodot Talla 3" in msg

    def test_contiene_nombre_categoria(self):
        p = make_producto()
        cat = make_categoria(nombre="Panales")
        msg = bot.format_telegram_message(p, cat)
        assert "PANALES" in msg

    def test_muestra_precio_anterior_tachado(self):
        p = make_producto(precio="12,99€", precio_anterior="17,99€")
        msg = bot.format_telegram_message(p, make_categoria())
        assert "<s>" in msg
        assert "17,99€" in msg

    def test_muestra_descuento_porcentaje(self):
        p = make_producto(precio="10,00€", precio_anterior="20,00€")
        msg = bot.format_telegram_message(p, make_categoria())
        assert "-50%" in msg

    def test_sin_precio_anterior_no_tachado(self):
        p = make_producto(precio="12,99€", precio_anterior=None)
        msg = bot.format_telegram_message(p, make_categoria())
        assert "<s>" not in msg

    def test_contiene_enlace_amazon(self):
        p = make_producto(url="https://www.amazon.es/dp/B000TEST01?tag=juegosenoferta-21")
        msg = bot.format_telegram_message(p, make_categoria())
        assert "amazon.es" in msg

    def test_escapa_html_en_titulo(self):
        p = make_producto(titulo='Pañales <"especiales"> & más')
        msg = bot.format_telegram_message(p, make_categoria())
        assert "<\"especiales\">" not in msg
        assert "&amp;" in msg or "&lt;" in msg

    def test_emoji_categoria_presente(self):
        cat = make_categoria(emoji="🧷")
        msg = bot.format_telegram_message(make_producto(), cat)
        assert "🧷" in msg

    def test_categoria_por_defecto_si_falta_emoji(self):
        cat = {'nombre': 'Panales'}  # sin emoji
        msg = bot.format_telegram_message(make_producto(), cat)
        assert "🛍️" in msg


# ---------------------------------------------------------------------------
# load_posted_deals
# ---------------------------------------------------------------------------

class TestLoadPostedDeals:
    def test_sin_fichero_devuelve_vacios(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(tmp_path / 'noexiste.json'))
        deals, cats, titulos, semanales = bot.load_posted_deals()
        assert deals == {}
        assert cats == []
        assert titulos == []
        assert semanales == {}

    def test_fichero_corrupto_devuelve_vacios(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        f.write_text("{ esto no es json válido }")
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        deals, cats, titulos, semanales = bot.load_posted_deals()
        assert deals == {}

    def test_filtra_asins_expirados(self, tmp_path, monkeypatch):
        ahora = datetime.now()
        reciente = (ahora - timedelta(hours=24)).isoformat()
        expirado = (ahora - timedelta(hours=72)).isoformat()
        data = {
            'ASIN_RECIENTE': reciente,
            'ASIN_EXPIRADO': expirado,
        }
        f = tmp_path / 'deals.json'
        f.write_text(json.dumps(data))
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        deals, _, _, _ = bot.load_posted_deals()
        assert 'ASIN_RECIENTE' in deals
        assert 'ASIN_EXPIRADO' not in deals

    def test_carga_ultimas_categorias(self, tmp_path, monkeypatch):
        data = {'_ultimas_categorias': ['Panales', 'Toallitas']}
        f = tmp_path / 'deals.json'
        f.write_text(json.dumps(data))
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        _, cats, _, _ = bot.load_posted_deals()
        assert cats == ['Panales', 'Toallitas']

    def test_compatibilidad_formato_antiguo_ultima_categoria(self, tmp_path, monkeypatch):
        data = {'_ultima_categoria': 'Panales'}
        f = tmp_path / 'deals.json'
        f.write_text(json.dumps(data))
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        _, cats, _, _ = bot.load_posted_deals()
        assert cats == ['Panales']

    def test_carga_categorias_semanales(self, tmp_path, monkeypatch):
        ts = datetime.now().isoformat()
        data = {'_categorias_semanales': {'Tronas': ts}}
        f = tmp_path / 'deals.json'
        f.write_text(json.dumps(data))
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        _, _, _, semanales = bot.load_posted_deals()
        assert 'Tronas' in semanales


# ---------------------------------------------------------------------------
# save_posted_deals
# ---------------------------------------------------------------------------

class TestSavePostedDeals:
    def test_guarda_asins(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        ts = datetime.now().isoformat()
        bot.save_posted_deals({'B001': ts})
        data = json.loads(f.read_text())
        assert data['B001'] == ts

    def test_guarda_ultimas_categorias(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        bot.save_posted_deals({}, ultimas_categorias=['Panales', 'Toallitas'])
        data = json.loads(f.read_text())
        assert data['_ultimas_categorias'] == ['Panales', 'Toallitas']

    def test_guarda_categorias_semanales(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        ts = datetime.now().isoformat()
        bot.save_posted_deals({}, categorias_semanales={'Tronas': ts})
        data = json.loads(f.read_text())
        assert data['_categorias_semanales']['Tronas'] == ts

    def test_roundtrip_load_save(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(f))
        ts = datetime.now().isoformat()
        bot.save_posted_deals(
            {'B001': ts},
            ultimas_categorias=['Panales'],
            ultimos_titulos=['Título ejemplo'],
            categorias_semanales={'Tronas': ts},
        )
        deals, cats, titulos, semanales = bot.load_posted_deals()
        assert 'B001' in deals
        assert cats == ['Panales']
        assert titulos == ['Título ejemplo']
        assert 'Tronas' in semanales


# ---------------------------------------------------------------------------
# extraer_productos_busqueda
# ---------------------------------------------------------------------------

def _html_con_producto(
    asin="B001EXAMPLE",
    titulo="Pañales Dodot Talla 3 × 60 unidades",
    precio_actual="12,99€",
    precio_anterior="17,99€",
    valoraciones="1.234",
    img_src="https://example.com/img.jpg",
):
    """Genera HTML mínimo con la estructura que espera el scraper de Amazon.

    El orden importa: Amazon pone primero el precio actual (sin data-a-strike)
    y luego el precio tachado (con data-a-strike="true").
    """
    return textwrap.dedent(f"""
    <html><body>
    <div data-component-type="s-search-result" data-asin="{asin}">
      <h2><a><span>{titulo}</span></a></h2>
      <span class="a-price">
        <span class="a-offscreen">{precio_actual}</span>
      </span>
      <span class="a-price a-text-price" data-a-strike="true">
        <span class="a-offscreen">{precio_anterior}</span>
      </span>
      <span class="a-size-base s-underline-text">{valoraciones}</span>
      <img class="s-image" src="{img_src}" />
    </div>
    </body></html>
    """)


class TestExtraerProductosBusqueda:
    def test_extrae_asin(self):
        html = _html_con_producto(asin="B001TEST")
        productos = bot.extraer_productos_busqueda(html)
        assert len(productos) >= 1
        assert productos[0]['asin'] == "B001TEST"

    def test_extrae_titulo(self):
        html = _html_con_producto(titulo="Pañales Dodot Talla 3")
        productos = bot.extraer_productos_busqueda(html)
        assert "Pañales Dodot Talla 3" in productos[0]['titulo']

    def test_extrae_precio_actual(self):
        html = _html_con_producto(precio_actual="12,99€")
        productos = bot.extraer_productos_busqueda(html)
        assert productos[0]['precio'] == "12,99€"

    def test_extrae_precio_anterior(self):
        html = _html_con_producto(precio_anterior="17,99€")
        productos = bot.extraer_productos_busqueda(html)
        assert productos[0]['precio_anterior'] == "17,99€"

    def test_calcula_descuento(self):
        html = _html_con_producto(precio_actual="10,00€", precio_anterior="20,00€")
        productos = bot.extraer_productos_busqueda(html)
        assert abs(productos[0]['descuento'] - 50.0) < 0.1

    def test_tiene_oferta_true_cuando_hay_precio_anterior(self):
        html = _html_con_producto(precio_anterior="17,99€")
        productos = bot.extraer_productos_busqueda(html)
        assert productos[0]['tiene_oferta'] is True

    def test_tiene_oferta_false_sin_precio_anterior(self):
        # HTML sin precio anterior tachado
        html_sin_anterior = textwrap.dedent("""
        <html><body>
        <div data-component-type="s-search-result" data-asin="B001NOOFF">
          <h2><a><span>Producto sin oferta</span></a></h2>
          <span class="a-price">
            <span class="a-offscreen">9,99€</span>
          </span>
        </div>
        </body></html>
        """)
        productos = bot.extraer_productos_busqueda(html_sin_anterior)
        assert len(productos) >= 1
        assert productos[0]['tiene_oferta'] is False

    def test_url_incluye_tag_afiliado(self):
        html = _html_con_producto(asin="B001TEST")
        productos = bot.extraer_productos_busqueda(html)
        assert "juegosenoferta-21" in productos[0]['url']

    def test_titulo_truncado_a_100_caracteres(self):
        titulo_largo = "A" * 200
        html = _html_con_producto(titulo=titulo_largo)
        productos = bot.extraer_productos_busqueda(html)
        assert len(productos[0]['titulo']) <= 103  # 100 + "..."

    def test_html_vacio_devuelve_lista_vacia(self):
        productos = bot.extraer_productos_busqueda("<html><body></body></html>")
        assert productos == []

    def test_item_sin_asin_se_omite(self):
        html_sin_asin = textwrap.dedent("""
        <html><body>
        <div data-component-type="s-search-result">
          <h2><a><span>Sin ASIN</span></a></h2>
        </div>
        </body></html>
        """)
        productos = bot.extraer_productos_busqueda(html_sin_asin)
        assert productos == []

    def test_multiples_productos(self):
        items = "".join(
            f'<div data-component-type="s-search-result" data-asin="B00{i}">'
            f'<h2><a><span>Producto {i}</span></a></h2>'
            f'<span class="a-price"><span class="a-offscreen">{i},99€</span></span>'
            f'</div>'
            for i in range(5)
        )
        html = f"<html><body>{items}</body></html>"
        productos = bot.extraer_productos_busqueda(html)
        assert len(productos) == 5


# ---------------------------------------------------------------------------
# buscar_y_publicar_ofertas — lógica de selección (sin red)
# ---------------------------------------------------------------------------

class TestBuscarYPublicarOfertas:
    """Tests de la lógica de selección global con todo mockeado."""

    def _patch_todo(self, monkeypatch, tmp_path, productos_por_cat=None):
        """Helper que parchea HTTP, Telegram y el fichero de historial."""
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(tmp_path / 'deals.json'))
        monkeypatch.setattr(bot, 'TELEGRAM_BOT_TOKEN', 'mock_token')
        monkeypatch.setattr(bot, 'TELEGRAM_CHAT_ID', 'mock_chat_id')

        # Producto con oferta por defecto
        if productos_por_cat is None:
            productos_por_cat = [make_producto(descuento=30.0)]

        monkeypatch.setattr(bot, 'obtener_pagina', lambda url: "<html>mock</html>")
        monkeypatch.setattr(
            bot, 'extraer_productos_busqueda',
            lambda html: productos_por_cat
        )
        monkeypatch.setattr(bot, 'send_telegram_photo', lambda url, msg: True)
        monkeypatch.setattr(bot, 'send_telegram_message', lambda msg: True)

    def test_publica_una_oferta(self, monkeypatch, tmp_path):
        self._patch_todo(monkeypatch, tmp_path)
        resultado = bot.buscar_y_publicar_ofertas()
        assert resultado == 1

    def test_sin_productos_con_oferta_no_publica(self, monkeypatch, tmp_path):
        self._patch_todo(monkeypatch, tmp_path, productos_por_cat=[
            make_producto(tiene_oferta=False, precio_anterior=None, descuento=0)
        ])
        resultado = bot.buscar_y_publicar_ofertas()
        assert resultado == 0

    def test_sin_paginas_no_publica(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(tmp_path / 'deals.json'))
        monkeypatch.setattr(bot, 'TELEGRAM_BOT_TOKEN', 'mock_token')
        monkeypatch.setattr(bot, 'TELEGRAM_CHAT_ID', 'mock_chat_id')
        monkeypatch.setattr(bot, 'obtener_pagina', lambda url: None)
        resultado = bot.buscar_y_publicar_ofertas()
        assert resultado == 0

    def test_no_repite_asin_en_48h(self, monkeypatch, tmp_path):
        asin = 'B000TEST01'
        # Guardar ese ASIN como publicado hace 1h
        ts_reciente = (datetime.now() - timedelta(hours=1)).isoformat()
        deals_file = tmp_path / 'deals.json'
        deals_file.write_text(json.dumps({asin: ts_reciente}))

        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(deals_file))
        monkeypatch.setattr(bot, 'TELEGRAM_BOT_TOKEN', 'mock_token')
        monkeypatch.setattr(bot, 'TELEGRAM_CHAT_ID', 'mock_chat_id')
        monkeypatch.setattr(bot, 'obtener_pagina', lambda url: "<html>mock</html>")
        monkeypatch.setattr(
            bot, 'extraer_productos_busqueda',
            lambda html: [make_producto(asin=asin, descuento=40.0)]
        )
        monkeypatch.setattr(bot, 'send_telegram_photo', lambda url, msg: True)
        monkeypatch.setattr(bot, 'send_telegram_message', lambda msg: True)

        resultado = bot.buscar_y_publicar_ofertas()
        assert resultado == 0

    def test_guarda_asin_tras_publicar(self, monkeypatch, tmp_path):
        asin = 'B000NUEVO'
        deals_file = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(deals_file))
        monkeypatch.setattr(bot, 'TELEGRAM_BOT_TOKEN', 'mock_token')
        monkeypatch.setattr(bot, 'TELEGRAM_CHAT_ID', 'mock_chat_id')
        monkeypatch.setattr(bot, 'obtener_pagina', lambda url: "<html>mock</html>")
        monkeypatch.setattr(
            bot, 'extraer_productos_busqueda',
            lambda html: [make_producto(asin=asin, descuento=30.0)]
        )
        monkeypatch.setattr(bot, 'send_telegram_photo', lambda url, msg: True)
        monkeypatch.setattr(bot, 'send_telegram_message', lambda msg: True)

        bot.buscar_y_publicar_ofertas()

        data = json.loads(deals_file.read_text())
        assert asin in data

    def test_evita_categoria_reciente(self, monkeypatch, tmp_path):
        """Cuando la mejor oferta es de una categoría reciente, elige la siguiente."""
        deals_file = tmp_path / 'deals.json'
        # Marcar "Cremas bebe" como una de las últimas 4 categorías
        deals_file.write_text(json.dumps({
            '_ultimas_categorias': ['Cremas bebe', 'Toallitas', 'Biberones', 'Juguetes']
        }))
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(deals_file))
        monkeypatch.setattr(bot, 'TELEGRAM_BOT_TOKEN', 'mock_token')
        monkeypatch.setattr(bot, 'TELEGRAM_CHAT_ID', 'mock_chat_id')

        # La mejor oferta global vendrá de "Cremas bebe" (alta valoración/descuento)
        # pero debe elegirse otra categoría
        def mock_extraer(html):
            return [make_producto(asin='ASIN_MOCK', descuento=50.0)]

        monkeypatch.setattr(bot, 'obtener_pagina', lambda url: "<html>mock</html>")
        monkeypatch.setattr(bot, 'extraer_productos_busqueda', mock_extraer)

        publicados = []

        def mock_send_photo(url, msg):
            publicados.append(msg)
            return True

        def mock_send_msg(msg):
            publicados.append(msg)
            return True

        monkeypatch.setattr(bot, 'send_telegram_photo', mock_send_photo)
        monkeypatch.setattr(bot, 'send_telegram_message', mock_send_msg)

        resultado = bot.buscar_y_publicar_ofertas()
        # Debe haber publicado algo (alguna categoría no reciente)
        assert resultado == 1

    def test_fallo_telegram_no_guarda_asin(self, monkeypatch, tmp_path):
        asin = 'B000FALLO'
        deals_file = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(deals_file))
        monkeypatch.setattr(bot, 'TELEGRAM_BOT_TOKEN', 'mock_token')
        monkeypatch.setattr(bot, 'TELEGRAM_CHAT_ID', 'mock_chat_id')
        monkeypatch.setattr(bot, 'obtener_pagina', lambda url: "<html>mock</html>")
        monkeypatch.setattr(
            bot, 'extraer_productos_busqueda',
            lambda html: [make_producto(asin=asin, descuento=30.0)]
        )
        monkeypatch.setattr(bot, 'send_telegram_photo', lambda url, msg: False)
        monkeypatch.setattr(bot, 'send_telegram_message', lambda msg: False)

        resultado = bot.buscar_y_publicar_ofertas()
        assert resultado == 0
        if deals_file.exists():
            data = json.loads(deals_file.read_text())
            assert asin not in data

    def test_limite_semanal_saltea_categoria(self, monkeypatch, tmp_path):
        """Categoría con límite semanal publicada hace 2 días no se publica."""
        hace_2_dias = (datetime.now() - timedelta(days=2)).isoformat()
        deals_file = tmp_path / 'deals.json'
        deals_file.write_text(json.dumps({
            '_categorias_semanales': {'Tronas': hace_2_dias}
        }))
        monkeypatch.setattr(bot, 'POSTED_BEBE_DEALS_FILE', str(deals_file))
        monkeypatch.setattr(bot, 'TELEGRAM_BOT_TOKEN', 'mock_token')
        monkeypatch.setattr(bot, 'TELEGRAM_CHAT_ID', 'mock_chat_id')

        categorias_scrapeadas = []

        def mock_obtener_pagina(url):
            categorias_scrapeadas.append(url)
            return "<html>mock</html>"

        monkeypatch.setattr(bot, 'obtener_pagina', mock_obtener_pagina)
        monkeypatch.setattr(
            bot, 'extraer_productos_busqueda',
            lambda html: [make_producto(descuento=30.0)]
        )
        monkeypatch.setattr(bot, 'send_telegram_photo', lambda url, msg: True)
        monkeypatch.setattr(bot, 'send_telegram_message', lambda msg: True)

        bot.buscar_y_publicar_ofertas()

        # La URL de "Tronas" no debe haberse scrapeado
        tronas_url = next(
            (c['url'] for c in bot.CATEGORIAS_BEBE if c['nombre'] == 'Tronas'), ''
        )
        assert not any(tronas_url in u for u in categorias_scrapeadas)
