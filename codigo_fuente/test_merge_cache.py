# -*- coding: utf-8 -*-
"""
Prueba del problema 3 (Oportunidades: faltan datos en cada sesion).

Bug real diagnosticado con datos de produccion: gdelt_cache.json solo tenia
1 tema de 20 posibles despues de dias corriendo, y social_cache.json solo 5
de 20 -- porque get_gdelt/get_demand/get_social escribian el cache ENTERO
con lo conseguido en ESA pasada, pisando los temas buenos de pasadas
anteriores en vez de sumarse.

Esta prueba corre 100% aislada: usa archivos de cache temporales (nunca los
del proyecto real) y modulos gdelt/trends/social con las funciones de red
reemplazadas por datos falsos -- no toca internet ni los caches de Fernando.

Corre con:  python test_merge_cache.py
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import monitor


def _expirar_cache(path):
    """Fuerza el 'ts' del cache a 0 para que la proxima llamada no lea el
    cache fresco de la pasada anterior sin mas -- en produccion esto pasa
    solo cuando el TTL (3h/6h) vence de verdad; aca se simula para poder
    probar dos pasadas reales en el mismo test."""
    with open(path, encoding="utf-8") as f:
        cache = json.load(f)
    cache["ts"] = 0
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


class TestMergeNoPisaCacheAnterior(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = {
            "GDELT_CACHE": monitor.GDELT_CACHE,
            "TREND_CACHE": monitor.TREND_CACHE,
            "SOCIAL_CACHE": monitor.SOCIAL_CACHE,
        }
        monitor.GDELT_CACHE = os.path.join(self.tmpdir, "gdelt_cache.json")
        monitor.TREND_CACHE = os.path.join(self.tmpdir, "trends_cache.json")
        monitor.SOCIAL_CACHE = os.path.join(self.tmpdir, "social_cache.json")

    def tearDown(self):
        monitor.GDELT_CACHE = self._orig["GDELT_CACHE"]
        monitor.TREND_CACHE = self._orig["TREND_CACHE"]
        monitor.SOCIAL_CACHE = self._orig["SOCIAL_CACHE"]

    def test_gdelt_acumula_temas_entre_pasadas_con_429_parcial(self):
        """Pasada 1: solo 'Ejecutivo' responde (el resto 429). Pasada 2: solo
        'Salud' responde. El cache final debe tener LOS DOS, no solo el
        ultimo -- eso es exactamente lo que fallaba en produccion."""
        temas = ["Ejecutivo", "Salud", "Ambiente"]
        with mock.patch.object(monitor.gdelt, "interest") as m_interest, \
             mock.patch.object(monitor.gdelt, "last_error", "HTTP 429"):
            m_interest.return_value = {"Ejecutivo": {"vol": [1, 2], "tone": -1.0, "tone_series": [-1]}}
            data, estado = monitor.get_gdelt(temas, modo_lectura=False)
        self.assertIn("Ejecutivo", data)
        self.assertNotIn("Salud", data)  # todavia no llego su turno

        _expirar_cache(monitor.GDELT_CACHE)  # simula que paso el TTL (3h) hasta la pasada 2
        with mock.patch.object(monitor.gdelt, "interest") as m_interest, \
             mock.patch.object(monitor.gdelt, "last_error", "HTTP 429"):
            m_interest.return_value = {"Salud": {"vol": [3, 4], "tone": 0.5, "tone_series": [1]}}
            data2, estado2 = monitor.get_gdelt(temas, modo_lectura=False)

        # el bug real: antes 'Ejecutivo' desaparecia aca porque se pisaba el cache entero
        self.assertIn("Ejecutivo", data2, "se perdio el tema de la pasada anterior (bug real)")
        self.assertIn("Salud", data2)
        self.assertEqual(len(data2), 2)

        with open(monitor.GDELT_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        self.assertEqual(set(cache["g"].keys()), {"Ejecutivo", "Salud"})
        self.assertEqual(set(cache["g_ts"].keys()), {"Ejecutivo", "Salud"})

    def test_demand_acumula_temas_entre_pasadas(self):
        temas = ["Ejecutivo", "Salud"]
        with mock.patch.object(monitor, "_trends_demand") as m_trends:
            m_trends.return_value = ({"Ejecutivo": 40}, {"Ejecutivo": {"v": [1], "t": ["h"]}}, None)
            vals, tend, estado, fuente = monitor.get_demand(temas, modo_lectura=False)
        self.assertIn("Ejecutivo", vals)

        _expirar_cache(monitor.TREND_CACHE)
        with mock.patch.object(monitor, "_trends_demand") as m_trends:
            m_trends.return_value = ({"Salud": 70}, {"Salud": {"v": [2], "t": ["h"]}}, None)
            vals2, tend2, estado2, fuente2 = monitor.get_demand(temas, modo_lectura=False)

        self.assertIn("Ejecutivo", vals2, "se perdio el tema de la pasada anterior (bug real)")
        self.assertIn("Salud", vals2)

    def test_social_acumula_temas_entre_pasadas(self):
        temas = ["Ejecutivo", "Salud"]

        class FakePost:
            def __init__(self, fuente):
                self.fuente = fuente; self.autor = "x"; self.texto = "texto"
                self.url = "http://x"; self.likes = 1; self.reposts = 0; self.fecha = "2026-09-23"
                self.tipo = "persona"; self.canal = ""; self.canal_tipo = ""; self.canal_subs = None

        with mock.patch.object(monitor.social, "recolectar") as m_rec, \
             mock.patch.object(monitor.social, "analizar_osint", return_value=None):
            m_rec.side_effect = lambda query, **kw: (
                [FakePost("bluesky")] if "Ejecutivo" in query or query == monitor.TREND_TERMS.get("Ejecutivo", "Ejecutivo") else [], None)
            monitor.SOCIAL_MAX = 1  # fuerza a que solo procese 1 tema por pasada
            data, estado = monitor.get_social(["Ejecutivo"], modo_lectura=False)
        self.assertIn("Ejecutivo", data)

        _expirar_cache(monitor.SOCIAL_CACHE)
        with mock.patch.object(monitor.social, "recolectar") as m_rec, \
             mock.patch.object(monitor.social, "analizar_osint", return_value=None):
            m_rec.side_effect = lambda query, **kw: ([FakePost("reddit")], None)
            data2, estado2 = monitor.get_social(["Salud"], modo_lectura=False)

        self.assertIn("Ejecutivo", data2, "se perdio el tema de la pasada anterior (bug real)")
        self.assertIn("Salud", data2)


class TestSaludFuentes(unittest.TestCase):
    def test_distingue_ok_error_y_desactivado(self):
        self.assertTrue(monitor._fuente_ok("ok (Google Trends, 20/20 temas)"))
        self.assertTrue(monitor._fuente_ok("cache vencido (1 temas acumulados)"))
        self.assertFalse(monitor._fuente_ok("error: HTTP 429"))
        self.assertFalse(monitor._fuente_ok("esperando primera pasada del trabajador"))
        self.assertIsNone(monitor._fuente_ok("desactivado"))

    def test_construir_salud_fuentes_no_pierde_ninguna_fuente(self):
        report = [("El Universo", "politica", 10, "ok"), ("Wambra", "auto", 0, "HTTP 429")]
        fuentes = monitor.construir_salud_fuentes(
            report, "ok (Google Trends, 20/20 temas)", "cache vencido (1 temas acumulados)",
            "ok (+2 nuevos)", "ok (12 nuevos)", "ok (5 temas, OSINT en 3)",
            "ok (4 nuevas)", "ok (3 nuevas)")
        nombres = {f["fuente"] for f in fuentes}
        # Fase 9 (Problema A1) sumo una fuente mas: "Embeddings (agrupamiento)".
        self.assertEqual(len(fuentes), 9)
        self.assertIn("Feeds RSS", nombres)
        feeds = next(f for f in fuentes if f["fuente"] == "Feeds RSS")
        self.assertFalse(feeds["ok"])  # Wambra fallo -> no todos los feeds ok
        self.assertIn("1/2 feeds", feeds["detalle"])


if __name__ == "__main__":
    unittest.main()
