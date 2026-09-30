# -*- coding: utf-8 -*-
"""
Fase 21 -- pedido de Fernando (2026-09-30): "estas recogiendo muchas noticias
viejas y tweets o videos viejos de hace 2 o 3 dias... quiero que no cojas otra
cosa que las cosas que se publican en las ultimas 10 horas como nuevas. Ademas
haz especial enfasis en la cuenta emergencias.ec y sus usuarios con los que
interactua". Sin red real: Apify y las redes se reemplazan por dobles.
"""
import datetime as dt
import os
import tempfile
import unittest

import alertas
import comunidad
import redes
import social
import xapi

AHORA = dt.datetime.now(dt.timezone.utc)


def _x(dt_):
    return dt_.strftime("%a %b %d %H:%M:%S +0000 %Y")


def _tweet(tid, autor, texto, horas_atras=1, **extra):
    t = {"id": str(tid), "text": texto, "createdAt": _x(AHORA - dt.timedelta(hours=horas_atras)),
         "url": "https://x.com/%s/status/%s" % (autor, tid), "author": {"userName": autor}}
    t.update(extra)
    return t


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (redes.CACHE_PATH, redes.GASTO_PATH, xapi.CACHE_PATH, comunidad.COMUNIDAD_PATH,
                     alertas.ALERTAS_PATH, redes.activo, xapi.activo, xapi.buscar_consulta, redes.presupuesto_hoy)
        redes.CACHE_PATH = os.path.join(self.tmp, "redes_cache.json")
        redes.GASTO_PATH = os.path.join(self.tmp, "redes_gasto.json")
        xapi.CACHE_PATH = os.path.join(self.tmp, "x_cache.json")
        comunidad.COMUNIDAD_PATH = os.path.join(self.tmp, "comunidad.json")
        alertas.ALERTAS_PATH = os.path.join(self.tmp, "alertas.json")
        redes.activo = lambda: True
        xapi.activo = lambda: True
        redes.presupuesto_hoy = lambda red: 0.10

    def tearDown(self):
        (redes.CACHE_PATH, redes.GASTO_PATH, xapi.CACHE_PATH, comunidad.COMUNIDAD_PATH, alertas.ALERTAS_PATH,
         redes.activo, xapi.activo, xapi.buscar_consulta, redes.presupuesto_hoy) = self.orig


class TestVentana10h(unittest.TestCase):
    def test_ventana_por_defecto_es_10_horas(self):
        for mod in (social, comunidad, xapi):
            self.assertEqual(mod.VENTANA_H, 10)
        self.assertLessEqual(alertas.ALERTA_MAX_EDAD_H, 10)
        self.assertLessEqual(social.YT_DIAS, 2)

    def test_redes_descarta_lo_de_hace_dias(self):
        viejo = social.SocialPost("bluesky", texto="Hace dos dias", autor="a", url="u1",
                                  fecha=(AHORA - dt.timedelta(days=2)).isoformat())
        nuevo = social.SocialPost("bluesky", texto="Hace dos horas", autor="b", url="u2",
                                  fecha=(AHORA - dt.timedelta(hours=2)).isoformat())
        once = social.SocialPost("bluesky", texto="Hace once horas", autor="c", url="u3",
                                 fecha=(AHORA - dt.timedelta(hours=11)).isoformat())
        orig = (social.bluesky_buscar, social.reddit_buscar, social.mastodon_buscar, social.telegram_buscar,
                social.filtrar_ruido)
        social.bluesky_buscar = lambda *a, **k: [viejo, nuevo, once]
        social.reddit_buscar = social.mastodon_buscar = social.telegram_buscar = lambda *a, **k: []
        social.filtrar_ruido = lambda ps: ps
        try:
            posts, _ = social.recolectar("Guayaquil", youtube=False, ambito="guayaquil")
        finally:
            (social.bluesky_buscar, social.reddit_buscar, social.mastodon_buscar, social.telegram_buscar,
             social.filtrar_ruido) = orig
        self.assertEqual([p.autor for p in posts], ["b"])


class TestTweetsDeHistoria(_Tmp):
    def test_al_leer_solo_lo_reciente(self):
        xapi.guardar_tweets_historia("h1", [_tweet(1, "a", "viejo", horas_atras=30),
                                            _tweet(2, "b", "nuevo", horas_atras=2)])
        self.assertEqual([t["id"] for t in xapi.tweets_de_historia("h1")], ["2"])


class TestEmergencias(_Tmp):
    def _fake(self, respuestas):
        self.consultas = []

        def buscar(consulta, clave, horas, max_items, simular=False):
            self.consultas.append(consulta)
            return respuestas.pop(0) if respuestas else [], 0.001
        xapi.buscar_consulta = buscar

    def test_consulta_la_cuenta_sus_respuestas_y_menciones(self):
        self._fake([[
            _tweet(1, "EmergenciasEc", "#Guayaquil Incendio en Sauces 8, bomberos en camino. Reporta @vecino_sauces",
                   replyCount=40),
            _tweet(2, "maria_gye", "@EmergenciasEc aqui en Sauces 8 sigue el humo, no llegan los bomberos",
                   inReplyToUsername="EmergenciasEc"),
        ]])
        r = redes.pasada_emergencias()
        self.assertIn("2 tweets nuevos", r)
        q = self.consultas[0]
        for parte in ("from:EmergenciasEc", "to:EmergenciasEc", "@EmergenciasEc", "since:"):
            self.assertIn(parte, q)
        d = redes.emergencias_dashboard()
        tipos = {t["autor"]: t["tipo"] for t in d["tweets"]}
        self.assertEqual(tipos, {"@EmergenciasEc": "cuenta", "@maria_gye": "respuesta"})
        # Su red: quien le respondio y a quien menciono ella.
        self.assertEqual({u for u, _ in redes.red_emergencias()}, {"maria_gye", "vecino_sauces"})
        # La persona que respondio entra a Comunidad (la cuenta, no: es una pagina).
        reg = comunidad._cargar()
        self.assertEqual({p["autor"] for p in reg["posts"].values()}, {"@maria_gye"})
        # Y el reporte de la cuenta entra a Alertas.
        self.assertTrue(alertas.listar_activas())
        # A los 10 minutos no se repite.
        self.assertEqual(redes.pasada_emergencias(), "todavia no toca")

    def test_despues_lee_su_red(self):
        self._fake([[_tweet(1, "EmergenciasEc", "Choque en la Perimetral, reporta @testigo_uno")],
                    [_tweet(2, "testigo_uno", "Trafico parado en la Perimetral por el choque")]])
        # En la misma vuelta: primero la cuenta (aprende que menciono a
        # @testigo_uno) y enseguida lee a esa red.
        r = redes.pasada_emergencias()
        self.assertIn("su red (1 cuentas)", r)
        self.assertEqual(len(self.consultas), 2)
        self.assertIn("from:testigo_uno", self.consultas[-1])

    def test_tope_propio(self):
        self._fake([])
        redes._sumar_gasto_emerg(0.10 * redes.EMERG_PARTE_X)
        r = redes.pasada_emergencias()
        self.assertIn("presupuesto", r)
        self.assertEqual(self.consultas, [])

    def test_panel_solo_muestra_lo_de_las_ultimas_horas(self):
        redes._guardar_feed_emerg([_tweet(1, "EmergenciasEc", "viejo", horas_atras=12),
                                   _tweet(2, "EmergenciasEc", "nuevo", horas_atras=1)], "cuenta")
        self.assertEqual([t["texto"] for t in redes.emergencias_dashboard()["tweets"]], ["nuevo"])

    def test_la_capa_de_cuentas_no_la_paga_dos_veces(self):
        vistas = []
        orig = redes.xapi.consulta_cuentas
        redes.xapi.consulta_cuentas = lambda cuentas, horas=2: vistas.extend(c["usuario"] for c in cuentas) or ""
        try:
            redes.pasada([], [], [], simular_red=True,
                         cuentas=[{"usuario": "EmergenciasEc"}, {"usuario": "ECU911_"}])
        finally:
            redes.xapi.consulta_cuentas = orig
        self.assertNotIn("EmergenciasEc", vistas)


class TestAlertasPanel(_Tmp):
    def test_panel_de_alertas_sin_lo_de_hace_mas_de_10h(self):
        reciente = (AHORA - dt.timedelta(hours=2)).isoformat()
        alertas.registrar_senal("x", "a", "Incendio en Sauces, Guayaquil", "u1", reciente)
        reg = alertas._cargar()
        for a in reg.values():
            a["ultima_senal"] = (AHORA - dt.timedelta(hours=15)).isoformat()
        alertas._guardar(reg)
        self.assertEqual(alertas.listar_activas(), [])


class TestNoticiasSinFecha(unittest.TestCase):
    def test_sin_fecha_no_es_reciente(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("antigua = hours is None or hours > FEED_FRESH_H", src)


if __name__ == "__main__":
    unittest.main()
