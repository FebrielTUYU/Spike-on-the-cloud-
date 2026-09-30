# -*- coding: utf-8 -*-
"""
Prueba del problema 6 (el contexto de Wikipedia describe a la persona, no
la situacion): ia.extraer_entidades_con_evento debe poder proponer un
candidato de EVENTO aparte de las entidades con nombre propio, y
extraer_entidades() (usada por el resto del pipeline) debe seguir
devolviendo solo la lista de entidades, sin romper compatibilidad.

No golpea ninguna IA: mockea ia._generar (punto unico de transporte desde la Fase 10).

Corre con:  python test_evento.py
"""
import json
import unittest
from unittest import mock

import ia


class TestExtraerEntidadesConEvento(unittest.TestCase):
    def setUp(self):
        self._modelo_patch = mock.patch.object(ia, "elegir_modelo", return_value="qwen2.5:3b")
        self._modelo_patch.start()

    def tearDown(self):
        self._modelo_patch.stop()

    def test_devuelve_entidades_y_evento_por_separado(self):
        resp = {"entidades": [{"nombre": "Daniel Noboa", "busqueda": "Daniel Noboa presidente de Ecuador"}],
                "evento": {"nombre": "Paro nacional de Ecuador de 2022", "busqueda": "Paro nacional de Ecuador de 2022"}}
        with mock.patch.object(ia, "_generar", return_value=json.dumps(resp)):
            entidades, evento = ia.extraer_entidades_con_evento("t", "r")
        self.assertEqual(len(entidades), 1)
        self.assertEqual(evento["nombre"], "Paro nacional de Ecuador de 2022")

    def test_evento_null_no_rompe(self):
        resp = {"entidades": [], "evento": None}
        with mock.patch.object(ia, "_generar", return_value=json.dumps(resp)):
            entidades, evento = ia.extraer_entidades_con_evento("t", "r")
        self.assertEqual(entidades, [])
        self.assertIsNone(evento)

    def test_evento_sin_nombre_se_descarta(self):
        resp = {"entidades": [], "evento": {"nombre": "", "busqueda": "algo"}}
        with mock.patch.object(ia, "_generar", return_value=json.dumps(resp)):
            _, evento = ia.extraer_entidades_con_evento("t", "r")
        self.assertIsNone(evento)

    def test_extraer_entidades_mantiene_compatibilidad(self):
        """El resto del pipeline (monitor.py, antes de este cambio) llama
        ia.extraer_entidades() esperando SOLO la lista -- no debe romperse."""
        resp = {"entidades": [{"nombre": "Quito", "busqueda": "Quito"}], "evento": None}
        with mock.patch.object(ia, "_generar", return_value=json.dumps(resp)):
            entidades = ia.extraer_entidades("t", "r")
        self.assertEqual(entidades, [{"nombre": "Quito", "busqueda": "Quito"}])


if __name__ == "__main__":
    unittest.main()
