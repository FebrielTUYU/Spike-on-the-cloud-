# -*- coding: utf-8 -*-
"""
Fase 23 (Parte A) -- pedido de Fernando (2026-09-30): "cuentas de noticias
comunitarias: paginas o personas que publican lo que pasa en los barrios...
Ahi se concentran las quejas." Con cuatro condiciones:
  - descubrir candidatas con datos REALES que Spike ya tiene, sin inventar
    usuarios, y descartar medios grandes e instituciones;
  - un tipo nuevo "comunitaria" que NUNCA cuenta como fuente oficial en
    Alertas y cuyas publicaciones entran a Comunidad como voz de la gente;
  - nada se agrega solo: el panel guarda solo lo que Fernando aprueba
    (y las URLs de Facebook que pega, validadas);
  - presupuesto: una consulta "from:A OR from:B" por tanda, medir tweets/dia y
    bajar primero la frecuencia de las comunitarias si el mes se acerca al tope.
Sin red real: Apify se reemplaza por dobles y todo se escribe en una carpeta
temporal.
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import alertas
import comunidad
import cuentas
import facebook
import redes
import xapi

AHORA = dt.datetime.now(dt.timezone.utc)


def _x(d):
    return d.strftime("%a %b %d %H:%M:%S +0000 %Y")


def _tweet(tid, autor, texto, horas_atras=1, **author_extra):
    a = {"userName": autor}
    a.update(author_extra)
    return {"id": str(tid), "text": texto, "createdAt": _x(AHORA - dt.timedelta(hours=horas_atras)),
            "url": "https://x.com/%s/status/%s" % (autor, tid), "author": a}


def _post(autor, texto, horas_atras=2, fuente="x"):
    return comunidad.normalizar_post(fuente, autor, texto, "https://x.com/%s/1" % autor.strip("@"),
                                     (AHORA - dt.timedelta(hours=horas_atras)).isoformat(), ahora=AHORA)


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (comunidad.COMUNIDAD_PATH, xapi.CACHE_PATH, xapi.CUENTAS_PATH, redes.CACHE_PATH,
                     redes.GASTO_PATH, facebook.FUENTES_PATH, alertas.ALERTAS_PATH, redes.activo,
                     xapi.buscar_consulta, redes.presupuesto_hoy, alertas.registrar_senal, xapi.activo,
                     redes._paso_frecuencia)
        comunidad.COMUNIDAD_PATH = os.path.join(self.tmp, "comunidad.json")
        xapi.CACHE_PATH = os.path.join(self.tmp, "x_cache.json")
        xapi.CUENTAS_PATH = os.path.join(self.tmp, "x_cuentas_locales.json")
        redes.CACHE_PATH = os.path.join(self.tmp, "redes_cache.json")
        redes.GASTO_PATH = os.path.join(self.tmp, "redes_gasto.json")
        facebook.FUENTES_PATH = os.path.join(self.tmp, "facebook_fuentes.json")
        alertas.ALERTAS_PATH = os.path.join(self.tmp, "alertas.json")
        redes.activo = lambda: True
        xapi.activo = lambda: True
        redes.presupuesto_hoy = lambda red: 0.10
        # Mismas cuentas de antes de la Fase 23 (sin campo 'tipo').
        self._escribir(xapi.CUENTAS_PATH, {"cuentas": [
            {"usuario": "ECU911_", "nombre": "ECU 911", "oficial": True, "verificada": False, "activa": True},
            {"usuario": "EmergenciasEc", "oficial": False, "verificada": True, "activa": True}]})

    def tearDown(self):
        (comunidad.COMUNIDAD_PATH, xapi.CACHE_PATH, xapi.CUENTAS_PATH, redes.CACHE_PATH, redes.GASTO_PATH,
         facebook.FUENTES_PATH, alertas.ALERTAS_PATH, redes.activo, xapi.buscar_consulta, redes.presupuesto_hoy,
         alertas.registrar_senal, xapi.activo, redes._paso_frecuencia) = self.orig

    def _escribir(self, ruta, datos):
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)

    def _leer(self, ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)


# ----------------------------------------------------------------- 1. descubrimiento
class TestDescubrimiento(_Tmp):
    def _fuentes_reales(self):
        """Tres fuentes de datos con la forma real de los archivos de Spike."""
        posts = [_post("@vecina_garzota", "En la Garzota llevamos 3 dias sin luz, nadie hace nada"),
                 _post("@vecina_garzota", "Robaron otra vez en la Garzota, hasta cuando"),
                 _post("@una_sola_vez", "Sin agua en el Guasmo desde ayer")]
        reg = {"version": comunidad.VERSION, "posts": {p["id"]: p for p in posts if p}, "ultimas": {}}
        self._escribir(comunidad.COMUNIDAD_PATH, reg)
        tweets = [
            # pagina de barrio con formato de noticia: SI es candidata
            _tweet(1, "GyeDenuncia", "#ATENCION | Moradores de Sauces denuncian que hace una semana no pasa el carro de la basura",
                   name="Guayaquil Denuncia", followers=8000),
            _tweet(2, "GyeDenuncia", "Vecinos del Suburbio reclaman por baches en la calle 20, nadie hace nada",
                   name="Guayaquil Denuncia", followers=8000),
            # medio grande: NO
            _tweet(3, "DiarioGrande", "Inundacion en el Guasmo tras la lluvia en Guayaquil", name="Diario Grande",
                   followers=900000),
            _tweet(4, "DiarioGrande", "Sin agua en Sauces, reportan moradores de Guayaquil", name="Diario Grande",
                   followers=900000),
            # institucion: NO
            _tweet(5, "PoliciaZona8", "Robo en la Alborada, Guayaquil: detenidos dos sospechosos",
                   name="Policia Ecuador Guayaquil - Zona8", followers=30000),
            _tweet(6, "PoliciaZona8", "Asalto en Urdesa, Guayaquil, capturados", name="Policia Ecuador Guayaquil - Zona8",
                   followers=30000),
            # politico (bio en profile_bio, como la trae Apify): NO
            _tweet(7, "unministro", "Operativo contra robos en el Guasmo de Guayaquil", name="Un Ministro",
                   profile_bio={"description": "Ministro del Interior"}, followers=40000),
            _tweet(8, "unministro", "Mas patrullaje contra la extorsion en Guayaquil", name="Un Ministro",
                   profile_bio={"description": "Ministro del Interior"}, followers=40000),
            # quejas que etiquetan a una pagina de barrio: candidata "solo mencionada"
            _tweet(9, "vecino1", "@AlertaSur sin luz en el Guasmo Sur desde las 6, Guayaquil"),
            _tweet(10, "vecino2", "@AlertaSur se inunda la Floresta otra vez, Guayaquil"),
            _tweet(11, "vecino3", "@AlertaSur asaltaron un bus en la Trinitaria, Guayaquil"),
            # de hace 30 dias: no cuenta
            _tweet(12, "cuenta_vieja", "Sin agua en el Guasmo, Guayaquil", horas_atras=24 * 30),
            _tweet(13, "cuenta_vieja", "Baches en Sauces, Guayaquil", horas_atras=24 * 30),
        ]
        self._escribir(xapi.CACHE_PATH, {"historias": {"link1": {"tweets": tweets}}})
        self._escribir(redes.CACHE_PATH, {
            "red_emergencias": {"vecina_garzota": {"n": 4, "ult": AHORA.isoformat()},
                                "solo_red": {"n": 3, "ult": AHORA.isoformat()}},
            "emergencias_feed": [
                {"id": "20", "autor": "@vecina_garzota", "texto": "En la Garzota llevamos 3 dias sin luz, nadie hace nada",
                 "url": "u", "fecha": AHORA.isoformat(), "tipo": "respuesta"},
                {"id": "21", "autor": "@solo_red", "texto": "Balacera en la Isla Trinitaria ahora, Guayaquil",
                 "url": "u2", "fecha": AHORA.isoformat(), "tipo": "red"}]})

    def test_rankea_por_quejas_distintas_y_filtra_medios_e_instituciones(self):
        self._fuentes_reales()
        c = {x["usuario"]: x for x in cuentas.candidatas(ahora=AHORA)}
        self.assertIn("GyeDenuncia", c)
        self.assertIn("vecina_garzota", c)
        self.assertIn("AlertaSur", c)
        for fuera in ("DiarioGrande", "PoliciaZona8", "unministro", "cuenta_vieja", "una_sola_vez"):
            self.assertNotIn(fuera, c, fuera)
        # La misma queja por dos vias (comunidad.json y el feed de EmergenciasEc) cuenta una vez.
        self.assertEqual(c["vecina_garzota"]["quejas"], 2)
        self.assertEqual(c["vecina_garzota"]["interacciones"], 4)
        self.assertEqual(c["GyeDenuncia"]["quejas"], 2)
        self.assertTrue(c["GyeDenuncia"]["verificada"])
        # Solo mencionada: nunca se la vio publicar -> no verificada.
        self.assertEqual(c["AlertaSur"]["quejas"], 0)
        self.assertEqual(c["AlertaSur"]["menciones"], 3)
        self.assertFalse(c["AlertaSur"]["verificada"])
        orden = [x["usuario"] for x in cuentas.candidatas(ahora=AHORA)]
        self.assertLess(orden.index("vecina_garzota"), orden.index("AlertaSur"))
        self.assertTrue(c["GyeDenuncia"]["ejemplo"]["texto"])

    def test_no_inventa_usuarios(self):
        self._fuentes_reales()
        crudo = json.dumps([self._leer(p) for p in (comunidad.COMUNIDAD_PATH, xapi.CACHE_PATH, redes.CACHE_PATH)])
        for x in cuentas.candidatas(ahora=AHORA):
            self.assertIn(x["usuario"], crudo)

    def test_seguidas_y_descartadas_no_se_sugieren(self):
        self._fuentes_reales()
        cuentas.agregar("GyeDenuncia")
        cuentas.descartar("AlertaSur")
        c = {x["usuario"] for x in cuentas.candidatas(ahora=AHORA)}
        self.assertNotIn("GyeDenuncia", c)
        self.assertNotIn("AlertaSur", c)
        self.assertNotIn("EmergenciasEc", c)

    def test_sin_datos_no_hay_sugerencias(self):
        self.assertEqual(cuentas.candidatas(ahora=AHORA), [])


# ----------------------------------------------------------------- 2. tipo comunitaria
class TestTipoComunitaria(_Tmp):
    def test_entradas_viejas_sin_tipo(self):
        cfg = cuentas.cargar_config()
        tipos = {c["usuario"]: cuentas.tipo_cuenta(c) for c in cfg["cuentas"]}
        self.assertEqual(tipos, {"ECU911_": "oficial", "EmergenciasEc": "local"})

    def test_agregar_guarda_tipo_comunitaria(self):
        ok, _ = cuentas.agregar("@GyeDenuncia", "Guayaquil Denuncia", verificada=True)
        self.assertTrue(ok)
        c = [x for x in self._leer(xapi.CUENTAS_PATH)["cuentas"] if x["usuario"] == "GyeDenuncia"][0]
        self.assertEqual((c["tipo"], c["oficial"], c["verificada"], c["activa"]), ("comunitaria", False, True, True))
        # Las demas cuentas siguen intactas.
        self.assertEqual(len(self._leer(xapi.CUENTAS_PATH)["cuentas"]), 3)

    def test_nunca_es_oficial(self):
        self.assertFalse(cuentas.es_oficial({"usuario": "x", "tipo": "comunitaria", "oficial": True}))
        self.assertTrue(cuentas.es_oficial({"usuario": "ECU911_", "oficial": True}))

    def test_no_pisa_una_oficial_ni_acepta_usuarios_invalidos(self):
        self.assertFalse(cuentas.agregar("ECU911_")[0])
        self.assertFalse(cuentas.agregar("no valido con espacios")[0])
        self.assertFalse(cuentas.agregar("x" * 16)[0])
        self.assertFalse(cuentas.agregar("ñandú")[0])  # X solo acepta handles ASCII
        self.assertFalse(cuentas.quitar("ECU911_")[0])

    def test_pausar_activar_quitar(self):
        cuentas.agregar("GyeDenuncia")
        cuentas.activar("GyeDenuncia", False)
        self.assertEqual(cuentas.comunitarias(), [])
        cuentas.activar("GyeDenuncia", True)
        self.assertEqual([c["usuario"] for c in cuentas.comunitarias()], ["GyeDenuncia"])
        self.assertTrue(cuentas.quitar("GyeDenuncia")[0])
        self.assertEqual(cuentas.comunitarias(solo_activas=False), [])

    def test_descartar_se_guarda(self):
        cuentas.descartar("AlertaSur")
        self.assertEqual([d["usuario"] for d in self._leer(xapi.CUENTAS_PATH)["descartadas"]], ["AlertaSur"])
        # Aprobarla despues la saca de descartadas.
        cuentas.agregar("AlertaSur")
        self.assertEqual(self._leer(xapi.CUENTAS_PATH)["descartadas"], [])


# ----------------------------------------------------------------- 3. Alertas y Comunidad
class TestAlertasYComunidad(_Tmp):
    def _capturar_senales(self):
        self.senales = []

        def registrar(fuente, autor, texto, url, fecha, oficial=False, **kw):
            self.senales.append((autor, oficial))
            return {"ok": True}
        alertas.registrar_senal = registrar

    def test_comunitaria_no_confirma_alertas(self):
        self._capturar_senales()
        cuentas.agregar("GyeDenuncia")
        # Aunque alguien la marque 'oficial' a mano en el archivo, no cuenta.
        cfg = self._leer(xapi.CUENTAS_PATH)
        for c in cfg["cuentas"]:
            if c["usuario"] == "GyeDenuncia":
                c["oficial"] = True
        self._escribir(xapi.CUENTAS_PATH, cfg)
        xapi.buscar_consulta = lambda q, clave, horas, max_items, simular=False, **kw: (
            [_tweet(1, "GyeDenuncia", "Incendio en Sauces 8, Guayaquil, bomberos en camino")], 0.001)
        redes.pasada_comunitarias()
        self.assertEqual(self.senales, [("GyeDenuncia", False)])

    def test_capa_de_cuentas_oficiales_no_incluye_comunitarias(self):
        self._capturar_senales()
        cuentas.agregar("GyeDenuncia")
        consultas = []

        def buscar(q, clave, horas, max_items, simular=False, **kw):
            consultas.append(q)
            return [_tweet(2, "ECU911_", "Incendio en Sauces, Guayaquil")], 0.001
        xapi.buscar_consulta = buscar
        redes._paso_frecuencia = lambda clave, h: clave == "_cuentas_x"  # solo la capa de cuentas
        redes.pasada([], ["incendio"], [], cuentas=cuentas.cargar_config()["cuentas"])
        self.assertEqual(len(consultas), 1)
        self.assertIn("from:ECU911_", consultas[0])
        self.assertNotIn("GyeDenuncia", consultas[0])
        self.assertNotIn("EmergenciasEc", consultas[0])
        self.assertEqual(self.senales, [("ECU911_", True)])

    def test_publicaciones_entran_a_comunidad_como_voz_de_la_gente(self):
        texto = "#ATENCION | Moradores del Guasmo Sur llevan 3 dias sin agua, nadie de Interagua responde"
        t = _tweet(1, "AlertaGye", texto, name="Alerta Gye")
        # Sin aprobar: el handle parece de noticias y queda afuera (comportamiento de la Fase 20).
        self.assertEqual(comunidad.registrar_tweets([t]), 0)
        cuentas.agregar("AlertaGye")
        self.assertEqual(comunidad.registrar_tweets([t]), 1)
        p = list(comunidad._cargar()["posts"].values())[0]
        self.assertEqual((p["autor"], p["via"], p["categoria"]), ("@AlertaGye", "comunitaria", "agua"))
        # Igual tiene que ser de Guayaquil y nombrar un problema.
        self.assertEqual(comunidad.registrar_tweets([_tweet(2, "AlertaGye", "Sin agua en Quito norte")]), 0)
        self.assertEqual(comunidad.registrar_tweets([_tweet(3, "AlertaGye", "Buenos dias Guayaquil, feliz martes")]), 0)

    def test_es_persona_con_y_sin_marca(self):
        self.assertFalse(comunidad.es_persona("@AlertaGye"))
        self.assertTrue(comunidad.es_persona("@AlertaGye", comunitaria=True))
        self.assertFalse(comunidad.es_persona("@AlertaGye", oficial=True, comunitaria=True))


# ----------------------------------------------------------------- 4. presupuesto
class TestPresupuesto(_Tmp):
    def setUp(self):
        super().setUp()
        self.consultas = []

        def buscar(q, clave, horas, max_items, simular=False, **kw):
            self.consultas.append(q)
            return [_tweet(len(self.consultas), "GyeDenuncia", "Sin agua en el Guasmo, Guayaquil, nadie hace nada")], 0.002
        xapi.buscar_consulta = buscar
        alertas.registrar_senal = lambda *a, **k: None

    def test_una_consulta_por_tanda(self):
        for i in range(40):
            cuentas.agregar("barrio_%02d" % i)
        tandas = xapi.tandas_cuentas(cuentas.comunitarias())
        self.assertGreater(len(tandas), 1)
        for t in tandas:
            self.assertLessEqual(len(xapi.consulta_cuentas(t).split(" since:")[0]), xapi.TANDA_MAX_CHARS)
        self.assertEqual(sum(len(t) for t in tandas), 40)
        redes.pasada_comunitarias()
        self.assertEqual(len(self.consultas), len(tandas))
        self.assertTrue(all(q.startswith("(from:") for q in self.consultas))

    def test_mide_tweets_por_dia(self):
        cuentas.agregar("GyeDenuncia")
        self.assertIsNone(redes.comunitarias_dashboard()["tweets_dia_prom"])  # sin medir: None, no 0
        redes.pasada_comunitarias()
        d = redes.comunitarias_dashboard()
        self.assertEqual((d["hoy"]["consultas"], d["hoy"]["tweets"]), (1, 1))
        self.assertAlmostEqual(d["hoy"]["usd"], 0.002)
        self.assertEqual(d["tweets_dia_prom"], 1.0)
        self.assertEqual(redes.estado_dashboard()["comunitarias"]["hoy"]["tweets"], 1)
        # Frecuencia propia: a los pocos minutos no se repite.
        self.assertEqual(redes.pasada_comunitarias(), "todavia no toca")

    def test_cerca_del_tope_bajan_primero_las_comunitarias(self):
        cuentas.agregar("GyeDenuncia")

        def gastado_en_el_mes(frac):  # gasto de dias anteriores (hoy: 0)
            self._escribir(redes.GASTO_PATH, {"dias": {}, "historial": [],
                                              "meses": {redes._mes(): {"x": redes.TOPE_MES_USD * frac}}})
        gastado_en_el_mes(0.80)  # queda 20%
        minutos, motivo = redes.ritmo_comunitarias()
        self.assertEqual(minutos, redes.FREQ_COMUNITARIAS_MIN * 4)
        self.assertIn("reducida", motivo)
        gastado_en_el_mes(0.95)  # queda 5%
        self.assertIn("pausada", redes.pasada_comunitarias())
        self.assertEqual(self.consultas, [])
        # EmergenciasEc sigue: su consulta cabe en lo que queda del mes.
        self.assertTrue(redes.cabe("x", xapi.costo_estimado(redes.EMERG_MAX_ITEMS))[0])
        r = redes.pasada_emergencias()
        self.assertNotIn("saltada", r)
        self.assertIn("from:EmergenciasEc", self.consultas[0])

    def test_techo_de_cobro_de_apify_acotado(self):
        cuentas.agregar("GyeDenuncia")
        techos = []

        def buscar(q, clave, horas, max_items, simular=False, tope_seguridad_usd=0.30):
            techos.append(tope_seguridad_usd)
            return [], 0.0
        xapi.buscar_consulta = buscar
        redes.pasada_comunitarias()
        self.assertEqual(len(techos), 1)
        self.assertLessEqual(techos[0], xapi.costo_estimado(redes.COMUNITARIAS_MAX_ITEMS) * 2)
        self.assertLessEqual(techos[0], 0.10 * redes.COMUNITARIAS_PARTE_X)

    def test_tope_diario_propio(self):
        cuentas.agregar("GyeDenuncia")
        redes._sumar_uso_comunitarias(0, 0.10 * redes.COMUNITARIAS_PARTE_X, 0)
        r = redes.pasada_comunitarias()
        self.assertIn("parte de las comunitarias", r)
        self.assertEqual(self.consultas, [])


# ----------------------------------------------------------------- 5. Facebook
class TestFacebook(_Tmp):
    def test_agrega_paginas_y_grupos_validos(self):
        self.assertTrue(cuentas.fb_agregar("paginas", "https://m.facebook.com/GuayaquilDenuncia/?ref=bookmarks")[0])
        self.assertTrue(cuentas.fb_agregar("grupos", "https://www.facebook.com/groups/vecinosdesauces/posts/123")[0])
        d = self._leer(facebook.FUENTES_PATH)
        self.assertEqual(d["paginas"], ["https://www.facebook.com/GuayaquilDenuncia"])
        self.assertEqual(d["grupos"], ["https://www.facebook.com/groups/vecinosdesauces"])
        self.assertIn("_ayuda", d)
        self.assertEqual(facebook.fuentes(), {"paginas": d["paginas"], "grupos": d["grupos"]})

    def test_rechaza_lo_que_no_sirve(self):
        for tipo, url in (("paginas", "https://twitter.com/algo"), ("paginas", "facebook.com/sin_esquema"),
                          ("paginas", "https://www.facebook.com/groups/vecinos"), ("grupos", "https://www.facebook.com/UnaPagina"),
                          ("paginas", "https://www.facebook.com/login"), ("otro", "https://www.facebook.com/x"),
                          ("paginas", "https://facebook.com.evil.example/GuayaquilDenuncia"),
                          ("paginas", "https://usuario@facebook.com/GuayaquilDenuncia"),
                          ("paginas", "javascript:alert(1)//facebook.com/x"), ("grupos", "https://www.facebook.com/groups/")):
            self.assertFalse(cuentas.fb_agregar(tipo, url)[0], url)
        self.assertEqual(cuentas.fuentes_facebook(), {"paginas": [], "grupos": []})

    def test_perfil_con_id_y_siempre_canonico(self):
        ok, _ = cuentas.fb_agregar("paginas", "https://web.facebook.com/profile.php?id=100064#top")
        self.assertTrue(ok)
        self.assertEqual(cuentas.fuentes_facebook()["paginas"], ["https://www.facebook.com/profile.php?id=100064"])
        for u in cuentas.fuentes_facebook()["paginas"]:
            self.assertTrue(u.startswith("https://www.facebook.com/"))

    def test_sin_duplicados_y_quitar(self):
        cuentas.fb_agregar("paginas", "https://www.facebook.com/GuayaquilDenuncia")
        self.assertFalse(cuentas.fb_agregar("paginas", "https://facebook.com/GuayaquilDenuncia/")[0])
        self.assertTrue(cuentas.fb_quitar("paginas", "https://www.facebook.com/GuayaquilDenuncia")[0])
        self.assertEqual(cuentas.fuentes_facebook()["paginas"], [])


# ----------------------------------------------------------------- 6. panel
class TestPanel(_Tmp):
    def test_panel_trae_todo_lo_que_dibuja_el_dashboard(self):
        cuentas.agregar("GyeDenuncia")
        cuentas.fb_agregar("grupos", "https://www.facebook.com/groups/vecinosdesauces")
        p = cuentas.panel(ahora=AHORA)
        self.assertEqual([c["usuario"] for c in p["seguidas"]], ["GyeDenuncia"])
        self.assertEqual(p["seguidas"][0]["tipo"], "comunitaria")
        self.assertEqual(p["oficiales"], ["ECU911_"])
        self.assertEqual(p["facebook"]["grupos"], ["https://www.facebook.com/groups/vecinosdesauces"])
        self.assertIn("ritmo", p["uso"])
        self.assertEqual(p["sugeridas"], [])


if __name__ == "__main__":
    unittest.main()
