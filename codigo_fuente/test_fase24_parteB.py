# -*- coding: utf-8 -*-
"""
Fase 24, Parte B -- recoleccion local mas amplia (Guayaquil). Sin red: Apify,
YouTube, Google News y ntfy son dobles; todo se escribe en carpetas temporales.
  B1 X: consultas que no exigen "Guayaquil" (instituciones, barrios), rotacion
     y rendimiento por consulta;
  B2 YouTube: comentarios de los canales de medios;
  B3 fuentes institucionales marcadas como tales;
  B3b funcionarios: tipo, registro, aviso, adelanto frente a la prensa;
  B5 Bluesky y Mastodon fuera del Pulso social y de Comunidad.
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import comunidad
import feeds
import funcionarios
import lugares
import mapa
import pulso
import redes
import social
import xapi
import youtube_canales as yc

AHORA = dt.datetime.now(dt.timezone.utc)


def _x(d):
    return d.strftime("%a %b %d %H:%M:%S +0000 %Y")


def _tw(tid, autor, texto, horas=1, **extra):
    t = {"id": str(tid), "text": texto, "createdAt": _x(AHORA - dt.timedelta(hours=horas)),
         "url": "https://x.com/%s/status/%s" % (autor, tid), "author": {"userName": autor}}
    t.update(extra)
    return t


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (comunidad.COMUNIDAD_PATH, redes.CACHE_PATH, redes.GASTO_PATH, xapi.CACHE_PATH, xapi.CUENTAS_PATH,
                     redes.activo, xapi.buscar_consulta, redes.presupuesto_hoy, funcionarios.CONFIG_PATH,
                     funcionarios.ESTADO_PATH, yc.ESTADO_PATH, yc.CANALES_PATH)
        comunidad.COMUNIDAD_PATH = os.path.join(self.tmp, "comunidad.json")
        redes.CACHE_PATH = os.path.join(self.tmp, "redes_cache.json")
        redes.GASTO_PATH = os.path.join(self.tmp, "redes_gasto.json")
        xapi.CACHE_PATH = os.path.join(self.tmp, "x_cache.json")
        xapi.CUENTAS_PATH = os.path.join(self.tmp, "x_cuentas.json")
        funcionarios.CONFIG_PATH = os.path.join(self.tmp, "funcionarios.json")
        funcionarios.ESTADO_PATH = os.path.join(self.tmp, "funcionarios_estado.json")
        yc.ESTADO_PATH = os.path.join(self.tmp, "yt_estado.json")
        yc.CANALES_PATH = os.path.join(self.tmp, "yt_canales.json")
        redes.activo = lambda: True
        redes.presupuesto_hoy = lambda red: 0.10

    def tearDown(self):
        (comunidad.COMUNIDAD_PATH, redes.CACHE_PATH, redes.GASTO_PATH, xapi.CACHE_PATH, xapi.CUENTAS_PATH,
         redes.activo, xapi.buscar_consulta, redes.presupuesto_hoy, funcionarios.CONFIG_PATH,
         funcionarios.ESTADO_PATH, yc.ESTADO_PATH, yc.CANALES_PATH) = self.orig


# ----------------------------------------------------------------- B5
class TestB5SinBlueskyNiMastodon(unittest.TestCase):
    def test_pulso_y_comunidad_los_dejan_afuera(self):
        self.assertEqual(pulso.FUERA_DEL_PULSO, {"bluesky", "mastodon"})
        self.assertIsNone(pulso._post("bluesky", "a", "texto de prueba", "", "", "x"))
        self.assertIsNotNone(pulso._post("x", "a", "texto de prueba", "", "", "x"))
        self.assertFalse(comunidad.COMUNIDAD_BLUESKY)
        self.assertFalse(social.PULSO_BLUESKY or social.PULSO_MASTODON)

    def test_recolectar_no_llama_a_bluesky(self):
        llamadas = []
        orig = (social.bluesky_buscar, social.mastodon_buscar, social.reddit_buscar, social.telegram_buscar)
        social.bluesky_buscar = lambda *a, **k: llamadas.append("bluesky") or []
        social.mastodon_buscar = lambda *a, **k: llamadas.append("mastodon") or []
        social.reddit_buscar = lambda *a, **k: []
        social.telegram_buscar = lambda *a, **k: []
        try:
            social.recolectar("tema", youtube=False, ambito="internacional")
        finally:
            social.bluesky_buscar, social.mastodon_buscar, social.reddit_buscar, social.telegram_buscar = orig
        self.assertEqual(llamadas, [])


# ----------------------------------------------------------------- B1
class TestB1ConsultasX(_Tmp):
    def test_consultas_sin_exigir_guayaquil(self):
        cs = comunidad.consultas_x(horas=2)
        ids = [c["id"] for c in cs]
        self.assertEqual(ids[0], "instituciones")
        self.assertIn("guayaquil", ids)
        self.assertTrue(any(i.startswith("barrios_") for i in ids))
        inst = cs[0]["q"]
        for u in ("to:alcaldiagye", "@Interagua_Ec", "-from:alcaldiagye", "-filter:retweets", "since:"):
            self.assertIn(u, inst)
        self.assertNotIn('"Guayaquil"', inst)  # el termino no se exige; solo aparece dentro de usuarios
        for c in cs:
            if c["id"].startswith("barrios_"):
                self.assertNotIn('"Guayaquil"', c["q"])
                self.assertLessEqual(len(c["q"]), 520)
                for ruidoso in ("Kennedy", "Centro", "Bellavista"):
                    self.assertNotIn('"%s"' % ruidoso, c["q"])

    def test_queja_a_una_institucion_de_guayaquil_cuenta_aunque_no_diga_guayaquil(self):
        n = comunidad.registrar_tweets([_tw(1, "vecina", "@alcaldiagye la calle esta llena de baches y nadie hace nada")])
        self.assertEqual(n, 1)
        # Una institucion nacional no alcanza, y otra ciudad nombrada tampoco.
        self.assertEqual(comunidad.registrar_tweets([_tw(2, "vecino", "@CNEL_EP llevamos 3 horas sin luz")]), 0)
        self.assertEqual(comunidad.registrar_tweets([_tw(3, "otro", "@alcaldiagye en Quito tambien hay baches")]), 0)

    def test_rotacion_y_rendimiento(self):
        consultas = []

        def buscar(q, clave, horas, max_items, simular=False, **k):
            consultas.append(q)
            return [], 0.0
        xapi.buscar_consulta = buscar
        ids = [c["id"] for c in comunidad.consultas_x(horas=1)]
        for _ in range(len(ids)):
            redes._marcar_corrida  # noqa
            redes._ultima_vez = lambda clave: None  # siempre "toca"
            redes.pasada_comunidad()
        # Cada consulta corrio una vez (rota, no repite la misma).
        rend = {r["id"]: r for r in redes.rendimiento_comunidad()}
        self.assertEqual(set(rend), set(ids))
        self.assertTrue(all(r["corridas"] == 1 for r in rend.values()))

    def test_las_que_no_rinden_se_apagan_una_semana(self):
        for _ in range(redes.RENDIMIENTO_CORRIDAS_MIN):
            redes._anotar_rendimiento("barrios_0", 20, 0, 0.005)
        r = {x["id"]: x for x in redes.rendimiento_comunidad()}["barrios_0"]
        self.assertTrue(r["apagada"])
        self.assertNotEqual(redes._elegir_consulta_comunidad(["barrios_0", "instituciones"]), "barrios_0")
        for _ in range(redes.RENDIMIENTO_CORRIDAS_MIN):
            redes._anotar_rendimiento("instituciones", 20, 8, 0.005)  # 16 por cada $0.01
        self.assertFalse({x["id"]: x for x in redes.rendimiento_comunidad()}["instituciones"]["apagada"])

    def test_costo_cero_de_apify_no_da_rendimiento_infinito(self):
        redes._anotar_rendimiento("guayaquil", 20, 2, 0.0)
        r = {x["id"]: x for x in redes.rendimiento_comunidad()}["guayaquil"]
        self.assertGreater(r["usd"], 0)
        self.assertLess(r["rendimiento"], 100)

    def test_panel_trae_proyeccion_y_consultas(self):
        orig = xapi.activo
        xapi.activo = lambda: True
        try:
            e = redes.estado_dashboard()
        finally:
            xapi.activo = orig
        self.assertIn("proyeccion_mes", e)
        self.assertIn("consultas_comunidad", e)


# ----------------------------------------------------------------- B2
class TestB2YouTube(_Tmp):
    def setUp(self):
        super().setUp()
        self.orig_get, self.orig_clave = yc._get, yc._clave
        yc._clave = lambda: "clave"
        hace = lambda h: (AHORA - dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def get(ruta, params, unidades):
            yc._gastar(unidades)
            if ruta == "playlistItems":
                return {"items": [
                    {"snippet": {"resourceId": {"videoId": "v1"}, "publishedAt": hace(3),
                                 "title": "Moradores del Guasmo denuncian que no pasa el recolector"}},
                    {"snippet": {"resourceId": {"videoId": "v2"}, "publishedAt": hace(100), "title": "video viejo"}}]}
            return {"items": [
                {"snippet": {"topLevelComment": {"id": "c1", "snippet": {
                    "authorDisplayName": "Vecina", "textDisplay": "Aqui la basura se acumula desde hace una semana",
                    "publishedAt": hace(1)}}}},
                {"snippet": {"topLevelComment": {"id": "c2", "snippet": {
                    "authorDisplayName": "Otro", "textDisplay": "jaja", "publishedAt": hace(1)}}}}]}
        yc._get = get

    def tearDown(self):
        yc._get, yc._clave = self.orig_get, self.orig_clave
        super().tearDown()

    def test_comentario_de_video_de_guayaquil_entra_con_el_sector_del_titulo(self):
        posts, est = yc.pasada(forzar=True)
        self.assertEqual(len(posts), 1)
        self.assertEqual((posts[0]["barrio"], posts[0]["categoria"]), ("Guasmo", "basura"))
        self.assertIn("4 videos", est)  # uno por canal: el de hace 100 h no cuenta
        # La segunda vez no repite comentarios ya vistos.
        posts2, _ = yc.pasada(forzar=True)
        self.assertEqual(posts2, [])

    def test_respeta_el_presupuesto_de_unidades(self):
        orig = yc.UNIDADES_DIA
        yc.UNIDADES_DIA = 0
        yc._get = self.orig_get  # el real: corta antes de llamar
        try:
            posts, _ = yc.pasada(forzar=True)
        finally:
            yc.UNIDADES_DIA = orig
        self.assertEqual(posts, [])
        self.assertIn("presupuesto", yc.last_error or "")

    def test_cuota_se_reserva_bajo_candado(self):
        import threading
        orig = yc.UNIDADES_DIA
        yc.UNIDADES_DIA = 5
        yc._get = self.orig_get
        llamadas = []
        import urllib.request
        orig_open = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: llamadas.append(1) or (_ for _ in ()).throw(OSError("sin red"))
        try:
            hilos = [threading.Thread(target=yc._get, args=("x", {}, 1)) for _ in range(20)]
            [h.start() for h in hilos]; [h.join() for h in hilos]
        finally:
            urllib.request.urlopen = orig_open
            yc.UNIDADES_DIA = orig
        self.assertEqual(yc.unidades_hoy(), 5)
        self.assertEqual(len(llamadas), 5)

    def test_busqueda_por_barrio_una_vez_por_turno(self):
        hace = lambda h: (AHORA - dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rutas = []
        barrio = yc._barrios_busqueda()[0]
        orig_canales = yc.canales
        yc.canales = lambda: []  # solo la busqueda
        def get(ruta, params, unidades):
            yc._gastar(unidades); rutas.append((ruta, params.get("q"), unidades))
            if ruta == "search":
                return {"items": [{"id": {"videoId": "s1"}, "snippet": {"publishedAt": hace(2),
                                   "title": "Vecinos de %s denuncian falta de agua" % barrio}}]}
            return {"items": [{"snippet": {"topLevelComment": {"id": "k1", "snippet": {
                "authorDisplayName": "Vecina", "textDisplay": "Tres dias sin agua potable en la cuadra",
                "publishedAt": hace(1)}}}}]}
        yc._get = get
        try:
            posts, est = yc.pasada(forzar=True)
            posts2, _ = yc.pasada(forzar=True)
        finally:
            yc.canales = orig_canales
        self.assertEqual(rutas[0], ("search", '"%s" Guayaquil' % barrio, 100))
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["barrio"], barrio)  # el barrio buscado, aunque el comentario no lo nombre
        self.assertIn("busqueda por barrio", est)
        self.assertEqual(sum(1 for r in rutas if r[0] == "search"), 1)  # la segunda pasada todavia no toca
        self.assertEqual(posts2, [])

    def test_busqueda_bloqueada_no_insiste_hasta_manana(self):
        orig_canales = yc.canales
        yc.canales = lambda: []
        busquedas = []
        def get(ruta, params, unidades):
            busquedas.append(ruta)
            yc.last_error = "search HTTP 429"
            return None
        yc._get = get
        try:
            yc.pasada(forzar=True)
            yc.pasada(forzar=True)
        finally:
            yc.canales = orig_canales
        self.assertEqual(busquedas, ["search"])
        self.assertTrue(yc.estado_dashboard()["busqueda_bloqueada_hoy"])

    def test_canales_verificados_por_defecto(self):
        nombres = {c["nombre"] for c in yc.canales()}
        self.assertEqual(nombres, {"El Universo", "Ecuavisa", "RTS", "Diario Extra"})


# ----------------------------------------------------------------- B3
class TestB3Fuentes(unittest.TestCase):
    def test_institucionales_marcadas(self):
        for o in ("CNEL EP", "Bomberos Guayaquil", "INAMHI", "Municipio de Guayaquil", "ECU 911"):
            self.assertIn(o, feeds.OUTLETS_INSTITUCIONALES)
        self.assertNotIn("El Universo", feeds.OUTLETS_INSTITUCIONALES)

    def test_busquedas_nuevas(self):
        outs = {f["outlet"] for f in feeds.FEEDS}
        for o in ("Busqueda: Interagua", "Busqueda: problemas Guayaquil", "Metro Ecuador"):
            self.assertIn(o, outs)


# ----------------------------------------------------------------- B3b
class TestB3bFuncionarios(_Tmp):
    def test_tipo_por_reglas(self):
        self.assertEqual(funcionarios.tipo_rapido("Reimberg anuncia un golpe importante contra el crimen organizado"), "anuncio")
        self.assertEqual(funcionarios.tipo_rapido("Capturamos a 5 integrantes de una banda en Durán"), "accion")
        self.assertEqual(funcionarios.tipo_rapido("Según la Policía, el crimen bajó"), "declaracion")
        self.assertEqual(funcionarios.tipo_rapido("Hoy se registran 12 homicidios menos que en agosto"), "dato")

    def test_consulta_unica_con_los_seguidos(self):
        q = funcionarios.consulta(0.2, xapi._since)
        self.assertTrue(q.startswith("(from:JohnReimberg OR from:MinInteriorEc)"))

    def test_procesa_solo_tuits_propios_registra_y_avisa(self):
        import declaraciones
        import movil
        orig = (declaraciones.registrar, movil.cargar_config, movil.enviar)
        reg, avisos = [], []
        declaraciones.registrar = lambda *a, **k: reg.append(a)
        movil.cargar_config = lambda: {"avisos_activos": True}
        movil.enviar = lambda conf, titulo, msg, **k: avisos.append(titulo) or True
        try:
            nuevos = funcionarios.procesar_tuits([
                _tw(10, "JohnReimberg", "Reimberg anuncia un golpe importante contra el crimen organizado"),
                _tw(11, "alguien", "@JohnReimberg respuesta de un tercero"),
                _tw(12, "MinInteriorEc", "RT @otro: algo"),
            ], xapi.fecha_iso)
            again = funcionarios.procesar_tuits([_tw(10, "JohnReimberg", "repetido")], xapi.fecha_iso)
        finally:
            declaraciones.registrar, movil.cargar_config, movil.enviar = orig
        self.assertEqual([n["id"] for n in nuevos], ["10"])
        self.assertEqual(nuevos[0]["tipo"], "anuncio")
        self.assertEqual(again, [])
        self.assertEqual(len(reg), 1)
        self.assertEqual(len(avisos), 1)
        self.assertIn("anuncia", avisos[0])

    def test_adelanto_frente_a_la_prensa(self):
        funcionarios.procesar_tuits([_tw(20, "JohnReimberg", "Operativo contra extorsionadores en Guayaquil deja 5 detenidos",
                                         horas=2)], xapi.fecha_iso, notificar=False)
        nota = {"titulo": "Operativo contra extorsionadores deja 5 detenidos en Guayaquil", "link": "l", "medio": "M",
                "fecha": AHORA - dt.timedelta(hours=1)}
        vieja = dict(nota, fecha=AHORA - dt.timedelta(hours=5))  # anterior al tuit: no cuenta
        n = funcionarios.buscar_prensa(rss_fn=lambda nombre: [vieja, nota])
        self.assertEqual(n, 1)
        d = funcionarios.dashboard()
        self.assertAlmostEqual(d["adelanto"]["mediana_min"], 60, delta=2)

    def test_se_cuelga_de_la_historia_o_es_primicia(self):
        funcionarios.procesar_tuits([_tw(30, "JohnReimberg", "Operativo contra extorsionadores en Guayaquil deja 5 detenidos"),
                                     _tw(31, "JohnReimberg", "Anunciamos un nuevo plan de seguridad para Manabí"),
                                     _tw(32, "JohnReimberg", "Feliz domingo a todas las familias ecuatorianas")],
                                    xapi.fecha_iso, notificar=False)
        h = {"titular": "Operativo contra extorsionadores en Guayaquil deja cinco detenidos", "resumen": "John Reimberg"}
        primicias = funcionarios.colgar_en_historias([h])
        self.assertEqual(len(h["dijo_funcionario"]), 1)
        # El saludo (32) no tiene historia pero tampoco es un hecho: no es primicia.
        self.assertEqual([p["id"] for p in primicias], ["31"])

    def test_costo_cero_de_apify_igual_descuenta_la_parte_de_funcionarios(self):
        xapi.buscar_consulta = lambda *a, **k: ([_tw(40, "otro", "nada")] * 20, 0.0)
        orig = redes._paso_frecuencia
        redes._paso_frecuencia = lambda *a, **k: True
        try:
            r = redes.pasada_funcionarios()
        finally:
            redes._paso_frecuencia = orig
        self.assertIn("20 tuits", r)
        self.assertAlmostEqual(redes.gasto_funcionarios_hoy(), xapi.costo_estimado(20))


# ----------------------------------------------------------------- B4
class TestB4Lugares(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (lugares.CACHE_PATH, lugares.LUGARES_PATH, dict(lugares._PENDIENTES))
        lugares.CACHE_PATH = os.path.join(self.tmp, "nominatim_cache.json")
        lugares.LUGARES_PATH = os.path.join(self.tmp, "lugares_gye.json")
        lugares._PENDIENTES.clear()
        lugares._cache_mem = None
        lugares._lugares_mem = (None, None)

    def tearDown(self):
        lugares.CACHE_PATH, lugares.LUGARES_PATH, pend = self.orig
        lugares._PENDIENTES.clear(); lugares._PENDIENTES.update(pend)
        lugares._cache_mem = None
        lugares._lugares_mem = (None, None)

    def test_calles_del_texto(self):
        self.assertEqual(lugares.calles_en("La calle Rumichaca y la Av. 9 de Octubre. Calle principal"),
                         [("Calle Rumichaca", "Rumichaca"), ("Avenida 9 de Octubre", "9 de Octubre")])

    def test_hilo_rapido_no_usa_red_y_deja_pendiente(self):
        self.assertIsNone(lugares.encontrar("Iguanas rescatadas en el aeropuerto de Guayaquil"))
        self.assertIn("Aeropuerto Internacional José Joaquín de Olmedo, Guayaquil", lugares.pendientes())

    def test_resolver_respeta_caja_calle_y_pausa(self):
        lugares.encontrar("Iguanas en el aeropuerto de Guayaquil; obras en la calle Rumichaca y en la calle Lejana")
        respuestas = {
            "Aeropuerto Internacional José Joaquín de Olmedo, Guayaquil": [{"lat": "-2.158", "lon": "-79.883"}],
            "calle:Rumichaca": [{"lat": "-2.187", "lon": "-79.886", "category": "highway"}],
            "calle:Lejana": [{"lat": "-0.180", "lon": "-78.470", "category": "highway"}],  # Quito: fuera de la caja
        }
        pausas = []
        r = lugares.resolver_pendientes(buscar=lambda q: respuestas[q], dormir=pausas.append)
        self.assertEqual(r, "lugares: 2 ubicados, 1 no encontrados")
        self.assertEqual(len(pausas), 2)
        self.assertTrue(all(p >= 1.0 for p in pausas))
        nombre, coords, metodo = lugares.encontrar("Droga desde el aeropuerto de Guayaquil")
        self.assertEqual((nombre, metodo), ("Aeropuerto Jose Joaquin de Olmedo", "lugar"))
        self.assertEqual(lugares.encontrar("Se reconstruye la calle Rumichaca")[2], "calle")
        self.assertEqual(lugares.pendientes(), {})  # "Lejana" no encontrada: no se repide enseguida
        lugares.encontrar("calle Lejana")
        self.assertEqual(lugares.pendientes(), {})

    def test_calle_que_vuelve_como_iglesia_se_descarta(self):
        lugares.encontrar("cierre en la Av. 9 de Octubre")
        lugares.resolver_pendientes(buscar=lambda q: [{"lat": "-2.198", "lon": "-79.896", "category": "amenity"}],
                                    dormir=lambda s: None)
        self.assertIsNone(lugares.encontrar("cierre en la Av. 9 de Octubre"))

    def test_mapa_usa_sector_antes_que_lugar_y_ventana_de_72h(self):
        lugares.encontrar("aeropuerto de Guayaquil")
        lugares.resolver_pendientes(buscar=lambda q: [{"lat": "-2.158", "lon": "-79.883"}], dormir=lambda s: None)
        ahora = dt.datetime(2026, 10, 1, 12, tzinfo=dt.timezone.utc)
        h = lambda tit, horas: {"titular": tit, "ciudad": "Guayaquil", "newest": (ahora - dt.timedelta(hours=horas)).isoformat(),
                                "fuentes": [{"link": tit}]}
        hs = [h("Robo en Urdesa cerca del aeropuerto de Guayaquil", 2), h("Droga en el aeropuerto de Guayaquil", 30),
              h("Guayaquil prepara sus fiestas", 5), h("Iguanas en el aeropuerto de Guayaquil", 80)]
        m = mapa.puntos(hs, [], None, ahora=ahora)
        prec = {p["titulo"]: p["precision"] for p in m["puntos"]}
        self.assertEqual(prec["Robo en Urdesa cerca del aeropuerto de Guayaquil"], "sector")
        self.assertEqual(prec["Droga en el aeropuerto de Guayaquil"], "lugar")
        self.assertNotIn("Iguanas en el aeropuerto de Guayaquil", prec)  # mas de 72 h
        self.assertEqual(m["sin_sector"], 1)  # "prepara sus fiestas": la ciudad entera


if __name__ == "__main__":
    unittest.main()
