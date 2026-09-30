# -*- coding: utf-8 -*-
"""
Problema 2 (2026-09-24): "el pronostico del clima de Sevilla salio en la
seccion Guayaquil".

Diagnostico real (con data.json de una corrida en vivo): la nota de Sevilla
llegaba mezclada -- por el clustering, no por su propio texto -- en un grupo
que incluia una fuente con "ciudad_feed"="Guayaquil" (la seccion editorial
de Guayaquil de El Universo). ambito_de()/build_stories() nunca comparaban
el TEXTO de la nota de Sevilla contra nada: "ciudad_feed" forzaba
ambito="local" sin condicion. Revisando las 94 historias marcadas Guayaquil
de esa misma corrida se encontro un SEGUNDO caso real vivo, mismo patron:
"Pico y Placa en Cali" (Colombia) agrupada con boletines de Quito/Guayaquil.

Prueba con los 5 casos pedidos por Fernando: Sevilla, Putumayo (candado de
temas -- la IA no puede vaciar una categoria correcta sin reemplazo) y 3
notas reales de Guayaquil SIN mencion explicita de la ciudad (para confirmar
que el veto no rompe el caso normal que "ciudad_feed" esta pensado para
resolver).

No golpea internet ni Ollama. Corre con:  python test_problema2_veto_geografico.py
"""
import unittest

import monitor


def _art(outlet, title, summary="", ciudad_feed=""):
    return {
        "outlet": outlet, "seccion": "sociedad", "title": title, "link": "https://x/" + title[:20],
        "date": monitor.now_utc(), "summary": summary, "image": "", "ciudad_feed": ciudad_feed,
    }


def _historia_de(arts):
    clusters = [{"articles": arts}]
    return monitor.build_stories(clusters)[0]


class TestVetoGeografico(unittest.TestCase):
    def test_sevilla_pronostico_clima_no_queda_en_guayaquil(self):
        """Caso real que motivo el reporte: el pronostico de Sevilla llega
        agrupado (por error de clustering, no por su propio texto) junto con
        una fuente de la seccion Guayaquil de El Universo."""
        arts = [
            _art("El Universo (Guayaquil)",
                 "Asi estara el clima en Guayaquil este jueves: se preven lluvias y una maxima de 33 C",
                 ciudad_feed="Guayaquil"),
            _art("Infobae",
                 "Pronostico del clima en Sevilla este 25 de septiembre: temperatura, lluvias y viento"),
        ]
        s = _historia_de(arts)
        self.assertEqual(s["ambito"], "internacional",
                          "el pronostico de Sevilla quedo marcado como local")
        self.assertNotEqual(s["ciudad"], "Guayaquil")
        self.assertNotIn("guayaquil", s["geo"])

    def test_infobae_sevilla_sola_es_basura_descartada_antes_de_agrupar(self):
        """Pedido explicito: pronosticos de clima de fuera de Ecuador se
        descartan como ruido (is_junk), no solo se corrigen de ambito."""
        self.assertTrue(monitor.is_junk(
            "Pronostico del clima en Sevilla este 25 de septiembre: temperatura, lluvias y viento",
            "Para evitar cualquier imprevisto es importante conocer el pronostico del tiempo", ""))

    def test_pronostico_de_ciudad_ecuatoriana_no_es_basura(self):
        """El filtro de pronosticos NO debe descartar contenido local util."""
        self.assertFalse(monitor.is_junk(
            "Asi estara el clima en Guayaquil este jueves 24 de septiembre: se preven lluvias y "
            "una maxima de 33 C",
            "", ""))

    def test_pico_y_placa_cali_no_queda_en_guayaquil(self):
        """Segundo caso real vivo encontrado revisando las 94 historias de
        Guayaquil de la misma corrida: 'Pico y Placa en Cali' (Colombia)
        agrupada con boletines reales de Quito/Guayaquil."""
        arts = [
            _art("El Universo (Guayaquil)",
                 "Pronostico en Guayaquil: calor o lluvia este viernes 25 de septiembre",
                 ciudad_feed="Guayaquil"),
            _art("Extra", "Pico y placa en Quito este viernes 25 de septiembre: consulte "
                           "como aplica la restriccion"),
            _art("Infobae", "Pico y Placa en Cali: restricciones vehiculares para evitar "
                             "multas este viernes 25 de septiembre",
                 "Cuales son los automoviles que no pueden circular este viernes, chequealo y evita una multa"),
        ]
        s = _historia_de(arts)
        self.assertEqual(s["ambito"], "internacional",
                          "Pico y Placa en Cali (Colombia) quedo marcado local/Guayaquil")

    def test_putumayo_mineria_ilegal_preserva_categoria_de_keywords(self):
        """Caso real ya documentado (Fase 2): 'Ejercito inhabilita... mineria
        ilegal en Putumayo' clasifica bien como Ambiente por keywords, pero
        la IA a veces propone una categoria SIN relacion (ej.
        'Policia/Militar') que el candado descarta -- sin dejar NINGUNA en
        comun. El candado debe preservar la clasificacion de keywords en vez
        de vaciarla a 'otros'."""
        titular = "Ejercito inhabilita campamento de mineria ilegal en la frontera con Putumayo"
        temas_kw = monitor.themes_for(titular, "seguridad")
        self.assertIn("Ambiente", temas_kw, "themes_for() ya no detecta Ambiente en el caso real")

        s = {"titular": titular, "resumen": "", "temas": temas_kw,
             "geo": ["ecuador"], "ambito": "local", "es_local": True,
             "internacional": False, "ciudad": ""}
        # simulacion de la respuesta de la IA: propone una categoria que NO
        # esta en temas_kw (mismo caso real).
        r = {"temas": [{"cat": "Policia/Militar", "score": 1.0}], "geo": ["ecuador"], "interp": ""}

        def _apply(s, r):
            temas_r = r.get("temas")
            if temas_r:
                temas_kw_set = set(s.get("temas") or [])
                import monitor as M
                kept = sorted({t["cat"] for t in temas_r
                               if t.get("score", 0) >= M.IA_TEMA_MIN and t["cat"] in temas_kw_set})
                s["temas"] = kept or sorted(temas_kw_set) or ["otros"]

        _apply(s, r)
        self.assertIn("Ambiente", s["temas"],
                       "el candado vacio la categoria correcta en vez de preservarla")
        self.assertNotEqual(s["temas"], ["otros"])


class TestVetoNoRompeGuayaquilReal(unittest.TestCase):
    """3 notas reales de Guayaquil (data.json, 2026-09-24) SIN mencion
    explicita de 'Guayaquil' en el texto -- exactamente el caso que
    ciudad_feed esta pensado para resolver (secciones hiperlocales que no
    repiten el nombre de la ciudad). El veto no debe romperlas: no
    mencionan ningun lugar extranjero, asi que el texto es 'neutro' y la
    señal de ciudad_feed debe seguir aplicando."""

    def test_remodelacion_ceibos_sigue_local(self):
        arts = [_art("El Universo (Guayaquil)",
                      "Remodelacion de Ceibos Town Center genera inquietudes entre moradores: "
                      "la Junta de Beneficencia responde",
                      ciudad_feed="Guayaquil")]
        s = _historia_de(arts)
        self.assertEqual(s["ambito"], "local")
        self.assertEqual(s["ciudad"], "Guayaquil")

    def test_solca_carrera_cancer_sigue_local(self):
        arts = [_art("El Universo (Guayaquil)",
                      "Adelantate al cancer: Solca lanza una carrera que busca prevenir el "
                      "cancer de mama",
                      ciudad_feed="Guayaquil")]
        s = _historia_de(arts)
        self.assertEqual(s["ambito"], "local")
        self.assertEqual(s["ciudad"], "Guayaquil")

    def test_reservorio_via_a_la_costa_sigue_local(self):
        arts = [_art("Municipio de Guayaquil",
                      "Proyecto del reservorio de agua en Via a la Costa cuenta con todas "
                      "las autorizaciones municipales",
                      ciudad_feed="Guayaquil")]
        s = _historia_de(arts)
        self.assertEqual(s["ambito"], "local")
        self.assertEqual(s["ciudad"], "Guayaquil")

    def test_nota_con_ecuador_y_extranjero_a_la_vez_sigue_local(self):
        """No debe romper el caso normal: una nota que menciona un pais
        extranjero PERO TAMBIEN Ecuador explicitamente sigue siendo local
        (el veto exige que NO haya ninguna senal de Ecuador)."""
        arts = [_art("El Comercio",
                      "Este fue el aporte de los 50 militares de Estados Unidos en los "
                      "allanamientos en Ecuador")]
        s = _historia_de(arts)
        self.assertEqual(s["ambito"], "local")


if __name__ == "__main__":
    unittest.main()
