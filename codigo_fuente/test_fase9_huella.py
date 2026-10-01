# -*- coding: utf-8 -*-
"""
Fase 9, Problema B1 -- "la lectura de IA describe otra noticia".

Causa real (ver CLAUDE.md): get_ia()/get_contexto()/get_veredicto() cachean
por fuentes[0].link (clave ESTABLE), pero calculan el resultado UNA sola vez
con el titular representante de ese momento. Cuando la historia suma medios
y el representante cambia, la tarjeta muestra el titular NUEVO con la
lectura VIEJA. Se agrego una huella de contenido (_huella_contenido) que
detecta ese desfase.

No golpea Ollama: monkeypatchea ia.analizar/ia.disponible/ia.interpretar.
Corre con:  python test_fase9_huella.py
"""
import json
import os
import tempfile
import unittest

import ia
import monitor as m


def _story(titular, resumen="", link="https://x/1", n_fuentes=1):
    return {
        "titular": titular, "resumen": resumen, "temas": [], "ambito": "local",
        # es_local (Fase 11 v2): get_contexto() ahora filtra por este campo
        # (antes solo miraba 'ambito' para el ORDEN de prioridad, nunca para
        # excluir) -- una historia de prueba "local" tiene que llevarlo,
        # igual que build_stories() lo pone de verdad en el pipeline real.
        "es_local": True, "interes": 100,
        "fuentes": [{"link": link, "title": titular, "outlet": "El Universo"}] * n_fuentes,
    }


class TestHuellaGetIA(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_cache = m.IA_CACHE
        m.IA_CACHE = os.path.join(self._tmp, "ia_cache.json")
        self._orig_disponible = ia.disponible
        self._orig_analizar = ia.analizar
        self._orig_interpretar = ia.interpretar
        ia.disponible = lambda modelo="": True
        self.llamadas_analizar = []

        def _analizar_falso(titular, resumen, temas_kw=None, forzado=""):
            self.llamadas_analizar.append(titular)
            return {"temas": [], "geo": ["internacional"]}

        ia.analizar = _analizar_falso
        # Fase 24 (A1): get_ia pide el triaje en lotes; el lote falso usa la misma funcion.
        self._orig_lote = getattr(ia, "analizar_lote", None)
        ia.analizar_lote = lambda items, **k: [_analizar_falso(i["titular"], i.get("resumen", ""), i.get("temas_kw"))
                                               for i in items]
        ia.interpretar = lambda *a, **k: "una lectura cualquiera"

    def tearDown(self):
        m.IA_CACHE = self._orig_cache
        ia.disponible = self._orig_disponible
        ia.analizar = self._orig_analizar
        ia.analizar_lote = self._orig_lote
        ia.interpretar = self._orig_interpretar

    def test_representante_cambia_marca_desactualizada_en_modo_lectura(self):
        s1 = _story("Titular original de la nota")
        m.get_ia([s1], modo_lectura=False)
        self.assertEqual(len(self.llamadas_analizar), 1)

        # La historia sumo un medio y cambio de representante (mismo link
        # fuentes[0], la clave estable) -- el hilo rapido debe seguir
        # mostrando la lectura vieja, pero marcada.
        s2 = _story("Titular COMPLETAMENTE distinto tras sumar un medio nuevo",
                     link="https://x/1", n_fuentes=2)
        estado = m.get_ia([s2], modo_lectura=True)
        self.assertTrue(s2.get("ia_desactualizada"),
                         "debio marcarse desactualizada: cambio el representante y la cantidad de medios")
        self.assertIn("desactualizada", estado)

    def test_sin_cambios_no_se_marca_ni_se_recalcula(self):
        s1 = _story("Titular que no cambia")
        m.get_ia([s1], modo_lectura=False)
        self.assertEqual(len(self.llamadas_analizar), 1)
        s2 = _story("Titular que no cambia", link="https://x/1", n_fuentes=1)
        m.get_ia([s2], modo_lectura=False)
        self.assertEqual(len(self.llamadas_analizar), 1, "no debio recalcular sin cambios reales")
        self.assertFalse(s2.get("ia_desactualizada"))

    def test_worker_recalcula_cuando_la_huella_cambio(self):
        s1 = _story("Titular original de la nota")
        m.get_ia([s1], modo_lectura=False)
        self.assertEqual(len(self.llamadas_analizar), 1)

        s2 = _story("Titular nuevo tras sumar un medio", link="https://x/1", n_fuentes=2)
        m.get_ia([s2], modo_lectura=False)
        self.assertEqual(len(self.llamadas_analizar), 2,
                          "el trabajador debio recalcular: la huella ya no coincidia")
        self.assertFalse(s2.get("ia_desactualizada"), "tras recalcular, ya no esta desactualizada")


class TestHuellaGetContexto(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_cache = m.CONTEXTO_CACHE
        m.CONTEXTO_CACHE = os.path.join(self._tmp, "contexto_cache.json")
        self._orig_construir = m._construir_contexto
        self.llamadas = []

        def _construir_falso(s, registro=None):
            self.llamadas.append(s["titular"])
            return {"texto": "contexto de " + s["titular"], "entidades": [], "comenciones": [],
                    "principal": None, "previas": [], "antecedentes": [], "actores": [],
                    "que_es_nuevo": [], "que_falta_saber": [], "limitaciones": "", "descartadas": 0}
        m._construir_contexto = _construir_falso
        self._orig_disponible = ia.disponible
        ia.disponible = lambda modelo="": True

    def tearDown(self):
        m.CONTEXTO_CACHE = self._orig_cache
        m._construir_contexto = self._orig_construir
        ia.disponible = self._orig_disponible

    def test_contexto_desactualizado_se_marca_y_se_rehace(self):
        s1 = _story("Nota original")
        m.get_contexto([s1], modo_lectura=False)
        self.assertEqual(len(self.llamadas), 1)

        s2 = _story("Nota con representante nuevo", link="https://x/1", n_fuentes=3)
        estado = m.get_contexto([s2], modo_lectura=True)
        self.assertTrue(s2.get("contexto_desactualizado"))
        self.assertIn("desactualizado", estado)

        m.get_contexto([s2], modo_lectura=False)
        self.assertEqual(len(self.llamadas), 2, "el trabajador debio rehacer el contexto")
        self.assertFalse(s2.get("contexto_desactualizado"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
