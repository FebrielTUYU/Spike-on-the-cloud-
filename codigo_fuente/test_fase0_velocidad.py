# -*- coding: utf-8 -*-
"""
Pruebas de la Fase 0 (2026-09-23, velocidad): cache de fetch por feed
(frecuencia propia + peticion condicional) y el registro real de demora
(first_seen vs. pub_date). No golpea la red: todo con datos sinteticos y
monitor.fetch() reemplazada.

Corre con:  python test_fase0_velocidad.py
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import monitor as m


class TestFetchFeedFrecuencia(unittest.TestCase):
    def test_no_le_toca_turno_reusa_cache_sin_llamar_a_fetch(self):
        llamado = []
        orig = m.fetch
        m.fetch = lambda *a, **k: llamado.append(1) or (b"", None, None, 200)
        try:
            cache_entry = {"ultimo_fetch": __import__("time").time(),
                           "items": [{"outlet": "X", "seccion": "auto", "title": "t",
                                      "link": "https://x/1", "date": None, "summary": "",
                                      "image": "", "ciudad_feed": ""}]}
            f = {"outlet": "X", "seccion": "auto", "url": "https://x/feed", "frecuencia_seg": 999999}
            items, estado, nuevo = m._fetch_feed(f, cache_entry)
            self.assertEqual(estado, "cache (esperando turno)")
            self.assertEqual(len(items), 1)
            self.assertFalse(llamado, "no deberia haber llamado a la red si no le tocaba el turno")
        finally:
            m.fetch = orig

    def test_304_reusa_items_sin_re_parsear(self):
        orig = m.fetch
        m.fetch = lambda url, etag=None, last_modified=None: (None, etag, last_modified, 304)
        try:
            cache_entry = {"ultimo_fetch": 0, "etag": "abc",
                           "items": [{"outlet": "X", "seccion": "auto", "title": "t",
                                      "link": "https://x/1", "date": None, "summary": "",
                                      "image": "", "ciudad_feed": ""}]}
            f = {"outlet": "X", "seccion": "auto", "url": "https://x/feed"}
            items, estado, nuevo = m._fetch_feed(f, cache_entry)
            self.assertEqual(estado, "ok (304 sin cambios)")
            self.assertEqual(len(items), 1)
            self.assertEqual(nuevo["etag"], "abc")
        finally:
            m.fetch = orig

    def test_200_con_fecha_serializa_y_deserializa_bien(self):
        raw_rss = ('<?xml version="1.0"?><rss><channel>'
                   '<item><title>Hola</title><link>https://x/2</link>'
                   '<pubDate>Wed, 23 Sep 2026 12:00:00 +0000</pubDate>'
                   '<description>resumen</description></item>'
                   '</channel></rss>').encode("utf-8")
        orig = m.fetch
        m.fetch = lambda url, etag=None, last_modified=None: (raw_rss, "et2", "lm2", 200)
        try:
            f = {"outlet": "X", "seccion": "auto", "url": "https://x/feed"}
            items, estado, nuevo = m._fetch_feed(f, {})
            self.assertEqual(estado, "ok")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["date"], dt.datetime(2026, 9, 23, 12, 0, 0, tzinfo=dt.timezone.utc))
            # lo guardado en cache tiene que poder releerse bien la proxima vez
            items2 = [m._deserializar_articulo(a) for a in nuevo["items"]]
            self.assertEqual(items2[0]["date"], items[0]["date"])
        finally:
            m.fetch = orig


class TestLatenciaPorFeed(unittest.TestCase):
    def setUp(self):
        self._orig_path = m.LATENCIA_PATH
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        m.LATENCIA_PATH = path

    def tearDown(self):
        try:
            os.remove(m.LATENCIA_PATH)
        except Exception:
            pass
        m.LATENCIA_PATH = self._orig_path

    def test_registra_solo_la_primera_vez(self):
        ahora = m.now_utc()
        arts = [{"outlet": "X", "link": "https://x/1", "date": ahora}]
        m._registrar_first_seen(arts)
        reg1 = m._cargar_latencia()
        primer_visto = reg1["https://x/1"]["first_seen"]
        m._registrar_first_seen(arts)  # de nuevo, mismo link
        reg2 = m._cargar_latencia()
        self.assertEqual(reg2["https://x/1"]["first_seen"], primer_visto,
                          "un link ya visto no deberia actualizar su first_seen")

    def test_calcula_mediana_y_peor_caso_reales(self):
        base = m.now_utc()
        reg = {
            "https://x/1": {"outlet": "X", "pub_date": (base - dt.timedelta(minutes=5)).isoformat(),
                             "first_seen": base.isoformat()},
            "https://x/2": {"outlet": "X", "pub_date": (base - dt.timedelta(minutes=15)).isoformat(),
                             "first_seen": base.isoformat()},
            "https://x/3": {"outlet": "X", "pub_date": (base - dt.timedelta(minutes=1)).isoformat(),
                             "first_seen": base.isoformat()},
        }
        m._guardar_latencia(reg)
        stats = m.calcular_latencia_por_feed()
        self.assertEqual(stats["X"]["n"], 3)
        self.assertEqual(stats["X"]["mas_de_10min"], 1)
        self.assertAlmostEqual(stats["X"]["peor_min"], 15, delta=0.1)

    def test_sin_pub_date_no_cuenta_para_la_demora(self):
        base = m.now_utc()
        reg = {"https://x/1": {"outlet": "Y", "pub_date": None, "first_seen": base.isoformat()}}
        m._guardar_latencia(reg)
        stats = m.calcular_latencia_por_feed()
        self.assertNotIn("Y", stats, "sin pub_date no hay con que medir demora, no deberia inventar un numero")


if __name__ == "__main__":
    unittest.main()
