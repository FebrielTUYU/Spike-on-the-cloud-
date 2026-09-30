# -*- coding: utf-8 -*-
"""
Fase 20b -- pedido de Fernando: "Si X es cada 3 horas no funciona, debe ser de
minimo cada 10 minutos. Comentarios cada 8 horas no funciona, deben cada hora
al menos. Encuentra una forma de poder integrar whatsapp y facebook."
Sin red real: Apify/Bluesky/YouTube se reemplazan por dobles.
"""
import datetime as dt
import io
import os
import tempfile
import unittest
import zipfile

import comunidad
import facebook
import redes
import whatsapp

AHORA = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)

CHAT = """29/09/26, 15:04 - Los mensajes y las llamadas están cifrados de extremo a extremo.
29/09/26, 15:05 - Maria Lopez: Vecinos, llevamos 2 dias sin agua en la manzana 12
y nadie de Interagua responde
29/09/26, 15:06 - +593 99 123 4567: <Multimedia omitido>
29/09/26, 15:07 - Juan agregó a Pedro
[30/09/26, 3:04:12 p. m.] Pedro Ruiz: La basura no la recogen desde el lunes, huele horrible
30/9/2026 8:15 a. m. - Maria Lopez: Buenos dias a todos
30/9/2026 8:16 a. m. - Maria Lopez: Otra vez sin luz desde las 6"""


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (comunidad.COMUNIDAD_PATH, redes.CACHE_PATH, redes.GASTO_PATH, facebook.FUENTES_PATH,
                     whatsapp.CARPETA)
        comunidad.COMUNIDAD_PATH = os.path.join(self.tmp, "comunidad.json")
        redes.CACHE_PATH = os.path.join(self.tmp, "redes_cache.json")
        redes.GASTO_PATH = os.path.join(self.tmp, "redes_gasto.json")
        facebook.FUENTES_PATH = os.path.join(self.tmp, "facebook_fuentes.json")
        whatsapp.CARPETA = os.path.join(self.tmp, "whatsapp_import")

    def tearDown(self):
        (comunidad.COMUNIDAD_PATH, redes.CACHE_PATH, redes.GASTO_PATH, facebook.FUENTES_PATH,
         whatsapp.CARPETA) = self.orig


class TestFrecuencias(unittest.TestCase):
    def test_x_cada_10_min_y_comentarios_cada_hora(self):
        self.assertLessEqual(redes.FREQ_COMUNIDAD_X_MIN, 10)
        self.assertLessEqual(comunidad.YT_CADA_H, 1)
        self.assertLessEqual(comunidad.BSKY_CADA_MIN, 10)

    def test_comunidad_no_vive_en_el_trabajador(self):
        # El trabajador puede tardar mas de 10 min: X no puede depender de el.
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.py"), encoding="utf-8") as f:
            src = f.read()
        ini = src.index("def enrich_pass(")
        self.assertNotIn("comunidad.recolectar(", src[ini:src.index("\ndef ", ini + 10)])
        self.assertIn("threading.Thread(target=comunidad_loop", src)


class TestPasadaComunidadX(_Tmp):
    def _fakes(self, tweets, costo=0.002):
        self.llamadas = []
        orig = (redes.activo, redes.xapi.buscar_consulta, redes.presupuesto_hoy)
        redes.activo = lambda: True
        def buscar(consulta, clave, horas, max_items, simular=False):
            self.llamadas.append((consulta, horas, max_items))
            return tweets, costo
        redes.xapi.buscar_consulta = buscar
        redes.presupuesto_hoy = lambda red: 0.10
        self.addCleanup(lambda: setattr(redes, "activo", orig[0]))
        self.addCleanup(lambda: setattr(redes.xapi, "buscar_consulta", orig[1]))
        self.addCleanup(lambda: setattr(redes, "presupuesto_hoy", orig[2]))

    def test_corre_registra_y_respeta_la_frecuencia(self):
        tw = [{"id": "1", "text": "Llevamos 2 dias sin agua en Sauces, Guayaquil", "createdAt": "Wed Sep 30 11:50:00 +0000 2026",
               "url": "https://x.com/v/1", "author": {"userName": "vecino_sauces"}}]
        self._fakes(tw)
        r = redes.pasada_comunidad()
        self.assertIn("1 tweets nuevos", r)
        self.assertEqual(len(self.llamadas), 1)
        self.assertLessEqual(self.llamadas[0][1], 1.0)  # ventana corta: se paga lo nuevo
        self.assertEqual(redes.pasada_comunidad(), "todavia no toca")
        self.assertAlmostEqual(redes.gasto_comunidad_hoy(), 0.002)

    def test_tope_propio_deja_margen_a_las_alertas(self):
        self._fakes([], costo=0.0)
        redes._sumar_gasto_comunidad(0.10 * redes.COMUNIDAD_PARTE_X)
        r = redes.pasada_comunidad()
        self.assertIn("parte de Comunidad", r)
        self.assertEqual(self.llamadas, [])

    def test_gasto_de_facebook_no_descuenta_de_x(self):
        antes = redes.presupuesto_restante_mes()
        redes.registrar_gasto("facebook", 1.0, "prueba")
        self.assertAlmostEqual(redes.presupuesto_restante_mes(), antes)


class TestWhatsApp(_Tmp):
    def test_parseo_formatos_android_ios_y_multilinea(self):
        msgs = whatsapp.parsear(CHAT)
        textos = [m["texto"] for m in msgs]
        self.assertIn("Vecinos, llevamos 2 dias sin agua en la manzana 12\ny nadie de Interagua responde", textos)
        self.assertTrue(any(t.startswith("La basura") for t in textos))
        self.assertFalse(any("Multimedia" in t or "cifrad" in t or "agregó" in t for t in textos))
        self.assertEqual(msgs[0]["fecha"], "2026-09-29T15:05:00-05:00")
        self.assertEqual([m for m in msgs if m["texto"].startswith("La basura")][0]["fecha"], "2026-09-30T15:04:00-05:00")

    def test_anonimiza_y_usa_el_barrio_del_grupo(self):
        r = comunidad.importar_whatsapp("Chat de WhatsApp con Vecinos Sauces 8.txt", CHAT.encode("utf-8"), ahora=AHORA)
        self.assertEqual(r["grupo"], "Vecinos Sauces 8")
        self.assertEqual(r["sector"], "Sauces")
        self.assertEqual(r["utiles"], 3)  # agua, basura, luz; "Buenos dias" no
        reg = comunidad._cargar()
        autores = {p["autor"] for p in reg["posts"].values()}
        self.assertTrue(all(a.startswith("Vecino ") for a in autores))
        self.assertFalse(any("Maria" in a or "593" in a for a in autores))
        self.assertEqual({p["barrio"] for p in reg["posts"].values()}, {"Sauces"})
        # Mismo chat otra vez: nada nuevo.
        self.assertEqual(comunidad.importar_whatsapp("Chat de WhatsApp con Vecinos Sauces 8.txt",
                                                     CHAT.encode("utf-8"), ahora=AHORA)["nuevos"], 0)

    def test_zip_y_carpeta(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("_chat.txt", CHAT)
        os.makedirs(whatsapp.CARPETA)
        with open(os.path.join(whatsapp.CARPETA, "Chat de WhatsApp con Guasmo Sur.zip"), "wb") as f:
            f.write(buf.getvalue())
        res = comunidad.procesar_carpeta_whatsapp(ahora=AHORA)
        self.assertEqual(len(res), 1)
        self.assertEqual(comunidad.procesar_carpeta_whatsapp(ahora=AHORA), [])  # ya procesado
        out = comunidad.actualizar([], ahora=AHORA)
        self.assertIn("whatsapp", out["por_fuente"])
        self.assertTrue(out["whatsapp_grupos"])


class TestFacebook(_Tmp):
    def test_sin_fuentes_no_gasta_y_crea_plantilla(self):
        self.assertEqual(facebook.fuentes(), {"paginas": [], "grupos": []})
        self.assertTrue(os.path.exists(facebook.FUENTES_PATH))
        self.assertFalse(facebook.activo())

    def test_parseo_tolerante_y_filtro_de_personas(self):
        items = [{"text": "En la Alborada, Guayaquil, el recolector de basura no pasa hace una semana",
                  "profileName": "Rosa Mendez", "date": "2026-09-30T10:00:00.000Z", "commentUrl": "https://fb/c/1"},
                 {"message": "Sin luz en Mapasingue, Guayaquil, desde anoche", "user": {"name": "Diario Extra"},
                  "time": 1790740800},
                 {"text": "sin autor"}]
        pubs = [p for p in (facebook.item_a_publicacion(i) for i in items) if p]
        self.assertEqual(len(pubs), 2)
        self.assertEqual(comunidad.registrar_facebook(pubs, ahora=AHORA), 1)  # el medio no cuenta

    def test_recolectar_llama_actores_y_anota_gasto_aparte(self):
        with open(facebook.FUENTES_PATH, "w", encoding="utf-8") as f:
            f.write('{"paginas": ["https://www.facebook.com/MunicipioGuayaquil"], "grupos": []}')
        llamadas = []
        import xapi
        o_act, o_run = xapi.activo, xapi._run_actor
        xapi.activo = lambda: True
        def run(actor, entrada, tope_seguridad_usd=0.3, **kw):
            llamadas.append(actor)
            if actor == facebook.ACTOR_POSTS:
                return [{"url": "https://fb/p/1"}], 0.01, "r1"
            return [{"text": "Los baches de Sauces, Guayaquil, ya no se aguantan", "profileName": "Luis Paz",
                     "date": "2026-09-30T09:00:00Z"}], 0.02, "r2"
        xapi._run_actor = run
        try:
            pubs, est = facebook.recolectar()
        finally:
            xapi.activo, xapi._run_actor = o_act, o_run
        self.assertEqual(llamadas, [facebook.ACTOR_POSTS, facebook.ACTOR_COMENTARIOS])
        self.assertEqual(len(pubs), 1)
        self.assertAlmostEqual(redes.gasto_mes("facebook"), 0.03)
        self.assertEqual(redes.gasto_mes("x"), 0.0)


if __name__ == "__main__":
    unittest.main()
