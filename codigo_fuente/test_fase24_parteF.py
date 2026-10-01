# -*- coding: utf-8 -*-
"""
Fase 24, Parte F1 -- notificaciones de lo importante (reemplazan a "Ultima hora").
Sin red: ntfy y Windows no se llaman (enviar=False o dobles).
"""
import datetime as dt
import os
import tempfile
import unittest

import notificaciones as N


def _h(tit, horas=1, ciudad="Guayaquil", n=1, alto=False, cat="", link=None):
    return {"titular": tit, "hours": horas, "ciudad": ciudad, "ambito": "local", "n_outlets": n,
            "outlets": ["M%d" % i for i in range(n)], "alto_impacto": alto, "categoria": cat,
            "fuentes": [{"link": link or ("l-" + tit)}]}


class TestNotificaciones(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (N.CONFIG_PATH, N.ESTADO_PATH)
        N.CONFIG_PATH = os.path.join(self.tmp, "n.json")
        N.ESTADO_PATH = os.path.join(self.tmp, "ne.json")

    def tearDown(self):
        N.CONFIG_PATH, N.ESTADO_PATH = self.orig

    def test_primera_vez_solo_linea_base(self):
        r = N.procesar([_h("Balacera en Pascuales", alto=True)], enviar=False)
        self.assertIn("linea base", r["estado"])
        self.assertEqual(r["historial"], [])

    def test_avisa_lo_nuevo_una_sola_vez(self):
        N.procesar([], enviar=False)
        r = N.procesar([_h("Balacera en Pascuales", alto=True), _h("Feria de libros", n=1)], enviar=False)
        self.assertEqual([x["titulo"] for x in r["historial"]], ["Balacera en Pascuales"])
        r2 = N.procesar([_h("Balacera en Pascuales", alto=True)], enviar=False)
        self.assertEqual(len(r2["historial"]), 1)
        self.assertIn("0 nuevas", r2["estado"])

    def test_viejo_no_cuenta_como_nuevo(self):
        N.procesar([], enviar=False)
        r = N.procesar([_h("Balacera vieja", alto=True, horas=8)], enviar=False)
        self.assertEqual(r["historial"], [])

    def test_reglas_editables(self):
        N.procesar([], enviar=False)
        N.guardar_config({"reglas": {"alto_impacto": False, "historia_fuerte_min_medios": 2}})
        r = N.procesar([_h("Balacera en Pascuales", alto=True), _h("Corte de agua en el sur", n=2)], enviar=False)
        self.assertEqual([x["titulo"] for x in r["historial"]], ["Corte de agua en el sur"])
        self.assertEqual(N.config()["reglas"]["historia_fuerte_min_medios"], 2)
        N.guardar_config({"reglas": {"inventada": True}, "max_por_hora": 999})
        self.assertNotIn("inventada", N.config()["reglas"])
        self.assertEqual(N.config()["max_por_hora"], 100)

    def test_alertas_y_primicias(self):
        N.procesar([], enviar=False)
        r = N.procesar([], alertas=[{"id": "a1", "tipo": "inundacion", "lugar": "Sauces", "estado": "corroborado",
                                     "senales": [{"url": "u"}]}, {"id": "a2", "estado": "sin_confirmar"}],
                       funcionarios={"primicias": ["t1"], "tuits": [{"id": "t1", "nombre": "Ministro", "texto": "Capturamos a 5"},
                                                                    {"id": "t2", "nombre": "Ministro", "texto": "Hola"}]},
                       enviar=False)
        self.assertEqual(sorted(x["tipo"] for x in r["historial"]), ["alerta", "funcionario"])

    def test_tope_por_hora(self):
        N.procesar([], enviar=False)
        N.guardar_config({"max_por_hora": 1})
        mandados = []
        orig = N._mandar
        N._mandar = lambda items, conf, ahora: mandados.extend(items)
        try:
            r = N.procesar([_h("Uno", alto=True), _h("Dos", alto=True)], enviar=True)
            import time; time.sleep(0.2)
        finally:
            N._mandar = orig
        self.assertEqual(len(mandados), 1)
        self.assertEqual(sorted(x["enviado"] for x in r["historial"]), [False, True])

    def test_silencio(self):
        c = N.config()
        noche = dt.datetime(2026, 10, 1, 5, tzinfo=dt.timezone.utc)   # 00:00 en Ecuador
        dia = dt.datetime(2026, 10, 1, 17, tzinfo=dt.timezone.utc)    # 12:00 en Ecuador
        self.assertTrue(N._en_silencio(c, noche))
        self.assertFalse(N._en_silencio(c, dia))


if __name__ == "__main__":
    unittest.main()
