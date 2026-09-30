# -*- coding: utf-8 -*-
"""Fase 22b -- bug real: "al abrirlo me sigue apareciendo la vieja interfaz".
serve() mostraba el dashboard.html de la corrida anterior (armado con la
plantilla VIEJA) y el refresco solo traia datos, nunca el diseño nuevo."""
import json
import os
import shutil
import tempfile
import unittest

import monitor


class TestInterfazNueva(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = monitor.HERE
        monitor.HERE = self.tmp
        with open(os.path.join(self.tmp, "dashboard_template.html"), "w", encoding="utf-8") as f:
            f.write('<html>DISEÑO NUEVO<script id="payload">/*__DATA__*/null</script></html>')
        with open(os.path.join(self.tmp, "data.json"), "w", encoding="utf-8") as f:
            json.dump({"generado": "2026-09-30T10:00:00", "historias": [{"titular": "a</script>b"}]}, f)
        with open(os.path.join(self.tmp, "dashboard.html"), "w", encoding="utf-8") as f:
            f.write("<html>DISEÑO VIEJO</html>")

    def tearDown(self):
        monitor.HERE = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rearma_con_la_plantilla_actual(self):
        self.assertTrue(monitor.regenerar_dashboard_desde_data())
        html = open(os.path.join(self.tmp, "dashboard.html"), encoding="utf-8").read()
        self.assertIn("DISEÑO NUEVO", html)
        self.assertNotIn("DISEÑO VIEJO", html)
        self.assertIn('"ui_version"', html)
        self.assertNotIn("a</script>b", html)  # no rompe el <script> del payload

    def test_sin_data_json_no_hace_nada(self):
        os.remove(os.path.join(self.tmp, "data.json"))
        self.assertFalse(monitor.regenerar_dashboard_desde_data())
        html = open(os.path.join(self.tmp, "dashboard.html"), encoding="utf-8").read()
        self.assertIn("DISEÑO VIEJO", html)

    def test_version_cambia_con_el_diseno(self):
        self.assertNotEqual(monitor._ui_version("a"), monitor._ui_version("b"))
        self.assertEqual(monitor._ui_version("a"), monitor._ui_version("a"))

    def test_la_pagina_se_recarga_si_cambia_el_diseno(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html"),
                   encoding="utf-8").read()
        self.assertIn("nuevo.ui_version!==UI_VERSION", src)
        self.assertIn("location.reload()", src)


if __name__ == "__main__":
    unittest.main()
