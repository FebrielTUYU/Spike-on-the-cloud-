# -*- coding: utf-8 -*-
"""
Fase 24, Parte C -- precision. Sin red: la IA es un doble.
  C1 tipo de afirmacion y quien la hace;
  C2 taxonomia de 12 categorias con razon, menos del 10 % sin categoria;
  C3 pares dudosos del coseno: decide la IA, nunca se une por plantilla.
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import categorias as C
import ia
import monitor


class TestC2Categorias(unittest.TestCase):
    def test_reglas_con_razon(self):
        cat, razon = C.clasificar_reglas("Retiro de poste permitira renovar el sistema sanitario en la avenida")
        self.assertEqual(cat, "obras_servicios")
        self.assertIn("poste", razon)
        self.assertEqual(C.clasificar_reglas("US Supreme Court lets Trump resume deportations")[0], "justicia")
        self.assertEqual(C.clasificar_reglas("Lluvias en Guayaquil: el pronostico del Inamhi")[0], "riesgos_clima")

    def test_sin_palabras_usa_el_tema_viejo_y_si_no_queda_vacio(self):
        self.assertEqual(C.clasificar_reglas("Algo paso", temas=["Empleo"]), ("empleo", "por el tema Empleo"))
        self.assertIsNone(C.clasificar_reglas("Algo paso")[0])

    def test_menos_del_10_por_ciento_sin_categoria_en_datos_reales(self):
        try:
            with open(os.path.join(monitor.HERE, "data.json"), encoding="utf-8") as f:
                H = json.load(f).get("historias") or []
        except Exception:
            self.skipTest("sin data.json")
        sin = sum(1 for h in H if not C.clasificar_reglas(h.get("titular", ""), h.get("resumen", ""), h.get("temas"))[0])
        self.assertLess(sin / max(1, len(H)), 0.10)

    def test_ia_manda_pero_con_candado(self):
        s = {"titular": "Poste provoco el retraso de las obras en La Alborada, segun el Municipio de Guayaquil",
             "resumen": "", "temas": []}
        monitor._aplicar_categoria(s, {"cat24": "obras_servicios", "razon24": "obra municipal",
                                       "tipo24": "declaracion", "quien24": "Municipio de Guayaquil"})
        self.assertEqual((s["categoria"], s["categoria_fuente"], s["tipo"], s["tipo_quien"]),
                         ("obras_servicios", "ia", "declaracion", "Municipio de Guayaquil"))
        # La IA no puede inventar una categoria ni a quien atribuir.
        self.assertEqual(C.candado("farandula", "rumor", "Juan Perez", "x", "Titular", "resumen"),
                         (None, None, "", "x"))
        # Revision de Codex: un pedazo de nombre no pasa ("Nobo" dentro de "Noboa").
        self.assertEqual(C.candado("politica", "anuncio", "Nobo", "", "Noboa anuncia cambios", "")[2], "")
        self.assertEqual(C.candado("politica", "anuncio", "Noboa", "", "Noboa anuncia cambios", "")[2], "Noboa")


class TestC1Tipo(unittest.TestCase):
    def test_caso_del_poste(self):
        self.assertEqual(C.tipo_reglas("Poste de energia provoco el retraso de las obras, segun el Municipio de Guayaquil"),
                         ("declaracion", "Municipio de Guayaquil"))
        self.assertEqual(C.tipo_reglas("Municipio retiro el poste de la avenida")[0], "accion")

    def test_dato_anuncio_y_cita(self):
        self.assertEqual(C.tipo_reglas("Cynthia Viteri lidera con 35,63 % de intencion de voto")[0], "dato")
        self.assertEqual(C.tipo_reglas("Metro de Quito cambiará los tiempos de viaje")[0], "anuncio")
        self.assertEqual(C.tipo_reglas('Omar Paganini: "America Latina tiene que navegar entre dos potencias"')[0],
                         "declaracion")

    def test_lote_de_la_ia_trae_categoria_y_tipo_validados(self):
        orig = ia._generar_json
        ia._generar_json = lambda *a, **k: {"items": [
            {"n": 1, "temas": [], "geo": ["guayaquil"], "categoria": "obras_servicios", "razon": "obra",
             "tipo": "declaracion", "quien": "Municipio de Guayaquil"},
            {"n": 2, "temas": [], "geo": [], "categoria": "chismes", "tipo": "accion", "quien": "Alguien Inventado"}]}
        try:
            r = ia.analizar_lote([{"titular": "Poste retraso obras, segun el Municipio de Guayaquil", "resumen": ""},
                                  {"titular": "Capturan a un sospechoso", "resumen": ""}])
        finally:
            ia._generar_json = orig
        self.assertEqual((r[0]["cat24"], r[0]["tipo24"], r[0]["quien24"]),
                         ("obras_servicios", "declaracion", "Municipio de Guayaquil"))
        self.assertEqual((r[1]["cat24"], r[1]["quien24"]), (None, ""))


def _entrada(eid, titulo, emb, horas=1, nombres=(), numeros=(), fechas=(), ciudad=""):
    ahora = dt.datetime.now(dt.timezone.utc)
    return {"fundador_titulo": titulo, "fundador_resumen": "", "rep_titulo": titulo, "rep_resumen": "",
            "fuentes": [{"link": "l-" + eid, "outlet": "M", "title": titulo}], "embedding": emb,
            "embedding_modelo": ia.EMBED_MODEL, "ultimo": ahora - dt.timedelta(hours=horas),
            "creado": ahora - dt.timedelta(hours=horas), "nombres": set(nombres), "numeros": set(numeros),
            "fechas": set(fechas), "ciudad": ciudad, "tokens": set(), "actualizaciones": []}


class TestC3MismoHecho(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (monitor._cargar_registro, monitor._guardar_registro, monitor.MISMO_HECHO_CACHE,
                     getattr(ia, "mismo_hecho_lote"))
        monitor.MISMO_HECHO_CACHE = os.path.join(self.tmp, "mh.json")
        # dos vectores con coseno ~0.75 (franja dudosa) y uno casi igual
        a, b = [1.0, 0.0], [0.75, 0.6614]
        self.reg = {
            "e1": _entrada("e1", "Militares hallan 250.000 dolares en un vehiculo", a, horas=3, numeros={"250000"}),
            "e2": _entrada("e2", "Un auto con 250 000 dolares fue descubierto en Guayaquil", b, horas=1, numeros={"250000"}),
            "e3": _entrada("e3", "Lluvias en Guayaquil: pronostico del 29 de septiembre", a, nombres={"guayaquil"},
                           fechas={"29-09"}),
            "e4": _entrada("e4", "Lluvias en Guayaquil: pronostico del 30 de septiembre", b, nombres={"guayaquil"},
                           fechas={"30-09"}),
        }
        self.guardado = []
        monitor._cargar_registro = lambda: {k: dict(v) for k, v in self.reg.items()}
        monitor._guardar_registro = lambda r: self.guardado.append(set(r))
        self.preguntas = []

        def juez(pares):
            self.preguntas.append([(x["titular"], y["titular"]) for x, y in pares])
            return [True] * len(pares)
        ia.mismo_hecho_lote = juez

    def tearDown(self):
        (monitor._cargar_registro, monitor._guardar_registro, monitor.MISMO_HECHO_CACHE, ia.mismo_hecho_lote) = self.orig

    def test_une_lo_que_la_ia_confirma_y_nunca_pregunta_por_plantillas(self):
        r = monitor._mismo_hecho_pendientes_registro()
        self.assertIn("+1 fusiones", r)
        self.assertEqual(len(self.preguntas), 1)
        self.assertEqual(len(self.preguntas[0]), 1)  # el par de pronosticos de fechas distintas ni se pregunta
        self.assertEqual(self.guardado, [{"e1", "e3", "e4"}])  # e2 absorbido por la mas vieja (e1)

    def test_cambiar_el_criterio_vuelve_a_evaluar(self):
        monitor._mismo_hecho_pendientes_registro()
        self.preguntas.clear()
        orig = monitor.MISMO_HECHO_VERSION
        monitor.MISMO_HECHO_VERSION = "otro"
        try:
            monitor._mismo_hecho_pendientes_registro()
        finally:
            monitor.MISMO_HECHO_VERSION = orig
        self.assertEqual(len(self.preguntas), 1)

    def test_la_decision_queda_en_cache(self):
        monitor._mismo_hecho_pendientes_registro()
        self.preguntas.clear()
        self.assertEqual(monitor._mismo_hecho_pendientes_registro(), "sin pares dudosos")
        self.assertEqual(self.preguntas, [])

    def test_lote_de_la_ia_ante_la_duda_no(self):
        orig = ia._generar_json
        ia._generar_json = lambda *a, **k: {"pares": [{"n": 1, "mismo": "si"}, {"n": 2, "mismo": "tal vez"}]}
        try:
            r = self.orig[3]([({"titular": "a"}, {"titular": "b"}), ({"titular": "c"}, {"titular": "d"})])
        finally:
            ia._generar_json = orig
        self.assertEqual(r, [True, None])


if __name__ == "__main__":
    unittest.main()
