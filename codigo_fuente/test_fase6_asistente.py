# -*- coding: utf-8 -*-
"""
Pruebas de la Fase 6 (2026-09-23/24): pendientes del Asistente (Bloque 2)
apuntados al cierre de la sesion del 23/9 -- angulos_reportaje (pendiente 1),
filtro de campos crudos antes de armar el material (pendiente 3), y un ciclo
de herramientas que necesita varias rondas encadenadas (pendiente 4). No
golpea ninguna IA: ia._generar se monkeypatchea para scriptear las decisiones del
ciclo de herramientas.

Corre con:  python test_fase6_asistente.py
"""
import json
import os
import tempfile
import unittest

import agente
import herramientas as h
import ia


def _tmp_json_path():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return path


class TestAngulosReportaje(unittest.TestCase):
    def setUp(self):
        self._orig_here = h.HERE
        self._tmp_dir = tempfile.mkdtemp()
        h.HERE = self._tmp_dir

    def tearDown(self):
        h.HERE = self._orig_here

    def _escribir(self, data):
        with open(os.path.join(self._tmp_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_tema_con_alta_demanda_y_sin_cobertura_es_la_brecha_mas_alta(self):
        self._escribir({
            "historias": [
                {"titular": "Nota A", "temas": ["Empleo"], "es_local": True,
                 "fuentes": [{"link": "https://x/1"}]},
            ],
            "tendencias": {"Carceles": {"v": [10, 20, 80, 90, 85, 88, 90, 40]},
                            "Empleo": {"v": [10, 10, 10, 10, 10, 10, 10, 10]}},
            "social": {},
        })
        r = h.angulos_reportaje()
        temas = [a["tema"] for a in r["angulos"]]
        self.assertEqual(temas[0], "Carceles")  # alta demanda, 0 cobertura -> brecha maxima
        self.assertEqual(r["angulos"][0]["cobertura_actual"], 0)

    def test_sin_ninguna_senal_devuelve_lista_vacia_con_nota(self):
        self._escribir({"historias": [], "tendencias": {}, "social": {}})
        r = h.angulos_reportaje()
        self.assertEqual(r["angulos"], [])
        self.assertIn("nota", r)

    def test_filtra_por_ambito_local(self):
        self._escribir({
            "historias": [
                {"titular": "Nota EC", "temas": ["Empleo"], "es_local": True,
                 "fuentes": [{"link": "https://x/1"}]},
            ],
            "tendencias": {},
            "social": {
                "Empleo": {"n_posts": 50, "ambito": "ecuador"},
                "Elecciones": {"n_posts": 80, "ambito": "internacional"},
            },
        })
        r = h.angulos_reportaje(ambito="local")
        temas = [a["tema"] for a in r["angulos"]]
        self.assertIn("Empleo", temas)
        self.assertNotIn("Elecciones", temas)  # internacional queda fuera del filtro local

    def test_notas_ya_publicadas_se_incluyen_para_citar(self):
        self._escribir({
            "historias": [
                {"titular": "Nota cubierta", "temas": ["Empleo"], "es_local": True,
                 "fuentes": [{"link": "https://x/1"}]},
            ],
            "tendencias": {"Empleo": {"v": [50, 50, 50, 50, 50, 50, 50, 50]}},
            "social": {},
        })
        r = h.angulos_reportaje()
        empleo = next(a for a in r["angulos"] if a["tema"] == "Empleo")
        self.assertEqual(len(empleo["notas_ya_publicadas"]), 1)
        self.assertEqual(empleo["notas_ya_publicadas"][0]["titular"], "Nota cubierta")


class TestFiltroCamposCrudos(unittest.TestCase):
    """Pendiente 3: veredicto 'pendiente' (sin valor real) no debe llegar al
    material que se le manda al modelo -- antes se citaba casi textual
    ('veredicto_texto: Todavia no procesado') como si fuera un dato util."""

    def setUp(self):
        self._orig_here = h.HERE
        self._tmp_dir = tempfile.mkdtemp()
        h.HERE = self._tmp_dir

    def tearDown(self):
        h.HERE = self._orig_here

    def _escribir(self, historias, saved=None):
        with open(os.path.join(self._tmp_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump({"historias": historias}, f, ensure_ascii=False)
        with open(os.path.join(self._tmp_dir, "saved.json"), "w", encoding="utf-8") as f:
            json.dump(saved or [], f, ensure_ascii=False)

    def test_veredicto_pendiente_se_omite_en_resumen_historia(self):
        historia = {"titular": "Nota", "fuentes": [{"link": "https://x/1"}],
                    "veredicto": {"estado": "pendiente", "texto": "Todavia no procesado.", "citas": []}}
        self._escribir([historia])
        res = h.buscar_historias(q="Nota")
        self.assertEqual(len(res), 1)
        self.assertIsNone(res[0]["veredicto_contraste"])
        self.assertIsNone(res[0]["veredicto_texto"])

    def test_veredicto_real_si_se_incluye(self):
        historia = {"titular": "Nota B", "fuentes": [{"link": "https://x/2"}],
                    "veredicto": {"estado": "contradice", "texto": "El contrato no coincide.", "citas": ["SERCOP"]}}
        self._escribir([historia])
        res = h.buscar_historias(q="Nota B")
        self.assertEqual(res[0]["veredicto_contraste"], "contradice")
        self.assertEqual(res[0]["veredicto_texto"], "El contrato no coincide.")

    def test_detalle_historia_omite_veredicto_pendiente(self):
        historia = {"titular": "Nota C", "fuentes": [{"link": "https://x/3"}],
                    "veredicto": {"estado": "pendiente", "texto": "Todavia no procesado.", "citas": []}}
        self._escribir([historia])
        det = h.detalle_historia("https://x/3")
        self.assertIsNone(det["veredicto_contraste"])
        self.assertEqual(det["veredicto_citas"], [])

    def test_detalle_historia_omite_contexto_generico(self):
        historia = {"titular": "Nota D", "fuentes": [{"link": "https://x/4"}],
                    "contexto": {"texto": "sin contexto disponible"}}
        self._escribir([historia])
        det = h.detalle_historia("https://x/4")
        self.assertIsNone(det["contexto_verificado"])


class TestCicloVariasRondas(unittest.TestCase):
    """Pendiente 4: una pregunta que genuinamente necesita 3-4 consultas
    encadenadas -- confirma que el corte por repeticion (vistos) NO recorta
    un caso legitimo de varias consultas DISTINTAS, y que SI corta cuando el
    modelo repite la misma consulta con los mismos argumentos."""

    def setUp(self):
        self._orig_generar = ia._generar

    def tearDown(self):
        ia._generar = self._orig_generar

    def test_4_rondas_distintas_se_ejecutan_todas(self):
        secuencia = [
            {"accion": "consultar", "herramienta": "buscar_historias", "args": {"tema": "Carceles"}},
            {"accion": "consultar", "herramienta": "tendencia_tema", "args": {"tema": "Carceles"}},
            {"accion": "consultar", "herramienta": "comparar_periodo", "args": {"tema": "Carceles", "dias_atras": 7}},
            {"accion": "consultar", "herramienta": "buscar_guardadas", "args": {"q": "carceles"}},
            {"accion": "responder"},
        ]
        llamadas = {"n": 0}
        def _gen_falso(*a, **k):
            r = secuencia[min(llamadas["n"], len(secuencia) - 1)]
            llamadas["n"] += 1
            return json.dumps(r)
        ia._generar = _gen_falso
        pasos = agente.ciclo_herramientas("que hay de nuevo sobre carceles", max_rondas=4)
        self.assertEqual(len(pasos), 4)  # las 4 rondas distintas se ejecutaron, ninguna se corto de mas
        nombres = [p["herramienta"] for p in pasos]
        self.assertEqual(nombres, ["buscar_historias", "tendencia_tema", "comparar_periodo", "buscar_guardadas"])

    def test_repetir_la_misma_consulta_corta_el_ciclo(self):
        secuencia = [
            {"accion": "consultar", "herramienta": "tendencia_tema", "args": {"tema": "Carceles"}},
            {"accion": "consultar", "herramienta": "tendencia_tema", "args": {"tema": "Carceles"}},  # repetida
            {"accion": "consultar", "herramienta": "tendencia_tema", "args": {"tema": "Carceles"}},
        ]
        llamadas = {"n": 0}
        def _gen_falso(*a, **k):
            r = secuencia[min(llamadas["n"], len(secuencia) - 1)]
            llamadas["n"] += 1
            return json.dumps(r)
        ia._generar = _gen_falso
        pasos = agente.ciclo_herramientas("pregunta cualquiera", max_rondas=4)
        self.assertEqual(len(pasos), 1)  # se corto en la segunda ronda, que repetia la primera

    def test_respeta_el_limite_de_max_rondas(self):
        # el modelo siempre pide seguir consultando, nunca dice "responder"
        def _gen_falso(prompt="", *a, **k):
            n = prompt.count("->")  # cuenta cuantos pasos ya hay en la transcripcion
            return json.dumps(
                {"accion": "consultar", "herramienta": "tendencia_tema", "args": {"tema": "Tema%d" % n}})
        ia._generar = _gen_falso
        pasos = agente.ciclo_herramientas("pregunta cualquiera", max_rondas=4)
        self.assertEqual(len(pasos), 4)  # nunca mas de max_rondas, aunque el modelo pida seguir


if __name__ == "__main__":
    unittest.main()
