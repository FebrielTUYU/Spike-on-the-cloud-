# -*- coding: utf-8 -*-
"""Fase 22c: reserva de presupuesto para las consultas, lectura de la
comunidad con IA (validada en codigo) y mapa de Guayaquil. Sin red real."""
import datetime as dt
import json
import os
import tempfile
import unittest

import comunidad
import ia
import mapa
import monitor

AHORA = dt.datetime.now(dt.timezone.utc)


class TestReservaConsultas(unittest.TestCase):
    """Bug real: el trabajo de fondo gastaba el tope diario y el Asistente
    respondia 'presupuesto agotado ... ¿Esta Ollama corriendo?'."""
    def setUp(self):
        self.orig = (ia.gasto_hoy, ia.gasto_mes, ia.TOPE_DIA_USD, ia.RESERVA_INTERACTIVA_USD)
        ia.TOPE_DIA_USD, ia.RESERVA_INTERACTIVA_USD = 1.0, 0.30
        ia.gasto_hoy = lambda: 0.75
        ia.gasto_mes = lambda: 1.0

    def tearDown(self):
        ia.gasto_hoy, ia.gasto_mes, ia.TOPE_DIA_USD, ia.RESERVA_INTERACTIVA_USD = self.orig

    def test_el_fondo_no_toca_la_reserva(self):
        ok, razon = ia._cabe_en_presupuesto(0.05)
        self.assertFalse(ok)
        self.assertIn("reservados", razon)

    def test_la_consulta_del_usuario_usa_la_reserva(self):
        with ia.interactivo():
            ok, _ = ia._cabe_en_presupuesto(0.05)
        self.assertTrue(ok)
        self.assertFalse(ia.es_interactivo())  # se apaga al salir

    def test_mensaje_claro_sin_ollama(self):
        ia.gasto_hoy = lambda: 1.0
        with ia.interactivo():
            ok, razon = ia._cabe_en_presupuesto(0.05)
        self.assertFalse(ok)
        self.assertIn("se renueva a medianoche", razon)
        self.assertNotIn("Ollama", razon)
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html"),
                   encoding="utf-8").read()
        self.assertNotIn("Ollama corriendo", src)


def _com():
    return {"temas": [
        {"id": "Urdesa|basura", "titulo": "Basura — Urdesa", "barrio": "Urdesa", "categoria": "basura",
         "categoria_label": "Basura", "personas": 4, "n": 6, "cubierto": False,
         "publicaciones": [{"texto": "En Urdesa la basura lleva 3 dias"}]},
        {"id": "Guasmo|agua", "titulo": "Agua — Guasmo", "barrio": "Guasmo", "categoria": "agua",
         "categoria_label": "Agua", "personas": 3, "n": 3, "cubierto": True, "publicaciones": []},
        {"id": "%s|luz" % comunidad.SIN_SECTOR, "titulo": "Luz", "barrio": comunidad.SIN_SECTOR,
         "categoria": "luz", "categoria_label": "Luz", "personas": 2, "n": 2, "cubierto": False, "publicaciones": []},
    ], "total_publicaciones": 11}


class TestLecturaComunidad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = (comunidad.LECTURA_PATH, ia._generar_json)
        comunidad.LECTURA_PATH = os.path.join(self.tmp, "lectura.json")

    def tearDown(self):
        comunidad.LECTURA_PATH, ia._generar_json = self.orig

    def test_descarta_citas_inventadas_y_zonas_que_no_estan(self):
        ia._generar_json = lambda *a, **k: {
            "resumen": "La gente se queja de basura y agua.",
            "lo_que_mas_habla": [{"texto": "Basura", "temas": ["T1"]}, {"texto": "Inventado", "temas": ["T9"]}],
            "factor_comun": {"texto": "Servicios municipales", "temas": ["T1", "T2"]},
            "zonas": [{"zona": "Urdesa", "que_dice": "basura", "temas": ["T1"]},
                      {"zona": "Samborondon", "que_dice": "no esta en los datos", "temas": ["T1"]},
                      {"zona": comunidad.SIN_SECTOR, "que_dice": "x", "temas": ["T3"]}],
            "para_reportear": [{"idea": "Ruta del recolector", "temas": ["T1"]}],
            "limitaciones": "Pocas personas."}
        r = comunidad.actualizar_lectura(_com(), ahora=AHORA)
        self.assertIn("nueva", r)
        d = comunidad.cargar_lectura()
        L = d["lectura"]
        self.assertEqual([x["texto"] for x in L["lo_que_mas_habla"]], ["Basura"])
        self.assertEqual([z["zona"] for z in L["zonas"]], ["Urdesa"])
        self.assertEqual(d["descartadas"], 3)
        self.assertEqual(d["refs"]["T1"]["id"], "Urdesa|basura")

    def test_no_repite_si_no_cambio_nada(self):
        n = []
        ia._generar_json = lambda *a, **k: n.append(1) or {"resumen": "x", "lo_que_mas_habla": [],
                                                            "zonas": [], "para_reportear": []}
        comunidad.actualizar_lectura(_com(), ahora=AHORA)
        self.assertEqual(comunidad.actualizar_lectura(_com(), ahora=AHORA), "lectura: sin cambios")
        self.assertEqual(len(n), 1)

    def test_con_pocos_temas_no_gasta(self):
        ia._generar_json = lambda *a, **k: self.fail("no debia llamar a la IA")
        self.assertIn("pocos temas", comunidad.actualizar_lectura({"temas": _com()["temas"][:1]}, ahora=AHORA))


class TestMapa(unittest.TestCase):
    def _h(self, titular, **kw):
        h = {"titular": titular, "resumen": "", "ciudad": "Guayaquil", "antigua": False,
             "newest": AHORA.isoformat(), "fuentes": [{"link": "http://x/%d" % len(titular)}]}
        h.update(kw)
        return h

    def test_noticia_de_urdesa_va_a_urdesa_con_su_apreciacion(self):
        r = mapa.puntos([self._h("ATM multa a bus que se paso el semaforo en rojo en Urdesa")])
        p = r["puntos"][0]
        self.assertEqual((p["sector"], p["donde"], p["tipo"]), ("Urdesa", "titular", "noticia"))
        self.assertAlmostEqual(p["lat"], mapa.COORDS["Urdesa"][0], places=2)

    def test_sin_sector_no_se_inventa_un_punto(self):
        r = mapa.puntos([self._h("Municipio anuncia plan de lluvias")])
        self.assertEqual(r["puntos"], [])
        self.assertEqual(r["sin_sector"], 1)

    def test_historia_madre_se_reparte_por_sector(self):
        madre = self._h("Lluvias en Guayaquil — 29 sep", sub_actualizaciones=[
            {"titular": "Se inunda Sauces 6", "sector": "", "link": "a", "outlets": ["x"]},
            {"titular": "Calles anegadas en el Guasmo", "sector": "", "link": "b", "outlets": ["y"]}])
        r = mapa.puntos([madre])
        self.assertEqual(sorted(p["sector"] for p in r["puntos"]), ["Guasmo", "Sauces"])

    def test_alertas_y_comunidad_en_el_mapa(self):
        r = mapa.puntos([], [{"lugar": "Guasmo", "tipo": "inundacion", "estado": "corroborado",
                              "senales": [{"texto": "Se inunda el Guasmo", "url": ""}]}], _com())
        tipos = sorted(p["tipo"] for p in r["puntos"])
        self.assertEqual(tipos, ["alerta", "comunidad", "comunidad"])

    def test_todos_los_barrios_de_comunidad_tienen_ubicacion(self):
        faltan = [b for b in comunidad.BARRIOS if b not in mapa.COORDS]
        self.assertEqual(faltan, [])


class TestDuranApellido(unittest.TestCase):
    """Bug real: 'Murio Nafer Duran' (cantante colombiano) quedo como noticia
    de Guayaquil/Duran."""
    def test_apellido_no_es_el_canton(self):
        self.assertNotEqual(monitor.detect_city("Murio Nafer Duran: asi despidio el mundo del vallenato"), "Duran")

    def test_el_canton_si(self):
        self.assertEqual(monitor.detect_city("Balacera en Duran deja dos heridos"), "Duran")



class TestMapaAlArrancar(unittest.TestCase):
    """Bug real: al abrir, el mapa decia "Sin datos del mapa todavia" porque el
    data.json de la corrida anterior era de antes del mapa; y los mosaicos de
    CARTO pedian clave ("API KEY REQUIRED")."""

    def test_regenerar_arma_el_mapa_desde_data_viejo(self):
        with tempfile.TemporaryDirectory() as d:
            viejo_here = monitor.HERE
            try:
                monitor.HERE = d
                h = {"titular": "Inundacion en Urdesa deja calles anegadas", "resumen": "",
                     "ciudad": "Guayaquil", "newest": "2026-09-30T12:00:00+00:00",
                     "fuentes": [{"link": "http://x/1"}]}
                with open(os.path.join(d, "data.json"), "w", encoding="utf-8") as f:
                    json.dump({"historias": [h]}, f)
                tpl = open(os.path.join(viejo_here, "dashboard_template.html"), encoding="utf-8").read()
                with open(os.path.join(d, "dashboard_template.html"), "w", encoding="utf-8") as f:
                    f.write(tpl)
                self.assertTrue(monitor.regenerar_dashboard_desde_data())
                html = open(os.path.join(d, "dashboard.html"), encoding="utf-8").read()
                self.assertIn('"sector": "Urdesa"', html)
            finally:
                monitor.HERE = viejo_here

    def test_mosaicos_sin_clave(self):
        tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html"),
                   encoding="utf-8").read()
        self.assertNotIn("basemaps.cartocdn.com", tpl)
        self.assertIn("tile.openstreetmap.org", tpl)

if __name__ == "__main__":
    unittest.main()
