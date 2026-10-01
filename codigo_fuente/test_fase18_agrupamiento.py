# -*- coding: utf-8 -*-
"""
Fase 18, P0-2 y P0-3 -- agrupamiento y "que es Guayaquil".

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo, con articulos
REALES copiados de historias_registro.json (pruebas/fase18_casos_reales.json):

- Cartagena, Fuerza Regida/CDMX, Republica Dominicana, La Libertad y
  Huaquillas NO pueden terminar dentro de una historia de Guayaquil.
- "fechas y precios", "ataque armado", "corte de agua" no alcanzan solos para
  unir dos notas.
- Noticia nacional (IVA del feriado) -> Ecuador, sin ciudad, aunque la
  publique una seccion de Guayaquil.
- Titular = el del articulo fundador, no el del mas nuevo.
- Lluvias en Guayaquil del 29-sep: de ~10 tarjetas a 1 historia madre (<=2).
- Samborondon/Duran: dentro de Gran Guayaquil pero con su propia localidad.
- "Nueva" solo si la historia se creo hace poco; si no, "Actualizacion".

No golpea red ni IA (monitor.ia = None durante la prueba).
"""
import datetime as dt
import json
import os
import re
import tempfile
import unittest

import monitor

AQUI = os.path.dirname(os.path.abspath(__file__))
FX = json.load(open(os.path.join(AQUI, "pruebas", "fase18_casos_reales.json"), encoding="utf-8"))


def _corrimiento(arts):
    """Corre todas las fechas un numero ENTERO de dias para que el mas nuevo
    quede en el pasado reciente (conserva la hora del dia: la agrupacion por
    dia local no cambia)."""
    ultimo = max(monitor._iso_a_dt(a["date"]) for a in arts)
    dias = (monitor.now_utc() - ultimo).days
    return dt.timedelta(days=max(0, dias))


def _articulos(lista, corr=None):
    corr = corr if corr is not None else _corrimiento(lista)
    out = []
    for a in lista:
        b = dict(a)
        b["date"] = monitor._iso_a_dt(a["date"]) + corr
        b.setdefault("summary", "")
        b.setdefault("seccion", "")
        b.setdefault("image", "")
        b["ciudad_feed"] = a.get("ciudad_feed") or ""
        out.append(b)
    return sorted(out, key=lambda x: x["date"])


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = (monitor.REGISTRO_PATH, monitor.ia)
        monitor.REGISTRO_PATH = os.path.join(self._tmp, "historias_registro.json")
        monitor.ia = None

    def tearDown(self):
        monitor.REGISTRO_PATH, monitor.ia = self._orig

    def _historias(self, lista, de_a_uno=True):
        arts = _articulos(lista)
        stories = []
        if de_a_uno:
            # como en produccion: cada articulo llega en una pasada distinta
            for a in arts:
                stories = monitor.agrupar_con_memoria([a])
        else:
            stories = monitor.agrupar_con_memoria(arts)
        return stories


def _titulos(s):
    return [f["title"] for f in s["fuentes"]]


RX_AJENO = re.compile(r"Cartagena|CDMX|Rep[uú]blica Dominicana|La Libertad|Huaquillas|Est[eé]reo Picnic|Cotopaxi", re.I)


class TestMezclasReales(_Base):
    def setUp(self):
        super().setUp()
        self.stories = self._historias(FX["mezclas"])

    def test_ninguna_historia_de_guayaquil_contiene_otro_lugar(self):
        for s in self.stories:
            if s["ciudad"] != "Guayaquil":
                continue
            ajenas = [t for t in _titulos(s) if RX_AJENO.search(t)]
            self.assertEqual(ajenas, [], "historia de Guayaquil con fuente ajena: %s" % _titulos(s))
            self.assertFalse(RX_AJENO.search(s["titular"]), s["titular"])

    def test_cartagena_no_se_funde_con_cortes_de_agua_de_guayaquil(self):
        for s in self.stories:
            t = " || ".join(_titulos(s))
            if "Cartagena, sin agua" in t:
                self.assertNotIn("Guayaquil", t)

    def test_fechas_y_precios_no_es_puente(self):
        for s in self.stories:
            t = _titulos(s)
            if any("Roberto Bolaños" in x for x in t):
                self.assertEqual(len(t), 1, t)

    def test_ataque_armado_no_es_puente_entre_ciudades(self):
        for s in self.stories:
            t = " || ".join(_titulos(s))
            if "vía a Daule" in t:
                self.assertNotIn("Huaquillas", t)
                self.assertNotIn("La Libertad", t)

    def test_republica_dominicana_no_se_funde_con_clinica_de_guayaquil(self):
        for s in self.stories:
            t = " || ".join(_titulos(s))
            if "clínica de adicciones" in t:
                self.assertNotIn("República Dominicana", t)

    def test_iva_del_feriado_es_nacional_sin_ciudad(self):
        iva = [s for s in self.stories if "IVA" in s["titular"]]
        self.assertTrue(iva)
        for s in iva:
            self.assertEqual(s["ciudad"], "", s["titular"])
            self.assertEqual(s["ambito"], "local", s["titular"])

    def test_la_libertad_no_es_guayaquil(self):
        for s in self.stories:
            if "La Libertad" in s["titular"]:
                self.assertNotEqual(s["ciudad"], "Guayaquil")
                self.assertEqual(s["ambito"], "local")


class TestTitularFundador(_Base):
    def test_titular_es_el_de_la_primera_nota(self):
        a = [{"outlet": "El Universo", "title": "Bomberos controlan incendio en bodega de la Bahía de Guayaquil",
              "link": "https://x/1", "date": "2026-09-29T10:00:00+00:00", "summary": ""},
             {"outlet": "Expreso", "title": "Incendio en bodega de la Bahía de Guayaquil: bomberos investigan causas",
              "link": "https://x/2", "date": "2026-09-29T14:00:00+00:00", "summary": ""}]
        st = self._historias(a)
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["titular"], a[0]["title"])
        self.assertEqual(st[0]["n_outlets"], 2)


class TestEventoEnCurso(_Base):
    def test_lluvias_del_29_quedan_en_una_historia_madre(self):
        stories = monitor.agrupar_eventos_en_curso(self._historias(FX["lluvias"]))
        dia = []
        for s in stories:
            if s["ciudad"] != "Guayaquil":
                continue
            locales = [monitor._iso_a_dt(f["date"]) - dt.timedelta(hours=5) for f in s["fuentes"] if f.get("date")]
            if not re.search(r"lluvi|inund|anega|aguacero|acumulaci", " ".join(_titulos(s)), re.I):
                continue
            # historias con alguna fuente del mismo dia local que la ultima fuente del fixture
            if any(d.day == max(locales).day for d in locales) and max(locales).strftime("%d") in ("29", "30", "28"):
                dia.append(s)
        ultimo_dia = max(max(monitor._iso_a_dt(f["date"]) for f in s["fuentes"]) for s in dia) - dt.timedelta(hours=5)
        del_dia = [s for s in dia if (max(monitor._iso_a_dt(f["date"]) for f in s["fuentes"]) - dt.timedelta(hours=5)).date() == ultimo_dia.date()]
        self.assertLessEqual(len(del_dia), 2, [s["titular"] for s in del_dia])
        madres = [s for s in del_dia if s.get("evento_en_curso")]
        self.assertTrue(madres)
        m = madres[0]
        self.assertRegex(m["titular"], r"^Lluvias en Guayaquil")
        self.assertGreaterEqual(len(m["sub_actualizaciones"]), 3)
        # ninguna historia de otro pais dentro de la madre
        self.assertFalse(any("El Salvador" in t for t in _titulos(m)))


class TestLocalidadYMarcas(_Base):
    def test_samborondon_es_gran_guayaquil_con_localidad_propia(self):
        a = [{"outlet": "Expreso", "title": "Lluvias golpean a Samborondón: ¿qué zonas registraron acumulación de agua?",
              "link": "https://x/s", "date": "2026-09-29T10:00:00+00:00", "summary": ""}]
        s = self._historias(a)[0]
        self.assertEqual(s["ciudad"], "Guayaquil")
        self.assertEqual(s.get("localidad"), "Samborondón")

    def test_nueva_vs_actualizacion(self):
        ahora = monitor.now_utc()
        viejo = (ahora - dt.timedelta(hours=9)).isoformat()
        nuevo = (ahora - dt.timedelta(minutes=20)).isoformat()
        a = [{"outlet": "El Universo", "title": "Municipio de Guayaquil cierra el paso a desnivel de la Kennedy por fisuras",
              "link": "https://x/k1", "date": viejo, "summary": ""},
             {"outlet": "Expreso", "title": "Paso a desnivel de la Kennedy cerrado por fisuras: Municipio de Guayaquil da detalles",
              "link": "https://x/k2", "date": nuevo, "summary": ""}]
        arts = _articulos(a, corr=dt.timedelta(0))
        monitor.agrupar_con_memoria([arts[0]])
        s = monitor.agrupar_con_memoria([arts[1]])[0]
        self.assertEqual(s["n_outlets"], 2)
        self.assertFalse(s["es_nueva"])
        self.assertAlmostEqual(s["horas_desde_creacion"], 9, delta=0.5)
        b = [{"outlet": "Extra", "title": "Choque múltiple en la vía Perimetral deja tres heridos en Guayaquil",
              "link": "https://x/p1", "date": nuevo, "summary": ""}]
        s2 = [x for x in monitor.agrupar_con_memoria(_articulos(b, corr=dt.timedelta(0))) if "Perimetral" in x["titular"]][0]
        self.assertTrue(s2["es_nueva"])


if __name__ == "__main__":
    unittest.main()
