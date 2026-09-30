# -*- coding: utf-8 -*-
"""
Fase 9, Problema D (version Apify) -- X via un actor de terceros de Apify,
sin cuenta logueada, autorizado por Fernando SOLO como prueba de un mes.

No golpea la red real (Apify cobra de verdad): monkeypatchea
urllib.request.urlopen con respuestas fabricadas con la FORMA REAL verificada
en vivo el 2026-09-26 (ver CLAUDE.md / docstring de xapi.py), y aisla
x_gasto.json/x_cache.json/x_config.json en un directorio temporal. Corre con:
python test_fase9_xapi.py
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error

import xapi


def _tweet(id_, text, reply_count=0, conversation_id=None, author=None):
    return {
        "id": id_, "text": text, "createdAt": "Sat Sep 26 00:44:19 +0000 2026",
        "url": "https://x.com/i/web/status/%s" % id_, "conversationId": conversation_id or id_,
        "isReply": False, "inReplyToId": None, "replyCount": reply_count, "likeCount": 3,
        "retweetCount": 1, "quoteCount": 0, "viewCount": 500, "lang": "es",
        "author": author or {"userName": "alguien", "name": "Alguien", "location": "Guayaquil, Ecuador",
                              "followers": 100, "isBlueVerified": False, "description": "vecino de Guayaquil"},
    }


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run_ok(run_id="run1", dataset_id="ds1"):
    return {"data": {"id": run_id, "defaultDatasetId": dataset_id, "status": "SUCCEEDED"}}


class _XApiAislado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_gasto = xapi.GASTO_PATH
        self._orig_cache = xapi.CACHE_PATH
        self._orig_config = xapi.CONFIG_PATH
        xapi.GASTO_PATH = os.path.join(self._tmp, "x_gasto.json")
        xapi.CACHE_PATH = os.path.join(self._tmp, "x_cache.json")
        xapi.CONFIG_PATH = os.path.join(self._tmp, "x_config.json")
        import urllib.request
        self._orig_urlopen = urllib.request.urlopen
        self._orig_tope_dia = xapi.TOPE_DIA_USD
        self._orig_tope_mes = xapi.TOPE_MES_USD
        self._orig_env = os.environ.get("MONITOR_APIFY_TOKEN")
        self._orig_backend = xapi.BACKEND
        xapi.BACKEND = "apify"

    def tearDown(self):
        xapi.GASTO_PATH = self._orig_gasto
        xapi.CACHE_PATH = self._orig_cache
        xapi.CONFIG_PATH = self._orig_config
        import urllib.request
        urllib.request.urlopen = self._orig_urlopen
        xapi.TOPE_DIA_USD = self._orig_tope_dia
        xapi.TOPE_MES_USD = self._orig_tope_mes
        xapi.BACKEND = self._orig_backend
        if self._orig_env is None:
            os.environ.pop("MONITOR_APIFY_TOKEN", None)
        else:
            os.environ["MONITOR_APIFY_TOKEN"] = self._orig_env

    def _con_token(self, token="fake-apify-token"):
        os.environ["MONITOR_APIFY_TOKEN"] = token

    def _mock_secuencia(self, respuestas):
        """Cada llamada a urlopen consume la siguiente respuesta de la lista
        (en orden: POST /runs, GET /datasets/.../items, GET /actor-runs/...)."""
        cola = list(respuestas)
        llamadas = []

        def _urlopen_falso(req, timeout=15):
            llamadas.append(req.full_url if hasattr(req, "full_url") else req)
            if not cola:
                raise AssertionError("se pidieron mas respuestas HTTP de las esperadas")
            item = cola.pop(0)
            if isinstance(item, Exception):
                raise item
            return _FakeResponse(item)

        import urllib.request
        urllib.request.urlopen = _urlopen_falso
        return llamadas


class TestSinToken(_XApiAislado):
    def test_desactivado_sin_token(self):
        os.environ.pop("MONITOR_APIFY_TOKEN", None)
        self.assertFalse(xapi.activo())
        items, costo = xapi.buscar_historia("Samborondon CJNG")
        self.assertIsNone(items)
        self.assertEqual(costo, 0.0)
        self.assertIn("token", xapi.last_error.lower())

    def test_config_json_tambien_activa(self):
        os.environ.pop("MONITOR_APIFY_TOKEN", None)
        with open(xapi.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"apify_token": "desde-config"}, f)
        self.assertTrue(xapi.activo())

    def test_estado_dashboard_nunca_incluye_el_token(self):
        self._con_token("token-secreto-123")
        estado = xapi.estado_dashboard()
        self.assertNotIn("token-secreto-123", json.dumps(estado))
        self.assertNotIn("token-secreto-123", str(xapi.last_error))


class TestSimulacion(_XApiAislado):
    def test_simular_no_hace_red(self):
        self._con_token()
        llamadas = self._mock_secuencia([])
        items, costo = xapi.buscar_historia("Samborondon CJNG", max_items=25, simular=True)
        self.assertEqual(len(llamadas), 0)
        self.assertTrue(items.get("_simulado"))
        self.assertEqual(xapi.gasto_hoy(), 0.0)

    def test_simular_funcion_no_necesita_token(self):
        os.environ.pop("MONITOR_APIFY_TOKEN", None)
        historias = [{"titular": "Operativo en Samborondon", "query": "Samborondon CJNG"}]
        plan = xapi.simular(historias, ["incendio", "balacera"], ["Alborada", "Sauces"])
        self.assertGreater(len(plan["plan"]), 0)
        self.assertGreater(plan["costo_proyectado_dia"], 0)
        self.assertTrue(plan["dentro_del_tope_dia"])

    def test_pasada_en_modo_simulacion_no_llama_a_la_red(self):
        self._con_token()
        llamadas = self._mock_secuencia([])
        estado = xapi.pasada([{"titular": "t1", "query": "q1"}], ["incendio"], ["Alborada"], simular_red=True)
        self.assertIn("SIMULACION", estado)
        self.assertEqual(len(llamadas), 0)
        self.assertEqual(xapi.gasto_mes(), 0.0)


class TestPresupuesto(_XApiAislado):
    def test_tope_diario_corta_antes_de_la_red(self):
        self._con_token()
        xapi.TOPE_DIA_USD = 0.001  # tope minusculo a proposito
        llamadas = self._mock_secuencia([])
        items, costo = xapi.buscar_historia("algo", max_items=25)
        self.assertIsNone(items)
        self.assertEqual(len(llamadas), 0)
        self.assertIn("tope diario", xapi.last_error)

    def test_request_exitosa_registra_costo_real_de_la_corrida(self):
        self._con_token()
        tweets = [_tweet("1", "Lluvias intensas en Guayaquil esta noche")]
        self._mock_secuencia([
            _run_ok(),
            tweets,
            {"data": {"usageTotalUsd": 0.00625}},  # costo real reportado por Apify
        ])
        items, costo = xapi.buscar_historia("Guayaquil lluvias", max_items=25)
        self.assertEqual(len(items), 1)
        self.assertAlmostEqual(costo, 0.00625, places=6)
        self.assertAlmostEqual(xapi.gasto_hoy(), 0.00625, places=6)

    def test_sin_costo_real_usa_el_estimado(self):
        self._con_token()
        self._mock_secuencia([_run_ok(), [], Exception("sin info de costo")])
        items, costo = xapi.buscar_historia("algo", max_items=10)
        self.assertAlmostEqual(costo, 10 * xapi.PRECIO_TWEET_PRINCIPAL, places=6)


class TestDedupPorId(_XApiAislado):
    def test_id_repetido_no_se_procesa_dos_veces(self):
        self._con_token()
        tweets = [_tweet("100", "incendio Guayaquil sector norte"), _tweet("200", "otro incendio Guayaquil")]
        self._mock_secuencia([_run_ok(), tweets, {"data": {}}])
        nuevos1, _costo = xapi.buscar_alertas_gye(["incendio"], ["Alborada"], max_items=10)
        self.assertEqual(len(nuevos1), 2)
        # segunda corrida: el actor devuelve los MISMOS tweets otra vez (comun
        # en un scraper sin since_id real) -- no deben contarse de nuevo.
        self._mock_secuencia([_run_ok(run_id="run2", dataset_id="ds2"), tweets, {"data": {}}])
        nuevos2, _costo2 = xapi.buscar_alertas_gye(["incendio"], ["Alborada"], max_items=10)
        self.assertEqual(len(nuevos2), 0, "los ids ya vistos no debian procesarse de nuevo")


class TestErrorHTTP(_XApiAislado):
    def test_402_queda_reportado_sin_cobro(self):
        self._con_token()

        def _urlopen_falso(req, timeout=15):
            raise urllib.error.HTTPError(req.full_url, 402, "Payment Required", {}, io.BytesIO(b""))

        import urllib.request
        urllib.request.urlopen = _urlopen_falso
        items, costo = xapi.buscar_historia("algo")
        self.assertIsNone(items)
        self.assertEqual(costo, 0.0)
        self.assertIn("402", xapi.last_error)
        self.assertEqual(xapi.gasto_mes(), 0.0)


class TestAlertasYClasificacionAutor(_XApiAislado):
    def test_tweet_emergencias_ec_crea_alerta_de_inundacion(self):
        import alertas
        tmp2 = tempfile.mkdtemp()
        # aislar el registro de alertas (mismo patron que test_problema3_alertas.py)
        orig_alertas_path = alertas.ALERTAS_PATH
        alertas.ALERTAS_PATH = os.path.join(tmp2, "alertas.json")
        try:
            tweet = _tweet("500", "Se reportan inundaciones en varios sectores de Guayaquil. Confirmen",
                            reply_count=25, author={"userName": "EmergenciasEc", "name": "Emergencias Ecuador",
                                                     "location": "Guayaquil, Ecuador", "followers": 5000,
                                                     "isBlueVerified": True, "description": "Alertas ciudadanas"})
            r = alertas.registrar_senal("x", tweet["author"]["userName"], tweet["text"], tweet["url"],
                                          "", oficial=False)
            self.assertIsNotNone(r, "el texto de inundacion en Guayaquil debio reconocerse como alerta")
            self.assertEqual(r["tipo"], "inundacion")
        finally:
            alertas.ALERTAS_PATH = orig_alertas_path

    def test_tweet_de_medio_no_cuenta_como_voz_ciudadana(self):
        tweet_medio = _tweet("600", "Expreso informa: fuertes lluvias afectan Guayaquil",
                              author={"userName": "Expreso_ec", "name": "Diario Expreso",
                                      "location": "Guayaquil, Ecuador", "followers": 200000,
                                      "isBlueVerified": True, "description": "Diario de Guayaquil"})
        self.assertEqual(xapi.clasificar_autor(tweet_medio), "medio")

    def test_tweet_de_persona_cuenta_como_voz_ciudadana(self):
        tweet_persona = _tweet("700", "que fuerte la lluvia en mi barrio",
                                author={"userName": "juanperez88", "name": "Juan Perez",
                                        "location": "Guayaquil", "followers": 30,
                                        "isBlueVerified": False, "description": "estudiante"})
        self.assertEqual(xapi.clasificar_autor(tweet_persona), "persona")

    def test_cuenta_institucional_conocida_se_clasifica_institucion(self):
        tweet_inst = _tweet("800", "Mantenimiento de la red electrica en el sector",
                             author={"userName": "CNELEP", "name": "CNEL EP",
                                     "location": "Ecuador", "followers": 90000,
                                     "isBlueVerified": True, "description": "Empresa electrica"})
        self.assertEqual(xapi.clasificar_autor(tweet_inst), "institucion")


if __name__ == "__main__":
    unittest.main(verbosity=2)
