# -*- coding: utf-8 -*-
"""
Fase 10, parte A -- transporte de ia.py contra la API REST de Gemini.

No golpea la red real: monkeypatchea urllib.request.urlopen con respuestas
fabricadas. Aisla ia_gasto.json/ia_nube_estado.json en un directorio
temporal. Corre con:  python test_fase10_gemini.py
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request

import ia


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _modelos_ok():
    return _FakeResponse({"models": [{"name": "models/%s" % ia.MODELO_RAPIDO},
                                       {"name": "models/%s" % ia.MODELO_PROFUNDO},
                                       {"name": "models/%s" % ia.EMBED_MODEL}]})


def _respuesta_texto(texto, perfil_input=10, perfil_output=5):
    return {"candidates": [{"content": {"parts": [{"text": texto}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": perfil_input, "candidatesTokenCount": perfil_output}}


class _IaAislado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_gasto = ia.GASTO_PATH
        self._orig_estado = ia.ESTADO_PATH
        self._orig_key = ia.GEMINI_API_KEY
        ia.GASTO_PATH = os.path.join(self._tmp, "ia_gasto.json")
        ia.ESTADO_PATH = os.path.join(self._tmp, "ia_nube_estado.json")
        ia.GEMINI_API_KEY = "fake-key-de-prueba-nunca-real"
        self._orig_urlopen = urllib.request.urlopen
        self._orig_tope_dia = ia.TOPE_DIA_USD
        self._orig_tope_mes = ia.TOPE_MES_USD

    def tearDown(self):
        ia.GASTO_PATH = self._orig_gasto
        ia.ESTADO_PATH = self._orig_estado
        ia.GEMINI_API_KEY = self._orig_key
        urllib.request.urlopen = self._orig_urlopen
        ia.TOPE_DIA_USD = self._orig_tope_dia
        ia.TOPE_MES_USD = self._orig_tope_mes

    def _mock_secuencia(self, mapa_por_ruta):
        """'mapa_por_ruta': {substring_de_url: respuesta_o_excepcion (o lista
        de ellas, consumida en orden)}."""
        llamadas = []
        colas = {k: (list(v) if isinstance(v, list) else [v]) for k, v in mapa_por_ruta.items()}

        def _urlopen_falso(req, timeout=15):
            url = req.full_url
            llamadas.append((url, req.data))
            for sub, cola in colas.items():
                if sub in url:
                    if not cola:
                        raise AssertionError("se pidieron mas respuestas para %s de las esperadas" % sub)
                    item = cola.pop(0) if len(cola) > 1 or len(colas[sub]) == 1 else cola[0]
                    if len(mapa_por_ruta[sub]) > 1 or not isinstance(mapa_por_ruta[sub], list):
                        pass
                    if isinstance(item, Exception):
                        raise item
                    return item
            raise AssertionError("URL no mockeada: %s" % url)

        urllib.request.urlopen = _urlopen_falso
        return llamadas


class TestPayload(_IaAislado):
    def test_generar_arma_bien_el_payload_json(self):
        capturado = {}

        def _urlopen_falso(req, timeout=15):
            if "/models?" in req.full_url or req.full_url.endswith("/models"):
                return _modelos_ok()
            capturado["body"] = json.loads(req.data.decode("utf-8"))
            capturado["headers"] = dict(req.header_items())
            return _FakeResponse(_respuesta_texto('{"ok": true}'))

        urllib.request.urlopen = _urlopen_falso
        texto = ia._generar(prompt="hola", json_mode=True, perfil=ia.PERFIL_RAPIDO, max_tokens=50)
        self.assertEqual(texto, '{"ok": true}')
        self.assertEqual(capturado["body"]["contents"][0]["parts"][0]["text"], "hola")
        self.assertEqual(capturado["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(capturado["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"], "low")

    def test_generar_stream_arma_bien_el_payload_y_llama_on_delta(self):
        sse_lineas = [
            b'data: ' + json.dumps({"candidates": [{"content": {"parts": [{"text": "Hola"}]}}]}).encode() + b'\n',
            b'data: ' + json.dumps({"candidates": [{"content": {"parts": [{"text": " mundo"}]},
                                                       "finishReason": "STOP"}],
                                     "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3}}).encode() + b'\n',
        ]

        class _FakeStreamResp:
            def __init__(self, lineas):
                self._lineas = lineas

            def __iter__(self):
                return iter(self._lineas)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _urlopen_falso(req, timeout=15):
            if req.full_url.endswith("/models"):
                return _modelos_ok()
            self.assertIn("streamGenerateContent", req.full_url)
            self.assertIn("alt=sse", req.full_url)
            return _FakeStreamResp(sse_lineas)

        urllib.request.urlopen = _urlopen_falso
        deltas = []
        texto = ia._generar_stream("contame algo", deltas.append, perfil=ia.PERFIL_PROFUNDO, max_tokens=100)
        self.assertEqual(texto, "Hola mundo")
        self.assertEqual(deltas, ["Hola", " mundo"])


class TestClaveNuncaExpuesta(_IaAislado):
    def test_la_clave_no_aparece_en_last_error_ni_en_estado(self):
        def _urlopen_falso(req, timeout=15):
            if req.full_url.endswith("/models"):
                return _modelos_ok()
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"error":"nope"}'))

        urllib.request.urlopen = _urlopen_falso
        ia._generar(prompt="hola", perfil=ia.PERFIL_RAPIDO)
        self.assertNotIn(ia.GEMINI_API_KEY, str(ia.last_error))
        self.assertNotIn(ia.GEMINI_API_KEY, ia.estado())
        self.assertNotIn(ia.GEMINI_API_KEY, json.dumps(ia.estado_gasto()))


class TestReintentoYPausaPor429(_IaAislado):
    def test_429_reintenta_y_despues_pausa(self):
        llamadas = {"n": 0}

        def _urlopen_falso(req, timeout=15):
            if req.full_url.endswith("/models"):
                return _modelos_ok()
            llamadas["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {},
                                          io.BytesIO(b'{"error":{"message":"rate limited"}}'))

        urllib.request.urlopen = _urlopen_falso
        r = ia._generar(prompt="hola", perfil=ia.PERFIL_RAPIDO, timeout=5)
        self.assertIsNone(r)
        self.assertEqual(llamadas["n"], 3, "debio reintentar 2 veces ademas del intento original")
        self.assertTrue(ia._pausado(ia.PERFIL_RAPIDO))

    def test_cuota_cero_pausa_largo_sin_reintentar_de_mas(self):
        llamadas = {"n": 0}

        def _urlopen_falso(req, timeout=15):
            if req.full_url.endswith("/models"):
                return _modelos_ok()
            llamadas["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {},
                                          io.BytesIO(b'Quota exceeded, limit: 0, model: gemini-3.1-pro'))

        urllib.request.urlopen = _urlopen_falso
        r = ia._generar(prompt="hola", perfil=ia.PERFIL_PROFUNDO, timeout=5)
        self.assertIsNone(r)
        self.assertIn("facturacion", ia.last_error)


class TestBloqueoDeSeguridad(_IaAislado):
    def test_finish_reason_safety_devuelve_none(self):
        def _urlopen_falso(req, timeout=15):
            if req.full_url.endswith("/models"):
                return _modelos_ok()
            return _FakeResponse({"candidates": [{"content": {}, "finishReason": "SAFETY"}]})

        urllib.request.urlopen = _urlopen_falso
        r = ia._generar(prompt="una nota sensible de crimen organizado", perfil=ia.PERFIL_RAPIDO)
        self.assertIsNone(r)
        self.assertIn("bloqueada", ia.last_error)
        self.assertIn("SAFETY", ia.last_error)


class TestTopeDeGasto(_IaAislado):
    def test_tope_corta_antes_de_llamar(self):
        ia.TOPE_DIA_USD = 0.0000001  # tope minusculo a proposito

        def _urlopen_falso(req, timeout=15):
            if req.full_url.endswith("/models"):
                return _modelos_ok()
            raise AssertionError("no debio llegar a la red -- el presupuesto no alcanzaba")

        urllib.request.urlopen = _urlopen_falso
        r = ia._generar(prompt="hola" * 1000, perfil=ia.PERFIL_RAPIDO, max_tokens=500)
        self.assertIsNone(r)
        self.assertIn("presupuesto agotado", ia.last_error)


class TestModeloInexistente(_IaAislado):
    def test_modelo_inexistente_queda_reportado(self):
        ia.MODELO_RAPIDO_ORIG = ia.MODELO_RAPIDO
        modelo_falso = "gemini-no-existe-1.0"
        orig = ia.MODELO_RAPIDO
        ia.MODELO_RAPIDO = modelo_falso
        try:
            def _urlopen_falso(req, timeout=15):
                if req.full_url.endswith("/models"):
                    return _FakeResponse({"models": [{"name": "models/otro-modelo"}]})
                raise AssertionError("no debio llamar a generateContent con un modelo no confirmado")

            urllib.request.urlopen = _urlopen_falso
            self.assertFalse(ia._modelo_existe(modelo_falso))
            self.assertFalse(ia.disponible())
            self.assertIn(modelo_falso, ia.last_error)
        finally:
            ia.MODELO_RAPIDO = orig


class TestFallbackProfundoARapido(_IaAislado):
    def test_perfil_profundo_pausado_cae_a_rapido_y_funciona(self):
        ia._pausar(ia.PERFIL_PROFUNDO, 5, "prueba")
        llamadas_modelo = []

        def _urlopen_falso(req, timeout=15):
            if req.full_url.endswith("/models"):
                return _modelos_ok()
            llamadas_modelo.append(req.full_url)
            return _FakeResponse(_respuesta_texto("respuesta del modelo rapido"))

        urllib.request.urlopen = _urlopen_falso
        r = ia._generar(prompt="hola", perfil=ia.PERFIL_PROFUNDO)
        self.assertEqual(r, "respuesta del modelo rapido")
        self.assertTrue(any(ia.MODELO_RAPIDO in u for u in llamadas_modelo))
        self.assertFalse(any(ia.MODELO_PROFUNDO in u for u in llamadas_modelo))


if __name__ == "__main__":
    unittest.main(verbosity=2)
