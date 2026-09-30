# -*- coding: utf-8 -*-
"""
Fase 11 (v2) -- contexto de 4 bloques. Pruebas sin golpear Gemini (ia._generar_json
mockeado, mismo patron que test_evento.py/test_fase5_declaraciones.py).

Corre con:  python test_fase11_contexto.py
"""
import datetime as dt
import unittest

import contexto
import ia
import monitor


def _utc(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


class TestContextoValidacion(unittest.TestCase):
    def setUp(self):
        self._orig = ia._generar_json

    def tearDown(self):
        ia._generar_json = self._orig

    def _material(self):
        return [{"id": "R1", "texto": "Antecedente real", "link": None},
                {"id": "M1", "texto": "Otro medio real", "link": None}]

    def test_sin_material_no_llama_a_la_ia(self):
        llamado = []
        ia._generar_json = lambda *a, **k: llamado.append(1) or {}
        r = contexto.construir("Titular", "Resumen", [])
        self.assertEqual(llamado, [])
        self.assertEqual(r["antecedentes"], [])
        self.assertIn("sin material", r["limitaciones"])

    def test_afirmacion_con_id_valido_se_conserva(self):
        ia._generar_json = lambda *a, **k: {
            "antecedentes": [{"texto": "Paso esto antes", "fuentes": ["R1"]}],
            "actores": [], "que_es_nuevo": [], "que_falta_saber": [], "limitaciones": "",
        }
        r = contexto.construir("T", "R", self._material())
        self.assertEqual(len(r["antecedentes"]), 1)
        self.assertEqual(r["antecedentes"][0]["fuentes"], ["R1"])
        self.assertEqual(r["descartadas"], 0)

    def test_afirmacion_con_id_inventado_se_descarta(self):
        ia._generar_json = lambda *a, **k: {
            "antecedentes": [{"texto": "Dato inventado", "fuentes": ["R99"]}],
            "actores": [], "que_es_nuevo": [], "que_falta_saber": [], "limitaciones": "",
        }
        r = contexto.construir("T", "R", self._material())
        self.assertEqual(r["antecedentes"], [])
        self.assertEqual(r["descartadas"], 1)

    def test_afirmacion_sin_lista_de_fuentes_se_descarta(self):
        ia._generar_json = lambda *a, **k: {
            "antecedentes": [{"texto": "Sin fuentes"}],
            "actores": [], "que_es_nuevo": [], "que_falta_saber": [], "limitaciones": "",
        }
        r = contexto.construir("T", "R", self._material())
        self.assertEqual(r["antecedentes"], [])
        self.assertEqual(r["descartadas"], 1)

    def test_actores_usa_campo_apariciones_no_fuentes(self):
        ia._generar_json = lambda *a, **k: {
            "antecedentes": [], "que_es_nuevo": [], "que_falta_saber": [], "limitaciones": "",
            "actores": [{"nombre": "Fulano", "rol": "acusado", "apariciones": ["R1"]},
                        {"nombre": "Mengano", "rol": "testigo", "apariciones": ["R99"]}],
        }
        r = contexto.construir("T", "R", self._material())
        self.assertEqual(len(r["actores"]), 1)
        self.assertEqual(r["actores"][0]["nombre"], "Fulano")

    def test_que_falta_saber_sin_ids_es_valida(self):
        # una pregunta genuina puede surgir de lo que el material NO dice
        ia._generar_json = lambda *a, **k: {
            "antecedentes": [], "actores": [], "que_es_nuevo": [], "limitaciones": "",
            "que_falta_saber": [{"pregunta": "¿Que paso despues?", "por_que_importa": "x", "fuentes": []}],
        }
        r = contexto.construir("T", "R", self._material())
        self.assertEqual(len(r["que_falta_saber"]), 1)

    def test_que_falta_saber_con_id_inventado_se_descarta(self):
        ia._generar_json = lambda *a, **k: {
            "antecedentes": [], "actores": [], "que_es_nuevo": [], "limitaciones": "",
            "que_falta_saber": [{"pregunta": "¿Que paso?", "por_que_importa": "x", "fuentes": ["R99"]}],
        }
        r = contexto.construir("T", "R", self._material())
        self.assertEqual(r["que_falta_saber"], [])
        self.assertEqual(r["descartadas"], 1)

    def test_ia_fallo_devuelve_none(self):
        ia._generar_json = lambda *a, **k: None
        r = contexto.construir("T", "R", self._material())
        self.assertIsNone(r)


class TestFiltroLugarOMedio(unittest.TestCase):
    """Caso real (Fase 11 v2, Paso 1): 'Teleamazonas'/'Duran'/el aeropuerto
    terminaban como 'principal' de una historia sin relacion real."""

    def test_outlet_conocido_se_descarta(self):
        self.assertTrue(monitor._es_lugar_o_medio("Teleamazonas"))
        self.assertTrue(monitor._es_lugar_o_medio("El Universo"))

    def test_extracto_de_lugar_se_descarta(self):
        self.assertTrue(monitor._es_lugar_o_medio(
            "Duran", "Duran es una urbe de la provincia de Guayas, ubicada frente a Guayaquil."))

    def test_extracto_de_aeropuerto_se_descarta(self):
        self.assertTrue(monitor._es_lugar_o_medio(
            "Aeropuerto Jose Joaquin de Olmedo",
            "El Aeropuerto Jose Joaquin de Olmedo es un aeropuerto internacional ubicado en Guayaquil."))

    def test_persona_real_no_se_descarta(self):
        self.assertFalse(monitor._es_lugar_o_medio(
            "Fito", "Alias Fito lidera la banda criminal Los Choneros."))

    def test_nombre_sin_extracto_no_se_descarta_ante_la_duda(self):
        self.assertFalse(monitor._es_lugar_o_medio("Daniel Noboa"))


class TestHashFuentes(unittest.TestCase):
    def test_cambia_si_se_agrega_una_fuente(self):
        s1 = {"fuentes": [{"link": "https://a.com/1"}]}
        s2 = {"fuentes": [{"link": "https://a.com/1"}, {"link": "https://b.com/2"}]}
        self.assertNotEqual(monitor._hash_fuentes(s1), monitor._hash_fuentes(s2))

    def test_estable_si_no_cambia_nada(self):
        s = {"fuentes": [{"link": "https://a.com/1"}, {"link": "https://b.com/2"}]}
        self.assertEqual(monitor._hash_fuentes(s), monitor._hash_fuentes(s))

    def test_no_depende_del_orden(self):
        s1 = {"fuentes": [{"link": "https://a.com/1"}, {"link": "https://b.com/2"}]}
        s2 = {"fuentes": [{"link": "https://b.com/2"}, {"link": "https://a.com/1"}]}
        self.assertEqual(monitor._hash_fuentes(s1), monitor._hash_fuentes(s2))


class TestEsLocalEntry(unittest.TestCase):
    def test_con_ciudad_es_local(self):
        self.assertTrue(monitor._es_local_entry({"ciudad": "Guayaquil", "rep_titulo": "", "fundador_titulo": ""}))

    def test_texto_ecuador_es_local(self):
        self.assertTrue(monitor._es_local_entry(
            {"ciudad": "", "rep_titulo": "El Municipio de Quito anuncia obra", "fundador_titulo": ""}))

    def test_texto_extranjero_no_es_local(self):
        self.assertFalse(monitor._es_local_entry(
            {"ciudad": "", "rep_titulo": "El gobierno de Colombia anuncia reforma", "fundador_titulo": ""}))


class TestPersistenciaEmbeddingModelo(unittest.TestCase):
    """Bug real confirmado en el Paso 1: embedding_modelo se escribia en
    memoria pero nunca se guardaba ni se restauraba -- cada pasada volvia a
    tratar TODAS las entradas como pendientes."""

    def setUp(self):
        self._orig_path = monitor.REGISTRO_PATH
        import tempfile, os
        self._tmp = tempfile.mktemp(suffix=".json")
        monitor.REGISTRO_PATH = self._tmp

    def tearDown(self):
        import os
        monitor.REGISTRO_PATH = self._orig_path
        try:
            os.remove(self._tmp)
        except OSError:
            pass

    def test_embedding_modelo_sobrevive_guardar_y_cargar(self):
        registro = {
            "abc123": {
                "creado": _utc("2026-09-20T00:00:00"), "ultimo": _utc("2026-09-20T00:00:00"),
                "rep_titulo": "Titulo", "rep_resumen": "", "fundador_titulo": "Titulo", "fundador_resumen": "",
                "ciudad": "", "servicio": "", "fechas": set(), "embedding_multi": None,
                "tokens": set(), "nombres": set(), "numeros": set(),
                "embedding": [0.1, 0.2, 0.3], "embedding_modelo": "gemini-embedding-001",
                "embedding_multi_modelo": None, "fuentes": [], "actualizaciones": [],
            }
        }
        monitor._guardar_registro(registro)
        recargado = monitor._cargar_registro()
        self.assertEqual(recargado["abc123"]["embedding_modelo"], "gemini-embedding-001")
        self.assertEqual(recargado["abc123"]["embedding"], [0.1, 0.2, 0.3])


class TestRetencionLocalVsInternacional(unittest.TestCase):
    """Fase 11 (v2), Paso 2: lo local se retiene MONITOR_REGISTRO_DIAS_LOCAL
    (90 dias), lo internacional sigue en MAX_AGE_DAYS (3 dias) de siempre."""

    def _articulo(self, outlet, title, dias_atras, ciudad_feed=""):
        fecha = monitor.now_utc() - dt.timedelta(days=dias_atras)
        return {"outlet": outlet, "title": title, "link": "https://x.com/%s-%d" % (outlet, dias_atras),
                "date": fecha, "seccion": "seguridad", "summary": "", "image": "", "ciudad_feed": ciudad_feed}

    def test_local_vieja_sobrevive_la_purga_internacional(self):
        registro = {}
        viejo_local = self._articulo("El Universo", "Operativo en Guayaquil deja varios detenidos", 10,
                                      ciudad_feed="Guayaquil")
        registro = monitor._fusionar_en_registro([viejo_local], registro)
        self.assertEqual(len(registro), 1, "la entrada local de 10 dias no deberia purgarse (MAX_AGE_DAYS=3)")

    def test_internacional_vieja_se_purga_igual_que_siempre(self):
        registro = {}
        viejo_intl = self._articulo("Reuters", "Government of France announces reform", 10)
        registro = monitor._fusionar_en_registro([viejo_intl], registro)
        self.assertEqual(len(registro), 0, "una entrada internacional de 10 dias deberia purgarse (MAX_AGE_DAYS=3)")


class TestAntecedentesYActoresDelRegistro(unittest.TestCase):
    def _entrada(self, titulo, dias_atras, nombres, embedding=None, ciudad=""):
        return {
            "creado": monitor.now_utc() - dt.timedelta(days=dias_atras),
            "ultimo": monitor.now_utc() - dt.timedelta(days=dias_atras),
            "rep_titulo": titulo, "rep_resumen": "", "fundador_titulo": titulo, "fundador_resumen": "",
            "ciudad": ciudad, "servicio": "", "fechas": set(), "embedding_multi": None,
            "tokens": set(), "nombres": set(nombres), "numeros": set(),
            "embedding": embedding, "embedding_modelo": "m" if embedding else None,
            "embedding_multi_modelo": None,
            "fuentes": [{"link": "https://x.com/%s" % titulo[:10], "outlet": "X", "title": titulo}],
            "actualizaciones": [],
        }

    def test_entrada_propia_se_encuentra_por_link(self):
        registro = {"e1": self._entrada("Historia A", 0, {"fulano"})}
        s = {"fuentes": [{"link": registro["e1"]["fuentes"][0]["link"]}]}
        eid, e = monitor._entrada_propia_registro(s, registro)
        self.assertEqual(eid, "e1")

    def test_antecedente_debe_ser_estrictamente_anterior(self):
        # 'propio' (fundador_titulo real) determina el set de comparacion --
        # "Fulano Perez fue capturado nuevamente en la ciudad de Guayaquil" extrae {fulano,perez,guayaquil}
        # (3 nombres, asi que hacen falta 2+ en comun, ver _antecedentes_registro).
        registro = {
            "viejo": self._entrada("Fulano Perez fue visto liderando una banda criminal en la ciudad de Guayaquil", 5, {"fulano", "perez", "guayaquil"}),
            "propio": self._entrada("Fulano Perez fue capturado nuevamente en la ciudad de Guayaquil", 0, {"fulano", "perez", "guayaquil"}),
            "futuro": self._entrada("Fulano Perez fue citado a declarar ante fiscales en la ciudad de Guayaquil", -5, {"fulano", "perez", "guayaquil"}),  # mas nuevo
        }
        antecedentes = monitor._antecedentes_registro(registro["propio"], registro)
        titulos = [e["rep_titulo"] for e in antecedentes]
        self.assertIn("Fulano Perez fue visto liderando una banda criminal en la ciudad de Guayaquil", titulos)
        self.assertNotIn("Fulano Perez fue citado a declarar ante fiscales en la ciudad de Guayaquil", titulos)

    def test_sin_nombre_en_comun_no_es_antecedente(self):
        registro = {
            "otro": self._entrada("Zutano viaja al exterior", 5, {"zutano"}),
            "propio": self._entrada("Fulano Perez fue capturado nuevamente en la ciudad de Guayaquil", 0, {"fulano", "perez", "guayaquil"}),
        }
        antecedentes = monitor._antecedentes_registro(registro["propio"], registro)
        self.assertEqual(antecedentes, [])

    def test_un_solo_nombre_en_comun_no_alcanza_si_el_fundador_tiene_2_o_mas(self):
        # Bug real corregido en vivo (caso "esposa de alias Fito"): un solo
        # nombre generico compartido (ej. "Noboa", mencionado en decenas de
        # notas no relacionadas) no debe alcanzar para ser "antecedente" si
        # el fundador tiene 2+ nombres propios disponibles para exigir mas.
        registro = {
            "ruido": self._entrada("Una nota sin relacion real menciona a Perez", 5, {"perez"}),
            "propio": self._entrada("Fulano Perez fue capturado nuevamente en la ciudad de Guayaquil", 0, {"fulano", "perez", "guayaquil"}),
        }
        antecedentes = monitor._antecedentes_registro(registro["propio"], registro)
        self.assertEqual(antecedentes, [], "1 nombre en comun no debe alcanzar si el fundador tiene 2+")

    def test_apariciones_actor_excluye_la_propia_entrada(self):
        registro = {
            "propio": self._entrada("Hecho de hoy sobre fulano", 0, {"fulano"}),
            "otra": self._entrada("Fulano aparece en otro caso", 3, {"fulano"}),
        }
        apariciones = monitor._apariciones_actor_registro("fulano", registro, excluir_eid="propio")
        self.assertEqual(len(apariciones), 1)
        self.assertEqual(apariciones[0]["rep_titulo"], "Fulano aparece en otro caso")


class TestGetContextoTopLocal(unittest.TestCase):
    """Fase 11 (v2): automatico solo para las CONTEXTO_TOP historias locales
    mejor rankeadas -- las internacionales ya no compiten por el cupo."""

    def setUp(self):
        self._orig_construir = monitor._construir_contexto
        self._orig_ia = monitor.ia
        self._orig_wiki = monitor.wiki
        self._orig_top = monitor.CONTEXTO_TOP
        self._orig_max_new = monitor.CONTEXTO_MAX_NEW
        self._orig_cache_path = monitor.CONTEXTO_CACHE
        import tempfile
        monitor.CONTEXTO_CACHE = tempfile.mktemp(suffix=".json")
        monitor.CONTEXTO_TOP = 2
        monitor.CONTEXTO_MAX_NEW = 10
        self._llamadas = []

        class _IAFalsa:
            def disponible(self_inner, modelo=None):
                return True

        monitor.ia = _IAFalsa()
        monitor.wiki = object()

        def _fake_construir(s, registro=None, perfil=None):
            self._llamadas.append(s["titular"])
            self._perfiles = getattr(self, "_perfiles", {})
            self._perfiles[s["titular"]] = perfil or "profundo"
            return {"texto": "x", "entidades": [], "comenciones": [], "principal": None, "previas": [],
                    "antecedentes": [], "actores": [], "que_es_nuevo": [], "que_falta_saber": [],
                    "limitaciones": "", "descartadas": 0}
        monitor._construir_contexto = _fake_construir

    def tearDown(self):
        import os
        monitor._construir_contexto = self._orig_construir
        monitor.ia = self._orig_ia
        monitor.wiki = self._orig_wiki
        monitor.CONTEXTO_TOP = self._orig_top
        monitor.CONTEXTO_MAX_NEW = self._orig_max_new
        try:
            os.remove(monitor.CONTEXTO_CACHE)
        except OSError:
            pass
        monitor.CONTEXTO_CACHE = self._orig_cache_path

    def _historia(self, titular, es_local, interes, link):
        return {"titular": titular, "resumen": "", "es_local": es_local, "interes": interes,
                "fuentes": [{"link": link}], "temas": [], "ambito": "local" if es_local else "internacional"}

    def test_solo_procesa_top_n_locales_ignora_internacionales(self):
        stories = [
            self._historia("Local A (mas interes)", True, 100, "https://x.com/a"),
            self._historia("Local B", True, 50, "https://x.com/b"),
            self._historia("Local C (deberia quedar afuera, top=2)", True, 10, "https://x.com/c"),
            self._historia("Internacional grande", False, 999, "https://x.com/d"),
        ]
        monitor.get_contexto(stories)
        self.assertIn("Local A (mas interes)", self._llamadas)
        self.assertIn("Local B", self._llamadas)
        # Fase 18 (P2-10): lo local fuera del top N YA NO queda afuera -- se
        # contextualiza con el perfil RAPIDO (el top N sigue con el profundo).
        self.assertIn("Local C (deberia quedar afuera, top=2)", self._llamadas)
        self.assertEqual(self._perfiles["Local A (mas interes)"], "profundo")
        self.assertEqual(self._perfiles["Local C (deberia quedar afuera, top=2)"], "rapido")
        self.assertNotIn("Internacional grande", self._llamadas)

    def test_entrada_de_formato_viejo_se_recalcula_una_vez(self):
        # Bug real encontrado verificando en vivo (reinicio real de 'serve'):
        # una entrada cacheada de ANTES de este cambio (sin 'antecedentes')
        # nunca tenia '_fuentes_hash' para comparar, asi que el chequeo de
        # "esta vencida" daba siempre False y se quedaba en formato viejo
        # para siempre, aunque la historia siguiera en el top local.
        s = self._historia("Historia con cache vieja", True, 100, "https://x.com/vieja")
        key = monitor.story_key(s)
        with open(monitor.CONTEXTO_CACHE, "w", encoding="utf-8") as f:
            import json
            json.dump({key: {"texto": "viejo", "entidades": [], "comenciones": [], "principal": None}}, f)
        monitor.get_contexto([s])
        self.assertIn("Historia con cache vieja", self._llamadas,
                       "una entrada de formato viejo deberia recalcularse la primera vez que le toque cupo")


if __name__ == "__main__":
    unittest.main()
