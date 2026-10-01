# -*- coding: utf-8 -*-
"""
Fase 9, Problema C -- Pulso social anclado a historias, con filtro de
pertenencia y posturas citadas (no un resumen unico).

No golpea Bluesky/Reddit/YouTube ni Ollama: monkeypatchea
social.recolectar/ia.clasificar_posturas. Corre con:
python test_fase9_social_historias.py
"""
import os
import tempfile
import unittest

import ia
import monitor as m
import social


def _story(titular, ciudad="Guayaquil", es_local=True, link="https://x/1", resumen=""):
    return {
        "titular": titular, "resumen": resumen, "ciudad": ciudad, "es_local": es_local,
        "fuentes": [{"link": link, "title": titular, "outlet": "El Universo"}],
        "temas": ["Seguridad"],
    }


def _post(fuente, texto, autor="alguien", tipo="persona", comentarios_n=0, comentarios=None):
    return social.SocialPost(fuente=fuente, texto=texto, autor=autor, url="https://x/%s" % autor,
                              likes=1, reposts=0, comentarios_n=comentarios_n,
                              comentarios=comentarios or [], tipo=tipo, fecha=m.now_utc().isoformat())  # Fase 21: hora real (ventana de 10 h)


class TestSocialHistorias(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_cache = m.SOCIAL_HIST_CACHE
        m.SOCIAL_HIST_CACHE = os.path.join(self._tmp, "social_historias_cache.json")
        self._orig_recolectar = social.recolectar
        self._orig_clasificar = ia.clasificar_posturas

    def tearDown(self):
        m.SOCIAL_HIST_CACHE = self._orig_cache
        social.recolectar = self._orig_recolectar
        ia.clasificar_posturas = self._orig_clasificar

    def test_ancla_por_entidades_no_por_categoria(self):
        """La query armada para la historia usa sus ENTIDADES (nombre propio/
        ciudad), nunca el nombre generico de la categoria -- causa real del
        ruido (Armenia/Venezuela bajo 'Asamblea/Leyes')."""
        s = _story("Alcaldesa Cynthia Viteri inaugura obra en Ceibos")
        query, nombres, ciudad = m._social_query_historia(s)
        self.assertIn("viteri", [n.lower() for n in nombres])
        self.assertNotIn("Asamblea/Leyes", query)

    def test_filtro_pertenencia_descarta_posts_sin_relacion(self):
        s = _story("Alcaldesa Cynthia Viteri inaugura obra en Ceibos")
        capturado = {}

        def _recolectar_falso(query, subreddit="", limite=15, youtube=True, ambito=None, term_base=None):
            capturado["query"] = query
            return [
                _post("bluesky", "Cynthia Viteri inauguro la obra en Ceibos, buena gestion"),
                _post("bluesky", "El PRI de Mexico presento su nueva estrategia electoral"),  # sin relacion
            ], []

        social.recolectar = _recolectar_falso
        ia.clasificar_posturas = lambda *a, **k: []
        out, estado = m.get_social_historias([s], modo_lectura=False)
        key = "https://x/1"
        self.assertEqual(out[key]["n_posts"], 1, "el post de Mexico no debio contar como perteneciente")
        self.assertEqual(out[key]["n_descartados"], 1)

    def test_posturas_solo_con_citas_reales(self):
        s = _story("Operativo CJNG en Samborondon deja varios detenidos")

        def _recolectar_falso(query, subreddit="", limite=15, youtube=True, ambito=None, term_base=None):
            return [
                _post("bluesky", "El operativo del CJNG en Samborondon fue un exito de la policia", autor="a1"),
                _post("youtube", "No creo que el operativo del CJNG haya sido limpio", autor="a2"),
            ], []

        social.recolectar = _recolectar_falso

        def _clasificar_falso(titular, resumen, posts, forzado="", timeout=90):
            # el modelo inventa un id que NO existe ("99") -- debe filtrarse
            return [
                {"postura": "a_favor", "ids": ["0"]},
                {"postura": "en_contra", "ids": ["1", "99"]},
                {"postura": "duda", "ids": ["99"]},  # sin ids reales -- se descarta entera
            ]

        ia.clasificar_posturas = _clasificar_falso
        out, estado = m.get_social_historias([s], modo_lectura=False)
        key = "https://x/1"
        posturas = out[key]["posturas"]
        nombres_posturas = {p["postura"] for p in posturas}
        self.assertIn("a_favor", nombres_posturas)
        self.assertIn("en_contra", nombres_posturas)
        self.assertNotIn("duda", nombres_posturas, "postura sin ids reales debio descartarse")
        en_contra = next(p for p in posturas if p["postura"] == "en_contra")
        self.assertEqual(en_contra["n"], 1, "el id inventado (99) no debio contarse")

    def test_modo_lectura_solo_lee_cache_sin_red(self):
        llamado = {"n": 0}

        def _recolectar_falso(*a, **k):
            llamado["n"] += 1
            return [], []

        social.recolectar = _recolectar_falso
        out, estado = m.get_social_historias([_story("Cualquier cosa")], modo_lectura=True)
        self.assertEqual(llamado["n"], 0, "modo_lectura nunca debe llamar a la red")
        self.assertEqual(out, {})

    def test_hilo_principal_usa_el_post_con_mas_comentarios(self):
        s = _story("Marcha en el centro de Guayaquil por el paro")

        def _recolectar_falso(query, subreddit="", limite=15, youtube=True, ambito=None, term_base=None):
            return [
                _post("reddit", "Guayaquil vive una marcha pacifica hoy", autor="p1", comentarios_n=2,
                      comentarios=["buena marcha", "ojala no haya problemas"]),
                _post("reddit", "Guayaquil: la marcha se dispersa sin problemas", autor="p2", comentarios_n=8,
                      comentarios=["excelente cobertura"] * 3),
            ], []

        social.recolectar = _recolectar_falso
        ia.clasificar_posturas = lambda *a, **k: []
        out, estado = m.get_social_historias([s], modo_lectura=False)
        hilo = out["https://x/1"]["hilo_principal"]
        self.assertIsNotNone(hilo)
        self.assertEqual(hilo["autor"], "p2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
