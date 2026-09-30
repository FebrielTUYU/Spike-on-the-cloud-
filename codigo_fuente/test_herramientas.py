# -*- coding: utf-8 -*-
"""
Prueba del Bloque 2 (Parte F, Asistente): las herramientas de solo lectura
que el agente usa para consultar datos reales. No golpea Ollama ni internet
-- reemplaza herramientas._cargar por datos sinteticos (mismo patron que
test_notas.py: monkeypatch de la funcion de carga, no del disco real).

Corre con:  python test_herramientas.py
"""
import unittest

import herramientas as h


class TestHerramientas(unittest.TestCase):
    def setUp(self):
        self._orig_cargar = h._cargar
        self._archivos = {}
        h._cargar = lambda nombre, default: self._archivos.get(nombre, default)

    def tearDown(self):
        h._cargar = self._orig_cargar

    def _historia(self, titular, tema, ambito="local", link=None, seccion="seguridad",
                  interes=10, outlets=None):
        return {
            "titular": titular, "temas": [tema], "ambito": ambito, "seccion": seccion,
            "outlets": outlets or ["El Universo"], "n_outlets": len(outlets or ["El Universo"]),
            "resumen": "resumen de " + titular, "interes": interes, "hours": 5,
            "fuentes": [{"outlet": "El Universo", "title": titular,
                         "link": link or ("https://x.com/" + titular[:20]), "date": "2026-09-23T00:00:00"}],
            "veredicto": {"estado": "pendiente", "texto": "Todavia no procesado.", "citas": []},
        }

    def test_normalizar_tema_tolera_minuscula(self):
        self.assertEqual(h._normalizar_tema("carceles"), "Carceles")
        self.assertEqual(h._normalizar_tema("CARCELES"), "Carceles")
        self.assertEqual(h._normalizar_tema("Carceles"), "Carceles")
        self.assertIsNone(h._normalizar_tema(None))

    def test_buscar_historias_filtra_por_tema_normalizado(self):
        self._archivos["data.json"] = {"historias": [
            self._historia("Motin en carcel de Guayaquil", "Carceles", interes=50),
            self._historia("Nueva ley tributaria", "Impuestos", interes=90),
        ]}
        r = h.buscar_historias(tema="carceles")  # minuscula, a proposito
        self.assertEqual(len(r), 1)
        self.assertIn("Motin", r[0]["titular"])

    def test_buscar_historias_filtra_por_veredicto(self):
        contradice = self._historia("Nota con contradiccion", "Carceles")
        contradice["veredicto"] = {"estado": "contradice", "texto": "x", "citas": []}
        pendiente = self._historia("Nota pendiente", "Carceles")
        self._archivos["data.json"] = {"historias": [contradice, pendiente]}
        r = h.buscar_historias(tema="Carceles", veredicto="contradice")
        self.assertEqual(len(r), 1)
        self.assertIn("contradiccion", r[0]["titular"])

    def test_buscar_historias_ordena_por_interes(self):
        self._archivos["data.json"] = {"historias": [
            self._historia("Nota A", "Carceles", interes=10),
            self._historia("Nota B", "Carceles", interes=99),
        ]}
        r = h.buscar_historias(tema="Carceles")
        self.assertEqual(r[0]["titular"], "Nota B")

    def test_buscar_historias_tolera_sinonimo_de_ambito(self):
        self._archivos["data.json"] = {"historias": [
            self._historia("Nota local", "Carceles", ambito="local"),
            self._historia("Nota mundo", "Carceles", ambito="internacional"),
        ]}
        r = h.buscar_historias(tema="Carceles", ambito="Ecuador")  # sinonimo de "local"
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["titular"], "Nota local")

    def test_detalle_historia_por_clave(self):
        hist = self._historia("Nota puntual", "Carceles", link="https://x.com/nota-puntual")
        self._archivos["data.json"] = {"historias": [hist]}
        self._archivos["saved.json"] = []
        d = h.detalle_historia("https://x.com/nota-puntual")
        self.assertIsNotNone(d)
        self.assertEqual(d["titular"], "Nota puntual")

    def test_detalle_historia_no_encontrada_devuelve_none(self):
        self._archivos["data.json"] = {"historias": []}
        self._archivos["saved.json"] = []
        self.assertIsNone(h.detalle_historia("https://no-existe.com"))

    def test_tendencia_tema_promedio_coincide_con_el_dashboard(self):
        # misma cuenta que demandaTema() en dashboard_template.html:
        # slice(-8,-1) sobre la serie cruda.
        serie = list(range(1, 23))  # 1..22
        self._archivos["data.json"] = {
            "tendencias": {"Carceles": {"v": serie}},
            "gdelt": {}, "social": {}, "fuente_interes": "Wikipedia",
            "estado_interes": "ok", "estado_gdelt": "ok", "estado_social": "ok",
        }
        r = h.tendencia_tema("carceles")
        esperado = round(sum(serie[-8:-1]) / len(serie[-8:-1]))
        self.assertEqual(r["demanda_busqueda_0_100"], esperado)

    def test_tendencia_tema_sin_dato_no_inventa_numero(self):
        self._archivos["data.json"] = {"tendencias": {}, "gdelt": {}, "social": {}}
        r = h.tendencia_tema("Carceles")
        self.assertIsNone(r["demanda_busqueda_0_100"])
        self.assertIsNone(r["cobertura_prensa_gdelt"])
        self.assertIsNone(r["pulso_social"])

    def test_comparar_periodo_avisa_si_no_hay_historial_tan_viejo(self):
        self._archivos["history.json"] = [
            {"ts": "2026-09-22T00:00:00+00:00", "temas": {"Carceles": 5}},
            {"ts": "2026-09-23T00:00:00+00:00", "temas": {"Carceles": 8}},
        ]
        r = h.comparar_periodo(tema="Carceles", dias_atras=30)
        self.assertIsNotNone(r["nota"], "deberia avisar que el historial no llega tan atras")

    def test_buscar_guardadas_y_notas_vacio_sin_error(self):
        self.assertEqual(h.buscar_guardadas(), [])
        self.assertEqual(h.buscar_notas(), [])

    def test_buscar_contratos_sercop_termino_nunca_consultado(self):
        self._archivos["sercop_cache.json"] = {"ts": 0, "terms": {"salud": []}}
        r = h.buscar_contratos_sercop("educacion")
        self.assertFalse(r["consultado"])
        self.assertEqual(r["contratos"], [])


if __name__ == "__main__":
    unittest.main()
