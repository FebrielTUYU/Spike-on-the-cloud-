# -*- coding: utf-8 -*-
"""
Fase 20 (v2) -- Comunidad Guayaquil = lo que dice la GENTE.

Escrita desde el pedido de Fernando: "no quiero notas de prensa porque
precisamente eso es lo ya cubierto, quiero identificar problemas que tenga la
gente... no solo esos 3 temas, sino mas, todo lo que se pueda abarcar".

Casos de autores y textos tomados de la corrida real del 2026-09-30.
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import comunidad

AQUI = os.path.dirname(os.path.abspath(__file__))
AHORA = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)


def _post(texto, autor="@vecina_gye", fuente="x", fecha="2026-09-29T15:00:00+00:00", tipo=None):
    return comunidad.normalizar_post(fuente, autor, texto, "https://x.com/%s/1" % autor.strip("@"), fecha,
                                     tipo=tipo, ahora=AHORA)


class TestQuienHabla(unittest.TestCase):
    def test_paginas_de_noticias_no_son_la_gente(self):
        for autor in ("UniversalGye", "TiempoRealEC", "el_telegrafo", "EcEnDirecto", "Centralinfec",
                      "Ecuador221ec", "lanacionecuador", "Alerta_Gyaquil7", "Expresoec", "ObrasQuito"):
            self.assertIsNone(_post("Se reporta que no hay agua en Sauces, Guayaquil, desde ayer", autor=autor), autor)

    def test_persona_si_cuenta(self):
        p = _post("Llevamos 3 dias sin agua en Sauces 8, Guayaquil, y nadie hace nada", autor="Soy4zul")
        self.assertEqual((p["categoria"], p["barrio"]), ("agua", "Sauces"))
        self.assertTrue(p["queja"])

    def test_cuenta_oficial_o_medio_marcado_no_cuenta(self):
        self.assertIsNone(_post("Corte de agua en Guayaquil", autor="Interagua"))
        self.assertIsNone(_post("Sin luz en la Alborada, Guayaquil", autor="pepe", tipo="medio"))

    def test_formato_de_noticia_no_cuenta(self):
        self.assertIsNone(_post("#Guayaquil | Accidente de transito en la via Perimetral", autor="juanito"))


class TestDondeYQue(unittest.TestCase):
    def test_otra_ciudad_sin_guayaquil_no_entra(self):
        self.assertIsNone(_post("Bus se incendió en la parroquia Tarquí de Manta"))
        self.assertIsNone(_post("Accidente en Naranjal, un motociclista herido en la via"))

    def test_calle_pedro_carbo_del_centro_si_es_guayaquil(self):
        p = _post("Balacera en 9 de Octubre y Pedro Carbo, centro de Guayaquil, que miedo")
        self.assertEqual(p["categoria"], "inseguridad")

    def test_muchas_categorias_no_solo_tres(self):
        casos = {
            "Llevamos dias sin agua en el Guasmo, Guayaquil": "agua",
            "Otra vez sin luz en Mapasingue, Guayaquil, se quemo el transformador": "luz",
            "El carro de la basura no pasa hace una semana por Sauces, Guayaquil": "basura",
            "Los baches de la calle en la Alborada, Guayaquil, ya son cráteres": "calles",
            "En Pascuales, Guayaquil, cobran vacunas a los negocios": "extorsion",
            "Los buses de la linea 81 ya no pasan por Monte Sinai, Guayaquil": "transporte",
            "Perros callejeros atacan a los niños en la Isla Trinitaria, Guayaquil": "animales",
            "La bulla de los parlantes en Urdesa, Guayaquil, no deja dormir": "ruido",
            "Invasion de terrenos en Monte Sinai, Guayaquil, nadie hace nada": "vivienda",
            "En el subcentro de salud del Guasmo, Guayaquil, no hay medicinas": "salud",
            "La calle oscura de la Garzota, Guayaquil, sin alumbrado hace un mes": "alumbrado",
            "La obra paralizada en la Via a la Costa, Guayaquil, lleva meses": "obras",
        }
        cats = set()
        for texto, esperado in casos.items():
            p = _post(texto)
            self.assertIsNotNone(p, texto)
            self.assertEqual(p["categoria"], esperado, texto)
            cats.add(p["categoria"])
        self.assertGreaterEqual(len(comunidad.CATEGORIAS), 20)
        self.assertEqual(len(cats), len(casos))

    def test_falsos_amigos(self):
        self.assertIsNone(comunidad.categorizar("Roberto fue a comer"))
        self.assertIsNone(comunidad.categorizar("que precioso dia, claro que si"))


class TestTemas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = comunidad.COMUNIDAD_PATH
        comunidad.COMUNIDAD_PATH = os.path.join(self.tmp, "comunidad.json")

    def tearDown(self):
        comunidad.COMUNIDAD_PATH = self.orig

    def test_personas_distintas_y_dias_distintos_suben(self):
        posts = [_post("Llevamos dias sin agua en el Guasmo, Guayaquil", autor="@a%d" % i,
                       fecha="2026-09-%02dT15:00:00+00:00" % d) for i, d in enumerate((25, 27, 29))]
        posts.append(_post("Un bache en Urdesa, Guayaquil", autor="@b"))
        t = comunidad.armar_temas(posts, [], AHORA)[0]
        self.assertEqual((t["barrio"], t["categoria"], t["personas"], t["dias"]), ("Guasmo", "agua", 3, 3))
        self.assertIn("3 personas distintas", t["por_que"])

    def test_misma_persona_varias_veces_no_infla(self):
        posts = [_post("Sin agua en el Guasmo, Guayaquil, dia %d" % i, autor="@misma") for i in range(5)]
        t = comunidad.armar_temas(posts, [], AHORA)[0]
        self.assertEqual(t["personas"], 1)

    def test_prensa_solo_marca_cubierto(self):
        posts = [_post("Sin agua en el Guasmo, Guayaquil, otra vez", autor="@x1"),
                 _post("Sin luz en la Alborada, Guayaquil", autor="@x2")]
        prensa = [{"titular": "Moradores del Guasmo sin agua potable", "ciudad": "Guayaquil",
                   "fuentes": [{"outlet": "Expreso", "link": "https://e/1", "date": "2026-09-29T10:00:00+00:00"}]}]
        temas = {t["categoria"]: t for t in comunidad.armar_temas(posts, prensa, AHORA)}
        self.assertTrue(temas["agua"]["cubierto"])
        self.assertFalse(temas["luz"]["cubierto"])
        self.assertIn("Sin notas de prensa", temas["luz"]["por_que"])
        # La prensa nunca crea un tema por su cuenta.
        self.assertEqual(set(temas), {"agua", "luz"})

    def test_lo_no_cubierto_sube(self):
        posts = [_post("Sin agua en el Guasmo, Guayaquil", autor="@x1"),
                 _post("Sin luz en la Alborada, Guayaquil", autor="@x2")]
        prensa = [{"titular": "Guasmo sin agua potable", "ciudad": "Guayaquil",
                   "fuentes": [{"outlet": "Expreso", "link": "https://e/1", "date": "2026-09-29T10:00:00+00:00"}]}]
        self.assertEqual(comunidad.armar_temas(posts, prensa, AHORA)[0]["categoria"], "luz")

    def test_registro_de_x_sin_duplicar_y_solo_personas(self):
        tweets = [{"id": "1", "text": "Sin agua en Sauces, Guayaquil, desde ayer", "createdAt": "Tue Sep 29 15:00:00 +0000 2026",
                   "url": "https://x.com/v/1", "author": {"userName": "vecino_sauces"}},
                  {"id": "2", "text": "Sin agua en Sauces, Guayaquil, informa Interagua", "createdAt": "Tue Sep 29 15:00:00 +0000 2026",
                   "url": "https://x.com/i/2", "author": {"userName": "TiempoRealEC"}}]
        self.assertEqual(comunidad.registrar_tweets(tweets, ahora=AHORA), 1)
        self.assertEqual(comunidad.registrar_tweets(tweets, ahora=AHORA), 0)

    def test_no_persistir_no_escribe(self):
        comunidad.actualizar([], persistir=False, ahora=AHORA)
        self.assertFalse(os.path.exists(comunidad.COMUNIDAD_PATH))


class TestDatosReales(unittest.TestCase):
    def test_pipeline_real_solo_personas_de_guayaquil(self):
        d = json.load(open(os.path.join(AQUI, "data.json"), encoding="utf-8"))
        out = comunidad.actualizar(d["historias"], d.get("alertas"), d.get("social"), d.get("social_historias"),
                                   ahora=AHORA, persistir=False)
        self.assertTrue(out["temas"])
        autores = {p["autor"].lower() for t in out["temas"] for p in t["publicaciones"]}
        for medio in ("universalgye", "tiemporealec", "el_telegrafo", "expresoec"):
            self.assertNotIn(medio, autores)
        self.assertGreaterEqual(len(out["todas_categorias"]), 20)


class TestAsistente(unittest.TestCase):
    def test_herramienta(self):
        import herramientas
        d = {"comunidad": comunidad.actualizar([], persistir=False, ahora=AHORA)}
        d["comunidad"]["temas"] = comunidad.armar_temas(
            [_post("Sin agua en el Guasmo, Guayaquil, nadie hace nada", autor="@x1")], [], AHORA)
        orig = herramientas._cargar
        herramientas._cargar = lambda nombre, default: d if nombre == "data.json" else orig(nombre, default)
        try:
            r = herramientas.temas_comunitarios(categoria="agua", barrio="guasmo", sin_cubrir=True)
            self.assertEqual(len(r), 1)
            self.assertEqual(r[0]["personas_distintas"], 1)
            self.assertTrue(r[0]["voces"])
        finally:
            herramientas._cargar = orig


if __name__ == "__main__":
    unittest.main()
