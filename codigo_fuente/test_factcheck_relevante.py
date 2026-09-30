# -*- coding: utf-8 -*-
"""
Prueba del bug real reportado por Fernando (2026-09-23): la historia "Trump
Praises Burnham..." mostraba un ClaimReview sobre "Keir Starmer con la
camiseta de Croacia" calificado 'Falso' -- sin ninguna relacion real con la
nota (ni siquiera la misma persona).

Causas reales (ver _factcheck_relevante/get_factcheck en monitor.py):
  1) el filtro de relevancia solo se aplicaba al fallback por entidad, nunca
     a la busqueda primaria por titular completo.
  2) exigia solo 1 palabra compartida (muy debil).
  3) factcheck_cache.json no tiene version/vencimiento: una entrada mala
     cacheada de una corrida vieja se queda para siempre.

Corre con:  python test_factcheck_relevante.py  (no golpea internet)
"""
import unittest

import monitor


class TestFactcheckRelevante(unittest.TestCase):
    def test_caso_real_burnham_croacia_se_descarta(self):
        s = {
            "titular": 'Trump Praises Burnham as "Natural Business Person" After First Meeting',
            "resumen": ("Prime Minister Andy Burnham of Britain met with President Trump for "
                        "the first time on the sidelines of the U.N. General Assembly on Tuesday."),
        }
        resultados = [
            {"claim": "Esta imagen muestra a Keir Starmer, primer ministro de Reino Unido, "
                      "con la camiseta de Croacia durante el partido contra Inglaterra en el Mundial.",
             "calificacion": "Falso"},
            {"claim": "Macron guarda una bolsa de cocaina en una reunion con el primer "
                      "ministro britanico y el canciller aleman cuando se dirigian a Kiev.",
             "calificacion": "Falso."},
        ]
        filtrados = monitor._factcheck_relevante(s, resultados, excluir="Primer ministro del Reino Unido")
        self.assertEqual(filtrados, [], "dejo pasar un ClaimReview sin relacion real con la nota")

    def test_exige_dos_palabras_no_una(self):
        s = {"titular": "Asamblea Nacional aprueba reforma tributaria en Ecuador", "resumen": ""}
        # comparte SOLO "asamblea" (1 palabra) con el titular -- no debe alcanzar
        debil = [{"claim": "La Asamblea de Venezuela aprobo una ley de emergencia economica"}]
        self.assertEqual(monitor._factcheck_relevante(s, debil), [])
        # comparte "asamblea" Y "reforma" (2 palabras) -- si debe pasar
        fuerte = [{"claim": "La Asamblea Nacional de Ecuador debate la reforma tributaria del gobierno"}]
        self.assertEqual(len(monitor._factcheck_relevante(s, fuerte)), 1)

    def test_no_descarta_por_las_dudas_si_no_hay_base(self):
        s = {"titular": "a", "resumen": ""}  # titular sin ninguna palabra >=4 letras
        resultados = [{"claim": "cualquier cosa"}]
        self.assertEqual(monitor._factcheck_relevante(s, resultados), resultados)


if __name__ == "__main__":
    unittest.main()
