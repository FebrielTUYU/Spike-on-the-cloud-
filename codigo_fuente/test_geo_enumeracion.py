# -*- coding: utf-8 -*-
"""
Prueba del bug real reportado por Fernando (2026-09-23, tercera ronda):
"las de Colombia se mezclan con la de Ecuador cuando la noticia no tiene
nada que ver con Ecuador". Caso real: una nota de Semana (Colombia) sobre
Alvaro Uribe hablando del "Escudo de las Americas" (alianza de ~15 paises)
quedaba marcada como historia LOCAL de Ecuador solo porque Ecuador aparecia
una vez en la enumeracion de paises miembro.

Corre con:  python test_geo_enumeracion.py  (no golpea internet)
"""
import unittest

import monitor


class TestEnumeracionDePaisesNoEsSenalLocal(unittest.TestCase):
    def test_caso_real_uribe_escudo_de_las_americas(self):
        texto = ("Alvaro Uribe celebra la consolidacion del Escudo de las Americas "
                 "El expresidente Alvaro Uribe se refirio a la segunda reunion del "
                 "Escudo de las Americas. Se trata de una alianza promovida por el "
                 "presidente Donald Trump que reune a Argentina, Bolivia, Chile, "
                 "Costa Rica, Ecuador, El Salvador, Guyana, Chile, Honduras, Panama, "
                 "Paraguay, Republica")
        self.assertFalse(monitor.is_ecuador(texto),
                          "una mencion suelta de Ecuador en una lista de 15 paises no debe contar como local")

    def test_no_rompe_casos_reales_de_ecuador(self):
        casos = [
            "Asamblea Nacional aprueba en primer debate la reforma tributaria en Ecuador",
            "Ecuador y Colombia reactivan su agenda bilateral y proponen gabinete binacional",
            "Daniel Noboa se reune con Kristi Noem como parte de su agenda en Estados Unidos",
            "Guayaquil amanecio con calles inundadas tras las lluvias",
            "El precio del diesel sube en Ecuador tras la focalizacion del subsidio",
        ]
        for c in casos:
            with self.subTest(c=c):
                self.assertTrue(monitor.is_ecuador(c))

    def test_enumeracion_con_senal_especifica_sigue_siendo_local(self):
        """Si ademas de la enumeracion hay una senal MAS especifica que el
        nombre del pais (una ciudad, una institucion), si debe contar."""
        texto = ("Cumbre reune a Argentina, Bolivia, Chile, Costa Rica y Ecuador: "
                 "la delegacion se reunio en Guayaquil para coordinar la agenda")
        self.assertTrue(monitor.is_ecuador(texto))

    def test_es_enumeracion_paises_cuenta_bien(self):
        pocos = "Ecuador y Colombia firman un acuerdo comercial"
        muchos = "Reunion entre Argentina, Bolivia, Chile, Peru y Venezuela sobre migracion"
        self.assertFalse(monitor._es_enumeracion_paises(monitor.norm(pocos)))
        self.assertTrue(monitor._es_enumeracion_paises(monitor.norm(muchos)))


if __name__ == "__main__":
    unittest.main()
