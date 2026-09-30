# -*- coding: utf-8 -*-
"""
Prueba del Problema 4 (cuarta pasada, 2026-09-23): en dias de un evento
grande cubierto por muchos medios a la vez (ej. semana de la Asamblea
General de la ONU), el enlace por MAXIMO (single-linkage) de cluster()
encadenaba historias DISTINTAS que solo compartian palabras de SEDE/EVENTO
("Nueva York", "Asamblea General", "ONU"), no el hecho puntual.

Caso real que disparo el bug: una nota de El Universo sobre Daniel
Noboa/Ecuador en la Asamblea General de la ONU termino agrupada junto con
Delcy Rodriguez/Trump, Iran, Cuba y la realeza europea -- y como el grupo
mezclado SI mencionaba "Ecuador" en una nota, toda la historia (10 medios,
8 internacionales) se clasifico como ambito local, encabezando el ambito
Ecuador sin que ningun medio ecuatoriano cubriera realmente ese angulo.

No golpea internet: arma articulos sinteticos con fecha y titular, iguales
en forma a los que devuelve parse_feed().

Corre con:  python test_cluster_evento_generico.py
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


class TestClusterNoEncadenaPorPalabrasDeEvento(unittest.TestCase):
    def test_nota_de_ecuador_no_se_encadena_via_sede_del_evento(self):
        """Caso real: la nota de Noboa/Ecuador NO debe terminar en el mismo
        cluster que Delcy Rodriguez/Trump solo por compartir 'Asamblea
        General'/'Nueva York'/'ONU'."""
        arts = [
            _art("El Universo", "Daniel Noboa y delegacion de Ecuador "
                                 "participan en la Asamblea General de la "
                                 "ONU, en Nueva York"),
            _art("ABC.es (Internacional)",
                 "Asamblea General de la ONU, en directo: discurso de Pedro "
                 "Sanchez, Zelenski y Delcy Rodriguez y ultima hora desde "
                 "Nueva York hoy"),
            _art("Clarin", "Giro de Donald Trump sobre Iran: negociaciones "
                            "de tres horas en Nueva York tras amenazar con "
                            "aniquilar al regimen persa"),
        ]
        clusters = monitor.cluster(arts)
        self.assertEqual(len(clusters), 3,
                          "tres historias distintas se encadenaron por compartir la sede del evento")

    def test_la_misma_historia_real_sigue_uniendo_varios_medios(self):
        """El arreglo no debe romper el caso normal: varios medios
        cubriendo el MISMO hecho puntual (no solo la sede) siguen
        agrupandose."""
        arts = [
            _art("El Pais (Espana)", "Trump y Delcy Rodriguez sellan el "
                                      "deshielo entre Caracas y Washington "
                                      "con un encuentro a puerta cerrada en "
                                      "Nueva York"),
            _art("La Nacion (AR)", "Delcy Rodriguez califico su primer "
                                    "encuentro con Donald Trump en Nueva "
                                    "York como una reunion historica"),
            _art("Clarin", "Tras un inedito cara a cara con Trump, Delcy "
                            "Rodriguez habla en la Asamblea General de la "
                            "ONU, en el primer discurso de Venezuela en "
                            "ocho anos"),
        ]
        clusters = monitor.cluster(arts)
        self.assertEqual(len(clusters), 1,
                          "la misma historia real (Delcy Rodriguez + Trump) se separo de mas")
        self.assertEqual(len(clusters[0]["articles"]), 3)


if __name__ == "__main__":
    unittest.main()
