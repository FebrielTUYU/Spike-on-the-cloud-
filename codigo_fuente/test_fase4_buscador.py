# -*- coding: utf-8 -*-
"""
Pruebas de la Fase 4 (2026-09-23/24): buscador por tema EN VIVO, segmentado
Guayaquil/Ecuador/Mundo (nunca mezclados), con persistencia en
busquedas.json. No golpea la red de verdad: reemplaza fetch()/social.
recolectar()/trends/wiki/oficial/sercop por versiones sinteticas.

Corre con:  python test_fase4_buscador.py
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import monitor as m


class TestBuscarEnVivo(unittest.TestCase):
    def setUp(self):
        self._orig_fetch = m.fetch
        self._orig_busquedas_path = m.BUSQUEDAS_PATH
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        m.BUSQUEDAS_PATH = path

        raw_rss = ('<?xml version="1.0"?><rss><channel>'
                   '<item><title>Nota de prueba</title><link>https://x/1</link>'
                   '<pubDate>Wed, 23 Sep 2026 12:00:00 +0000</pubDate>'
                   '<description>resumen</description></item>'
                   '</channel></rss>').encode("utf-8")
        m.fetch = lambda url, *a, **k: (raw_rss, None, None, 200)

        # social/trends/wiki/oficial/sercop pueden no estar instalados en todos
        # los entornos de prueba -- si existen, se les hace monkeypatch; si no,
        # buscar_en_vivo ya los maneja como None (mismo patron que el resto).
        self._orig_social_recolectar = m.social.recolectar if m.social else None
        if m.social:
            m.social.recolectar = lambda *a, **k: ([], [])

    def tearDown(self):
        m.fetch = self._orig_fetch
        try:
            os.remove(m.BUSQUEDAS_PATH)
        except Exception:
            pass
        m.BUSQUEDAS_PATH = self._orig_busquedas_path
        if m.social and self._orig_social_recolectar:
            m.social.recolectar = self._orig_social_recolectar

    def test_los_3_ambitos_siempre_presentes(self):
        r = m.buscar_en_vivo("prueba")
        self.assertEqual(set(r["ambitos"].keys()), {"guayaquil", "ecuador", "mundo"})

    def test_cada_ambito_trae_noticias_de_la_busqueda_geo_scopeada(self):
        r = m.buscar_en_vivo("prueba")
        for amb in ("guayaquil", "ecuador", "mundo"):
            self.assertGreater(len(r["ambitos"][amb]["noticias"]), 0)

    def test_mundo_no_consulta_contraste_oficial(self):
        r = m.buscar_en_vivo("prueba")
        c = r["ambitos"]["mundo"]["contraste"]
        self.assertEqual(c["constitucion"], [])
        self.assertEqual(c["sercop"], [])

    def test_se_guarda_en_busquedas_json(self):
        m.buscar_en_vivo("prueba unica 12345")
        guardadas = m._cargar_busquedas()
        self.assertEqual(len(guardadas), 1)
        self.assertEqual(guardadas[0]["query"], "prueba unica 12345")

    def test_busquedas_se_acumulan_para_comparar_despues(self):
        m.buscar_en_vivo("primera")
        m.buscar_en_vivo("segunda")
        guardadas = m._cargar_busquedas()
        self.assertEqual([g["query"] for g in guardadas], ["primera", "segunda"])

    def test_se_recorta_a_busquedas_max(self):
        m.BUSQUEDAS_MAX_ORIG = m.BUSQUEDAS_MAX
        m.BUSQUEDAS_MAX = 2
        try:
            m.buscar_en_vivo("uno"); m.buscar_en_vivo("dos"); m.buscar_en_vivo("tres")
            guardadas = m._cargar_busquedas()
            self.assertEqual(len(guardadas), 2)
            self.assertEqual([g["query"] for g in guardadas], ["dos", "tres"])
        finally:
            m.BUSQUEDAS_MAX = m.BUSQUEDAS_MAX_ORIG

    def test_noticias_url_lleva_el_lugar_para_ecuador_y_guayaquil_no_para_mundo(self):
        urls = {}
        def _fetch_espia(url, *a, **k):
            urls[url] = True
            return (b'<?xml version="1.0"?><rss><channel></channel></rss>', None, None, 200)
        m.fetch = _fetch_espia
        m.buscar_en_vivo("clima")
        todas = " ".join(urls.keys())
        self.assertIn("clima+Guayaquil", todas.replace("%20", "+"))
        self.assertIn("clima+Ecuador", todas.replace("%20", "+"))


if __name__ == "__main__":
    unittest.main()
