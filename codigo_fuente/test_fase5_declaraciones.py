# -*- coding: utf-8 -*-
"""
Pruebas de la Fase 5 (2026-09-23/24): Contraste de declaraciones con el
pasado. No golpea Ollama (Ollama no esta corriendo de forma confiable en el
entorno de estas pruebas): se monkeypatchea ia._generar/ia.extraer_declaracion/
ia.comparar_declaraciones, igual que ya se hizo para los Problemas 4 y 6 en
sesiones anteriores (veredicto_contraste/extraer_entidades_con_evento) -- el
*wiring* de punta a punta (declaraciones.py <-> monitor.py <-> ia.py) queda
probado con los 10 casos de abajo; la CALIDAD real del juicio del modelo
pesado sobre casos reales de Ecuador queda como pendiente para cuando
Fernando lo corra con Ollama activo (ver CLAUDE.md, Fase 5).

Corre con:  python test_fase5_declaraciones.py
"""
import json
import os
import tempfile
import unittest

import declaraciones as decl
import ia
import monitor as m


def _tmp_json_path():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return path


class TestDeclaracionesRegistro(unittest.TestCase):
    """declaraciones.py en aislamiento: registro, de_actor, filtro barato de
    candidatos (candidatos_contradiccion) -- nunca llama a Ollama."""

    def setUp(self):
        self._orig_path = decl.DECLARACIONES_PATH
        decl.DECLARACIONES_PATH = _tmp_json_path()

    def tearDown(self):
        try:
            os.remove(decl.DECLARACIONES_PATH)
        except Exception:
            pass
        decl.DECLARACIONES_PATH = self._orig_path

    def test_registrar_y_de_actor_round_trip(self):
        decl.registrar("Daniel Noboa", "Presidente", "aseguro algo", "2026-01-10",
                        "El Universo", "https://x/1")
        out = decl.de_actor("Daniel Noboa")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["texto"], "aseguro algo")

    def test_no_duplica_mismo_link(self):
        decl.registrar("Daniel Noboa", "Presidente", "dijo A", "2026-01-10", "El Universo", "https://x/1")
        decl.registrar("Daniel Noboa", "Presidente", "dijo A otra vez", "2026-01-10", "El Universo", "https://x/1")
        self.assertEqual(len(decl.de_actor("Daniel Noboa")), 1)

    def test_actor_normalizado_ignora_mayusculas_y_espacios(self):
        decl.registrar("daniel   noboa", "Presidente", "dijo A", "2026-01-10", "El Universo", "https://x/1")
        self.assertEqual(len(decl.de_actor("Daniel Noboa")), 1)

    def test_nunca_se_purga_por_fecha_vieja(self):
        # fecha de hace mas de un año: nada en el modulo la descarta -- a
        # diferencia de las historias del feed (MONITOR_MAX_DIAS), este
        # registro es deliberadamente permanente.
        decl.registrar("Actor Viejo", "", "algo de hace mucho", "2020-01-01", "Medio", "https://x/viejo")
        self.assertEqual(len(decl.de_actor("Actor Viejo")), 1)

    def test_candidatos_exige_mismo_actor(self):
        decl.registrar("Actor A", "", "el presupuesto nacional crecio este año", "2026-01-01", "M", "https://x/a")
        decl.registrar("Actor B", "", "el presupuesto nacional crecio este año", "2026-01-01", "M", "https://x/b")
        cand = decl.candidatos_contradiccion("Actor A", "el presupuesto nacional crecio otra vez", "2026-06-01")
        self.assertEqual(len(cand), 1)
        self.assertEqual(cand[0]["actor"], "Actor A")

    def test_candidatos_exige_2_o_mas_palabras_en_comun(self):
        decl.registrar("Alcaldesa", "", "critico el aumento de tarifas de agua potable", "2026-01-01", "M", "https://x/1")
        # comparte "ciudad" nada mas (0-1 palabras reales en comun) -> no es candidato
        cand = decl.candidatos_contradiccion("Alcaldesa", "inauguro un parque nuevo", "2026-06-01")
        self.assertEqual(cand, [])

    def test_candidatos_solo_contra_declaraciones_mas_viejas(self):
        decl.registrar("Ministro", "", "el subsidio al diesel se mantiene sin cambios", "2026-06-01", "M", "https://x/1")
        # misma fecha o mas nueva que la 'nueva' declaracion -> no cuenta como "anterior"
        cand = decl.candidatos_contradiccion("Ministro", "el subsidio al diesel se elimina gradualmente", "2026-06-01")
        self.assertEqual(cand, [])
        cand2 = decl.candidatos_contradiccion("Ministro", "el subsidio al diesel se elimina gradualmente", "2026-07-01")
        self.assertEqual(len(cand2), 1)

    def test_max_por_actor_recorta_lo_mas_viejo(self):
        orig = decl.MAX_POR_ACTOR
        decl.MAX_POR_ACTOR = 3
        try:
            for i in range(5):
                decl.registrar("Actor X", "", "declaracion numero %d con palabras variadas" % i,
                                "2026-01-0%d" % (i + 1), "M", "https://x/%d" % i)
            out = decl.de_actor("Actor X")
            self.assertEqual(len(out), 3)
            # se conservan las 3 mas nuevas (2,3,4), no las 3 primeras
            self.assertNotIn("declaracion numero 0 con palabras variadas", [d["texto"] for d in out])
        finally:
            decl.MAX_POR_ACTOR = orig


class TestIaExtraerYCompararDeclaraciones(unittest.TestCase):
    """ia.extraer_declaracion / ia.comparar_declaraciones, con ia._generar
    monkeypatcheado (punto unico de transporte desde la Fase 10) -- nunca
    golpea ninguna IA de verdad."""

    def setUp(self):
        self._orig_generar = ia._generar

    def tearDown(self):
        ia._generar = self._orig_generar

    def _responde(self, obj, captura=None):
        def _gen(*a, **k):
            if captura is not None:
                captura.update(k)
            return json.dumps(obj)
        ia._generar = _gen

    def test_extraer_declaracion_null_si_no_hay_atribucion(self):
        self._responde({"declaracion": None})
        self.assertIsNone(ia.extraer_declaracion("Se registro un sismo en Manabi", ""))

    def test_extraer_declaracion_devuelve_dict_si_hay_atribucion(self):
        self._responde({"declaracion": {"actor": "Daniel Noboa", "cargo": "Presidente",
                                         "texto": "el subsidio se mantiene sin cambios"}})
        d = ia.extraer_declaracion("El presidente aseguro que el subsidio se mantiene", "")
        self.assertEqual(d["actor"], "Daniel Noboa")
        self.assertEqual(d["cargo"], "Presidente")

    def test_comparar_usa_perfil_profundo(self):
        captura = {}
        self._responde({"estado": "posible_contradiccion", "texto": "x", "confianza": 0.6}, captura)
        ia.comparar_declaraciones("Actor", "nueva", "2026-06-01", "M1", "vieja", "2026-01-01", "M2")
        self.assertEqual(captura.get("perfil"), ia.PERFIL_PROFUNDO)
        self.assertTrue(captura.get("json_mode"))

    def test_estado_nunca_puede_ser_falso_ni_libre(self):
        # el modelo (hipoteticamente) responde algo fuera del vocabulario fijo
        self._responde({"estado": "falso", "texto": "x", "confianza": 0.9})
        r = ia.comparar_declaraciones("Actor", "nueva", "2026-06-01", "M1", "vieja", "2026-01-01", "M2")
        self.assertNotEqual(r["estado"], "falso")
        self.assertIn(r["estado"], ("posible_contradiccion", "consistente", "sin_relacion"))

    def test_confianza_se_recorta_a_0_1(self):
        self._responde({"estado": "consistente", "texto": "x", "confianza": 5})
        r = ia.comparar_declaraciones("Actor", "nueva", "2026-06-01", "M1", "vieja", "2026-01-01", "M2")
        self.assertLessEqual(r["confianza"], 1.0)

    def test_sin_backend_devuelve_none_sin_romper(self):
        # Fase 10: sin clave configurada, _generar devuelve None -> las funciones
        # devuelven None. Se simula limpiando GEMINI_API_KEY -- esta PC ya tiene
        # una clave real en .env (Fase 10 conecto Gemini de verdad), asi que sin
        # este aislamiento la llamada golpearia la red real en vez de "no backend".
        orig_key = ia.GEMINI_API_KEY
        ia.GEMINI_API_KEY = ""
        try:
            self.assertIsNone(ia.extraer_declaracion("El ministro dijo que...", ""))
            self.assertIsNone(ia.comparar_declaraciones("A", "n", "2026-06-01", "M", "v", "2026-01-01", "M"))
        finally:
            ia.GEMINI_API_KEY = orig_key


class TestGetDeclaracionesWiring(unittest.TestCase):
    """monitor.get_declaraciones() de punta a punta, con ia mockeada por
    caso -- 10 escenarios realistas (pedido de Fernando: probar con 10 casos
    reales antes de integrar), cubriendo extraccion, filtro barato,
    contradiccion real, consistencia, sin relacion, actor sin historial,
    orden temporal, normalizacion de actor, y los limites
    DECL_MAX_NEW/DECL_CONTRASTE_MAX."""

    def setUp(self):
        self._orig_decl_cache = m.DECL_CACHE_PATH
        self._orig_decl_path = decl.DECLARACIONES_PATH
        self._orig_max_new = m.DECL_MAX_NEW
        self._orig_contraste_max = m.DECL_CONTRASTE_MAX
        self._orig_extraer = ia.extraer_declaracion
        self._orig_comparar = ia.comparar_declaraciones
        self._orig_ia_disponible = getattr(m, "ia", None)
        # Fase 10: get_declaraciones ahora chequea ia.disponible() antes del
        # lote (sin eso, con la IA caida, las notas quedaban "procesadas" sin
        # declaracion para siempre). Aca se simula una IA disponible.
        self._orig_disponible = ia.disponible
        ia.disponible = lambda *a, **k: True
        m.DECL_CACHE_PATH = _tmp_json_path()
        decl.DECLARACIONES_PATH = _tmp_json_path()

    def tearDown(self):
        for p in (m.DECL_CACHE_PATH, decl.DECLARACIONES_PATH):
            try:
                os.remove(p)
            except Exception:
                pass
        m.DECL_CACHE_PATH = self._orig_decl_cache
        decl.DECLARACIONES_PATH = self._orig_decl_path
        m.DECL_MAX_NEW = self._orig_max_new
        m.DECL_CONTRASTE_MAX = self._orig_contraste_max
        ia.extraer_declaracion = self._orig_extraer
        ia.comparar_declaraciones = self._orig_comparar
        ia.disponible = self._orig_disponible

    def _story(self, i, titular, resumen, fecha, outlet="El Universo"):
        return {"titular": titular, "resumen": resumen, "newest": fecha,
                "fuentes": [{"link": "https://x/%d" % i, "outlet": outlet, "title": titular}]}

    def test_caso1_contradiccion_real_se_detecta(self):
        # Declaracion previa registrada a mano (simula una pasada anterior
        # del trabajador); la nota nueva la contradice segun el modelo pesado.
        decl.registrar("Ministro de Economia", "Ministro",
                        "el subsidio al diesel se mantiene sin cambios este año",
                        "2026-01-10", "El Universo", "https://x/previa1")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Ministro de Economia", "cargo": "Ministro",
            "texto": "el subsidio al diesel se elimina gradualmente desde agosto"}
        ia.comparar_declaraciones = lambda *a, **k: {
            "estado": "posible_contradiccion",
            "texto": "En enero dijo que se mantenia, en julio anuncia que se elimina.", "confianza": 0.7}
        stories = [self._story(1, "Ministro anuncia fin del subsidio al diesel", "resumen", "2026-07-15")]
        m.get_declaraciones(stories)
        self.assertIn("declaracion", stories[0])
        self.assertIn("contradiccion_declaracion", stories[0])
        self.assertEqual(stories[0]["contradiccion_declaracion"][0]["estado"], "posible_contradiccion")

    def test_caso2_sin_relacion_no_pasa_el_filtro_barato(self):
        decl.registrar("Alcaldesa", "Alcaldesa",
                        "critico el aumento de tarifas de agua potable en la ciudad",
                        "2026-01-10", "M", "https://x/previa2")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Alcaldesa", "cargo": "Alcaldesa", "texto": "inauguro un parque"}
        llamado = {"n": 0}
        def _comparar_falso(*a, **k):
            llamado["n"] += 1
            return {"estado": "sin_relacion", "texto": "no relacionado", "confianza": 0.9}
        ia.comparar_declaraciones = _comparar_falso
        stories = [self._story(2, "Alcaldesa inaugura parque", "resumen", "2026-07-01")]
        m.get_declaraciones(stories)
        # tokens("inauguro un parque") no comparte 2+ palabras con la previa
        # -> el filtro barato ni siquiera llega a llamar al modelo pesado.
        self.assertEqual(llamado["n"], 0)
        self.assertNotIn("contradiccion_declaracion", stories[0])

    def test_caso3_consistente_no_se_muestra_como_hallazgo(self):
        decl.registrar("Ministra de Educacion", "Ministra",
                        "anuncio que el ciclo escolar costero inicia el 1 de abril",
                        "2026-02-01", "M", "https://x/previa3")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Ministra de Educacion", "cargo": "Ministra",
            "texto": "confirmo que el ciclo escolar costero inicio el 1 de abril con normalidad"}
        ia.comparar_declaraciones = lambda *a, **k: {
            "estado": "consistente", "texto": "confirma lo ya anunciado", "confianza": 0.8}
        stories = [self._story(3, "Ciclo escolar costero arranca con normalidad", "resumen", "2026-04-02")]
        m.get_declaraciones(stories)
        self.assertIn("declaracion", stories[0])
        self.assertNotIn("contradiccion_declaracion", stories[0])  # candado en codigo: consistente no es un "hallazgo"

    def test_caso4_actores_distintos_nunca_se_comparan(self):
        decl.registrar("Actor B", "", "el presupuesto nacional crecio este año",
                        "2026-01-01", "M", "https://x/previa4b")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Actor A", "cargo": "", "texto": "el presupuesto nacional crecio otra vez"}
        llamado = {"n": 0}
        def _comparar_falso(*a, **k):
            llamado["n"] += 1
            return {"estado": "posible_contradiccion", "texto": "x", "confianza": 0.5}
        ia.comparar_declaraciones = _comparar_falso
        stories = [self._story(4, "Actor A habla del presupuesto", "resumen", "2026-06-01")]
        m.get_declaraciones(stories)
        self.assertEqual(llamado["n"], 0)  # Actor B nunca es candidato para Actor A

    def test_caso5_nota_sin_atribucion_no_registra_nada(self):
        ia.extraer_declaracion = lambda t, r="", forzado="": None
        stories = [self._story(5, "Se registro un sismo de magnitud 4.5 en Manabi", "resumen", "2026-06-01")]
        m.get_declaraciones(stories)
        self.assertNotIn("declaracion", stories[0])
        self.assertEqual(decl.de_actor("nadie"), [])

    def test_caso6_actor_nuevo_sin_historial_no_llama_al_modelo_pesado(self):
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Actor Nuevo", "cargo": "", "texto": "algo que dijo por primera vez"}
        llamado = {"n": 0}
        ia.comparar_declaraciones = lambda *a, **k: llamado.__setitem__("n", llamado["n"] + 1) or {
            "estado": "sin_relacion", "texto": "", "confianza": 0}
        stories = [self._story(6, "Actor Nuevo declara algo", "resumen", "2026-06-01")]
        m.get_declaraciones(stories)
        self.assertEqual(llamado["n"], 0)
        self.assertEqual(len(decl.de_actor("Actor Nuevo")), 1)

    def test_caso7_declaracion_previa_con_fecha_igual_no_es_candidata(self):
        decl.registrar("Ministro", "", "el subsidio al diesel se mantiene sin cambios",
                        "2026-06-01", "M", "https://x/previa7")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Ministro", "cargo": "", "texto": "el subsidio al diesel se elimina gradualmente"}
        llamado = {"n": 0}
        ia.comparar_declaraciones = lambda *a, **k: llamado.__setitem__("n", llamado["n"] + 1) or {
            "estado": "posible_contradiccion", "texto": "", "confianza": 0.5}
        stories = [self._story(7, "Ministro anuncia cambio", "resumen", "2026-06-01")]  # misma fecha
        m.get_declaraciones(stories)
        self.assertEqual(llamado["n"], 0)

    def test_caso8_actor_normalizado_encuentra_historial_pese_a_variacion_de_texto(self):
        decl.registrar("daniel   noboa", "", "el presupuesto crecio este trimestre",
                        "2026-01-01", "M", "https://x/previa8")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Daniel Noboa", "cargo": "Presidente", "texto": "el presupuesto crecio otra vez"}
        ia.comparar_declaraciones = lambda *a, **k: {
            "estado": "consistente", "texto": "", "confianza": 0.4}
        stories = [self._story(8, "Noboa habla del presupuesto", "resumen", "2026-06-01")]
        m.get_declaraciones(stories)
        self.assertIn("declaracion", stories[0])  # el match por actor normalizado funciono

    def test_caso9_respeta_decl_max_new_por_pasada(self):
        m.DECL_MAX_NEW = 1
        llamadas = {"n": 0}
        def _extraer_falso(t, r="", forzado=""):
            llamadas["n"] += 1
            return None
        ia.extraer_declaracion = _extraer_falso
        stories = [self._story(9, "Nota A", "r", "2026-06-01"),
                   self._story(10, "Nota B", "r", "2026-06-01"),
                   self._story(11, "Nota C", "r", "2026-06-01")]
        m.get_declaraciones(stories)
        self.assertEqual(llamadas["n"], 1)  # solo la primera historia se proceso esta pasada

    def test_caso10_cachea_la_comparacion_por_par_entre_pasadas(self):
        decl.registrar("Ministro", "", "el subsidio al diesel se mantiene sin cambios",
                        "2026-01-10", "M", "https://x/previa10")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Ministro", "cargo": "", "texto": "el subsidio al diesel se elimina gradualmente"}
        llamadas = {"n": 0}
        def _comparar(*a, **k):
            llamadas["n"] += 1
            return {"estado": "posible_contradiccion", "texto": "x", "confianza": 0.6}
        ia.comparar_declaraciones = _comparar
        stories = [self._story(12, "Ministro anuncia cambio", "resumen", "2026-07-15")]
        m.get_declaraciones(stories)  # primera pasada: llama al modelo pesado
        # segunda pasada del trabajador sobre la MISMA historia (re-proceso):
        # como el link ya esta en "_procesadas", se reaplica desde
        # "_por_historia" sin volver a llamar a extraer_declaracion NI a
        # comparar_declaraciones.
        stories2 = [self._story(12, "Ministro anuncia cambio", "resumen", "2026-07-15")]
        m.get_declaraciones(stories2)
        self.assertEqual(llamadas["n"], 1)
        self.assertIn("contradiccion_declaracion", stories2[0])

    def test_modo_lectura_reaplica_desde_cache_por_link(self):
        decl.registrar("Ministro", "", "el subsidio al diesel se mantiene sin cambios",
                        "2026-01-10", "M", "https://x/previaLL")
        ia.extraer_declaracion = lambda t, r="", forzado="": {
            "actor": "Ministro", "cargo": "", "texto": "el subsidio al diesel se elimina gradualmente"}
        ia.comparar_declaraciones = lambda *a, **k: {
            "estado": "posible_contradiccion", "texto": "x", "confianza": 0.6}
        stories = [self._story(13, "Ministro anuncia cambio", "resumen", "2026-07-15")]
        m.get_declaraciones(stories)  # pasada del trabajador: escribe el cache por link

        # simula run_fast: reconstruye 'stories' DESDE CERO (objeto nuevo) y
        # pide modo_lectura=True -- debe reaplicar sin llamar a Ollama.
        stories_frescas = [self._story(13, "Ministro anuncia cambio", "resumen", "2026-07-15")]
        estado = m.get_declaraciones(stories_frescas, modo_lectura=True)
        self.assertIn("declaracion", stories_frescas[0])
        self.assertIn("contradiccion_declaracion", stories_frescas[0])
        self.assertTrue(estado.startswith("cache"))


if __name__ == "__main__":
    unittest.main()
