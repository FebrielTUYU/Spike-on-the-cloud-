# -*- coding: utf-8 -*-
"""
Pruebas de la Fase 3 (2026-09-23/24): base de contraste oficial
(Constitucion indexada por articulo + boletines de instituciones publicas).
No golpea la red: usa datos sinteticos con la misma forma que devuelve
Wikisource/los RSS reales (ya verificados a mano en vivo, ver oficial.py).

Corre con:  python test_oficial.py
"""
import json
import os
import tempfile
import unittest

import oficial


class TestConstitucion(unittest.TestCase):
    def setUp(self):
        self._orig_path = oficial.CONSTITUCION_PATH
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        oficial.CONSTITUCION_PATH = path

    def tearDown(self):
        try:
            os.remove(oficial.CONSTITUCION_PATH)
        except Exception:
            pass
        oficial.CONSTITUCION_PATH = self._orig_path

    def _sembrar(self, articulos):
        payload = {"ts": __import__("time").time(),
                   "fuente": "prueba", "n_articulos": len(articulos), "articulos": articulos}
        with open(oficial.CONSTITUCION_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def test_sin_indice_no_inventa_nada(self):
        self.assertIsNone(oficial.articulo("1"))
        self.assertEqual(oficial.buscar_constitucion("libertad"), [])

    def test_articulo_por_numero(self):
        self._sembrar({"1": "El Ecuador es un Estado constitucional de derechos y justicia."})
        a = oficial.articulo("1")
        self.assertEqual(a["numero"], "1")
        self.assertIn("Estado constitucional", a["texto"])

    def test_articulo_inexistente_devuelve_none(self):
        self._sembrar({"1": "texto"})
        self.assertIsNone(oficial.articulo("9999"))

    def test_buscar_exige_todas_las_palabras(self):
        self._sembrar({
            "18": "El derecho a buscar, recibir, intercambiar, producir y difundir informacion.",
            "66": "Se reconoce el derecho a la libertad de expresion y de opinion.",
            "1": "El Ecuador es un Estado constitucional.",
        })
        r = oficial.buscar_constitucion("libertad expresion")
        self.assertEqual([a["numero"] for a in r], ["66"])

    def test_wikitext_se_parsea_bien_sin_markup(self):
        limpio = oficial._limpiar_wikitext("'''Texto''' con [[enlace|link]] y ''cursiva''.")
        self.assertNotIn("'''", limpio)
        self.assertNotIn("[[", limpio)
        self.assertIn("link", limpio)


class TestBoletinesOficiales(unittest.TestCase):
    def setUp(self):
        self._orig_path = oficial.OFICIAL_CACHE_PATH
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        oficial.OFICIAL_CACHE_PATH = path

    def tearDown(self):
        try:
            os.remove(oficial.OFICIAL_CACHE_PATH)
        except Exception:
            pass
        oficial.OFICIAL_CACHE_PATH = self._orig_path

    def _sembrar(self, cache):
        with open(oficial.OFICIAL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)

    def test_buscar_oficial_sin_cache_no_rompe(self):
        self.assertEqual(oficial.buscar_oficial("inflacion"), [])

    def test_buscar_oficial_encuentra_por_texto(self):
        self._sembrar({
            "url1": {"nombre": "Banco Central del Ecuador", "items": [
                {"titulo": "El BCE eleva la prevision de crecimiento economico", "link": "https://x/1", "fecha": "hoy"},
                {"titulo": "Noticia sin relacion", "link": "https://x/2", "fecha": "hoy"},
            ]},
        })
        r = oficial.buscar_oficial("crecimiento economico")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["institucion"], "Banco Central del Ecuador")

    def test_actualizar_respeta_frecuencia_propia(self):
        """No deberia pegarle a la red si ninguna fuente le toca el turno."""
        import time
        cache_previo = {f["url"]: {"nombre": f["nombre"], "ultimo_fetch": time.time(),
                                    "items": []} for f in oficial.FUENTES}
        self._sembrar(cache_previo)
        llamado = []
        orig = __import__("urllib.request", fromlist=["urlopen"]).urlopen
        import urllib.request
        urllib.request.urlopen = lambda *a, **k: llamado.append(1) or orig(*a, **k)
        try:
            oficial.actualizar(respetar_frecuencia=True)
        finally:
            urllib.request.urlopen = orig
        self.assertFalse(llamado, "no deberia haber consultado la red si a ninguna fuente le tocaba el turno")

    def test_estado_resume_disponibilidad(self):
        self._sembrar({"url1": {"nombre": "INEC", "items": [{"titulo": "x", "link": "", "fecha": ""}]}})
        st = oficial.estado()
        self.assertIn("boletines", st)
        self.assertIn("constitucion", st)


if __name__ == "__main__":
    unittest.main()
