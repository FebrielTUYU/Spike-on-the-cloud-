# -*- coding: utf-8 -*-
"""
Prueba de la Fase 0 (2026-09-23): bug real confirmado en vivo -- CBC News manda
la fecha con SIGLA de zona horaria ("...EDT") en vez de offset numerico, y
Python's strptime con %Z no reconoce siglas como "EDT"/"PST" (solo un puñado
fijo, basicamente UTC/GMT). El 100% de las notas de CBC quedaba con
date=None, lo que le daba el peor bonus de recencia posible en el ranking sin
importar que tan nueva fuera en realidad -- sin ningun error visible.

Corre con:  python test_parse_date_tz.py
"""
import datetime as dt
import unittest

import monitor as m


class TestParseDateAbreviaturas(unittest.TestCase):
    def test_edt_caso_real_de_cbc(self):
        d = m.parse_date("Wed, 23 Sep 2026 13:06:11 EDT")
        self.assertIsNotNone(d, "EDT no deberia devolver None")
        self.assertEqual(d, dt.datetime(2026, 9, 23, 17, 6, 11, tzinfo=dt.timezone.utc))

    def test_otras_siglas_comunes(self):
        casos = {
            "Wed, 23 Sep 2026 13:00:00 PST": dt.datetime(2026, 9, 23, 21, 0, 0, tzinfo=dt.timezone.utc),
            "Wed, 23 Sep 2026 13:00:00 GMT": dt.datetime(2026, 9, 23, 13, 0, 0, tzinfo=dt.timezone.utc),
            "Wed, 23 Sep 2026 13:00:00 CEST": dt.datetime(2026, 9, 23, 11, 0, 0, tzinfo=dt.timezone.utc),
        }
        for texto, esperado in casos.items():
            self.assertEqual(m.parse_date(texto), esperado, texto)

    def test_offset_numerico_normal_no_se_rompe(self):
        d = m.parse_date("Tue, 22 Sep 2026 22:50:16 +0000")
        self.assertEqual(d, dt.datetime(2026, 9, 22, 22, 50, 16, tzinfo=dt.timezone.utc))

    def test_iso_normal_no_se_rompe(self):
        d = m.parse_date("2026-09-23T17:06:11Z")
        self.assertEqual(d, dt.datetime(2026, 9, 23, 17, 6, 11, tzinfo=dt.timezone.utc))

    def test_sigla_desconocida_no_rompe_el_parseo(self):
        # una sigla que no esta en el diccionario: no debe reventar, solo caer
        # a None si ningun formato calza (mejor un dato faltante que un crash).
        d = m.parse_date("Wed, 23 Sep 2026 13:06:11 XYZ")
        self.assertIsNone(d)


if __name__ == "__main__":
    unittest.main()
