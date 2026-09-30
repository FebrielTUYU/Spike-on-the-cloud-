# -*- coding: utf-8 -*-
"""
Fase 18, P2-12 -- estadisticas honestas.

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo:
- Cada numero dice su fuente, su ALCANCE GEOGRAFICO real y su antiguedad.
- Wikipedia = hispanohablantes del mundo, NO Guayaquil: no se usa como
  "demanda" de una historia local ("sin dato local"). Caso real: una nota
  local salia con "demanda 100" sacada de Wikipedia, de hace 25 h.
- Dato de mas de 6 h -> marcado viejo; de mas de 48 h -> no se grafica.
"""
import json
import os
import tempfile
import time
import unittest

import monitor


class TestMetaDatos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (monitor.TREND_CACHE, monitor.GDELT_CACHE)
        monitor.TREND_CACHE = os.path.join(self.tmp, "t.json")
        monitor.GDELT_CACHE = os.path.join(self.tmp, "g.json")

    def tearDown(self):
        monitor.TREND_CACHE, monitor.GDELT_CACHE = self.orig

    def _escribir(self, ruta, d):
        with open(ruta, "w") as f:
            json.dump(d, f)

    def test_wikipedia_de_hace_25h_es_mundial_y_vieja(self):
        ahora = time.time()
        self._escribir(monitor.TREND_CACHE, {"fuente": "Wikipedia", "vals": {"Salud": 100},
                                             "vals_ts": {"Salud": ahora - 25 * 3600}})
        self._escribir(monitor.GDELT_CACHE, {"g": {"Ejecutivo": {}}, "g_ts": {"Ejecutivo": ahora - 6 * 24 * 3600}})
        m = monitor.meta_datos()
        self.assertIn("mundo", m["demanda"]["alcance"].lower())
        self.assertIn("no guayaquil", m["demanda"]["alcance"].lower())
        self.assertTrue(m["demanda"]["viejo"])
        self.assertFalse(m["demanda"]["no_graficar"])
        self.assertTrue(m["gdelt"]["no_graficar"])
        self.assertAlmostEqual(m["demanda"]["edad_h"], 25, delta=0.2)

    def test_trends_ec_reciente(self):
        self._escribir(monitor.TREND_CACHE, {"fuente": "Google Trends", "vals": {"Salud": 40},
                                             "vals_ts": {"Salud": time.time() - 3600}})
        m = monitor.meta_datos()
        self.assertIn("ecuador", m["demanda"]["alcance"].lower())
        self.assertFalse(m["demanda"]["viejo"])


class TestDemandaPorHistoria(unittest.TestCase):
    def _st(self):
        return [{"titular": "Local", "es_local": True, "temas": ["Salud"], "n_outlets": 1, "n_articles": 1},
                {"titular": "Mundo", "es_local": False, "temas": ["Salud"], "n_outlets": 1, "n_articles": 1}]

    def test_wikipedia_no_es_demanda_local(self):
        st = self._st()
        monitor.aplicar_demanda(st, {"Salud": 100}, {"fuente": "Wikipedia", "no_graficar": False})
        self.assertIsNone(st[0]["demanda"])
        self.assertEqual(st[0]["demanda_nota"], "sin dato local")
        self.assertEqual(st[1]["demanda"], 100)

    def test_trends_si_es_demanda_local(self):
        st = self._st()
        monitor.aplicar_demanda(st, {"Salud": 40}, {"fuente": "Google Trends", "no_graficar": False})
        self.assertEqual(st[0]["demanda"], 40)

    def test_dato_de_mas_de_48h_no_cuenta(self):
        st = self._st()
        monitor.aplicar_demanda(st, {"Salud": 40}, {"fuente": "Google Trends", "no_graficar": True})
        self.assertIsNone(st[0]["demanda"])
        self.assertIsNone(st[1]["demanda"])


if __name__ == "__main__":
    unittest.main()
