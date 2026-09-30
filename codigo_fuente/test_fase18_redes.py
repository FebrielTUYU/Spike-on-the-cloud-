# -*- coding: utf-8 -*-
"""
Fase 18 -- P1-5 (X via Apify), P1-6 (alertas: nada viejo, nada mal enlazado)
y P1-7 (Pulso social: solo gente de aqui, siempre con hora).

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo. Sin red: el actor
de Apify se reemplaza por una funcion que devuelve tweets.

AVISO HONESTO: los tweets del "caso 29-sep" son SINTETICOS (armados con la
forma real verificada de la respuesta del actor, ver xapi.py) -- desde el
entorno donde se escribio esta prueba no habia acceso a Apify para bajar los
tweets reales de esa tarde. La prueba demuestra el camino (consulta reactiva
-> alerta con fecha y hora -> historia madre), no el contenido real.
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import alertas
import monitor
import redes
import social
import xapi


def _hace(**kw):
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(**kw)


def _x_fecha(d):
    # formato clasico de X ("Tue Sep 29 20:40:00 +0000 2026"), el que trae el actor
    return d.strftime("%a %b %d %H:%M:%S +0000 %Y")


def _tweet(tid, texto, cuando, usuario="vecino_gye", replies=0):
    return {"id": str(tid), "text": texto, "createdAt": _x_fecha(cuando),
            "url": "https://x.com/%s/status/%s" % (usuario, tid), "replyCount": replies,
            "conversationId": str(tid), "author": {"userName": usuario, "location": "Guayaquil"}}


class _Aislado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (alertas.ALERTAS_PATH, redes.GASTO_PATH, redes.CACHE_PATH, xapi.CACHE_PATH,
                      xapi._leer_token, xapi._run_actor, xapi.CUENTAS_PATH)
        alertas.ALERTAS_PATH = os.path.join(self.tmp, "alertas.json")
        redes.GASTO_PATH = os.path.join(self.tmp, "redes_gasto.json")
        redes.CACHE_PATH = os.path.join(self.tmp, "redes_cache.json")
        xapi.CACHE_PATH = os.path.join(self.tmp, "x_cache.json")
        xapi.CUENTAS_PATH = os.path.join(self.tmp, "x_cuentas_locales.json")
        xapi._leer_token = lambda: "token-de-prueba"
        self.consultas = []

    def tearDown(self):
        (alertas.ALERTAS_PATH, redes.GASTO_PATH, redes.CACHE_PATH, xapi.CACHE_PATH,
         xapi._leer_token, xapi._run_actor, xapi.CUENTAS_PATH) = self._orig

    def _actor(self, tweets_por_consulta):
        def run(actor, input_dict, espera_seg=0, tope_seguridad_usd=0.3):
            q = " ".join(input_dict.get("searchTerms") or [])
            self.consultas.append(q)
            for clave, tweets in tweets_por_consulta.items():
                if clave in q:
                    return tweets, 0.001, "run-1"
            return [], 0.0, "run-0"
        xapi._run_actor = run


# ------------------------- P1-5: X -------------------------

class TestConsultasX(_Aislado):
    def test_terminos_de_alerta_con_tilde_y_un_solo_or(self):
        q = xapi.consulta_alertas(monitor.terminos_alerta_x(), "Guayaquil", horas=2)
        self.assertIn("inundación", q)
        self.assertIn('"corte de luz"', q)
        self.assertNotIn("corte_luz", q)
        self.assertNotIn("_", q.split("since:")[0])
        self.assertIn(" OR ", q)
        self.assertIn("Guayaquil", q)
        self.assertIn("since:", q)

    def test_se_descarta_lo_que_llega_fuera_de_la_ventana(self):
        tw = [_tweet(1, "Calles anegadas en la Alborada", _hace(minutes=30)),
              _tweet(2, "Inundación en Sauces", _hace(hours=3)),
              _tweet(3, "Inundación en Urdesa", _hace(hours=30))]
        self._actor({"Guayaquil": tw})
        items, _c = xapi.buscar_alertas(["inundación"], "Guayaquil", horas=2, max_items=15)
        self.assertEqual([t["id"] for t in items], ["1"])

    def test_capa_de_cuentas_hiperlocales_desde_json_editable(self):
        with open(xapi.CUENTAS_PATH, "w", encoding="utf-8") as f:
            json.dump({"cuentas": [{"usuario": "ECU911_", "nombre": "ECU 911"},
                                    {"usuario": "ATMGuayaquil", "nombre": "ATM"}]}, f)
        q = xapi.consulta_cuentas(xapi.cuentas_locales(), horas=2)
        self.assertIn("from:ECU911_", q)
        self.assertIn("from:ATMGuayaquil", q)
        self.assertIn(" OR ", q)
        self.assertIn("since:", q)

    def test_consulta_reactiva_por_evento_en_curso(self):
        ev = {"tipo": "lluvias", "lugar": "Guayaquil", "sectores": ["Atarazana", "Av. de las Americas", "Samanes"]}
        q = xapi.consulta_evento(ev, monitor.terminos_evento_x("lluvias"), horas=2)
        self.assertIn("Atarazana", q)
        self.assertIn("Samanes", q)
        self.assertIn("inundación", q)
        self.assertIn("since:", q)

    def test_consulta_por_historia_sin_palabras_de_arranque(self):
        casos = [{"titular": "Ataque armado en la vía a Daule: matan a comerciante de 33 años en Guayaquil",
                  "resumen": "", "ciudad": "Guayaquil", "es_local": True},
                 {"titular": "Fuerte lluvia inunda calles y complica el tránsito en el norte de Guayaquil",
                  "resumen": "", "ciudad": "Guayaquil", "es_local": True},
                 {"titular": "Hasta 12 horas sin agua en el norte de Guayaquil",
                  "resumen": "", "ciudad": "Guayaquil", "es_local": True}]
        for s in casos:
            q = monitor.consulta_x_historia(s)
            if q is not None:
                primera = s["titular"].split()[0].lower()
                self.assertNotIn(primera, q.lower().split(), q)
        s = {"titular": "Daniel Noboa reduce el IVA al 8 % durante el feriado", "resumen": "",
             "ciudad": "", "es_local": True}
        self.assertIn("noboa", monitor.consulta_x_historia(s).lower())

    def test_inundaciones_y_cortes_no_son_plantilla(self):
        self.assertFalse(monitor._es_boletin_plantilla({"titular": "Inundaciones en Guayaquil hoy 29 de septiembre", "resumen": ""}))
        self.assertFalse(monitor._es_boletin_plantilla({"titular": "Corte de agua en Guayaquil: 12 horas en el norte", "resumen": ""}))
        self.assertTrue(monitor._es_boletin_plantilla({"titular": "Pronóstico del clima en Guayaquil este 30 de septiembre", "resumen": ""}))


class TestPasadaX(_Aislado):
    def test_evento_en_curso_primero_y_tiktok_en_pausa(self):
        cache = {"malos_dias": {"tiktok": 2}}
        with open(redes.CACHE_PATH, "w") as f:
            json.dump(cache, f)
        self._actor({})
        ev = {"titular": "Lluvias en Guayaquil — 29 sep", "link": "madre-1",
              "evento": {"tipo": "lluvias", "lugar": "Guayaquil", "sectores": ["Atarazana"]}}
        estado = redes.pasada([], monitor.terminos_alerta_x(), [], eventos=[ev])
        self.assertTrue(self.consultas and "Atarazana" in self.consultas[0], self.consultas)
        self.assertIn("tiktok en pausa", estado)

    def test_caso_29_sep_tweets_llegan_con_hora_a_la_madre(self):
        tw = [_tweet(10, "Av. de las Américas completamente inundada, no hay paso hacia el norte #Guayaquil", _hace(minutes=40)),
              _tweet(11, "Calles anegadas en la Atarazana, el agua entra a las casas", _hace(minutes=25), usuario="otra_vecina")]
        self._actor({"Atarazana": tw})
        ev = {"titular": "Lluvias en Guayaquil — 29 sep", "link": "madre-29",
              "evento": {"tipo": "lluvias", "lugar": "Guayaquil", "sectores": ["Atarazana", "Av. de las Americas"]}}
        redes.pasada([], monitor.terminos_alerta_x(), [], eventos=[ev])
        guardados = xapi.tweets_de_historia("madre-29")
        self.assertEqual(len(guardados), 2)
        activas = alertas.listar_activas()
        self.assertTrue(activas)
        self.assertTrue(all("T" in s["fecha"] for a in activas for s in a["senales"]))
        self.assertEqual({a["tipo"] for a in activas}, {"inundacion"})


# ------------------------- P1-6: alertas -------------------------

class TestAlertas(_Aislado):
    def test_senal_de_mas_de_24h_se_descarta(self):
        self.assertIsNone(alertas.registrar_senal("x", "a", "Incendio en Urdesa", "u1", _hace(hours=30).isoformat()))
        self.assertIsNotNone(alertas.registrar_senal("x", "b", "Incendio en Urdesa", "u2", _hace(hours=2).isoformat()))

    def test_simulacro_no_es_alerta(self):
        self.assertIsNone(alertas.registrar_senal(
            "x", "m", "Este viernes se realizará el Simulacro Cantonal de sismo en Guayaquil",
            "u", _hace(hours=1).isoformat()))

    def test_atarazana_18_sep_no_se_enlaza_con_vivienda_del_sur_29_sep(self):
        # caso real (alertas.json): la alerta del vehiculo incendiado en La
        # Atarazana (18-sep) quedo enlazada a "Incendio en vivienda del sur
        # de Guayaquil" (29-sep). Se reproduce con las mismas distancias.
        viejo = _hace(hours=11 * 24 + 1)
        registro = {"a1": {"id": "a1", "clave": "incendio|Guayaquil (sector sin precisar)", "tipo": "incendio",
                           "lugar": "Guayaquil (sector sin precisar)", "primera_deteccion": viejo.isoformat(),
                           "ultima_senal": viejo.isoformat(), "estado": "sin_confirmar",
                           "senales": [{"fuente": "x", "autor": "z", "fecha": viejo.isoformat(), "oficial": False,
                                        "texto": "#Guayaquil Un vehículo se incendió en el sector de La Atarazana, al norte de la ciudad."}],
                           "ya_en_medios": True, "historia_link": "https://x/sur", "historia_titulo": "Incendio en vivienda del sur",
                           "ya_en_medios_ts": _hace(hours=1).isoformat(), "adelanto_min": 99999}}
        alertas._guardar(registro)
        h = {"titular": "Incendio en vivienda del sur de Guayaquil: niños estaban en la habitación",
             "resumen": "", "newest": _hace(hours=1).isoformat(), "fuentes": [{"link": "https://x/sur"}]}
        alertas.vincular_con_prensa([h])
        a = alertas._cargar()["a1"]
        self.assertFalse(a["ya_en_medios"])
        self.assertEqual(a["historia_link"], "")

    def test_alerta_sin_lugar_no_se_enlaza_con_nota_extranjera(self):
        alertas.registrar_senal("x", "q", "Bus se incendió en la parroquia Tarquí de Manta", "u", _hace(hours=1).isoformat())
        h = {"titular": "\"No nos dejaremos intimidar\": Estonia acusa Rusia por incendio en una bodega",
             "resumen": "", "newest": _hace(minutes=30).isoformat(), "fuentes": [{"link": "https://x/estonia"}]}
        alertas.vincular_con_prensa([h])
        self.assertFalse(any(a.get("ya_en_medios") for a in alertas._cargar().values()))

    def test_mismo_dia_y_mismo_lugar_si_se_enlaza(self):
        alertas.registrar_senal("x", "q", "Emergencia en el sur de Guayaquil: incendio afectó vivienda con niños",
                                "u", _hace(hours=3).isoformat())
        h = {"titular": "Incendio en vivienda del sur de Guayaquil: niños estaban en la habitación",
             "resumen": "", "newest": _hace(hours=1).isoformat(), "fuentes": [{"link": "https://x/sur"}]}
        self.assertEqual(alertas.vincular_con_prensa([h]), 1)


# ------------------------- P1-7: Pulso social -------------------------

class TestPulsoSocial(unittest.TestCase):
    def test_fecha_con_hora(self):
        self.assertEqual(social._iso_completo("2026-09-29T20:15:03.123Z")[:19], "2026-09-29T20:15:03")
        self.assertEqual(social._iso_completo(1790000000)[:4], "2026")
        self.assertTrue(social._es_reciente(_hace(hours=5).isoformat(), 1))
        self.assertFalse(social._es_reciente(_hace(hours=50).isoformat(), horas=48))

    def test_solo_senal_positiva_de_aqui(self):
        P = social.SocialPost
        self.assertFalse(monitor._post_senal_local(P("mastodon", texto="Qué lluvia hoy en Bilbao, todo inundado")))
        self.assertFalse(monitor._post_senal_local(P("bluesky", texto="La asamblea aprobó la ley de vivienda")))
        self.assertTrue(monitor._post_senal_local(P("bluesky", texto="Se inundó la Alborada otra vez")))
        self.assertTrue(monitor._post_senal_local(P("bluesky", texto="Guayaquil bajo el agua esta tarde")))

    def test_mastodon_fuera_de_los_ambitos_locales(self):
        orig = (social.mastodon_buscar, social.bluesky_buscar, social.reddit_buscar, social.youtube_buscar,
                social.telegram_buscar)
        llamado = []
        social.mastodon_buscar = lambda *a, **k: llamado.append(1) or []
        social.bluesky_buscar = social.reddit_buscar = social.telegram_buscar = lambda *a, **k: []
        social.youtube_buscar = lambda *a, **k: []
        try:
            social.recolectar("lluvias Ecuador", ambito="guayaquil", youtube=False)
            self.assertEqual(llamado, [])
            social.recolectar("lluvias", ambito="internacional", youtube=False)
            self.assertEqual(llamado, [1])
        finally:
            (social.mastodon_buscar, social.bluesky_buscar, social.reddit_buscar, social.youtube_buscar,
             social.telegram_buscar) = orig

    def test_pulso_local_sin_posts_de_mas_de_48h(self):
        P = social.SocialPost
        posts = [P("bluesky", texto="Lluvia en Guayaquil", fecha=_hace(hours=60).isoformat()),
                 P("bluesky", texto="Lluvia en Guayaquil ahora", fecha=_hace(hours=2).isoformat())]
        self.assertEqual(len(monitor._filtrar_pulso_local(posts)), 1)


if __name__ == "__main__":
    unittest.main()
