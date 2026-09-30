# -*- coding: utf-8 -*-
"""
Fase 11 (pedido de Fernando, dos correcciones juntas porque el mismo caso
real las reproduce a las dos):

1) El ranking de "interes" no tenia ninguna señal de GRAVEDAD del hecho --
   una nota local de un solo medio sobre un asesinato podia quedar hundida
   bajo coberturas internacionales de puro volumen. Ver monitor._bono_impacto.
2) El Asistente (herramientas.buscar_historias/buscar_guardadas/buscar_notas)
   no encontraba una nota real porque el filtro de texto libre 'q' exigia una
   SUBCADENA LITERAL completa -- el modelo nunca reproduce el titular exacto,
   y en el caso real la nota decia "baleada" mientras Fernando pregunto por
   "asesinato". Ver herramientas._coincide_texto_libre.

Caso real que motiva las dos pruebas: "Una mujer fue baleada tras retirar
USD 2.000 de una entidad bancaria en el centro de Guayaquil" (ambito local,
ciudad Guayaquil, tema Crimen/Violencia), confirmada en data.json en vivo.

Corre con:  python test_fase11_impacto_retrieval.py
"""
import unittest

import herramientas as h
import monitor


def _story_ranking(n_outlets, n_intl, n_articles, es_local, temas, demanda=0, recency=0):
    return {
        "n_outlets": n_outlets, "outlets_intl": ["x"] * n_intl, "n_articles": n_articles,
        "es_local": es_local, "temas": temas, "demanda": demanda, "recency": recency,
    }


class TestBonoImpacto(unittest.TestCase):
    def test_nota_local_de_crimen_recibe_bono(self):
        s = _story_ranking(1, 0, 1, True, ["Crimen/Violencia"])
        self.assertEqual(monitor._bono_impacto(s), 150)

    def test_nota_local_sin_tema_de_impacto_no_recibe_bono(self):
        s = _story_ranking(1, 0, 1, True, ["Cultura/Comunidad"])
        self.assertEqual(monitor._bono_impacto(s), 0)

    def test_nota_internacional_de_crimen_no_recibe_bono(self):
        # la cobertura internacional ya es la señal correcta para hechos graves afuera
        s = _story_ranking(5, 5, 5, False, ["Crimen/Violencia"])
        self.assertEqual(monitor._bono_impacto(s), 0)

    def test_caso_real_un_solo_medio_local_supera_a_varias_notas_triviales_locales(self):
        # el caso real: un solo medio, tema Crimen/Violencia, ambito local
        grave_un_medio = _story_ranking(1, 0, 1, True, ["Crimen/Violencia"], demanda=0, recency=0.9)
        trivial_dos_medios = _story_ranking(2, 0, 2, True, ["Cultura/Comunidad"], demanda=20, recency=0.5)

        def interes(s):
            bono = monitor._bono_impacto(s)
            return (monitor._peso_outlets(s) + s["n_articles"] * 6
                    + (s["demanda"] or 0) * 0.6 + s.get("recency", 0) * 20 + bono)

        self.assertGreater(interes(grave_un_medio), interes(trivial_dos_medios),
                            "un hecho grave local de un solo medio deberia superar a una nota trivial de mas medios")


class TestRetrievalAsistente(unittest.TestCase):
    def setUp(self):
        self._orig_cargar = h._cargar
        self._archivos = {}
        h._cargar = lambda nombre, default: self._archivos.get(nombre, default)

    def tearDown(self):
        h._cargar = self._orig_cargar

    def _historia_real(self):
        return {
            "titular": "Una mujer fue baleada tras retirar USD 2.000 de una entidad bancaria en el centro de Guayaquil",
            "resumen": "El hecho ocurrio cuando la victima salia de la agencia bancaria en pleno centro de Guayaquil.",
            "temas": ["Crimen/Violencia"], "ambito": "local", "seccion": "seguridad",
            "outlets": ["El Universo"], "n_outlets": 1, "interes": 286.5, "hours": 2.1,
            "fuentes": [{"outlet": "El Universo", "title": "...",
                         "link": "https://x.com/mujer-baleada-guayaquil", "date": "2026-09-28T00:00:00"}],
            "veredicto": {"estado": "pendiente", "texto": "Todavia no procesado.", "citas": []},
        }

    def test_query_parafraseada_encuentra_la_nota_real(self):
        # bug real: Fernando pregunto por el "asesinato" de una "mujer" en
        # el "centro" de "Guayaquil" tras "retirar" "efectivo" -- la nota
        # real dice "baleada", no "asesinato", y nunca repite la frase tal
        # cual. Con subcadena literal esto daba 0 resultados.
        self._archivos["data.json"] = {"historias": [self._historia_real()]}
        r = h.buscar_historias(q="asesinato de una mujer en el centro de Guayaquil tras retirar efectivo")
        self.assertEqual(len(r), 1, "la busqueda por palabras deberia encontrar la nota real aunque no repita la frase exacta")
        self.assertIn("baleada", r[0]["titular"])

    def test_query_sin_tildes_tambien_encuentra(self):
        self._archivos["data.json"] = {"historias": [self._historia_real()]}
        r = h.buscar_historias(q="mujer guayaquil")
        self.assertEqual(len(r), 1)

    def test_query_sin_relacion_no_trae_nada(self):
        self._archivos["data.json"] = {"historias": [self._historia_real()]}
        r = h.buscar_historias(q="elecciones presidenciales en Brasil")
        self.assertEqual(r, [])

    def test_buscar_guardadas_usa_el_mismo_match_por_palabras(self):
        self._archivos["saved.json"] = [self._historia_real()]
        r = h.buscar_guardadas(q="mujer baleada efectivo Guayaquil")
        self.assertEqual(len(r), 1)

    def test_buscar_notas_usa_el_mismo_match_por_palabras(self):
        self._archivos["notas.json"] = {
            "clave1": {"titular": "Seguimiento del caso de la mujer baleada en Guayaquil",
                       "texto": "Confirmar con la fiscalia el estado del caso.", "ts": "2026-09-28T00:00:00"},
        }
        r = h.buscar_notas(q="fiscalia caso mujer Guayaquil")
        self.assertEqual(len(r), 1)


if __name__ == "__main__":
    unittest.main()
