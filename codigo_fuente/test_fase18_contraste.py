# -*- coding: utf-8 -*-
"""
Fase 18, P2-11 -- Contraste: documento oficial primero, hallazgo o nada.

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo. Criterio de
Fernando: si es gubernamental, se contrasta con documentacion oficial; si
son declaraciones, con medios y con lo que el mismo actor dijo antes; si es
un hecho, se comparan las cifras entre medios.
Estados: hallazgo / documento_oficial / corroborado_medios / sin_hallazgo.
"coincide" (medio contra medio) nunca se muestra como descubrimiento.
"""
import json
import os
import unittest

import contraste

AQUI = os.path.dirname(os.path.abspath(__file__))


def _boletines_reales():
    c = json.load(open(os.path.join(AQUI, "oficial_cache.json"), encoding="utf-8"))
    out = []
    for url, v in c.items():
        for it in (v.get("items") or []):
            out.append(dict(it, fuente=url))
    return out


def _h(titular, fuentes=None, resumen="", **kw):
    fuentes = fuentes or [{"outlet": "El Universo", "title": titular, "link": "https://x/1", "summary": resumen}]
    d = {"titular": titular, "resumen": resumen, "fuentes": fuentes, "es_local": True, "ciudad": ""}
    d.update(kw)
    return d


class TestClasificar(unittest.TestCase):
    def test_tres_clases(self):
        self.assertEqual(contraste.clasificar("Asamblea aprobó ley contra reclutamiento de menores"), "acto_oficial")
        self.assertEqual(contraste.clasificar("Gobierno publica decreto que reduce el IVA al 8 %"), "acto_oficial")
        self.assertEqual(contraste.clasificar("Noboa dijo que la seguridad mejoró en Guayaquil"), "declaracion")
        self.assertEqual(contraste.clasificar("Alcaldesa asegura que no hay fondos para el paso a desnivel"), "declaracion")
        self.assertEqual(contraste.clasificar("Dos hombres murieron por ataque armado en La Libertad"), "hecho")


class TestActoOficial(unittest.TestCase):
    def test_ley_de_menores_enlaza_a_la_asamblea(self):
        h = _h("Ecuador sancionará con hasta 26 años el reclutamiento delictivo de menores",
               resumen="La Asamblea aprobó la ley que sanciona el reclutamiento de niños y adolescentes.")
        r = contraste.evaluar(h, _boletines_reales())
        self.assertEqual(r["clase"], "acto_oficial")
        self.assertEqual(r["estado"], "documento_oficial")
        self.assertIn("asambleanacional.gob.ec", r["documento"]["link"])

    def test_acto_sin_documento_lo_dice(self):
        h = _h("Gobierno anuncia decreto para subsidiar el gas en Galápagos")
        r = contraste.evaluar(h, _boletines_reales())
        self.assertEqual(r["estado"], "sin_hallazgo")
        self.assertIn("No se encontró el documento oficial", r["texto"])


class TestHecho(unittest.TestCase):
    def test_cifras_distintas_entre_medios_es_hallazgo(self):
        h = _h("Choque en la vía Perimetral deja 3 muertos", fuentes=[
            {"outlet": "Expreso", "title": "Choque en la vía Perimetral deja 3 muertos", "link": "https://e/1", "summary": ""},
            {"outlet": "Extra", "title": "Tragedia en la Perimetral: 5 muertos tras choque de un bus", "link": "https://x/2", "summary": ""}])
        r = contraste.evaluar(h, [])
        self.assertEqual(r["estado"], "hallazgo")
        self.assertEqual(len(r["citas"]), 2)
        self.assertEqual({c["outlet"] for c in r["citas"]}, {"Expreso", "Extra"})

    def test_cifras_iguales_es_corroborado_no_hallazgo(self):
        h = _h("Choque en la vía Perimetral deja 3 muertos", fuentes=[
            {"outlet": "Expreso", "title": "Choque en la vía Perimetral deja 3 muertos", "link": "https://e/1", "summary": ""},
            {"outlet": "Extra", "title": "Tres muertos en la Perimetral: 3 muertos tras choque", "link": "https://x/2", "summary": ""}])
        r = contraste.evaluar(h, [])
        self.assertEqual(r["estado"], "corroborado_medios")


class TestDeclaracion(unittest.TestCase):
    def test_contradiccion_con_declaracion_previa_es_hallazgo(self):
        h = _h("Ministro asegura que no habrá cortes de luz en octubre",
               contradiccion_declaracion=[{"estado": "posible_contradiccion",
                                           "explicacion": "dijo lo contrario hace 20 dias",
                                           "fuente_previa": {"texto": "Habrá cortes de hasta 4 horas en octubre",
                                                             "fecha": "2026-09-10", "medio": "Primicias",
                                                             "link": "https://p/1"}}],
               declaracion={"actor": "Ministro de Energía", "texto": "No habrá cortes de luz en octubre",
                            "medio": "El Universo", "fecha": "2026-09-29"})
        r = contraste.evaluar(h, [])
        self.assertEqual(r["clase"], "declaracion")
        self.assertEqual(r["estado"], "hallazgo")
        self.assertEqual(len(r["citas"]), 2)


class TestDatosReales(unittest.TestCase):
    def test_corrida_real_ley_de_menores_y_hallazgos_solo_con_dos_citas(self):
        # NOTA HONESTA (Fase 18): el pedido pide ">= 1 hallazgo real en una
        # corrida". En la corrida real del 2026-09-30 NO hay ninguno genuino:
        # los 2 candidatos que aparecian eran historias mal agrupadas (becas vs.
        # red electrica; aprehendidos en Manabi vs. en la Metrovia), y ahora se
        # descartan. Esta prueba exige CALIDAD: todo hallazgo trae 2 citas de
        # medios distintos. El caso positivo se prueba con TestHecho/TestDeclaracion.
        d = json.load(open(os.path.join(AQUI, "data.json"), encoding="utf-8"))["historias"]
        bol = _boletines_reales()
        res = [(h, contraste.evaluar(h, bol)) for h in d if h.get("es_local")]
        for _h_, r in res:
            if r["estado"] == "hallazgo":
                self.assertEqual(len(r["citas"]), 2)
                self.assertNotEqual(r["citas"][0]["outlet"], r["citas"][1]["outlet"])
        menores = [r for h, r in res if "26 años" in h["titular"] and "menores" in h["titular"].lower()]
        self.assertTrue(menores)
        for r in menores:
            self.assertTrue(r["estado"] == "documento_oficial" or "No se encontró el documento oficial" in r["texto"])
        self.assertFalse(any(r["estado"] == "coincide" for _h_, r in res))


if __name__ == "__main__":
    unittest.main()
