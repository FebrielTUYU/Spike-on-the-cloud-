# -*- coding: utf-8 -*-
"""
Fase 18, P1-9 -- internacionales con marco.

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo:
- Infobae/Semana: solo secciones de mundo/region (su feed general traia
  Mexico/Colombia local, plantas, farandula) -- ver filtrar_por_ruta.
- 0 historias internacionales de farandula o conciertos (caso real: "Fuerza
  Regida en la CDMX: Fechas, precios de boletos...").
- Triaje con IA (perfil rapido, en LOTE): solo quedan historias con
  relevancia global o para Ecuador/la region, cada una con una linea de
  "por que importa"; tope de internacionales publicadas por relevancia.
Sin red: ia._generar_json se reemplaza.
"""
import os
import tempfile
import unittest

import monitor


def _h(titulo, interes=50, link=None):
    return {"titular": titulo, "resumen": "", "ambito": "internacional", "internacional": True,
            "es_local": False, "interes": interes, "score": interes, "ciudad": "",
            "fuentes": [{"link": link or ("https://x/" + str(abs(hash(titulo)))), "title": titulo}]}


class TestFiltroRuta(unittest.TestCase):
    def test_solo_mundo_y_region(self):
        arts = [{"title": "Planta de hojas agujereadas ideal para interiores", "link": "https://www.infobae.com/mexico/2026/09/29/planta/", "summary": ""},
                {"title": "Dos aves superan el ruido de una motosierra", "link": "https://www.infobae.com/america/2026/09/29/aves/", "summary": ""},
                {"title": "María Becerra explicó por qué no participó", "link": "https://www.infobae.com/teleshow/2026/09/29/x/", "summary": ""},
                {"title": "Exportadores de Ecuador ante los aranceles", "link": "https://www.infobae.com/mexico/2026/09/29/y/", "summary": ""}]
        got = [a["title"] for a in monitor.filtrar_por_ruta(arts, ["america", "mundo"])]
        self.assertEqual(got, ["Dos aves superan el ruido de una motosierra", "Exportadores de Ecuador ante los aranceles"])


class TestFarandula(unittest.TestCase):
    def test_conciertos_y_farandula_fuera(self):
        self.assertTrue(monitor.es_farandula("Fuerza Regida en la CDMX: Fechas, precios de boletos y qué banco tendrá la preventa"))
        self.assertTrue(monitor.es_farandula("Fuerza Regida en vivo desde el Palacio De los Deportes: costos de los paquetes VIP"))
        self.assertTrue(monitor.es_farandula("Festival Estéreo Picnic 2027: fechas y precios de la boletería"))
        self.assertFalse(monitor.es_farandula("Trump anuncia nuevos aranceles a las importaciones de China"))
        self.assertFalse(monitor.es_farandula("Asamblea General de la ONU debate la crisis en Gaza"))


class TestTriaje(unittest.TestCase):
    def setUp(self):
        self.orig = (monitor.TRIAJE_INTL_PATH, monitor.ia)
        monitor.TRIAJE_INTL_PATH = os.path.join(tempfile.mkdtemp(), "triaje.json")

        class IaFalsa:
            PERFIL_RAPIDO = "rapido"
            llamadas = []

            @staticmethod
            def backend_listo():
                return True

            @classmethod
            def _generar_json(cls, prompt, **kw):
                cls.llamadas.append(prompt)
                items = []
                for i, linea in enumerate([l for l in prompt.splitlines() if l[:1].isdigit() and ". " in l]):
                    t = linea.split(". ", 1)[1]
                    if "aranceles" in t:
                        items.append({"i": i, "relevancia": "region", "marco": "Afecta a las exportaciones de la región, incluido Ecuador."})
                    elif "ONU" in t:
                        items.append({"i": i, "relevancia": "global", "marco": "Tensión diplomática con efectos en votaciones de la región."})
                    else:
                        items.append({"i": i, "relevancia": "no", "marco": ""})
                return {"items": items}
        self.IaFalsa = IaFalsa
        monitor.ia = IaFalsa

    def tearDown(self):
        monitor.TRIAJE_INTL_PATH, monitor.ia = self.orig

    def test_triaje_en_lote_marco_y_descarte(self):
        st = [_h("Trump anuncia aranceles a las importaciones de China", 80),
              _h("Asamblea General de la ONU debate la crisis en Gaza", 70),
              _h("Esqueleto o Monstera adansonii: la planta ideal para interiores", 90),
              _h("Fuerza Regida en la CDMX: Fechas, precios de boletos y preventa", 95)]
        estado = monitor.get_triaje_intl(st)
        self.assertEqual(len(self.IaFalsa.llamadas), 1, "tiene que ir en UN lote")
        out = monitor.aplicar_triaje_intl(st, modo_lectura=True)
        titulos = [s["titular"] for s in out]
        self.assertNotIn("Fuerza Regida en la CDMX: Fechas, precios de boletos y preventa", titulos)
        self.assertNotIn("Esqueleto o Monstera adansonii: la planta ideal para interiores", titulos)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(s.get("marco") for s in out))
        self.assertIn("+", estado)

    def test_tope_de_internacionales(self):
        orig = monitor.INTL_MAX
        monitor.INTL_MAX = 3
        try:
            st = [_h("Nota internacional numero %d sobre diplomacia" % i, i) for i in range(10)]
            st.append({"titular": "Local", "ambito": "local", "es_local": True, "interes": 1, "fuentes": [{"link": "l"}]})
            out = monitor.aplicar_triaje_intl(st, modo_lectura=True)
            self.assertEqual(sum(1 for s in out if s.get("ambito") == "internacional"), 3)
            self.assertEqual(sum(1 for s in out if s.get("es_local")), 1)
        finally:
            monitor.INTL_MAX = orig


if __name__ == "__main__":
    unittest.main()
