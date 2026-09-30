# -*- coding: utf-8 -*-
"""
Embeddings -- Fase 10, Fases 3/4 (Gemini conectado).

Antes probaba el estado "sin backend" (Ollama retirado, Gemini todavia sin
conectar). Ahora que el transporte habla de verdad con la API REST de
Gemini, esto prueba: (1) sin GEMINI_API_KEY, todo apagado y sin red; (2) con
clave y modelo confirmado (mockeado), embed_disponible() da True y
embed()/embed_lote() arman el payload correcto; (3) el trabajador sigue sin
tocar el registro si el backend no esta listo.

No golpea la red real: monkeypatchea urllib.request.urlopen. Corre con:
python test_fase9_embeddings.py
"""
import json
import os
import unittest

import ia
import monitor as m


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _IaAislado(unittest.TestCase):
    def setUp(self):
        self._orig_key = ia.GEMINI_API_KEY
        self._orig_estado_path = ia.ESTADO_PATH
        self._orig_gasto_path = ia.GASTO_PATH
        import tempfile
        tmp = tempfile.mkdtemp()
        ia.ESTADO_PATH = os.path.join(tmp, "ia_nube_estado.json")
        ia.GASTO_PATH = os.path.join(tmp, "ia_gasto.json")
        import urllib.request
        self._orig_urlopen = urllib.request.urlopen

    def tearDown(self):
        ia.GEMINI_API_KEY = self._orig_key
        ia.ESTADO_PATH = self._orig_estado_path
        ia.GASTO_PATH = self._orig_gasto_path
        import urllib.request
        urllib.request.urlopen = self._orig_urlopen


class TestSinClave(_IaAislado):
    def test_todo_apagado_sin_clave(self):
        ia.GEMINI_API_KEY = ""
        self.assertFalse(ia.configurada())
        self.assertFalse(ia.backend_listo())
        self.assertFalse(ia.embed_disponible())
        self.assertIn("GEMINI_API_KEY", ia.estado_embeddings())
        self.assertIsNone(ia.embed("cualquier texto"))


class TestConClaveYModeloConfirmado(_IaAislado):
    def setUp(self):
        super().setUp()
        ia.GEMINI_API_KEY = "fake-key-de-prueba"

        def _urlopen_falso(req, timeout=15):
            if "models?" in req.full_url or req.full_url.endswith("/models"):
                return _FakeResponse({"models": [{"name": "models/%s" % ia.EMBED_MODEL},
                                                    {"name": "models/%s" % ia.MODELO_RAPIDO}]})
            if "embedContent" in req.full_url:
                return _FakeResponse({"embedding": {"values": [0.1, 0.2, 0.3]}})
            raise AssertionError("URL no mockeada: %s" % req.full_url)

        import urllib.request
        urllib.request.urlopen = _urlopen_falso

    def test_embed_disponible_true(self):
        self.assertTrue(ia.embed_disponible())
        self.assertIn("ok", ia.estado_embeddings())

    def test_embed_devuelve_vector_real(self):
        vec = ia.embed("Guayaquil amanecio con lluvias")
        self.assertEqual(vec, [0.1, 0.2, 0.3])
        self.assertIsNone(ia.last_error)

    def test_embed_registra_gasto(self):
        antes = ia.gasto_hoy()
        ia.embed("un texto cualquiera de prueba")
        self.assertGreaterEqual(ia.gasto_hoy(), antes)


class TestTrabajadorSinBackend(_IaAislado):
    def test_no_toca_el_registro_sin_clave(self):
        ia.GEMINI_API_KEY = ""
        orig = m._cargar_registro
        llamado = {"n": 0}

        def _no_deberia(*a, **k):
            llamado["n"] += 1
            return {}

        m._cargar_registro = _no_deberia
        try:
            estado = m._embed_pendientes_registro()
        finally:
            m._cargar_registro = orig
        self.assertIn("sin modelo de embeddings", estado)
        self.assertEqual(llamado["n"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
