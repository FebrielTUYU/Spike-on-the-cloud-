# -*- coding: utf-8 -*-
"""
ia.interpretar() -- Lectura IA de cada tarjeta.

Hasta la Fase 9 esta prueba verificaba que interpretar() eligiera el modelo
pesado de Ollama (monitor-critico) con num_predict/timeout suficientes. Desde
la Fase 10 (migracion a la nube) no hay modelos locales: lo que importa es
que use el perfil PROFUNDO, con los ejemplos resueltos, y que el filtro
anti-parafrasis (es_literal) siga funcionando igual.

No golpea ninguna IA: monkeypatchea ia._generar. Corre con:
    python test_interpretar_modelo.py
"""
import unittest

import ia


class TestInterpretar(unittest.TestCase):
    def setUp(self):
        self._orig = ia._generar
        self.llamadas = []

    def tearDown(self):
        ia._generar = self._orig

    def _responde(self, *textos):
        cola = list(textos)
        def _gen(prompt="", **k):
            self.llamadas.append(k)
            return cola.pop(0) if cola else None
        ia._generar = _gen

    def test_usa_perfil_profundo_con_ejemplos_resueltos(self):
        self._responde("Lo relevante es quien paga el ajuste y si hay compensacion para transportistas.")
        texto = ia.interpretar("Gobierno sube el precio del diesel", "resumen")
        self.assertTrue(texto)
        k = self.llamadas[0]
        self.assertEqual(k["perfil"], ia.PERFIL_PROFUNDO)
        self.assertEqual(k["sistema"], ia._INTERP_SISTEMA)
        # 3 ejemplos (user+assistant) + la nota real
        self.assertEqual(len(k["mensajes"]), 2 * len(ia._INTERP_EJEMPLOS) + 1)

    def test_parafrasis_dos_veces_devuelve_vacio(self):
        self._responde("La noticia trata sobre el diesel.", "La nota informa sobre el diesel.")
        self.assertEqual(ia.interpretar("Gobierno sube el precio del diesel", ""), "")
        self.assertEqual(len(self.llamadas), 2)  # reintento una vez a mas temperatura

    def test_sin_backend_devuelve_none(self):
        # comportamiento real de la Fase 10 sin clave configurada: None (no "").
        # Se simula la ausencia de backend limpiando GEMINI_API_KEY -- no basta
        # con no mockear _generar, porque en esta PC .env SI tiene una clave real
        # (Fase 10 la conecto) y la llamada real nunca devolveria None por "sin backend".
        orig_key = ia.GEMINI_API_KEY
        ia.GEMINI_API_KEY = ""
        try:
            self.assertIsNone(ia.interpretar("Titular cualquiera", ""))
        finally:
            ia.GEMINI_API_KEY = orig_key


if __name__ == "__main__":
    unittest.main(verbosity=2)
