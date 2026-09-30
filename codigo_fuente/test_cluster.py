# -*- coding: utf-8 -*-
"""
Prueba del problema 5 (agrupamiento: "casi todas las historias quedan con
un solo medio", medido en produccion: 402/420 historias con n_outlets==1).

No golpea internet: arma articulos sinteticos con fecha y titular, iguales
en forma a los que devuelve parse_feed().

Corre con:  python test_cluster.py
"""
import datetime as dt
import unittest

import monitor


def _art(outlet, title, horas_atras=0):
    return {
        "outlet": outlet, "seccion": "auto", "title": title, "link": "",
        "date": monitor.now_utc() - dt.timedelta(hours=horas_atras),
        "summary": "", "image": "",
    }


class TestClusterUneMismaHistoriaEntreMedios(unittest.TestCase):
    def test_guayaquil_inundacion_se_une_aunque_bajo_el_umbral_general(self):
        """Caso real diagnosticado en produccion: 0.27 de similitud (bajo el
        umbral general 0.30), pero comparten el nombre propio 'Guayaquil'."""
        arts = [
            _art("El Universo", "Guayaquil amanecio con calles inundadas y "
                                 "caida de un arbol tras las lluvias"),
            _art("El Comercio", "Las lluvias anegan calles de Sauces y La "
                                 "Florida en el norte de Guayaquil"),
        ]
        clusters = monitor.cluster(arts)
        self.assertEqual(len(clusters), 1, "las dos notas del mismo hecho no se unieron")
        self.assertEqual(len(clusters[0]["articles"]), 2)

    def test_titulares_title_case_en_ingles_no_se_unen_por_palabras_comunes(self):
        """BUG REAL encontrado en vivo: 'Memoir'/'From'/'Takeaways' en Title
        Case ingles se contaban como 'nombre propio' y unian dos libros
        DISTINTOS (Ari Emanuel vs. Charles Spencer/Princess Diana)."""
        arts = [
            _art("NYT", "5 Takeaways From Ari Emanuel's Memoir"),
            _art("NYT", "Takeaways From Charles Spencer's Memoir, 'Swan Song,' "
                        "About Princess Diana"),
        ]
        clusters = monitor.cluster(arts)
        self.assertEqual(len(clusters), 2, "se unieron dos historias distintas por palabras Title Case")

    def test_ventana_de_tiempo_evita_union_de_hechos_distintos_muy_separados(self):
        """Dos notas con vocabulario parecido pero semanas de distancia no
        deberian unirse solo por coincidencia de palabras/nombre propio."""
        arts = [
            _art("El Universo", "Incendio en Guayaquil deja danos materiales", horas_atras=0),
            _art("El Comercio", "Nuevo incendio en Guayaquil afecta a comerciantes", horas_atras=24 * 20),
        ]
        clusters = monitor.cluster(arts)
        self.assertEqual(len(clusters), 2, "se unieron hechos separados por 20 dias")

    def test_no_rompe_el_caso_normal_titulares_casi_identicos(self):
        arts = [
            _art("El Universo", "Asamblea Nacional aprueba en primer debate la reforma tributaria"),
            _art("El Comercio", "La Asamblea de Ecuador debate la reforma tributaria del Gobierno"),
        ]
        clusters = monitor.cluster(arts)
        self.assertEqual(len(clusters), 1)


if __name__ == "__main__":
    unittest.main()
