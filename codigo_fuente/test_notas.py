# -*- coding: utf-8 -*-
"""
Prueba del Problema 6 (cuarta pasada, 2026-09-23): "Mis notas" se perdia
siempre porque el servidor nunca implemento POST /api/nota (404 en cada
guardado), y por separado, story_key() podia cambiar de un momento a otro
porque usaba fuentes[0] (la fuente MAS RECIENTE, que cambia cada vez que un
medio nuevo cubre una historia en desarrollo) en vez de la mas vieja.

No golpea la red ni el servidor http real (esta dentro de serve(), dificil
de levantar en una prueba unitaria) -- prueba las piezas que SI son testeables
sin servidor: el round-trip de load_notas/save_notas (mismo patron que
saved.json) y que build_stories() deja la fuente MAS VIEJA en fuentes[0].

Corre con:  python test_notas.py
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import monitor


class TestNotasRoundTrip(unittest.TestCase):
    def setUp(self):
        self._orig_path = monitor.NOTAS_PATH
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)  # que arranque sin existir, como en una instalacion nueva
        monitor.NOTAS_PATH = path

    def tearDown(self):
        try:
            os.remove(monitor.NOTAS_PATH)
        except Exception:
            pass
        monitor.NOTAS_PATH = self._orig_path

    def test_sin_archivo_devuelve_vacio_no_error(self):
        self.assertEqual(monitor.load_notas(), {})

    def test_guardar_y_releer_una_nota(self):
        notas = monitor.load_notas()
        notas["https://ejemplo.com/nota-1"] = {"texto": "llamar a fuente X", "titular": "Un titular", "ts": "2026-09-23T00:00:00"}
        monitor.save_notas(notas)
        releido = monitor.load_notas()
        self.assertEqual(releido["https://ejemplo.com/nota-1"]["texto"], "llamar a fuente X")

    def test_escritura_es_atomica_archivo_temporal_no_queda(self):
        monitor.save_notas({"k": {"texto": "x", "titular": "", "ts": ""}})
        self.assertFalse(os.path.exists(monitor.NOTAS_PATH + ".tmp"))
        self.assertTrue(os.path.exists(monitor.NOTAS_PATH))


class TestClaveDeHistoriaEstable(unittest.TestCase):
    """Bug real sospechado por Fernando: la clave de una nota/guardado depende
    de fuentes[0].link -- si esa posicion fuera la fuente MAS NUEVA, cada vez
    que otro medio cubre la misma historia en desarrollo la clave cambiaria y
    la nota quedaria huerfana. build_stories() ahora deja la fuente MAS VIEJA
    en fuentes[0] (la que casi no cambia entre corridas)."""

    def test_fuentes_0_es_la_mas_vieja_no_la_mas_nueva(self):
        base = monitor.now_utc()
        arts = [
            {"outlet": "El Universo", "seccion": "politica",
             "title": "Primeras versiones del hecho", "link": "https://eluniverso.com/vieja",
             "date": base - dt.timedelta(hours=10), "summary": "", "image": ""},
            {"outlet": "Expreso", "seccion": "politica",
             "title": "Nuevos detalles del hecho", "link": "https://expreso.ec/nueva",
             "date": base, "summary": "", "image": ""},
        ]
        clusters = [{"articles": arts}]
        stories = monitor.build_stories(clusters)
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["fuentes"][0]["link"], "https://eluniverso.com/vieja",
                          "fuentes[0] deberia ser la fuente mas vieja (mas estable), no la mas nueva")

    def test_story_key_no_cambia_si_se_agrega_una_fuente_mas_nueva(self):
        base = monitor.now_utc()
        arts1 = [{"outlet": "El Universo", "seccion": "politica",
                   "title": "Primeras versiones del hecho", "link": "https://eluniverso.com/vieja",
                   "date": base - dt.timedelta(hours=10), "summary": "", "image": ""}]
        s1 = monitor.build_stories([{"articles": arts1}])[0]
        key1 = monitor.story_key(s1)

        arts2 = arts1 + [{"outlet": "Expreso", "seccion": "politica",
                           "title": "Nuevos detalles del hecho", "link": "https://expreso.ec/nueva",
                           "date": base, "summary": "", "image": ""}]
        s2 = monitor.build_stories([{"articles": arts2}])[0]
        key2 = monitor.story_key(s2)

        self.assertEqual(key1, key2, "la clave de la historia cambio solo porque se sumo un medio nuevo")


if __name__ == "__main__":
    unittest.main()
