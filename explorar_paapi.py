#!/usr/bin/env python3
"""
Explorador de Amazon Creators API con SDK oficial
==================================================
Instalar dependencia:
  pip install python-amazon-paapi --upgrade

Ejecutar:
  source .env && python3 explorar_paapi.py

Variables de entorno necesarias en .env:
  export AMAZON_CLIENT_ID="tu_client_id"
  export AMAZON_CLIENT_SECRET="tu_client_secret"
"""

import os
import sys
import json
import ssl

# Fix SSL en macOS: Python no usa los certificados del sistema por defecto.
# Solo afecta a este script de prueba — en GitHub Actions (Linux) no hace falta.
ssl._create_default_https_context = ssl._create_unverified_context

# ── Verificar instalación del SDK ─────────────────────────────────────────────
try:
    from amazon_creatorsapi import AmazonCreatorsApi, Country
    from amazon_creatorsapi.models import SearchItemsResource, SortBy
    # Mostrar atributos disponibles para debug
    attrs = [a for a in dir(SearchItemsResource) if not a.startswith('_')]
    print(f"📋  SearchItemsResource attrs: {attrs[:10]}...")
except ImportError:
    print("❌  Falta el SDK. Instálalo con:")
    print("    pip install python-amazon-paapi --upgrade")
    sys.exit(1)

# ── Credenciales ──────────────────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("AMAZON_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("AMAZON_CLIENT_SECRET", "")
PARTNER_TAG   = "juegosenoferta-21"
VERSION       = "3.2"   # EU con Login with Amazon (LwA)

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌  Faltan credenciales en .env:")
    print('   export AMAZON_CLIENT_ID="tu_client_id"')
    print('   export AMAZON_CLIENT_SECRET="tu_client_secret"')
    sys.exit(1)

# ── Inicializar API ───────────────────────────────────────────────────────────
api = AmazonCreatorsApi(
    credential_id=CLIENT_ID,
    credential_secret=CLIENT_SECRET,
    version=VERSION,
    tag=PARTNER_TAG,
    country=Country.ES,
    throttling=1,
)

# ── Recursos a pedir ──────────────────────────────────────────────────────────
# Sin resources = el SDK usa todos los disponibles por defecto
RESOURCES = None

# ── Procesar un item ──────────────────────────────────────────────────────────
def procesar_item(item) -> dict:
    titulo = ""
    try:
        titulo = item.item_info.title.display_value
    except:
        titulo = "Sin título"

    marca = ""
    try:
        marca = item.item_info.by_line_info.brand.display_value
    except:
        pass

    precio = None
    precio_ref = None
    descuento_pct = None
    promociones = []

    try:
        listings = item.offers.listings
        if listings:
            p = listings[0].price
            precio = p.display_amount if p else None
            precio_num = p.amount if p else None

            sb = listings[0].saving_basis
            if sb:
                precio_ref = sb.display_amount
                precio_ref_num = sb.amount
                if precio_num and precio_ref_num and precio_ref_num > precio_num:
                    ahorro = precio_ref_num - precio_num
                    descuento_pct = round((ahorro / precio_ref_num) * 100, 1)

            for promo in (listings[0].promotions or []):
                try:
                    tipo = promo.type
                    pct  = promo.discount_percent
                    promociones.append(f"{tipo} -{pct}%" if pct else tipo)
                except:
                    pass
    except:
        pass

    imagen = False
    try:
        imagen = bool(item.images.primary.large.url)
    except:
        pass

    reviews = 0
    stars = 0
    try:
        reviews = item.customer_reviews.count.display_value
        stars   = item.customer_reviews.star_rating.display_value
    except:
        pass

    return {
        "asin":          item.asin,
        "titulo":        titulo[:65],
        "marca":         marca,
        "precio":        precio,
        "precio_ref":    precio_ref,
        "descuento_pct": descuento_pct,
        "promociones":   promociones,
        "valoraciones":  reviews,
        "estrellas":     stars,
        "imagen":        imagen,
        "url":           item.detail_page_url,
    }

def imprimir_item(p: dict, idx: int):
    desc_str = f"  💥 {p['descuento_pct']}% dto  ({p['precio_ref']} → {p['precio']})" if p['descuento_pct'] else "  — sin descuento"
    promo_str = f"  🎫 {', '.join(p['promociones'])}" if p['promociones'] else ""
    print(f"\n  [{idx+1}] {p['titulo']}")
    print(f"       ASIN: {p['asin']}  |  Marca: {p['marca'] or '—'}")
    print(f"       Precio: {p['precio'] or 'N/A'}{desc_str}")
    if promo_str:
        print(f"       {promo_str}")
    print(f"       ⭐ {p['estrellas']} ({p['valoraciones']} reseñas)  |  Imagen: {'✅' if p['imagen'] else '❌'}")

# ── Categorías de prueba ──────────────────────────────────────────────────────
PRUEBAS = [
    ("Pañales bebé",        "pañales bebe",        None,           SortBy.RELEVANCE),
    ("Toallitas bebé",      "toallitas bebe",       None,           SortBy.RELEVANCE),
    ("Juegos PS5",          "juegos ps5",           None,           SortBy.RELEVANCE),
    ("Mandos PS5",          "mando ps5 dualsense",  None,           SortBy.PRICE_COLON_LOW_TO_HIGH),
]

def main():
    print("=" * 60)
    print("  Amazon Creators API — Explorador de ofertas")
    print(f"  Tag: {PARTNER_TAG}  |  País: ES  |  Versión credencial: {VERSION}")
    print("=" * 60)

    con_descuento = 0
    sin_descuento = 0

    for label, keywords, browse_node, sort_by in PRUEBAS:
        print(f"\n{'─'*60}")
        print(f"📂  {label}")
        print(f"{'─'*60}")
        print(f"  🔍  Buscando: '{keywords}'...")

        try:
            kwargs = {"keywords": keywords, "sort_by": sort_by}
            if RESOURCES:
                kwargs["resources"] = RESOURCES
            if browse_node:
                kwargs["browse_node_id"] = browse_node

            results = api.search_items(**kwargs)
            items = results.items if results else []
            print(f"  📦  {len(items)} resultados")

            for idx, item in enumerate(items[:5]):
                p = procesar_item(item)
                imprimir_item(p, idx)
                if p["descuento_pct"]:
                    con_descuento += 1
                else:
                    sin_descuento += 1

        except Exception as e:
            print(f"  ❌  Error: {e}")

    print(f"\n{'='*60}")
    print(f"  RESUMEN")
    print(f"{'='*60}")
    print(f"  Con descuento : {con_descuento}")
    print(f"  Sin descuento : {sin_descuento}")
    print()

    # Respuesta raw del primer resultado para ver la estructura completa
    print("  ── Objeto raw del primer resultado (pañales) ──")
    try:
        results = api.search_items(keywords="pañales bebe")
        if results and results.items:
            item = results.items[0]
            # Intentar serializar a dict
            try:
                print(json.dumps(item.to_dict(), indent=2, ensure_ascii=False)[:3000])
            except:
                print(repr(item)[:2000])
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    main()
