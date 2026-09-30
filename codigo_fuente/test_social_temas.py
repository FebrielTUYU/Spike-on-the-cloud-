# -*- coding: utf-8 -*-
"""
Prueba del bug real grave reportado por Fernando (2026-09-23, tercera ronda):
"el pulso social sigue sin verificar y diferenciar bien entre internacional,
Ecuador y Guayaquil. No funciona."

Causa real encontrada: get_social() tomaba SIEMPRE 'themes[:SOCIAL_MAX]' --
los primeros N temas en orden ALFABETICO (themes_present ya llega
ordenado). Confirmado con social_cache.json real: los mismos 5 primeros
alfabeticos aparecian SIEMPRE, los otros 15 JAMAS. Si por casualidad
alfabetica ningun tema de un ambito caia en ese prefijo fijo, ese ambito
quedaba sin UNA SOLA publicacion, para siempre -- una exclusion total y
permanente, no intermitente.

Corre con:  python test_social_temas.py  (no golpea internet)
"""
import collections
import unittest

import monitor


class TestTemasPorRelevancia(unittest.TestCase):
    THEMES = sorted(["Ambiente", "Asamblea/Leyes", "Carceles", "Comercio/Inversion",
                      "Crimen/Violencia", "Educacion", "Ejecutivo", "Elecciones",
                      "Empleo", "Salud"])
    AMBITO = {"Ambiente": "guayaquil", "Asamblea/Leyes": "ecuador", "Carceles": "ecuador",
              "Comercio/Inversion": "ecuador", "Crimen/Violencia": "ecuador",
              "Educacion": "internacional", "Ejecutivo": "internacional",
              "Elecciones": "internacional", "Empleo": "internacional", "Salud": "internacional"}

    def test_no_repite_siempre_el_mismo_prefijo_alfabetico(self):
        """El bug real: antes, 200 llamadas daban EXACTAMENTE el mismo
        resultado (los primeros 5 alfabeticos) las 200 veces."""
        resultados = {tuple(sorted(monitor._temas_por_relevancia(self.THEMES, self.AMBITO, 5)))
                      for _ in range(50)}
        self.assertGreater(len(resultados), 1, "siempre elige exactamente el mismo conjunto de temas")

    def test_garantiza_los_tres_ambitos_cuando_hay_cupo(self):
        for _ in range(30):
            elegidos = monitor._temas_por_relevancia(self.THEMES, self.AMBITO, 5)
            ambitos = {self.AMBITO[t] for t in elegidos}
            self.assertEqual(ambitos, {"guayaquil", "ecuador", "internacional"},
                              "no garantiza representacion de los 3 ambitos")

    def test_con_el_tiempo_todos_los_temas_tienen_chance(self):
        contador = collections.Counter()
        for _ in range(300):
            for t in monitor._temas_por_relevancia(self.THEMES, self.AMBITO, 5):
                contador[t] += 1
        # con el bug real, 15/20 temas del catalogo completo daban 0 SIEMPRE;
        # aca, con 10 temas de prueba, ninguno deberia quedar en 0.
        for t in self.THEMES:
            self.assertGreater(contador[t], 0, "%r nunca fue elegido en 300 pasadas" % t)

    def test_nunca_elige_mas_de_max_temas(self):
        elegidos = monitor._temas_por_relevancia(self.THEMES, self.AMBITO, 5)
        self.assertEqual(len(elegidos), 5)
        self.assertEqual(len(set(elegidos)), 5)  # sin duplicados


if __name__ == "__main__":
    unittest.main()
