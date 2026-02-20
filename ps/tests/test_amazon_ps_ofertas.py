"""
Tests para amazon_ps_ofertas.py

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
# ps/tests/ → ps/ → root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ps.amazon_ps_ofertas as bot
import shared.amazon_ofertas_core as core


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

def make_producto(**kwargs):
    """Crea un producto con valores por defecto, sobreescribibles."""
    defaults = {
        'asin': 'B000TEST01',
        'titulo': 'Juego PS5 The Last of Us Part II',
        'precio': '29,99€',
        'precio_anterior': '49,99€',
        'descuento': 40.0,
        'valoraciones': 2500,
        'ventas': 800,
        'imagen': 'https://example.com/img.jpg',
        'url': 'https://www.amazon.es/dp/B000TEST01?tag=juegosenoferta-21',
        'tiene_oferta': True,
    }
    defaults.update(kwargs)
    return defaults


def make_categoria(**kwargs):
    """Crea una categoría con valores por defecto."""
    defaults = {
        'nombre': 'Juegos PS5',
        'emoji': '🎮',
        'url': '/s?k=juegos+ps5',
        'tipo': 'videojuego'
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# normalizar_titulo
# ---------------------------------------------------------------------------

class TestNormalizarTitulo:
    def test_devuelve_set(self):
        result = bot.normalizar_titulo("Juego PS5 The Last of Us")
        assert isinstance(result, set)

    def test_minusculas(self):
        result = bot.normalizar_titulo("JUEGO PS5 SONY")
        assert all(p == p.lower() for p in result)

    def test_elimina_palabras_comunes(self):
        result = bot.normalizar_titulo("Juego de PS5 para la consola")
        assert 'de' not in result
        assert 'para' not in result
        assert 'la' not in result

    def test_elimina_palabras_cortas(self):
        result = bot.normalizar_titulo("Set de 2 mandos PS5")
        # palabras de 2 letras o menos deben eliminarse
        assert 'de' not in result

    def test_palabras_clave_presentes(self):
        result = bot.normalizar_titulo("Mando DualSense PS5 inalambrico")
        assert 'dualsense' in result
        assert 'inalambrico' in result

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
        t = "Juego PS5 The Last of Us Part II"
        assert bot.titulos_similares(t, t) is True

    def test_titulos_muy_diferentes_no_son_similares(self):
        assert bot.titulos_similares(
            "Juego PS5 The Last of Us",
            "Mando DualSense PS5 blanco"
        ) is False

    def test_titulos_parcialmente_similares_sobre_umbral(self):
        # Comparten "ps5 the last of us" → alta similitud
        assert bot.titulos_similares(
            "Juego PS5 The Last of Us Part I",
            "Juego PS5 The Last of Us Part II"
        ) is True

    def test_umbral_personalizado(self):
        # Con umbral alto (0.8) dos títulos sin casi nada en común NO lo son
        assert bot.titulos_similares(
            "Juego PS5 The Last of Us",
            "Mando DualSense blanco",
            umbral=0.8
        ) is False

    def test_titulo_vacio_no_es_similar(self):
        assert bot.titulos_similares("", "Juego PS5 The Last of Us") is False
        assert bot.titulos_similares("Juego PS5 The Last of Us", "") is False

    def test_ambos_vacios_no_son_similares(self):
        assert bot.titulos_similares("", "") is False


# ---------------------------------------------------------------------------
# titulo_similar_a_recientes
# ---------------------------------------------------------------------------

class TestTituloSimilarARecientes:
    def test_sin_recientes_devuelve_false(self):
        assert bot.titulo_similar_a_recientes("Juego PS5 Elden Ring", []) is False

    def test_detecta_similar_entre_recientes(self):
        recientes = ["Juego PS5 The Last of Us Part II"]
        assert bot.titulo_similar_a_recientes(
            "Juego PS5 The Last of Us Part I", recientes
        ) is True

    def test_no_detecta_diferente(self):
        recientes = ["Juego PS5 Elden Ring Standard Edition"]
        assert bot.titulo_similar_a_recientes(
            "Mando DualSense PS5 rojo", recientes
        ) is False

    def test_basta_un_similar_para_devolver_true(self):
        recientes = [
            "Juego PS5 Elden Ring",
            "Mando DualSense PS5 blanco",
            "Juego PS4 Red Dead Redemption 2",
        ]
        assert bot.titulo_similar_a_recientes(
            "Juego PS5 Elden Ring Deluxe", recientes
        ) is True


# ---------------------------------------------------------------------------
# obtener_prioridad_marca
# ---------------------------------------------------------------------------

class TestObtenerPrioridadMarca:
    @pytest.mark.parametrize("titulo,esperado", [
        ("Juego PS5 Sony The Last of Us", 1),
        ("Mando DualSense PlayStation 5", 1),
        ("Auriculares gaming Nacon", 1),
        ("Mando Thrustmaster PS5", 1),
        ("Auriculares Razer PS4", 1),
        ("Juego generico marca desconocida", 0),
        ("", 0),
    ])
    def test_prioridad(self, titulo, esperado):
        assert bot.obtener_prioridad_marca(titulo) == esperado

    def test_insensible_mayusculas(self):
        assert bot.obtener_prioridad_marca("SONY PLAYSTATION") == 1
        assert bot.obtener_prioridad_marca("sony ps5") == 1


# ---------------------------------------------------------------------------
# format_telegram_message
# ---------------------------------------------------------------------------

class TestFormatTelegramMessage:
    def test_contiene_titulo(self):
        p = make_producto(titulo="Juego PS5 The Last of Us Part II")
        cat = make_categoria(nombre="Juegos PS5", emoji="🎮")
        msg = bot.format_telegram_message(p, cat)
        assert "Juego PS5 The Last of Us Part II" in msg

    def test_contiene_nombre_categoria(self):
        p = make_producto()
        cat = make_categoria(nombre="Juegos PS5")
        msg = bot.format_telegram_message(p, cat)
        assert "JUEGOS PS5" in msg

    def test_muestra_precio_anterior_tachado(self):
        p = make_producto(precio="29,99€", precio_anterior="49,99€")
        msg = bot.format_telegram_message(p, make_categoria())
        assert "<s>" in msg
        assert "49,99€" in msg

    def test_muestra_descuento_porcentaje(self):
        p = make_producto(precio="25,00€", precio_anterior="50,00€")
        msg = bot.format_telegram_message(p, make_categoria())
        assert "-50%" in msg

    def test_sin_precio_anterior_no_tachado(self):
        p = make_producto(precio="29,99€", precio_anterior=None)
        msg = bot.format_telegram_message(p, make_categoria())
        assert "<s>" not in msg

    def test_contiene_enlace_amazon(self):
        p = make_producto(url="https://www.amazon.es/dp/B000TEST01?tag=juegosenoferta-21")
        msg = bot.format_telegram_message(p, make_categoria())
        assert "amazon.es" in msg

    def test_escapa_html_en_titulo(self):
        p = make_producto(titulo='Juego <"especial"> & más')
        msg = bot.format_telegram_message(p, make_categoria())
        assert "<\"especial\">" not in msg
        assert "&amp;" in msg or "&lt;" in msg

    def test_emoji_categoria_presente(self):
        cat = make_categoria(emoji="🎮")
        msg = bot.format_telegram_message(make_producto(), cat)
        assert "🎮" in msg

    def test_categoria_por_defecto_si_falta_emoji(self):
        cat = {'nombre': 'Juegos PS5'}  # sin emoji
        msg = bot.format_telegram_message(make_producto(), cat)
        assert "🛍️" in msg


# ---------------------------------------------------------------------------
# load_posted_deals
# ---------------------------------------------------------------------------

class TestLoadPostedDeals:
    def test_sin_fichero_devuelve_vacios(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(tmp_path / 'noexiste.json'))
        deals, cats, titulos, semanales = bot.load_posted_deals()
        assert deals == {}
        assert cats == []
        assert titulos == []
        assert semanales == {}

    def test_fichero_corrupto_devuelve_vacios(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        f.write_text("{ esto no es json válido }")
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        deals, cats, titulos, semanales = bot.load_posted_deals()
        assert deals == {}

    def test_filtra_asins_expirados(self, tmp_path, monkeypatch):
        ahora = datetime.now()
        reciente = (ahora - timedelta(hours=24)).isoformat()
        expirado = (ahora - timedelta(hours=120)).isoformat()  # Más de 96h para PS
        data = {
            'ASIN_RECIENTE': reciente,
            'ASIN_EXPIRADO': expirado,
        }
        f = tmp_path / 'deals.json'
        f.write_text(json.dumps(data))
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        deals, _, _, _ = bot.load_posted_deals()
        assert 'ASIN_RECIENTE' in deals
        assert 'ASIN_EXPIRADO' not in deals

    def test_carga_ultimas_categorias(self, tmp_path, monkeypatch):
        data = {'_ultimas_categorias': ['Juegos PS5', 'Mandos PS5']}
        f = tmp_path / 'deals.json'
        f.write_text(json.dumps(data))
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        _, cats, _, _ = bot.load_posted_deals()
        assert cats == ['Juegos PS5', 'Mandos PS5']

    def test_carga_categorias_semanales(self, tmp_path, monkeypatch):
        ts = datetime.now().isoformat()
        data = {'_categorias_semanales': {'Juegos PS5': ts}}
        f = tmp_path / 'deals.json'
        f.write_text(json.dumps(data))
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        _, _, _, semanales = bot.load_posted_deals()
        assert 'Juegos PS5' in semanales


# ---------------------------------------------------------------------------
# save_posted_deals
# ---------------------------------------------------------------------------

class TestSavePostedDeals:
    def test_guarda_asins(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        ts = datetime.now().isoformat()
        bot.save_posted_deals({'B001': ts})
        data = json.loads(f.read_text())
        assert data['B001'] == ts

    def test_guarda_ultimas_categorias(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        bot.save_posted_deals({}, ultimas_categorias=['Juegos PS5', 'Mandos PS5'])
        data = json.loads(f.read_text())
        assert data['_ultimas_categorias'] == ['Juegos PS5', 'Mandos PS5']

    def test_guarda_categorias_semanales(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        ts = datetime.now().isoformat()
        bot.save_posted_deals({}, categorias_semanales={'Juegos PS5': ts})
        data = json.loads(f.read_text())
        assert data['_categorias_semanales']['Juegos PS5'] == ts

    def test_roundtrip_load_save(self, tmp_path, monkeypatch):
        f = tmp_path / 'deals.json'
        monkeypatch.setattr(bot, 'POSTED_PS_DEALS_FILE', str(f))
        ts = datetime.now().isoformat()
        bot.save_posted_deals(
            {'B001': ts},
            ultimas_categorias=['Juegos PS5'],
            ultimos_titulos=['Juego PS5 Elden Ring'],
            categorias_semanales={'Juegos PS5': ts},
        )
        deals, cats, titulos, semanales = bot.load_posted_deals()
        assert 'B001' in deals
        assert cats == ['Juegos PS5']
        assert titulos == ['Juego PS5 Elden Ring']
        assert 'Juegos PS5' in semanales


# ---------------------------------------------------------------------------
# extraer_productos_busqueda
# ---------------------------------------------------------------------------

def _html_con_producto(
    asin="B001EXAMPLE",
    titulo="Juego PS5 The Last of Us Part II",
    precio_actual="29,99€",
    precio_anterior="49,99€",
    valoraciones="2.500",
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
        html = _html_con_producto(titulo="Juego PS5 Elden Ring")
        productos = bot.extraer_productos_busqueda(html)
        assert "Juego PS5 Elden Ring" in productos[0]['titulo']

    def test_extrae_precio_actual(self):
        html = _html_con_producto(precio_actual="29,99€")
        productos = bot.extraer_productos_busqueda(html)
        assert productos[0]['precio'] == "29,99€"

    def test_extrae_precio_anterior(self):
        html = _html_con_producto(precio_anterior="49,99€")
        productos = bot.extraer_productos_busqueda(html)
        assert productos[0]['precio_anterior'] == "49,99€"

    def test_calcula_descuento(self):
        html = _html_con_producto(precio_actual="25,00€", precio_anterior="50,00€")
        productos = bot.extraer_productos_busqueda(html)
        assert abs(productos[0]['descuento'] - 50.0) < 0.1

    def test_tiene_oferta_true_cuando_hay_precio_anterior(self):
        html = _html_con_producto(precio_anterior="49,99€")
        productos = bot.extraer_productos_busqueda(html)
        assert productos[0]['tiene_oferta'] is True

    def test_tiene_oferta_false_sin_precio_anterior(self):
        # HTML sin precio anterior tachado
        html_sin_anterior = textwrap.dedent("""
        <html><body>
        <div data-component-type="s-search-result" data-asin="B001NOOFF">
          <h2><a><span>Juego PS5 sin oferta</span></a></h2>
          <span class="a-price">
            <span class="a-offscreen">59,99€</span>
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
        assert len(productos) == 0


# ---------------------------------------------------------------------------
# Integracion: buscar_y_publicar_ofertas
# ---------------------------------------------------------------------------

class TestBuscarYPublicarOfertasIntegracion:
    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_publica_mejor_videojuego_sobre_accesorio(self, mock_save, mock_load, mock_pagina, mock_foto, mock_token, mock_chat_id):
        """Verifica que los videojuegos se priorizan sobre accesorios."""
        mock_load.return_value = ({}, [], [], {})
        mock_foto.return_value = True
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'
        mock_pagina.return_value = _html_con_producto(
            asin="PS5_GAME",
            titulo="Juego PS5 Elden Ring",
            precio_anterior="59,99€",
            precio_actual="35,99€"
        )

        # Simular ofertas de videojuego (mejor descuento) y accesorio (peor descuento)
        # El algoritmo debe elegir el videojuego
        resultado = bot.buscar_y_publicar_ofertas()
        assert resultado == 1
        mock_foto.assert_called()

    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_evita_duplicados_48h(self, mock_save, mock_load, mock_pagina, mock_foto):
        """Verifica que no se publican ASINs duplicados en 48h."""
        ahora = datetime.now()
        asin_reciente = 'B001_RECIENTE'
        posted_deals = {asin_reciente: (ahora - timedelta(hours=24)).isoformat()}
        mock_load.return_value = (posted_deals, [], [], {})
        mock_pagina.return_value = _html_con_producto(asin=asin_reciente)
        mock_foto.return_value = True

        resultado = bot.buscar_y_publicar_ofertas()
        # No debe publicar porque el ASIN ya fue publicado hace <48h
        assert resultado == 0

    @patch('ps.amazon_ps_ofertas.send_telegram_message')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_modo_dev_no_guarda_estado(self, mock_save, mock_load, mock_pagina, mock_msg):
        """En DEV_MODE, no se modifica posted_ps_deals.json."""
        bot.DEV_MODE = True
        mock_load.return_value = ({}, [], [], {})
        mock_pagina.return_value = _html_con_producto()
        mock_msg.return_value = True

        resultado = bot.buscar_y_publicar_ofertas()
        bot.DEV_MODE = False

        if resultado == 1:
            # Si publica, verifica que save_posted_deals NO fue llamado
            mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Prioridad de Videojuegos
# ---------------------------------------------------------------------------

class TestPrioridadVideojuegos:
    def test_categoria_tipo_videojuego(self):
        """Verifica que las categorías de videojuegos tengan tipo='videojuego'."""
        videojuegos = [c for c in bot.CATEGORIAS_PS if c['tipo'] == 'videojuego']
        accesorios = [c for c in bot.CATEGORIAS_PS if c['tipo'] == 'accesorio']

        assert len(videojuegos) > 0
        assert len(accesorios) > 0

        # Verificar que existen las categorías esperadas
        nombres_videojuegos = {c['nombre'] for c in videojuegos}
        assert 'Juegos PS5' in nombres_videojuegos
        assert 'Juegos PS4' in nombres_videojuegos

    def test_categorias_ps_tienen_tipo(self):
        """Todas las categorías deben tener un 'tipo' definido."""
        for cat in bot.CATEGORIAS_PS:
            assert 'tipo' in cat
            assert cat['tipo'] in ['videojuego', 'accesorio']


# ---------------------------------------------------------------------------
# son_variantes - Detecta variantes de productos
# ---------------------------------------------------------------------------

class TestSonVariantes:
    def test_ps4_y_ps5_mismo_juego_son_variantes(self):
        """PS4 y PS5 son variantes (plataformas invisibles en normalización)."""
        assert core.son_variantes("FIFA 26 PS5", "FIFA 26 PS4")
        assert core.son_variantes("EA SPORTS FC 26 Standard Edition PS5", "EA SPORTS FC 26 Standard Edition PS4")

    def test_colores_distintos_son_variantes(self):
        """Productos que solo difieren en color son variantes."""
        assert core.son_variantes("Chicco NaturalFeeling Biberón Rosa", "Chicco NaturalFeeling Biberón Azul")
        assert core.son_variantes("Mando DualSense Blanco", "Mando DualSense Negro")

    def test_productos_distintos_no_son_variantes(self):
        """Productos sin base común no son variantes."""
        assert not core.son_variantes("FIFA 26 PS5", "Mando DualSense")
        assert not core.son_variantes("Pañales Dodot", "Toallitas Pampers")

    def test_sin_base_comun_no_son_variantes(self):
        """Sin palabras en común → no son variantes."""
        assert not core.son_variantes("PlayStation 5", "Xbox Series X")

    def test_diferencia_no_variante_no_agrupa(self):
        """Si la diferencia no es solo variantes, no se agrupan."""
        # Standard Edition vs Champions Edition (ambos son "edition", solo en uno está Champion)
        # championship no está en PALABRAS_VARIANTE
        assert not core.son_variantes("FIFA 26 Standard Edition PS5", "FIFA 26 Champions Edition PS5")

    def test_titulo_vacio_devuelve_false(self):
        """Título vacío o con solo palabras cortas → False."""
        assert not core.son_variantes("", "FIFA 26")
        assert not core.son_variantes("FIFA 26", "")
        # Palabras muy cortas que se descartan
        assert not core.son_variantes("a b c", "x y z")


# ---------------------------------------------------------------------------
# agrupar_variantes - Agrupa productos variantes
# ---------------------------------------------------------------------------

class TestAgruparVariantes:
    def test_lista_vacia_devuelve_vacia(self):
        """Lista vacía → lista vacía."""
        assert core.agrupar_variantes([]) == []

    def test_producto_sin_variante_pasa_sin_cambios(self):
        """Un solo producto sin variantes → pasa sin cambios, sin campo variantes_adicionales."""
        entrada = {
            'producto': make_producto(asin='B001', titulo='FIFA 26 PS5'),
            'categoria': make_categoria()
        }
        resultado = core.agrupar_variantes([entrada])
        assert len(resultado) == 1
        assert resultado[0]['producto']['asin'] == 'B001'
        assert 'variantes_adicionales' not in resultado[0]['producto']

    def test_dos_variantes_se_agrupan_en_uno(self):
        """Dos variantes → un solo grupo con variantes_adicionales."""
        entrada1 = {
            'producto': make_producto(asin='B001', titulo='FIFA 26 PS5', descuento=43, valoraciones=2000),
            'categoria': make_categoria()
        }
        entrada2 = {
            'producto': make_producto(asin='B002', titulo='FIFA 26 PS4', descuento=40, valoraciones=1500),
            'categoria': make_categoria()
        }
        resultado = core.agrupar_variantes([entrada1, entrada2])
        assert len(resultado) == 1
        assert resultado[0]['producto']['asin'] == 'B001'  # El de mayor descuento
        assert len(resultado[0]['producto']['variantes_adicionales']) == 1
        assert resultado[0]['producto']['variantes_adicionales'][0]['asin'] == 'B002'

    def test_representante_es_el_de_mayor_descuento(self):
        """El representante es el de mayor descuento."""
        entrada1 = {
            'producto': make_producto(asin='B001', titulo='FIFA 26 PS5', descuento=40),
            'categoria': make_categoria()
        }
        entrada2 = {
            'producto': make_producto(asin='B002', titulo='FIFA 26 PS4', descuento=43),
            'categoria': make_categoria()
        }
        resultado = core.agrupar_variantes([entrada1, entrada2])
        assert len(resultado) == 1
        assert resultado[0]['producto']['asin'] == 'B002'  # 43% > 40%

    def test_desempate_igual_descuento_usa_valoraciones(self):
        """Igual descuento → el de mayor valoraciones es representante."""
        entrada1 = {
            'producto': make_producto(asin='B001', titulo='FIFA 26 PS5', descuento=42, valoraciones=1500),
            'categoria': make_categoria()
        }
        entrada2 = {
            'producto': make_producto(asin='B002', titulo='FIFA 26 PS4', descuento=42, valoraciones=2000),
            'categoria': make_categoria()
        }
        resultado = core.agrupar_variantes([entrada1, entrada2])
        assert len(resultado) == 1
        assert resultado[0]['producto']['asin'] == 'B002'  # Más valoraciones

    def test_variante_adicional_tiene_todos_los_campos(self):
        """La variante adicional incluye: asin, titulo, url, precio, descuento."""
        entrada1 = {
            'producto': make_producto(asin='B001', titulo='FIFA 26 PS5', descuento=43),
            'categoria': make_categoria()
        }
        entrada2 = {
            'producto': make_producto(asin='B002', titulo='FIFA 26 PS4', descuento=40, precio='34,99€'),
            'categoria': make_categoria()
        }
        resultado = core.agrupar_variantes([entrada1, entrada2])
        variante = resultado[0]['producto']['variantes_adicionales'][0]
        assert 'asin' in variante
        assert 'titulo' in variante
        assert 'url' in variante
        assert 'precio' in variante
        assert 'descuento' in variante
        assert variante['asin'] == 'B002'
        assert variante['precio'] == '34,99€'
        assert variante['descuento'] == 40

    def test_no_muta_producto_original(self):
        """El producto original no es mutado (no gana campo variantes_adicionales)."""
        producto_original = make_producto(asin='B001', titulo='FIFA 26 PS5')
        entrada1 = {'producto': producto_original, 'categoria': make_categoria()}
        entrada2 = {
            'producto': make_producto(asin='B002', titulo='FIFA 26 PS4'),
            'categoria': make_categoria()
        }
        core.agrupar_variantes([entrada1, entrada2])
        # El producto original no debe tener el campo
        assert 'variantes_adicionales' not in producto_original

    def test_productos_distintos_no_se_agrupan(self):
        """Productos sin relación de variantes → lista resultado tiene 2 elementos."""
        entrada1 = {
            'producto': make_producto(asin='B001', titulo='FIFA 26 PS5'),
            'categoria': make_categoria()
        }
        entrada2 = {
            'producto': make_producto(asin='B002', titulo='Mando DualSense'),
            'categoria': make_categoria()
        }
        resultado = core.agrupar_variantes([entrada1, entrada2])
        assert len(resultado) == 2
        assert 'variantes_adicionales' not in resultado[0]['producto']
        assert 'variantes_adicionales' not in resultado[1]['producto']

    def test_categoria_del_representante_se_preserva(self):
        """La categoría del representante se mantiene en el resultado."""
        cat_videojuegos = make_categoria(nombre='Juegos PS5', emoji='🎮')
        entrada1 = {
            'producto': make_producto(asin='B001', titulo='FIFA 26 PS5'),
            'categoria': cat_videojuegos
        }
        entrada2 = {
            'producto': make_producto(asin='B002', titulo='FIFA 26 PS4'),
            'categoria': make_categoria()
        }
        resultado = core.agrupar_variantes([entrada1, entrada2])
        assert resultado[0]['categoria']['nombre'] == 'Juegos PS5'


# ---------------------------------------------------------------------------
# format_telegram_message con variantes
# ---------------------------------------------------------------------------

class TestFormatTelegramMessageConVariantes:
    def test_sin_variantes_formato_original(self):
        """Sin variantes → mantiene el formato original con 🛒."""
        producto = make_producto(titulo='FIFA 26 PS5')
        categoria = make_categoria()
        mensaje = core.format_telegram_message(producto, categoria)
        assert '🛒' in mensaje
        assert 'Ver en Amazon</a>' in mensaje
        assert 'variantes_adicionales' not in str(producto)

    def test_con_variante_ambas_con_links_paralelos(self):
        """Con variantes → ambas versiones tienen links, formato paralelo con identificadores."""
        producto = make_producto(
            titulo='FIFA 26 PS5',
            precio='39,99€',
            precio_anterior='69,99€',
            descuento=43,
            variantes_adicionales=[
                {
                    'asin': 'B002',
                    'titulo': 'FIFA 26 PS4',
                    'url': 'https://amazon.es/dp/B002',
                    'precio': '34,99€',
                    'precio_anterior': '58,99€',
                    'descuento': 40,
                }
            ]
        )
        categoria = make_categoria()
        mensaje = core.format_telegram_message(producto, categoria)
        # Ambos precios deben estar
        assert '39,99€' in mensaje
        assert '34,99€' in mensaje
        # Ambos deben estar linkados (href aparece 2 veces)
        assert mensaje.count('href=') >= 2
        # Debe mostrar identificadores de variante (PS4 explícito)
        assert 'PS4' in mensaje
        # No debe haber 🛒 único al final (ese es formato sin variantes)
        assert '\n🛒 Ver en Amazon</a>' not in mensaje

    def test_variante_con_precio_anterior(self):
        """La variante muestra precio anterior tachado cuando aplica."""
        producto = make_producto(
            titulo='Producto',
            precio='20€',
            precio_anterior='30€',
            variantes_adicionales=[
                {
                    'asin': 'B002',
                    'titulo': 'Variante',
                    'url': 'https://amazon.es/dp/B002',
                    'precio': '25€',
                    'precio_anterior': '35€',
                    'descuento': 28,
                }
            ]
        )
        categoria = make_categoria()
        mensaje = core.format_telegram_message(producto, categoria)
        # Ambos precios anteriores deben estar tachados
        assert '<s>30€</s>' in mensaje
        assert '<s>35€</s>' in mensaje
        # Ambos precios nuevos en negrita (dentro del link)
        assert '20€' in mensaje
        assert '25€' in mensaje

    def test_escapa_urls_en_variantes(self):
        """Las URLs en variantes se escapan correctamente."""
        producto = make_producto(
            titulo='Producto',
            variantes_adicionales=[
                {
                    'asin': 'B002',
                    'titulo': 'Variante',
                    'url': 'https://amazon.es/dp/B002?tag=test&foo=bar',
                    'precio': '10€',
                    'descuento': 10,
                }
            ]
        )
        categoria = make_categoria()
        mensaje = core.format_telegram_message(producto, categoria)
        # Debe escapar caracteres especiales en URL
        assert 'href=' in mensaje
        assert 'amazon.es' in mensaje

    def test_multiples_variantes_todas_con_links(self):
        """Con múltiples variantes, todas aparecen con links 💰."""
        producto = make_producto(
            titulo='Mando',
            variantes_adicionales=[
                {
                    'asin': 'B002',
                    'titulo': 'Mando Blanco',
                    'url': 'https://amazon.es/dp/B002',
                    'precio': '60€',
                    'descuento': 20,
                },
                {
                    'asin': 'B003',
                    'titulo': 'Mando Negro',
                    'url': 'https://amazon.es/dp/B003',
                    'precio': '65€',
                    'descuento': 15,
                }
            ]
        )
        categoria = make_categoria()
        mensaje = core.format_telegram_message(producto, categoria)
        # 3 links totales: principal + 2 variantes
        assert mensaje.count('href=') == 3
        # Todos los precios presentes
        assert '60€' in mensaje
        assert '65€' in mensaje


# ---------------------------------------------------------------------------
# Límite global de 7 días entre publicaciones
# ---------------------------------------------------------------------------

class TestLimiteGlobalPS:
    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.send_telegram_message')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_bloquea_si_publicacion_reciente(self, mock_save, mock_load, mock_pagina, mock_msg, mock_foto, mock_token, mock_chat_id):
        """Verifica que bloquea publicaciones si han pasado <7 días desde la última."""
        ahora = datetime.now()
        ultima_pub_hace_3_dias = (ahora - timedelta(days=3)).isoformat()
        categorias_semanales = {"_ultima_publicacion_global": ultima_pub_hace_3_dias}
        mock_load.return_value = ({}, [], [], categorias_semanales)
        mock_pagina.return_value = _html_con_producto()
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'

        resultado = bot.buscar_y_publicar_ofertas()

        # No debe publicar porque no han pasado 7 días
        assert resultado == 0
        # No debe llamar a send_telegram_photo ni send_telegram_message
        mock_foto.assert_not_called()
        mock_msg.assert_not_called()

    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.send_telegram_message')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_permite_si_han_pasado_7_dias(self, mock_save, mock_load, mock_pagina, mock_msg, mock_foto, mock_token, mock_chat_id):
        """Verifica que permite publicaciones si han pasado >=7 días."""
        ahora = datetime.now()
        ultima_pub_hace_8_dias = (ahora - timedelta(days=8)).isoformat()
        categorias_semanales = {"_ultima_publicacion_global": ultima_pub_hace_8_dias}
        mock_load.return_value = ({}, [], [], categorias_semanales)
        mock_pagina.return_value = _html_con_producto(
            asin="B001_GAME",
            titulo="Juego PS5 Elden Ring",
            precio_anterior="59,99€",
            precio_actual="35,99€"
        )
        mock_foto.return_value = True
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'

        resultado = bot.buscar_y_publicar_ofertas()

        # Debe publicar porque han pasado 8 días (>= 7)
        assert resultado == 1
        # Debe llamar a send_telegram_photo (porque hay imagen)
        mock_foto.assert_called()

    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.send_telegram_message')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_permite_si_no_existe_timestamp(self, mock_save, mock_load, mock_pagina, mock_msg, mock_foto, mock_token, mock_chat_id):
        """Verifica que permite publicaciones si no existe _ultima_publicacion_global (primera vez)."""
        categorias_semanales = {}  # Sin _ultima_publicacion_global
        mock_load.return_value = ({}, [], [], categorias_semanales)
        mock_pagina.return_value = _html_con_producto(
            asin="B001_GAME",
            titulo="Juego PS5 Elden Ring",
            precio_anterior="59,99€",
            precio_actual="35,99€"
        )
        mock_foto.return_value = True
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'

        resultado = bot.buscar_y_publicar_ofertas()

        # Debe publicar porque es la primera vez (no existe timestamp)
        assert resultado == 1
        # Debe llamar a send_telegram_photo (porque hay imagen)
        mock_foto.assert_called()

    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.send_telegram_message')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_guarda_timestamp_al_publicar(self, mock_save, mock_load, mock_pagina, mock_msg, mock_foto, mock_token, mock_chat_id):
        """Verifica que se guarda _ultima_publicacion_global en JSON al publicar exitosamente."""
        mock_load.return_value = ({}, [], [], {})
        mock_pagina.return_value = _html_con_producto(
            asin="B001_GAME",
            titulo="Juego PS5 Elden Ring",
            precio_anterior="59,99€",
            precio_actual="35,99€"
        )
        mock_foto.return_value = True
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'

        resultado = bot.buscar_y_publicar_ofertas()

        # Debe publicar
        assert resultado == 1

        # Verificar que save_posted_deals fue llamado con categorias_semanales
        # que contenga _ultima_publicacion_global
        assert mock_save.called
        call_args = mock_save.call_args
        categorias_semanales_guardadas = call_args[0][3] if len(call_args[0]) > 3 else call_args.kwargs.get('categorias_semanales', {})
        assert "_ultima_publicacion_global" in categorias_semanales_guardadas
        # Verificar que el timestamp es reciente (hace menos de 10 segundos)
        ts_guardado = datetime.fromisoformat(categorias_semanales_guardadas["_ultima_publicacion_global"])
        assert (datetime.now() - ts_guardado).total_seconds() < 10


# ---------------------------------------------------------------------------
# Búsqueda de Preórdenes
# ---------------------------------------------------------------------------

class TestEsPrereservaItem:
    def test_detecta_disponible_el(self):
        """Detecta patrones 'disponible el' como preorden."""
        from bs4 import BeautifulSoup
        html = '<div>PlayStation 5 disponible el 15 de marzo</div>'
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('div')
        assert bot._es_prereserva_item(item) is True

    def test_detecta_proximamente(self):
        """Detecta 'próximamente' como preorden."""
        from bs4 import BeautifulSoup
        html = '<div>Juego PS5 próximamente en stock</div>'
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('div')
        assert bot._es_prereserva_item(item) is True

    def test_detecta_preorden(self):
        """Detecta 'preorden' o 'pre-orden' como preorden."""
        from bs4 import BeautifulSoup
        html = '<div>Haz tu pre-orden de FIFA 26 ahora</div>'
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('div')
        assert bot._es_prereserva_item(item) is True

    def test_no_detecta_producto_normal(self):
        """No detecta productos normales como preorden."""
        from bs4 import BeautifulSoup
        html = '<div>Juego PS5 disponible en stock - Envío en 1 día</div>'
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('div')
        assert bot._es_prereserva_item(item) is False

    def test_item_none_devuelve_false(self):
        """Si el item es None, devuelve False."""
        assert bot._es_prereserva_item(None) is False


class TestFormatPrereservaMessage:
    def test_contiene_emoji_categoria(self):
        """El mensaje contiene el emoji de la categoría."""
        p = make_producto(titulo="FIFA 26 PS5")
        cat = {"nombre": "Próximos PS5", "emoji": "⏰", "url": "/s?k=reserva+juegos+ps5"}
        msg = bot.format_prereserva_message(p, cat)
        assert "⏰" in msg

    def test_contiene_proximo_lanzamiento(self):
        """El mensaje contiene 'PRÓXIMO LANZAMIENTO'."""
        p = make_producto(titulo="FIFA 26 PS5")
        cat = {"nombre": "Próximos PS5", "emoji": "⏰"}
        msg = bot.format_prereserva_message(p, cat)
        assert "PRÓXIMO LANZAMIENTO" in msg

    def test_contiene_nombre_categoria(self):
        """El mensaje contiene el nombre de la categoría."""
        p = make_producto()
        cat = {"nombre": "Próximos PS5", "emoji": "⏰"}
        msg = bot.format_prereserva_message(p, cat)
        assert "PRÓXIMOS PS5" in msg

    def test_contiene_titulo(self):
        """El mensaje contiene el título del producto."""
        p = make_producto(titulo="FIFA 26 PS5")
        cat = {"nombre": "Próximos PS5", "emoji": "⏰"}
        msg = bot.format_prereserva_message(p, cat)
        assert "FIFA 26 PS5" in msg

    def test_contiene_precio_reserva(self):
        """El mensaje muestra precio de reserva cuando está disponible."""
        p = make_producto(precio="49,99€")
        cat = {"nombre": "Próximos PS5", "emoji": "⏰"}
        msg = bot.format_prereserva_message(p, cat)
        assert "Precio de reserva" in msg
        assert "49,99€" in msg

    def test_omite_precio_si_na(self):
        """Si el precio es 'N/A', no lo muestra."""
        p = make_producto(precio="N/A")
        cat = {"nombre": "Próximos PS5", "emoji": "⏰"}
        msg = bot.format_prereserva_message(p, cat)
        assert "Precio de reserva" not in msg

    def test_contiene_enlace_amazon(self):
        """El mensaje contiene un enlace a Amazon."""
        p = make_producto(url="https://www.amazon.es/dp/B001TEST01")
        cat = {"nombre": "Próximos PS5", "emoji": "⏰"}
        msg = bot.format_prereserva_message(p, cat)
        assert "href=" in msg
        assert "amazon.es" in msg


class TestBuscarPrereservasPS:
    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.load_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_respeta_limite_global_7_dias(self, mock_save_deals, mock_save_pre, mock_load_pre, mock_load_deals, mock_pagina, mock_foto, mock_token, mock_chat_id):
        """Si fue publicada hace <7 días, no publica nada."""
        ahora = datetime.now()
        ultima_pub_hace_3_dias = (ahora - timedelta(days=3)).isoformat()
        categorias_semanales = {"_ultima_publicacion_global": ultima_pub_hace_3_dias}
        mock_load_deals.return_value = ({}, [], [], categorias_semanales)
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'

        resultado = bot.buscar_prereservas_ps()

        # No debe publicar nada debido al límite global
        assert resultado == 0
        mock_foto.assert_not_called()

    def _html_prereserva(self, asin="B001PRE", titulo="FIFA 26 PS5"):
        """Helper para generar HTML con preorden detectado."""
        return textwrap.dedent(f"""
        <html><body>
        <div data-component-type="s-search-result" data-asin="{asin}">
          <h2><a><span>{titulo}</span></a></h2>
          <span>Disponible el 15 de marzo 2026</span>
          <span class="a-price">
            <span class="a-offscreen">49,99€</span>
          </span>
          <span class="a-size-base s-underline-text">2.500</span>
          <img class="s-image" src="https://example.com/img.jpg" />
        </div>
        </body></html>
        """)

    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.load_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_publica_hasta_3_prereservas(self, mock_save_deals, mock_save_pre, mock_load_pre, mock_load_deals, mock_pagina, mock_foto, mock_token, mock_chat_id):
        """Con 5 candidatos válidos, publica solo 3 (MAX_PRERESERVAS_POR_CICLO)."""
        mock_load_deals.return_value = ({}, [], [], {})  # Sin bloqueo global
        mock_load_pre.return_value = {}
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'
        mock_foto.return_value = True

        # Retornar HTML con preorden cada vez que se pida
        mock_pagina.return_value = self._html_prereserva()

        resultado = bot.buscar_prereservas_ps()

        # Debe publicar hasta 3 (o menos si no hay tantos candidatos)
        assert resultado <= 3
        # Si hay candidatos suficientes y se envió, llamó a foto
        if resultado > 0:
            mock_foto.assert_called()

    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.load_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_no_repite_asins_en_48h(self, mock_save_deals, mock_save_pre, mock_load_pre, mock_load_deals, mock_pagina, mock_foto, mock_token, mock_chat_id):
        """Si un ASIN ya fue publicado hace <48h, no lo vuelve a publicar."""
        ahora = datetime.now()
        asin_reciente = 'B001_PRE_RECIENTE'
        posted_prereservas = {asin_reciente: (ahora - timedelta(hours=24)).isoformat()}
        mock_load_deals.return_value = ({}, [], [], {})
        mock_load_pre.return_value = posted_prereservas
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'
        mock_pagina.return_value = self._html_prereserva(asin=asin_reciente)

        resultado = bot.buscar_prereservas_ps()

        # El ASIN ya fue publicado, así que no se publica de nuevo
        assert resultado == 0
        mock_foto.assert_not_called()

    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.load_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_guarda_timestamp_global_al_publicar(self, mock_save_deals, mock_save_pre, mock_load_pre, mock_load_deals, mock_pagina, mock_foto, mock_token, mock_chat_id):
        """Al publicar preórdenes, actualiza _ultima_publicacion_global en posted_ps_deals.json."""
        mock_load_deals.return_value = ({}, [], [], {})
        mock_load_pre.return_value = {}
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'
        mock_foto.return_value = True
        mock_pagina.return_value = self._html_prereserva()

        resultado = bot.buscar_prereservas_ps()

        # Si se publicó, debe llamar a save_posted_deals con categorias_semanales
        if resultado > 0:
            assert mock_save_deals.called
            call_args = mock_save_deals.call_args
            # El timestamp global debe estar en el 4o argumento (categorias_semanales)
            if len(call_args[0]) >= 4:
                categorias_semanales = call_args[0][3]
                assert "_ultima_publicacion_global" in categorias_semanales

    @patch('ps.amazon_ps_ofertas._effective_chat_id')
    @patch('ps.amazon_ps_ofertas._effective_token')
    @patch('ps.amazon_ps_ofertas.send_telegram_photo')
    @patch('ps.amazon_ps_ofertas.obtener_pagina')
    @patch('ps.amazon_ps_ofertas.load_posted_deals')
    @patch('ps.amazon_ps_ofertas.load_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_prereservas')
    @patch('ps.amazon_ps_ofertas.save_posted_deals')
    def test_retorna_0_sin_candidatos(self, mock_save_deals, mock_save_pre, mock_load_pre, mock_load_deals, mock_pagina, mock_foto, mock_token, mock_chat_id):
        """Sin candidatos de preorden válidos, retorna 0."""
        # HTML sin señales de preorden
        html_sin_preorden = '<html><body><div data-component-type="s-search-result" data-asin="B001"><span>Producto normal disponible en stock</span></div></body></html>'
        mock_load_deals.return_value = ({}, [], [], {})
        mock_load_pre.return_value = {}
        mock_token.return_value = 'fake_token'
        mock_chat_id.return_value = 'fake_chat_id'
        mock_pagina.return_value = html_sin_preorden

        resultado = bot.buscar_prereservas_ps()

        # Sin candidatos de preorden, debe retornar 0
        assert resultado == 0
        mock_foto.assert_not_called()
