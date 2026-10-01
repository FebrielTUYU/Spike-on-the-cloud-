# -*- coding: utf-8 -*-
"""
Fase 24, Parte 0 -- medicion antes de cambiar nada:
  1) ia_gasto.json guarda QUE modulo hizo cada llamada y sus tokens, con
     totales por dia y modulo (antes solo decia "generar (rapido, ...)");
  2) pruebas/evaluacion_fase24.csv tiene 120 historias reales (60 locales con
     al menos 30 de Guayaquil, 60 internacionales) e incluye los casos citados;
  3) evaluar_fase24.py mide y se niega a reportar precision sin el visto bueno
     de Fernando.
Sin red: el gasto se escribe en una carpeta temporal.
"""
import json
import os
import tempfile
import unittest

import evaluar_fase24 as ev
import ia

AQUI = os.path.dirname(os.path.abspath(__file__))


class TestGastoPorModulo(unittest.TestCase):
    def setUp(self):
        self.orig = ia.GASTO_PATH
        ia.GASTO_PATH = os.path.join(tempfile.mkdtemp(), "ia_gasto.json")

    def tearDown(self):
        ia.GASTO_PATH = self.orig

    def _hist(self):
        with open(ia.GASTO_PATH, encoding="utf-8") as f:
            return json.load(f)

    def test_etiqueta_explicita_y_tokens(self):
        with ia.modulo("veredicto"):
            ia._registrar_gasto(0.002, "generar (rapido, x)", 1200, 80)
        h = self._hist()["historial"][-1]
        self.assertEqual((h["modulo"], h["tokens_in"], h["tokens_out"]), ("veredicto", 1200, 80))

    def test_se_deduce_de_quien_llama(self):
        # Una funcion de monitor.py conocida: se simula compilando el codigo con ese nombre de archivo.
        codigo = compile("def get_triaje_intl():\n    ia._registrar_gasto(0.001, 'g', 10, 2)\n",
                         os.path.join(AQUI, "monitor.py"), "exec")
        ns = {"ia": ia}
        exec(codigo, ns)
        ns["get_triaje_intl"]()
        codigo = compile("def f():\n    ia._registrar_gasto(0.001, 'g', 1, 1)\n", os.path.join(AQUI, "contexto.py"), "exec")
        exec(codigo, ns)
        ns["f"]()
        mods = [x["modulo"] for x in self._hist()["historial"]]
        self.assertEqual(mods, ["triaje", "contexto"])

    def test_la_funcion_publica_de_ia_manda(self):
        # embed() entra por ia.py: aunque la llame monitor.py, el modulo es "embeddings".
        orig = ia._registrar_gasto

        def embed():  # mismo nombre que la publica de ia.py, compilada como si viviera ahi
            pass
        codigo = compile("def embed():\n    _registrar_gasto(0.001, 'embed', 5, 0)\n", ia.__file__, "exec")
        ns = {"_registrar_gasto": orig}
        exec(codigo, ns)
        llamador = compile("def algo():\n    embed()\n", os.path.join(AQUI, "monitor.py"), "exec")
        ns2 = {"embed": ns["embed"]}
        exec(llamador, ns2)
        ns2["algo"]()
        self.assertEqual(self._hist()["historial"][-1]["modulo"], "embeddings")

    def test_totales_por_dia_y_modulo(self):
        for _ in range(3):
            with ia.modulo("contexto"):
                ia._registrar_gasto(0.01, "g", 100, 10)
        with ia.modulo("triaje"):
            ia._registrar_gasto(0.005, "g", 50, 5)
        pm = ia.gasto_por_modulo()
        self.assertEqual(pm["hoy"]["contexto"]["llamadas"], 3)
        self.assertAlmostEqual(pm["hoy"]["contexto"]["usd"], 0.03)
        self.assertEqual(pm["ultimos"]["triaje"]["tokens_in"], 50)
        self.assertIn("por_modulo", ia.estado_gasto())

    def test_llamadores_directos_de_monitor(self):
        for fn, esperado in (("get_clase_contraste", "clasificacion"), ("_ia_desenlace", "senales"),
                             ("_ia_texto_rapido", "senales"), ("get_triaje_intl", "triaje")):
            codigo = compile("def %s():" % fn + chr(10) + "    ia._registrar_gasto(0.001, 'g', 1, 1)" + chr(10),
                             os.path.join(AQUI, "monitor.py"), "exec")
            ns = {"ia": ia}
            exec(codigo, ns)
            ns[fn]()
            self.assertEqual(self._hist()["historial"][-1]["modulo"], esperado, fn)

    def test_hilos_no_pierden_gasto(self):
        import threading
        hs = [threading.Thread(target=lambda: [ia._registrar_gasto(0.001, "g", 1, 1) for _ in range(20)]) for _ in range(5)]
        [h.start() for h in hs]; [h.join() for h in hs]
        self.assertAlmostEqual(sum(v["usd"] for v in ia.gasto_por_modulo()["hoy"].values()), 0.1, places=6)

    def test_sin_llamadas_no_inventa(self):
        self.assertEqual(ia.gasto_por_modulo()["ultimos"], {})


class TestConjuntoDeEvaluacion(unittest.TestCase):
    def setUp(self):
        self.filas = ev.cargar_csv()

    def test_tamano_y_reparto(self):
        self.assertEqual(len(self.filas), 120)
        loc = [f for f in self.filas if f["spike_ambito"] != "mundo" or f["ambito_esperado"] != "mundo"]
        self.assertGreaterEqual(sum(1 for f in self.filas if f["spike_ambito"] == "guayaquil"), 30)
        self.assertEqual(sum(1 for f in self.filas if f["spike_ambito"] == "mundo"), 60)
        self.assertTrue(loc)

    def test_incluye_los_casos_citados(self):
        tit = " | ".join(f["titular"] for f in self.filas)
        for caso in ("Retiro de poste", "Poste de energía", "US Supreme Court lets Trump",
                     "Tribunal Supremo de EE. UU.", "Cristiano Ronaldo", "Walther Manrique", "New Jerson", "Lula"):
            self.assertIn(caso, tit)

    def test_columnas(self):
        for c in ("titular", "medios", "categoria_esperada", "ambito_esperado", "tipo_esperado",
                  "ciudad_esperada", "grupo", "revisado_por_fernando"):
            self.assertIn(c, self.filas[0])


class TestGuardarRevision(unittest.TestCase):
    def setUp(self):
        import shutil
        self.ruta = os.path.join(tempfile.mkdtemp(), "ev.csv")
        shutil.copy(ev.CSV_PATH, self.ruta)

    def test_guarda_una_fila_y_no_toca_las_demas(self):
        antes = ev.cargar_csv(self.ruta)
        ok, _ = ev.guardar_revision("0", {"tipo_esperado": "declaracion", "revisado_por_fernando": "si",
                                          "comentario_fernando": "ok"}, ruta=self.ruta)
        self.assertTrue(ok)
        despues = ev.cargar_csv(self.ruta)
        self.assertEqual((despues[0]["tipo_esperado"], despues[0]["revisado_por_fernando"]), ("declaracion", "si"))
        self.assertEqual(despues[0]["comentario_fernando"], "ok")
        for a, b in zip(antes[1:], despues[1:]):
            self.assertEqual({k: a[k] for k in a}, {k: b[k] for k in a})

    def test_rechaza_valores_y_campos_invalidos(self):
        self.assertFalse(ev.guardar_revision("0", {"tipo_esperado": "rumor"}, ruta=self.ruta)[0])
        self.assertFalse(ev.guardar_revision("0", {"titular": "otro"}, ruta=self.ruta)[0])
        self.assertFalse(ev.guardar_revision("999", {"grupo": "G1"}, ruta=self.ruta)[0])


class TestEvaluador(unittest.TestCase):
    FILAS = [
        {"id": "0", "titular": "A", "link": "l0", "categoria_esperada": "obras_servicios", "ambito_esperado": "guayaquil",
         "tipo_esperado": "accion", "ciudad_esperada": "Guayaquil", "util_esperado": "si", "grupo": "G1",
         "revisado_por_fernando": "si"},
        {"id": "1", "titular": "B", "link": "l1", "categoria_esperada": "obras_servicios", "ambito_esperado": "guayaquil",
         "tipo_esperado": "declaracion", "ciudad_esperada": "Guayaquil", "util_esperado": "si", "grupo": "G1",
         "revisado_por_fernando": "si"},
        {"id": "2", "titular": "C", "link": "l2", "categoria_esperada": "politica", "ambito_esperado": "mundo",
         "tipo_esperado": "dato", "ciudad_esperada": "Brasil", "util_esperado": "no", "grupo": "",
         "revisado_por_fernando": ""},
    ]

    def test_sin_visto_bueno_no_reporta(self):
        self.assertFalse(ev.revisado(self.FILAS))
        self.assertTrue(ev.revisado(self.FILAS[:2]))

    def test_metricas_y_pares(self):
        hs = [{"titular": "A", "fuentes": [{"link": "l0"}], "ambito": "local", "ciudad": "Guayaquil",
               "categoria": "obras_servicios", "tipo": "accion"},
              {"titular": "B", "fuentes": [{"link": "l1"}], "ambito": "local", "ciudad": "Guayaquil", "seccion": "economia"},
              {"titular": "C", "fuentes": [{"link": "l2"}], "ambito": "internacional", "seccion": "politica", "util": False}]
        r = ev.evaluar(self.FILAS, hs)
        m = r["metricas"]
        self.assertEqual((m["categoria"]["ok"], m["categoria"]["n"]), (2, 3))
        self.assertEqual((m["ambito"]["ok"], m["ambito"]["n"]), (3, 3))
        self.assertEqual((m["tipo"]["ok"], m["tipo"]["n"], m["tipo"]["sin_dato"]), (1, 1, 2))
        self.assertEqual((m["util"]["ok"], m["util"]["n"]), (1, 1))
        self.assertEqual(r["mal_separados"], [("0", "1")])
        # Si Spike las une (misma historia con los dos links), deja de haber error.
        hs2 = [{"titular": "A", "fuentes": [{"link": "l0"}, {"link": "l1"}], "ambito": "local", "ciudad": "Guayaquil"},
               hs[2]]
        r2 = ev.evaluar(self.FILAS, hs2)
        self.assertEqual((r2["mal_separados"], r2["mal_unidos"]), ([], []))

    def test_link_repetido_es_ambiguo(self):
        hs = [{"titular": "A", "fuentes": [{"link": "l0"}]}, {"titular": "A2", "fuentes": [{"link": "l0"}]}]
        r = ev.evaluar(self.FILAS[:1], hs)
        self.assertEqual(r["ambiguas"], ["0"])


if __name__ == "__main__":
    unittest.main()
