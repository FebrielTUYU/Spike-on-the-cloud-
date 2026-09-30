# -*- coding: utf-8 -*-
"""
Prueba del Problema 4 (cuarta pasada, 2026-09-23): el ranking de interes
pesaba un medio internacional EXACTAMENTE igual que uno local
(s["n_outlets"] a secas), aunque build_stories() ya calculaba
'outlets_intl' y nunca se usaba para puntuar.

Caso real confirmado en la corrida en vivo: una historia sobre Delcy
Rodriguez (VP de Venezuela) encabezaba el ambito Ecuador con 9 medios, 7
internacionales y solo 2 locales (El Universo, Expreso).

Corre con:  python test_ranking_medios.py
"""
import unittest

import monitor


def _story(n_outlets, n_intl, es_local):
    return {"n_outlets": n_outlets, "outlets_intl": ["x"] * n_intl, "es_local": es_local}


class TestPesoDeMedios(unittest.TestCase):
    def test_ambito_local_medios_internacionales_pesan_menos(self):
        # 2 locales + 7 internacionales, ambito local (el caso real de Delcy Rodriguez)
        mayoria_intl = _story(n_outlets=9, n_intl=7, es_local=True)
        # 9 medios locales, ambito local -- deberia pesar mas que el caso de arriba
        todos_locales = _story(n_outlets=9, n_intl=0, es_local=True)
        self.assertLess(monitor._peso_outlets(mayoria_intl), monitor._peso_outlets(todos_locales),
                         "una historia con mayoria de medios internacionales no deberia pesar igual que una 100% local")

    def test_ambito_local_pocos_locales_no_encabezan_solos_con_muchos_intl(self):
        pocos_locales_muchos_intl = _story(n_outlets=9, n_intl=7, es_local=True)
        tres_locales_solos = _story(n_outlets=3, n_intl=0, es_local=True)
        self.assertLess(monitor._peso_outlets(pocos_locales_muchos_intl), monitor._peso_outlets(tres_locales_solos),
                         "9 medios (7 intl + 2 locales) no deberia pesar mas que 3 medios locales solos")

    def test_ambito_internacional_no_cambia_el_peso(self):
        # en historias de ambito internacional, la cobertura extranjera SI es la senal relevante
        s = _story(n_outlets=9, n_intl=7, es_local=False)
        self.assertEqual(monitor._peso_outlets(s), 9 * 40)


if __name__ == "__main__":
    unittest.main()
