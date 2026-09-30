# -*- coding: utf-8 -*-
"""
Fase 18, P2-13 -- Consulta general que si responde.

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo. Caso real (captura
de Fernando): "En el caso que queramos medir una noticia comunitaria en
Guayaquil para realizarla en los proximos dias, ¿que idea podriamos
trabajar?" -> el Asistente respondio "no tengo datos", con 121 historias de
Guayaquil en el feed (entre ellas las inundaciones). Causa: buscar_historias
no tenia filtro por ciudad y con q="noticia comunitaria Guayaquil" exigia 2
de 3 palabras ("comunitaria" casi nunca aparece).

Las pruebas usan el data.json REAL del repo. La prueba de punta a punta con
Gemini real solo corre con MONITOR_TEST_GEMINI=1 (gasta presupuesto).
"""
import os
import unittest

import agente
import herramientas

PREGUNTA = ("En el caso que queramos medir una noticia comunitaria en Guayaquil para realizarla en "
            "los próximos días, ¿qué idea podríamos trabajar?")


class TestFiltros(unittest.TestCase):
    def test_filtro_por_ciudad(self):
        r = herramientas.buscar_historias(ciudad="Guayaquil", limite=50)
        self.assertGreater(len(r), 10)
        self.assertTrue(all(x.get("ciudad") == "Guayaquil" for x in r))

    def test_filtro_por_barrio(self):
        r = herramientas.buscar_historias(barrio="Samborondón", limite=50)
        self.assertTrue(r)
        self.assertTrue(all("samborond" in (x["titular"] + " " + (x.get("resumen") or "")).lower() for x in r))


class TestReintentoDelAgente(unittest.TestCase):
    def test_q_sin_resultados_reintenta_con_ciudad(self):
        r = agente._ejecutar_herramienta("buscar_historias", {"q": "noticia comunitaria", "ciudad": "Guayaquil"})
        self.assertIsInstance(r, list)
        self.assertTrue(r, "con q sin coincidencias tiene que reintentar por ciudad y no devolver vacio")

    def test_senales_disponibles_como_herramienta(self):
        self.assertIn("senales_oportunidad", herramientas.HERRAMIENTAS)
        self.assertIn("ciudad", agente._PROMPT_DECISION)
        self.assertIn("senales_oportunidad", agente._PROMPT_DECISION)


@unittest.skipUnless(os.environ.get("MONITOR_TEST_GEMINI") == "1", "gasta presupuesto de Gemini")
class TestPreguntaRealConGemini(unittest.TestCase):
    def test_pregunta_de_la_captura(self):
        partes, progreso = [], []
        texto = agente.responder_stream(PREGUNTA, [], lambda d: partes.append(d), on_progreso=progreso.append)
        texto = texto or "".join(partes)
        self.assertTrue(texto)
        self.assertNotIn("no tengo datos", texto.lower())
        print("\n--- CONSULTAS ---\n" + "\n".join(progreso))
        print("--- RESPUESTA ---\n" + texto)


if __name__ == "__main__":
    unittest.main()
