# -*- coding: utf-8 -*-
"""
Fase 24, Parte D -- Internacional: filtro util/basura nota por nota (nunca se
quita un feed), orden de prioridad (Fernando > reglas > IA), tope por medio,
"por que importa aqui" y feeds reactivados. Sin red.
"""
import os
import tempfile
import unittest

import categorias as C
import feeds
import ia
import monitor


def _h(tit, outlet="Infobae", intl=True, interes=1, link=None):
    return {"titular": tit, "resumen": "", "ambito": "internacional" if intl else "local", "internacional": intl,
            "outlets": [outlet], "interes": interes, "fuentes": [{"link": link or ("l-" + tit)}], "categoria": ""}


class TestUtilidad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = monitor.UTIL_MANUAL_PATH
        monitor.UTIL_MANUAL_PATH = os.path.join(self.tmp, "util_manual.json")

    def tearDown(self):
        monitor.UTIL_MANUAL_PATH = self.orig

    def test_reglas_ia_y_lo_local_no_se_toca(self):
        hs = [_h("Dennis Haskins, actor de Salvados por la campana, murio a los 75 anos"),
              dict(_h("US Supreme Court lets Trump resume deportations"), _util_ia=True),
              dict(_h("Pope Leo XIV: AI doom fears are not fake news"), _util_ia=False),
              _h("Corte de agua en Guayaquil", intl=False)]
        monitor._aplicar_utilidad(hs)
        self.assertEqual([h["util"] for h in hs], [False, True, False, True])
        self.assertEqual([h["util_fuente"] for h in hs], ["reglas", "ia", "ia", ""])
        self.assertFalse(any("_util_ia" in h for h in hs))

    def test_fernando_manda_sobre_todo(self):
        h = dict(_h("Matthew Perry: Netflix estrenara documental"), _util_ia=False)
        monitor.save_util_manual({monitor.story_key(h): {"util": "si"}})
        monitor._aplicar_utilidad([h])
        self.assertEqual((h["util"], h["util_fuente"]), (True, "fernando"))

    def test_tope_por_medio(self):
        orig = monitor.INTL_TOPE_MEDIO
        monitor.INTL_TOPE_MEDIO = 3
        try:
            hs = [dict(_h("Nota internacional numero %d sobre economia" % i, interes=10 - i), _util_ia=True)
                  for i in range(5)]
            hs.append(dict(_h("Nota de otro medio sobre economia", outlet="BBC Business"), _util_ia=True))
            monitor._aplicar_utilidad(hs)
        finally:
            monitor.INTL_TOPE_MEDIO = orig
        self.assertEqual([h["util"] for h in hs], [True, True, True, False, False, True])
        self.assertIn("tope", hs[3]["util_razon"])

    def test_candado_de_la_ia(self):
        self.assertEqual(C.candado_util("si", "  Sube el precio del crudo que exporta Ecuador "),
                         (True, "Sube el precio del crudo que exporta Ecuador"))
        self.assertEqual(C.candado_util("no", "algo"), (False, ""))
        self.assertEqual(C.candado_util("quizas", "algo"), (None, ""))

    def test_lote_trae_util_y_por_que_importa(self):
        orig = ia._generar_json
        ia._generar_json = lambda *a, **k: {"items": [
            {"n": 1, "temas": [], "geo": ["internacional"], "categoria": "economia", "tipo": "dato", "quien": "",
             "util": "si", "importa": "Ecuador exporta crudo"}]}
        try:
            r = ia.analizar_lote([{"titular": "Oil prices climb", "resumen": ""}])
        finally:
            ia._generar_json = orig
        self.assertEqual((r[0]["util24"], r[0]["importa24"]), (True, "Ecuador exporta crudo"))
        s = {"titular": "Oil prices climb", "resumen": "", "temas": []}
        monitor._aplicar_categoria(s, r[0])
        self.assertEqual(s["importa_aqui"], "Ecuador exporta crudo")


class TestFeedsReactivados(unittest.TestCase):
    def test_trece_internacionales_vuelven_y_los_muertos_no(self):
        outs = {f["outlet"] for f in feeds.FEEDS}
        for o in ("NYT Business", "BBC Business", "The Japan Times", "SCMP", "Le Figaro", "Der Standard", "Sky News",
                  "NPR (World)", "CBC News (World)", "ABC News (AU)", "The Hindu", "Straits Times", "La Jornada"):
            self.assertIn(o, outs)
        self.assertNotIn("Corriere della Sera", outs)
        self.assertNotIn("Der Spiegel", outs)


if __name__ == "__main__":
    unittest.main()
