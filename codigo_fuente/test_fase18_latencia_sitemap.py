# -*- coding: utf-8 -*-
"""
Fase 18, P1-8 -- velocidad real de los feeds.

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo:
- La latencia se calcula SOLO sobre articulos que aparecieron con el feed ya
  sondeado poco antes (no sobre el backlog de la primera lectura tras un
  arranque, que infla los numeros: medianas de 405-666 min en El Universo /
  El Diario).
- Soporte de "news sitemaps" (sitemap-news.xml) como fuente de ultimo
  minuto, con parser probado sobre un XML con el formato estandar de Google
  News (el mismo que ya se vio en El Comercio, Fase 0).
"""
import datetime as dt
import os
import tempfile
import unittest

import monitor

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://www.medio.ec/guayaquil/lluvias-atarazana.html</loc>
    <news:news>
      <news:publication><news:name>Medio</news:name><news:language>es</news:language></news:publication>
      <news:publication_date>2026-09-29T15:40:00-05:00</news:publication_date>
      <news:title>Lluvias inundan la Atarazana y la avenida de las Americas</news:title>
    </news:news>
  </url>
  <url>
    <loc>https://www.medio.ec/politica/asamblea.html</loc>
    <lastmod>2026-09-29T14:00:00-05:00</lastmod>
    <news:news><news:title>Asamblea debate reforma</news:title></news:news>
  </url>
</urlset>"""


class TestSitemap(unittest.TestCase):
    def test_parser_de_news_sitemap(self):
        arts = monitor.parse_sitemap_news(SITEMAP, "Medio", "auto")
        self.assertEqual(len(arts), 2)
        a = arts[0]
        self.assertEqual(a["title"], "Lluvias inundan la Atarazana y la avenida de las Americas")
        self.assertEqual(a["link"], "https://www.medio.ec/guayaquil/lluvias-atarazana.html")
        self.assertEqual(a["date"], dt.datetime(2026, 9, 29, 20, 40, tzinfo=dt.timezone.utc))
        self.assertEqual(arts[1]["date"], dt.datetime(2026, 9, 29, 19, 0, tzinfo=dt.timezone.utc))

    def test_feed_tipo_sitemap_usa_el_parser(self):
        orig = monitor.fetch
        monitor.fetch = lambda url, etag=None, last_modified=None: (SITEMAP, None, None, 200)
        try:
            got, st, _ = monitor._fetch_feed({"outlet": "Medio", "seccion": "auto", "url": "https://x/sitemap-news.xml",
                                              "tipo": "sitemap"}, {}, False)
        finally:
            monitor.fetch = orig
        self.assertEqual(st, "ok")
        self.assertEqual(len(got), 2)


class TestLatenciaReal(unittest.TestCase):
    def setUp(self):
        self.orig = monitor.LATENCIA_PATH
        monitor.LATENCIA_PATH = os.path.join(tempfile.mkdtemp(), "lat.json")

    def tearDown(self):
        monitor.LATENCIA_PATH = self.orig

    def test_backlog_tras_arranque_no_cuenta(self):
        ahora = monitor.now_utc()
        arts = [
            # feed sondeado hace 2 min, nota publicada hace 6 min -> SI cuenta (6 min de atraso)
            {"outlet": "Rapido", "link": "r1", "date": ahora - dt.timedelta(minutes=6)},
            # feed que no se sondeaba hace 5 h (PC apagada): nota de hace 4 h -> backlog, NO cuenta
            {"outlet": "Lento", "link": "l1", "date": ahora - dt.timedelta(hours=4)},
            # feed sondeado hace 2 min pero la nota es de hace 3 h (el medio la publico con fecha vieja
            # o recien aparecio en el feed): SI cuenta -- ese atraso es real del medio/feed
            {"outlet": "Rapido", "link": "r2", "date": ahora - dt.timedelta(hours=3)},
        ]
        prev_ok = {"Rapido": (ahora - dt.timedelta(minutes=2)).timestamp(),
                   "Lento": (ahora - dt.timedelta(hours=5)).timestamp()}
        monitor._registrar_first_seen(arts, prev_ok)
        lat = monitor.calcular_latencia_por_feed()
        self.assertEqual(lat["Rapido"]["n"], 2)
        self.assertNotIn("Lento", {k for k, v in lat.items() if v["n"] > 0})
        self.assertEqual(lat["Lento"]["n_descartados_backlog"], 1)


if __name__ == "__main__":
    unittest.main()
