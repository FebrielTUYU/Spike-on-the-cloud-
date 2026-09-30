# -*- coding: utf-8 -*-
"""
Prueba de la Fase 2 (2026-09-23/24): el marco de cobertura se calcula con
datos PROPIOS (historias/articulos ya recolectados) en vez de depender de
GDELT (bloqueado la mayor parte del tiempo). Cada snapshot de history.json
ahora guarda ademas "secciones_ambito" (Mundo/Ecuador/Guayaquil por
separado) y "cobertura" (volumen real de articulos, no de GDELT) -- las 5
categorias SIEMPRE presentes, aunque sea en 0, para que ningun panel las
filtre en silencio.

Corre con:  python test_fase2_cobertura.py
"""
import os
import tempfile
import unittest

import monitor as m


def _story(seccion, n_articles=1, es_local=False, internacional=False, ciudad=""):
    return {"seccion": seccion, "n_articles": n_articles, "es_local": es_local,
            "internacional": internacional, "ciudad": ciudad, "temas": []}


class TestSeccionesAmbitoYCobertura(unittest.TestCase):
    def setUp(self):
        self._orig_path = m.HIST_PATH
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        m.HIST_PATH = path

    def tearDown(self):
        try:
            os.remove(m.HIST_PATH)
        except Exception:
            pass
        m.HIST_PATH = self._orig_path

    def test_las_5_categorias_siempre_presentes_en_secciones_ambito(self):
        stories = [_story("politica", es_local=True, ciudad="Guayaquil")]
        hist = m.append_history(stories)
        snap = hist[-1]
        for amb in ("guayaquil", "local", "internacional"):
            self.assertEqual(set(snap["secciones_ambito"][amb].keys()), set(m.CATEGORIAS_VALIDAS),
                              "faltan categorias en secciones_ambito[%s]" % amb)

    def test_las_5_categorias_siempre_presentes_en_cobertura(self):
        hist = m.append_history([_story("politica")])
        self.assertEqual(set(hist[-1]["cobertura"].keys()), set(m.CATEGORIAS_VALIDAS))

    def test_guayaquil_no_se_cuenta_dos_veces_en_local(self):
        # una historia de Guayaquil debe contar en "guayaquil", NO en "local"
        # (que es el resto de Ecuador sin Guayaquil) -- evita que Guayaquil se
        # sume dos veces si alguien suma guayaquil+local a mano despues.
        stories = [_story("seguridad", es_local=True, ciudad="Guayaquil")]
        snap = m.append_history(stories)[-1]
        self.assertEqual(snap["secciones_ambito"]["guayaquil"]["seguridad"], 1)
        self.assertEqual(snap["secciones_ambito"]["local"]["seguridad"], 0)

    def test_cobertura_suma_n_articles_no_historias(self):
        stories = [_story("economia", n_articles=3), _story("economia", n_articles=2)]
        snap = m.append_history(stories)[-1]
        self.assertEqual(snap["cobertura"]["economia"], 5,
                          "cobertura deberia sumar n_articles (volumen real), no contar historias")


if __name__ == "__main__":
    unittest.main()
