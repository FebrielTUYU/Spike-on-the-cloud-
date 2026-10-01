# -*- coding: utf-8 -*-
"""
Fase 24, Parte A -- IA sin costo para el trabajo de fondo.
Pedido de Fernando: el fondo no gasta nada; cada tarea tiene un proveedor
gratuito titular y un respaldo distinto; si los dos se agotan la tarea
ESPERA (nunca cae en la clave pagada); lo que el pide en persona y lo privado
(casos, chat) sigue por la clave pagada; lotes, cache por contenido y
prioridad para gastar menos cupo.
Sin red: el transporte del enrutador y el de la clave pagada son dobles.
"""
import json
import os
import tempfile
import unittest


import ia
import ia_router
import monitor


class _Base(unittest.TestCase):
    def setUp(self):
        # El candado de pruebas deja pasar al enrutador SOLO durante esta prueba (transporte simulado).
        os.environ["MONITOR_IA_ROUTER_PRUEBAS"] = "1"
        self.tmp = tempfile.mkdtemp()
        self.orig = (ia_router.ESTADO_PATH, ia_router._post, ia_router.clave, ia._post_gemini, ia.GASTO_PATH)
        ia_router.ESTADO_PATH = os.path.join(self.tmp, "estado.json")
        ia.GASTO_PATH = os.path.join(self.tmp, "gasto.json")
        ia_router._VENTANA.clear()
        ia_router.clave = lambda prov: "clave-de-prueba"
        self.llamadas = []
        self.respuestas = {}  # (proveedor) -> lista de (codigo, cuerpo, cabeceras)
        self.pagada = []

        def post(url, headers, cuerpo, timeout):
            prov = "groq" if "groq" in url else "cerebras" if "cerebras" in url else "gemini_free"
            self.llamadas.append((prov, cuerpo.get("model") or url.split("/models/")[-1].split(":")[0]))
            cola = self.respuestas.get(prov) or []
            if cola:
                return cola.pop(0)
            if prov == "gemini_free":
                if "embedContent" in url:
                    return 200, {"embedding": {"values": [0.1, 0.2]}}, {}
                return 200, {"candidates": [{"content": {"parts": [{"text": "hola gemini"}]}}],
                             "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2}}, {}
            return 200, {"choices": [{"message": {"content": "hola %s" % prov}}],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 2}}, {"x-ratelimit-limit-requests": "1000"}
        ia_router._post = post

        def pagada(*a, **k):
            self.pagada.append(a)
            return {"candidates": [{"content": {"parts": [{"text": "respuesta pagada"}]}}],
                    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}}
        ia._post_gemini = pagada

    def tearDown(self):
        os.environ.pop("MONITOR_IA_ROUTER_PRUEBAS", None)
        (ia_router.ESTADO_PATH, ia_router._post, ia_router.clave, ia._post_gemini, ia.GASTO_PATH) = self.orig


class TestEnrutador(_Base):
    def test_fondo_va_por_el_titular_gratis(self):
        with ia.modulo("contexto"):
            t = ia._generar("pregunta", max_tokens=50)
        self.assertEqual(t, "hola groq")  # contexto: titular Groq
        self.assertEqual(self.pagada, [])

    def test_si_el_titular_se_agota_pasa_al_respaldo(self):
        self.respuestas["groq"] = [(429, '{"error": "rate limit per day"}', {})]
        with ia.modulo("contexto"):
            t = ia._generar("pregunta", max_tokens=50)
        self.assertEqual(t, "hola gemini")  # respaldo de contexto: Gemini gratis
        e = ia_router.estado_dashboard()
        self.assertTrue(any(f["proveedor"] == "groq" and f["agotado_hasta"] for f in e["filas"]))

    def test_si_todos_se_agotan_espera_y_nunca_usa_la_pagada(self):
        self.respuestas["cerebras"] = [(429, "{}", {"retry-after": "3600"})]
        self.respuestas["groq"] = [(429, "{}", {"retry-after": "3600"})]
        with ia.modulo("veredicto"):
            t = ia._generar("pregunta", max_tokens=50)
        self.assertIsNone(t)
        self.assertIn("espera", ia.last_error)
        self.assertEqual(self.pagada, [])

    def test_lo_interactivo_sigue_por_la_pagada(self):
        with ia.interactivo():
            t = ia._generar("pregunta de Fernando", max_tokens=50)
        self.assertEqual(t, "respuesta pagada")
        self.assertEqual(self.llamadas, [])

    def test_lo_privado_nunca_va_a_los_gratuitos(self):
        for mod in ("casos", "chat"):
            with ia.modulo(mod):
                ia._generar("documento privado", max_tokens=50)
        self.assertEqual(self.llamadas, [])
        self.assertEqual(len(self.pagada), 2)

    def test_documento_de_un_caso_nunca_va_gratis_aunque_entre_por_embed(self):
        # La indexacion de documentos corre en segundo plano (no interactiva).
        codigo = compile("def indexar():" + chr(10) + "    return ia.embed('texto privado del caso')" + chr(10),
                         os.path.join(os.path.dirname(os.path.abspath(ia.__file__)), "casos.py"), "exec")
        ns = {"ia": ia}
        exec(codigo, ns)
        ns["indexar"]()
        self.assertEqual(self.llamadas, [])
        self.assertEqual(len(self.pagada), 1)

    def test_limite_por_minuto_usa_el_respaldo(self):
        with ia.modulo("veredicto"):
            for _ in range(5):
                ia._generar("x", max_tokens=10)
        self.assertEqual([p for p, _ in self.llamadas], ["cerebras"] * 5)
        with ia.modulo("veredicto"):
            ia._generar("x", max_tokens=10)  # Cerebras: 5 por minuto -> respaldo Groq
        self.assertEqual(self.llamadas[-1][0], "groq")

    def test_registra_quien_respondio_y_limites_informados(self):
        with ia.modulo("contexto"):
            ia._generar("x", max_tokens=10)
        with open(ia_router.ESTADO_PATH, encoding="utf-8") as f:
            d = json.load(f)
        r = d["registro"][-1]
        self.assertEqual((r["tarea"], r["proveedor"], r["ok"]), ("contexto", "groq", True))
        self.assertEqual(d["limites"]["groq|openai/gpt-oss-120b"]["rpd"], 1000)

    def test_embeddings_de_fondo_gratis(self):
        with ia.modulo("embeddings"):
            v = ia.embed("texto")
        self.assertEqual(v, [0.1, 0.2])
        self.assertEqual(self.pagada, [])

    def test_sin_claves_el_fondo_no_esta_disponible(self):
        ia_router.clave = lambda prov: ""
        self.assertFalse(ia.fondo_disponible())
        self.assertTrue(ia_router.estado_dashboard()["todos_agotados"])

    def test_nada_de_esto_toca_el_gasto_pagado(self):
        with ia.modulo("triaje"):
            ia._generar("x", max_tokens=10)
        self.assertFalse(os.path.exists(ia.GASTO_PATH))


class TestRevisionCodex(_Base):
    def test_dos_hilos_no_pasan_el_ultimo_cupo_del_dia(self):
        import threading
        orig = dict(ia_router.LIMITES)
        ia_router.LIMITES[("cerebras", "*")] = {"rpm": 50, "rpd": 1}
        ia_router.LIMITES[("groq", "*")] = {"rpm": 50, "rpd": 0}
        lento = ia_router._post

        def post_lento(*a, **k):
            import time
            time.sleep(0.3)
            return lento(*a, **k)
        ia_router._post = post_lento
        try:
            res = []

            def uno():
                with ia.modulo("veredicto"):
                    res.append(ia._generar("x", max_tokens=10))
            hs = [threading.Thread(target=uno) for _ in range(3)]
            [h.start() for h in hs]
            [h.join() for h in hs]
            self.assertEqual(len([p for p, _ in self.llamadas if p == "cerebras"]), 1)
        finally:
            ia_router.LIMITES.clear()
            ia_router.LIMITES.update(orig)

    def test_embeddings_pausan_ante_errores(self):
        for codigo, cuerpo in ((403, "{}"), (500, "{}")):
            ia_router._VENTANA.clear()
            if os.path.exists(ia_router.ESTADO_PATH):
                os.remove(ia_router.ESTADO_PATH)
            self.respuestas["gemini_free"] = [(codigo, cuerpo, {})]
            with ia.modulo("embeddings"):
                self.assertIsNone(ia.embed("x"))
            e = ia_router.estado_dashboard()
            self.assertTrue(any(f["modelo"] == "gemini-embedding-001" and f["agotado_hasta"] for f in e["filas"]), codigo)
        self.assertEqual(self.pagada, [])

    def test_error_de_red_pausa_corta_y_usa_el_respaldo(self):
        def post(url, headers, cuerpo, timeout):
            if "cerebras" in url:
                raise OSError("sin red")
            self.llamadas.append(("groq", cuerpo.get("model")))
            return 200, {"choices": [{"message": {"content": "hola groq"}}], "usage": {}}, {}
        ia_router._post = post
        with ia.modulo("veredicto"):
            self.assertEqual(ia._generar("x", max_tokens=10), "hola groq")

    def test_material_de_un_caso_en_monitor_es_privado(self):
        codigo = compile("def _material_caso():" + chr(10) + "    return ia.embed('pregunta sobre el caso')" + chr(10),
                         os.path.join(os.path.dirname(os.path.abspath(ia.__file__)), "monitor.py"), "exec")
        ns = {"ia": ia}
        exec(codigo, ns)
        ns["_material_caso"]()
        self.assertEqual(self.llamadas, [])

    def test_casos_py_marca_privado_explicito(self):
        fuente = open(os.path.join(os.path.dirname(os.path.abspath(ia.__file__)), "casos.py"), encoding="utf-8").read()
        self.assertIn('with ia.modulo("casos"):', fuente)


class TestLotesYCache(_Base):
    def test_lote_con_huecos_reintenta_solo_los_que_faltan(self):
        orig = (monitor.IA_CACHE, ia.interpretar)
        monitor.IA_CACHE = os.path.join(self.tmp, "ia_cache.json")
        ia.interpretar = lambda *a, **k: "lectura"
        truncado = {"items": [{"n": 1, "temas": [], "geo": ["ecuador"]}]}  # pidio 3, vino 1
        completo = {"items": [{"n": 1, "temas": [], "geo": ["ecuador"]}, {"n": 2, "temas": [], "geo": ["ecuador"]}]}
        self.respuestas["gemini_free"] = [
            (200, {"candidates": [{"content": {"parts": [{"text": json.dumps(truncado)}]}}]}, {}),
            (200, {"candidates": [{"content": {"parts": [{"text": json.dumps(completo)}]}}]}, {})]
        try:
            hs = [{"titular": "t%d" % i, "resumen": "", "temas": [], "es_local": True, "fuentes": [{"link": "l%d" % i}]}
                  for i in range(3)]
            monitor.get_ia(hs)
            with open(monitor.IA_CACHE, encoding="utf-8") as f:
                self.assertEqual(len(json.load(f)), 3)
            self.assertEqual(len(self.llamadas), 2)
        finally:
            monitor.IA_CACHE, ia.interpretar = orig

    def _lote_ok(self, n):
        items = [{"n": i + 1, "temas": [{"cat": "Salud", "score": 0.9}, {"cat": "Inventada", "score": 1}],
                  "geo": ["ecuador"]} for i in range(n)]
        return 200, {"candidates": [{"content": {"parts": [{"text": json.dumps({"items": items})}]}}]}, {}

    def test_analizar_lote_alinea_y_no_inventa_categorias(self):
        self.respuestas["gemini_free"] = [self._lote_ok(3)]
        with ia.modulo("triaje"):
            r = ia.analizar_lote([{"titular": "a"}, {"titular": "b"}, {"titular": "c"}])
        self.assertEqual(len(r), 3)
        self.assertEqual([t["cat"] for t in r[0]["temas"]], ["Salud"])
        self.assertEqual(len(self.llamadas), 1)

    def test_get_ia_va_en_lotes_y_no_repite_lo_que_no_cambio(self):
        cache = os.path.join(self.tmp, "ia_cache.json")
        orig = (monitor.IA_CACHE, monitor.IA_LOTE, ia.interpretar)
        monitor.IA_CACHE, monitor.IA_LOTE = cache, 25
        ia.interpretar = lambda *a, **k: "lectura"
        try:
            hs = [{"titular": "Historia %d sobre salud" % i, "resumen": "r", "temas": ["Salud"], "es_local": True,
                   "ciudad": "Quito", "seccion": "sociedad", "interes": i, "fuentes": [{"link": "l%d" % i, "outlet": "M"}]}
                  for i in range(30)]
            self.respuestas["gemini_free"] = [self._lote_ok(25), self._lote_ok(5)]
            monitor.get_ia(hs)
            triajes = [x for x in self.llamadas if x[0] == "gemini_free"]
            self.assertEqual(len(triajes), 2)  # 30 historias -> 2 llamadas, no 30
            # Un medio mas levanta la misma nota (mismo texto): no se vuelve a pedir.
            for h in hs:
                h["fuentes"].append({"link": h["fuentes"][0]["link"] + "b", "outlet": "Otro"})
            antes = len(self.llamadas)
            monitor.get_ia(hs)
            self.assertEqual(len([x for x in self.llamadas[antes:] if x[0] == "gemini_free"]), 0)
            self.assertEqual(self.pagada, [])
        finally:
            monitor.IA_CACHE, monitor.IA_LOTE, ia.interpretar = orig

    def test_prioridad_solo_lo_que_se_muestra(self):
        hs = [{"titular": "t%d" % i, "seccion": "general", "interes": i, "fuentes": [{"link": "l%d" % i}],
               "internacional": True, "outlets": ["A"]} for i in range(40)]
        hs.append({"titular": "gye", "ciudad": "Guayaquil", "seccion": "general", "interes": 0, "fuentes": [{"link": "g"}]})
        m = monitor._claves_mostradas(hs)
        self.assertIn("g", m)  # todo Guayaquil
        self.assertEqual(len([k for k in m if k.startswith("l")]), monitor.MOSTRADAS_POR_SECCION)


if __name__ == "__main__":
    unittest.main()
