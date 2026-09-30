# -*- coding: utf-8 -*-
"""
Pruebas de la Fase 2 (2026-09-23/24): dos bugs reales de clasificacion.

1. La IA borraba categorias que themes_for() ya habia puesto bien: si la IA
   propone una categoria que NO se solapa nada con las de las keywords (caso
   real reproducido en vivo con Ollama: "Ejercito inhabilita... mineria
   ilegal en Putumayo" -> IA propuso "Policia/Militar" en vez de "Ambiente"),
   la nota caia en 'otros' en vez de conservar la clasificacion de keywords.

2. Candado de geografia asimetrico: "local"/"guayaquil" exigian respaldo
   real de texto, pero "internacional" se aceptaba sin condicion aunque el
   texto mencionara Ecuador explicitamente (caso real ya documentado:
   "Estados Unidos intercepta embarcacion de Ecuador" quedaba Internacional).

No golpea Ollama: pre-carga ia_cache.json con la respuesta exacta que ya se
reprodujo en vivo, y llama a get_ia(modo_lectura=True) (que solo lee cache).

Corre con:  python test_fase2_candado_ia.py
"""
import json
import os
import tempfile
import unittest

import monitor as m


def _story(titular, resumen, temas, es_local=True, ambito="local", link=None):
    return {
        "titular": titular, "resumen": resumen, "temas": list(temas),
        "es_local": es_local, "internacional": not es_local, "ambito": ambito,
        "ciudad": "", "geo": ["ecuador"] if es_local else ["internacional"],
        "fuentes": [{"link": link or ("https://x/" + titular[:20])}],
    }


class TestCandadoTemas(unittest.TestCase):
    def setUp(self):
        self._orig_path = m.IA_CACHE
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        m.IA_CACHE = path

    def tearDown(self):
        try:
            os.remove(m.IA_CACHE)
        except Exception:
            pass
        m.IA_CACHE = self._orig_path

    def _cachear(self, key, entry):
        with open(m.IA_CACHE, "w", encoding="utf-8") as f:
            json.dump({key: entry}, f)

    def test_ia_sin_solape_preserva_categoria_de_keywords(self):
        """Caso real: keywords ya dijeron Ambiente, la IA propone
        Policia/Militar (score 1.0, sin solape) -- antes caia en 'otros'."""
        s = _story("Ejercito inhabilita mineria ilegal en Putumayo",
                    "El Ejercito inhabilito dragas en Sucumbios", ["Ambiente"])
        key = s["fuentes"][0]["link"]
        self._cachear(key, {"temas": [{"cat": "Policia/Militar", "score": 1.0}], "geo": ["ecuador"]})
        m.get_ia([s], modo_lectura=True)
        self.assertEqual(s["temas"], ["Ambiente"], "deberia conservar Ambiente en vez de caer en otros")

    def test_ia_con_solape_parcial_sigue_funcionando_normal(self):
        """Caso normal (no debe romperse): la IA SI confirma una de las
        categorias de keywords -- se queda con esa, como siempre."""
        s = _story("Nueva ley tributaria en la Asamblea",
                    "Se debate el proyecto de reforma", ["Asamblea/Leyes", "Impuestos"])
        key = s["fuentes"][0]["link"]
        self._cachear(key, {"temas": [{"cat": "Impuestos", "score": 0.9},
                                       {"cat": "Asamblea/Leyes", "score": 0.3}], "geo": ["ecuador"]})
        m.get_ia([s], modo_lectura=True)
        self.assertEqual(s["temas"], ["Impuestos"])

    def test_ia_score_bajo_en_todo_preserva_keywords_no_borra(self):
        """La IA confirma una categoria de keywords pero con score bajo (no
        pasa IA_TEMA_MIN) -- sigue sin solape usable, se preserva keywords."""
        s = _story("Reforma economica", "resumen", ["Fiscal/Presupuesto"])
        key = s["fuentes"][0]["link"]
        self._cachear(key, {"temas": [{"cat": "Fiscal/Presupuesto", "score": 0.1}], "geo": ["ecuador"]})
        m.get_ia([s], modo_lectura=True)
        self.assertEqual(s["temas"], ["Fiscal/Presupuesto"])


class TestCandadoGeografiaSimetrico(unittest.TestCase):
    def setUp(self):
        self._orig_path = m.IA_CACHE
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        m.IA_CACHE = path

    def tearDown(self):
        try:
            os.remove(m.IA_CACHE)
        except Exception:
            pass
        m.IA_CACHE = self._orig_path

    def _cachear(self, key, entry):
        with open(m.IA_CACHE, "w", encoding="utf-8") as f:
            json.dump({key: entry}, f)

    def test_ia_no_puede_marcar_internacional_si_el_texto_menciona_ecuador(self):
        """Caso real ya documentado: 'Estados Unidos intercepta embarcacion
        de Ecuador' no deberia poder quedar Internacional solo porque la IA
        lo diga, si el texto menciona Ecuador de verdad."""
        s = _story("Estados Unidos intercepta embarcacion de Ecuador",
                    "La marina de EEUU detuvo una embarcacion con narcoticos con bandera de Ecuador",
                    ["Narcotrafico"], es_local=True, ambito="local")
        key = s["fuentes"][0]["link"]
        self._cachear(key, {"temas": [{"cat": "Narcotrafico", "score": 0.9}], "geo": ["internacional"]})
        m.get_ia([s], modo_lectura=True)
        self.assertEqual(s["ambito"], "local", "el texto menciona Ecuador, no deberia aceptar 'internacional' a ciegas")

    def test_ia_si_puede_marcar_internacional_sin_mencion_de_ecuador(self):
        """No debe romperse el caso normal: una nota que de verdad no
        menciona Ecuador SI puede pasar a internacional."""
        s = _story("Francia y Alemania firman acuerdo comercial",
                    "Los paises europeos ampliaron su cooperacion economica",
                    ["Comercio/Inversion"], es_local=True, ambito="local")
        key = s["fuentes"][0]["link"]
        self._cachear(key, {"temas": [{"cat": "Comercio/Inversion", "score": 0.9}], "geo": ["internacional"]})
        m.get_ia([s], modo_lectura=True)
        self.assertEqual(s["ambito"], "internacional")


if __name__ == "__main__":
    unittest.main()
