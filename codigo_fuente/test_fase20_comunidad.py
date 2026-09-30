# -*- coding: utf-8 -*-
"""
Fase 20 -- lente "Comunidad" de Guayaquil.

Escrita DESDE EL PEDIDO de Fernando antes del modulo: "que Spike ayude a
identificar temas comunitarios de Guayaquil para realizar noticias o
reportajes: problemas de barrio, eventos que se den dentro de la ciudad,
historias humanas... un escaneo de las personas en Guayaquil donde se
identifique y se pueda encontrar un tema para explotar".

Titulares REALES del data.json del 2026-09-30 (seccion Guayaquil).
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import comunidad

AQUI = os.path.dirname(os.path.abspath(__file__))


def _h(titular, fecha="2026-09-29T15:00:00+00:00", outlets=("Expreso",), ciudad="Guayaquil", link=None):
    link = link or "https://x/" + str(abs(hash(titular)))
    fuentes = [{"outlet": o, "title": titular, "link": link if i == 0 else link + "/" + str(i), "date": fecha}
               for i, o in enumerate(outlets)]
    return {"titular": titular, "resumen": "", "fuentes": fuentes, "ciudad": ciudad,
            "es_local": True, "n_outlets": len(outlets), "newest": fecha}


class TestDetectar(unittest.TestCase):
    def test_problemas_de_barrio_con_sector(self):
        d = comunidad.detectar(_h("14 sectores del norte de Guayaquil no tendrán agua por 12 horas"))
        self.assertEqual((d["categoria"], d["subtipo"]), ("problema", "agua"))
        self.assertEqual(d["barrio"], "Norte de Guayaquil")
        d = comunidad.detectar(_h("Pacientes denuncian falta de insumos en el Hospital Monte Sinaí de Guayaquil"))
        self.assertEqual((d["categoria"], d["subtipo"], d["barrio"]), ("problema", "salud", "Monte Sinai"))
        d = comunidad.detectar(_h("Socio Vivienda 2: Bandas retoman el control tras operativo policial en Guayaquil"))
        self.assertEqual((d["subtipo"], d["barrio"]), ("inseguridad", "Socio Vivienda"))
        d = comunidad.detectar(_h("La basura que queda en las calles de Guayaquil ya suma 16.799 casos en 2026"))
        self.assertEqual(d["subtipo"], "basura")

    def test_eventos_de_la_ciudad(self):
        for t in ("Maratón de Guayaquil 2026: fecha, ruta del 42K y entrega de kits",
                  "Festival EDOC abrió su cartelera en Guayaquil: estos son los directores y películas",
                  "Guayaquil alista la “Gala del Pasillo Ecuatoriano” este 1 de octubre"):
            self.assertEqual(comunidad.detectar(_h(t))["categoria"], "evento", t)

    def test_historias_humanas(self):
        for t in ("“Pensé que ya no volvería a ver a mis hijos”: la hipertensión deterioró su corazón",
                  "Aprendieron un oficio en ZUMAR y hoy enseñan a otros a construir su futuro",
                  "La nadadora que se hizo escuchar en Guayaquil: Linda Guerao"):
            self.assertEqual(comunidad.detectar(_h(t))["categoria"], "humana", t)

    def test_boletines_y_medidas_nacionales_no_son_temas(self):
        for t in ("Clima hoy en Guayaquil, Ecuador: el pronóstico del tiempo para este martes 29 septiembre de 2026",
                  "A qué hora y día finaliza el toque de queda en Guayaquil y otras provincias de Ecuador",
                  "IVA bajará al 8 % durante el feriado del 9 de octubre en Ecuador: estas son las fechas"):
            self.assertIsNone(comunidad.detectar(_h(t)), t)

    def test_fuera_de_guayaquil_no_entra(self):
        self.assertIsNone(comunidad.detectar(_h("Dos hombres murieron por ataque armado en La Libertad, Santa Elena",
                                                ciudad="Santa Elena")))

    def test_cooperativa_como_sector(self):
        d = comunidad.detectar(_h("Moradores de la cooperativa Janeth Toral denuncian que llevan una semana sin agua en Guayaquil"))
        self.assertEqual(d["barrio"], "Coop. Janeth Toral")
        self.assertEqual(d["subtipo"], "agua")


class TestRegistroYTemas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = comunidad.COMUNIDAD_PATH
        comunidad.COMUNIDAD_PATH = os.path.join(self.tmp, "comunidad.json")
        self.ahora = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)

    def tearDown(self):
        comunidad.COMUNIDAD_PATH = self.orig

    def test_problema_recurrente_en_dias_distintos_sube_y_explica_por_que(self):
        # Tres pasadas en dias distintos: cada una trae UNA nota distinta del
        # mismo problema en el mismo barrio (las viejas ya salieron del feed).
        dias = ["2026-09-12T15:00:00+00:00", "2026-09-20T15:00:00+00:00", "2026-09-29T15:00:00+00:00"]
        for i, f in enumerate(dias):
            comunidad.actualizar([_h("Moradores del Guasmo sur reportan que no tienen agua desde hace días (%d)" % i,
                                     fecha=f, outlets=("Extra",))], ahora=self.ahora)
        comunidad.actualizar([_h("Maratón de Guayaquil 2026: fecha, ruta del 42K", fecha=dias[-1])], ahora=self.ahora)
        out = comunidad.actualizar([], ahora=self.ahora)
        t = out["temas"][0]
        self.assertEqual((t["barrio"], t["subtipo"]), ("Guasmo", "agua"))
        self.assertEqual(t["dias"], 3)
        self.assertEqual(len(t["apariciones"]), 3)
        self.assertIn("3 días distintos", t["por_que"])
        self.assertTrue(t["pistas"])

    def test_misma_historia_en_varias_pasadas_no_se_cuenta_dos_veces(self):
        h = _h("Pascuales se convierte en la zona más violenta de Guayaquil por la disputa de bandas")
        comunidad.actualizar([h], ahora=self.ahora)
        out = comunidad.actualizar([h], ahora=self.ahora)
        self.assertEqual(sum(len(t["apariciones"]) for t in out["temas"]), 1)

    def test_historia_humana_de_un_solo_medio_se_marca_para_profundizar(self):
        out = comunidad.actualizar([_h("La nadadora que se hizo escuchar en Guayaquil: Linda Guerao",
                                       outlets=("El Universo",))], ahora=self.ahora)
        t = out["temas"][0]
        self.assertEqual(t["categoria"], "humana")
        self.assertIn("profundizar", t["por_que"])

    def test_items_viejos_se_purgan(self):
        comunidad.actualizar([_h("Moradores de Mapasingue sin agua", fecha="2026-05-01T12:00:00+00:00")],
                             ahora=self.ahora)
        out = comunidad.actualizar([], ahora=self.ahora)
        self.assertEqual(out["temas"], [])

    def test_no_persistir_no_escribe_disco(self):
        comunidad.actualizar([_h("Moradores de Mapasingue sin agua")], ahora=self.ahora, persistir=False)
        self.assertFalse(os.path.exists(comunidad.COMUNIDAD_PATH))

    def test_alerta_de_la_gente_en_el_mismo_barrio_suma(self):
        h = _h("Calles inundadas en Sauces tras la lluvia de la tarde", fecha="2026-09-29T20:00:00+00:00")
        alerta = {"tipo": "inundacion", "lugar": "Sauces", "primera_deteccion": "2026-09-29T19:30:00+00:00",
                  "estado": "corroborado"}
        out = comunidad.actualizar([h], alertas=[alerta], ahora=self.ahora)
        t = out["temas"][0]
        self.assertEqual(t["alertas"], 1)
        self.assertIn("alerta", t["por_que"])

    def test_variedad_el_top_no_es_solo_inseguridad(self):
        hs = [_h("Asesinan a un hombre en %s, Guayaquil" % b, fecha="2026-09-%02dT15:00:00+00:00" % d)
              for b in ("Pascuales", "Guasmo", "Mapasingue", "Sauces", "Alborada", "Urdesa")
              for d in (20, 25, 29)]
        hs.append(_h("Moradores de la Isla Trinitaria llevan tres días sin agua"))
        out = comunidad.actualizar(hs, ahora=self.ahora)
        top5 = [t["subtipo"] for t in out["temas"][:5]]
        self.assertIn("agua", top5)


class TestDatosReales(unittest.TestCase):
    def test_data_json_real_produce_temas_de_las_tres_categorias(self):
        d = json.load(open(os.path.join(AQUI, "data.json"), encoding="utf-8"))
        gye = [h for h in d["historias"] if h.get("ciudad") == "Guayaquil"]
        out = comunidad.actualizar(gye, persistir=False,
                                   ahora=dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc))
        cats = {t["categoria"] for t in out["temas"]}
        self.assertEqual(cats, {"problema", "evento", "humana"})
        # nada de boletines del clima entre los temas
        self.assertFalse(any("pronóstico del tiempo" in a["titular"].lower()
                             for t in out["temas"] for a in t["apariciones"]))


class TestAsistente(unittest.TestCase):
    def test_herramienta_filtra_por_categoria_y_barrio(self):
        import herramientas
        d = json.load(open(os.path.join(AQUI, "data.json"), encoding="utf-8"))
        d["comunidad"] = comunidad.actualizar(d["historias"], persistir=False,
                                              ahora=dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc))
        orig = herramientas._cargar
        herramientas._cargar = lambda nombre, default: d if nombre == "data.json" else orig(nombre, default)
        try:
            r = herramientas.temas_comunitarios(categoria="problemas", barrio="samborondon")
            self.assertTrue(r)
            self.assertTrue(all(x["barrio"] == "Samborondon" and x["categoria"] == "Problema del barrio" for x in r))
            self.assertIn("temas_comunitarios", herramientas.HERRAMIENTAS)
        finally:
            herramientas._cargar = orig


if __name__ == "__main__":
    unittest.main()
