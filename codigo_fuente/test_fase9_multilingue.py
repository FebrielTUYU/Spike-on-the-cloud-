# -*- coding: utf-8 -*-
"""
Fase 9, parte D3, Problema 3 -- la misma noticia en ingles y en español debe
ser UNA historia con marco global, no dos historias separadas por idioma.

Titulares reales tomados de historias_registro.json (26-09-2026, cumbre
Trump-Xi). Medido en vivo con Ollama real antes de elegir el modelo (ver
CLAUDE.md, Fase 9 parte D3): nomic-embed-text NO separa los pares que deben
unirse de los que no (0.595 vs 0.602, sin umbral posible); bge-m3 SI separa
(0.591-0.632 vs 0.509-0.549). Las pruebas de reconciliacion real usan bge-m3
y se saltan solas si no esta instalado.

Corre con:  python test_fase9_multilingue.py
"""
import datetime as dt
import os
import tempfile
import unittest

import monitor as m

try:
    import ia
except Exception:
    ia = None


def _art(outlet, title, horas_atras=0, link=None):
    return {
        "outlet": outlet, "seccion": "auto", "title": title,
        "link": link or ("https://%s/%s" % (outlet, abs(hash(title)))),
        "date": m.now_utc() - dt.timedelta(hours=horas_atras),
        "summary": "", "image": "", "ciudad_feed": "",
    }


class TestDeteccionIdioma(unittest.TestCase):
    def test_titulares_ingles_reales(self):
        for t in [
            "Trump hosts Xi for state dinner as pomp masks tensions",
            "5 takeaways from Trump's summit with Xi",
            "What Donald Trump and Xi Jinping revealed in the body language with their wives",
        ]:
            self.assertEqual(m._detectar_idioma(t), "en", t)

    def test_titulares_espanol_reales(self):
        for t in [
            "Trump y Xi Jinping exhiben unidad al cierre de la visita de Estado a EE.UU.",
            "Trump, Xi discuten sobre la guerra en Medio Oriente",
        ]:
            self.assertEqual(m._detectar_idioma(t), "es", t)


class TestEquivalenciaEntidades(unittest.TestCase):
    def test_eeuu_y_us_son_la_misma_entidad(self):
        self.assertEqual(m._canon_entidad("EE.UU."), m._canon_entidad("US"))
        self.assertEqual(m._canon_entidad("EEUU"), m._canon_entidad("USA"))

    def test_xi_y_xi_jinping_son_la_misma_entidad(self):
        self.assertEqual(m._canon_entidad("Xi"), m._canon_entidad("Xi Jinping"))

    def test_entidades_canonicas_de_titulares_reales_comparten_trump_y_xi(self):
        en = m._entidades_canonicas("Trump hosts Xi for state dinner as pomp masks tensions")
        es = m._entidades_canonicas("Trump y Xi Jinping exhiben unidad al cierre de la visita de Estado a EE.UU.")
        comunes = en & es
        self.assertIn("trump", comunes)
        self.assertIn("xi jinping", comunes)
        self.assertGreaterEqual(len(comunes), 2)


class _RegistroAislado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_path = m.REGISTRO_PATH
        m.REGISTRO_PATH = os.path.join(self._tmp, "historias_registro.json")

    def tearDown(self):
        m.REGISTRO_PATH = self._orig_path


class TestReconciliacionCruzadaDeIdioma(_RegistroAislado):
    @unittest.skipUnless(ia and ia.embed_disponible(ia.EMBED_MODEL_MULTILINGUE),
                          "requiere Ollama + bge-m3 instalado")
    def test_trump_xi_en_dos_idiomas_se_unen(self):
        # dos pasadas separadas (como si cada medio publicara en un momento
        # distinto) -- el hilo rapido (solo lexico) NO las une, son idiomas
        # distintos.
        pase_en = [_art("Reuters", "Trump hosts Xi for state dinner as pomp masks tensions")]
        stories_en = m.agrupar_con_memoria(pase_en)
        pase_es = [_art("Infobae", "Trump y Xi Jinping exhiben unidad al cierre de la visita de Estado a EE.UU.")]
        stories_es = m.agrupar_con_memoria(pase_es)
        self.assertEqual(len(m.agrupar_con_memoria([])), 2,
                          "el hilo rapido no debe unirlas -- son idiomas distintos, 0 overlap lexico")

        m._embed_multilingue_pendientes_registro()
        stories = m.agrupar_con_memoria([])
        self.assertEqual(len(stories), 1, "tras la reconciliacion cruzada de idioma debieron unirse")
        s = stories[0]
        self.assertTrue(s.get("cobertura_global"), "debio marcarse como cobertura global ES+EN")
        self.assertEqual(m._detectar_idioma(s["titular"]), "es", "el titular preferido debe ser el español")
        self.assertIn("es", s["fuentes_por_idioma"])
        self.assertIn("en", s["fuentes_por_idioma"])

    @unittest.skipUnless(ia and ia.embed_disponible(ia.EMBED_MODEL_MULTILINGUE),
                          "requiere Ollama + bge-m3 instalado")
    def test_iran_vs_visita_no_se_unen_aunque_compartan_trump_y_xi(self):
        """Caso real de control: comparte 'Trump'+'Xi' (2 entidades) pero es
        un hecho DISTINTO (Medio Oriente/Iran vs. la visita de Estado) --
        medido en vivo, coseno bajo (0.55) separa este caso."""
        pase1 = [_art("AP", "Trump, Xi discuss Middle East war as Iran presses 7-day plan to end fighting")]
        m.agrupar_con_memoria(pase1)
        pase2 = [_art("Infobae", "Trump y Xi Jinping exhiben unidad al cierre de la visita de Estado a EE.UU.")]
        m.agrupar_con_memoria(pase2)
        m._embed_multilingue_pendientes_registro()
        stories = m.agrupar_con_memoria([])
        self.assertEqual(len(stories), 2,
                          "hechos distintos (Iran vs. la visita) no debieron unirse pese a compartir Trump+Xi")


class TestBridgeGenericoEstadosUnidos(unittest.TestCase):
    """BUG REAL encontrado revisando a mano una muestra de 10 uniones
    cruzadas de idioma (ver CLAUDE.md, Fase 9 parte D3): una nota de un
    cartel en Ecuador se coló dentro de un cluster internacional sobre la
    cumbre Trump-Xi SOLO porque las dos mencionan 'Estados'/'Unidos' --
    igual de generico en cobertura internacional que 'Guayaquil'/'Ecuador'
    lo son en la local."""

    def test_estados_unidos_ya_no_es_nombre_compartido(self):
        nom1 = m._nombres_propios("China looks to reshape Asian order tras cumbre") - m.EVENTO_GENERICO - m.LUGARES_COMUNES
        nom2 = m._nombres_propios(
            "Ecuador y Estados Unidos capturaron a un cabecilla del Cartel Jalisco en Mocolí") - m.EVENTO_GENERICO - m.LUGARES_COMUNES
        self.assertFalse(nom1 & nom2, "'Estados'/'Unidos' no debe seguir siendo un puente generico")

    def test_caso_real_no_se_une_por_match_registro(self):
        a1 = _art("BBC News", "Trump and Xi come face-to-face as US and China battle to win the AI race")
        a1["_tok"] = m.tokens(a1["title"]) - m.EVENTO_GENERICO
        a1["_nom"] = m._nombres_propios(a1["title"]) - m.EVENTO_GENERICO - m.LUGARES_COMUNES
        a1["_num"] = m._numeros(a1["title"])
        a1["_fecha_menc"] = m.fecha_mencionada(a1["title"])
        a1["_ciudad"] = m.detect_city(a1["title"])
        a1["_servicio"] = m.servicio_mencionado(a1["title"])
        registro = {"e1": {
            "creado": m.now_utc(), "ultimo": m.now_utc(),
            "rep_titulo": a1["title"], "fundador_titulo": a1["title"],
            "tokens": set(a1["_tok"]), "nombres": set(a1["_nom"]), "numeros": set(a1["_num"]),
            "fechas": set(), "ciudad": "", "servicio": "",
        }}
        a2 = _art("Infobae", "Ecuador y Estados Unidos capturaron a un cabecilla del Cartel Jalisco en Mocolí")
        a2["_tok"] = m.tokens(a2["title"]) - m.EVENTO_GENERICO
        a2["_nom"] = m._nombres_propios(a2["title"]) - m.EVENTO_GENERICO - m.LUGARES_COMUNES
        a2["_num"] = m._numeros(a2["title"])
        a2["_fecha_menc"] = m.fecha_mencionada(a2["title"])
        a2["_ciudad"] = m.detect_city(a2["title"])
        a2["_servicio"] = m.servicio_mencionado(a2["title"])
        eid, sim, via = m._match_registro(a2, registro)
        self.assertIsNone(eid, "no debio matchear -- solo comparten 'Estados Unidos', ya excluido")


class TestMarcoGlobalEnBuildStories(unittest.TestCase):
    def test_cluster_con_dos_idiomas_arma_marco_global(self):
        art_en = _art("Reuters", "Trump hosts Xi for state dinner as pomp masks tensions",
                       horas_atras=2, link="https://reuters.com/1")
        art_es = _art("Infobae", "Trump y Xi Jinping exhiben unidad al cierre de la visita de Estado a EE.UU.",
                       horas_atras=1, link="https://infobae.com/1")
        cluster = {"articles": [art_en, art_es], "actualizaciones": []}
        stories = m.build_stories([cluster])
        self.assertEqual(len(stories), 1)
        s = stories[0]
        self.assertTrue(s["cobertura_global"])
        self.assertEqual(s["titular"], art_es["title"], "debe preferir el titular en español")
        self.assertFalse(s["es_traducido"])
        self.assertEqual(len(s["fuentes_por_idioma"]["es"]), 1)
        self.assertEqual(len(s["fuentes_por_idioma"]["en"]), 1)

    def test_cluster_un_solo_idioma_no_activa_marco_global(self):
        art1 = _art("Reuters", "Trump hosts Xi for state dinner as pomp masks tensions", link="https://r/1")
        art2 = _art("AP", "Takeaways from Trump's summit with Xi", link="https://ap/1")
        cluster = {"articles": [art1, art2], "actualizaciones": []}
        stories = m.build_stories([cluster])
        self.assertFalse(stories[0]["cobertura_global"])
        self.assertIsNone(stories[0]["fuentes_por_idioma"])

    def test_historia_local_de_ecuador_no_activa_marco_global(self):
        art1 = _art("El Universo", "Guayaquil amanecio con calles inundadas tras las lluvias", link="https://eu/1")
        cluster = {"articles": [art1], "actualizaciones": []}
        stories = m.build_stories([cluster])
        self.assertFalse(stories[0]["cobertura_global"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
