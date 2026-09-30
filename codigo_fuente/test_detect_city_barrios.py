# -*- coding: utf-8 -*-
"""
Prueba de la Fase 1 (2026-09-23/24): barrios de Guayaquil agregados a
detect_city() con evidencia real de titulares del dia. Cuida que ninguno
colisione con palabras comunes (mismo criterio que canar/napo/kennedy).

Corre con:  python test_detect_city_barrios.py
"""
import unittest

import monitor as m


class TestBarriosGuayaquil(unittest.TestCase):
    def test_barrios_reales_detectan_guayaquil(self):
        casos = [
            "Sicariato deja dos muertos en Pascuales",
            "Incendio consume local comercial en Urdesa",
            "Operativo militar en Isla Trinitaria deja varios detenidos",
            "Nuevo ataque armado registrado en Kennedy Norte esta madrugada",
            "Comerciantes de Flor de Bastion piden mas seguridad",
        ]
        for texto in casos:
            self.assertEqual(m.detect_city(texto), "Guayaquil", texto)

    def test_kennedy_solo_no_deberia_aparecer_como_termino_bare(self):
        # "Kennedy" sin "norte" NO debe estar en la lista (colisiona con JFK/
        # familia Kennedy en prensa internacional) -- se exige la frase completa.
        texto = "El aniversario del asesinato de John F. Kennedy se recuerda hoy"
        self.assertNotEqual(m.detect_city(texto), "Guayaquil")

    def test_duran_no_esta_como_termino_suelto(self):
        # Bug real encontrado en la Fase 1 probando Google News: "Duran" solo
        # colisiona con el apellido de un futbolista colombiano. No debe
        # matchear como ciudad via CITIES (queda cubierto por samborondon/
        # guayas si el texto trae mas contexto real).
        texto = "El futbolista Jhon Duran no fue convocado a la seleccion"
        self.assertNotEqual(m.detect_city(texto), "Guayaquil")


if __name__ == "__main__":
    unittest.main()
