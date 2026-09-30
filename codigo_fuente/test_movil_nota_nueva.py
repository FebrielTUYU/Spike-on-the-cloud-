# -*- coding: utf-8 -*-
"""
Prueba del disparador "nota nueva" de movil.py (Fase 0, pedido explicito de
Fernando: "push para noticias nuevas de Guayaquil/Ecuador, con limite de
avisos por hora"). Distinto de "historia fuerte" (que exige min_medios y en
la practica casi nunca dispara, ver LIMITACION CONOCIDA en movil.py) -- este
dispara con una sola fuente, siempre que sea reciente y este en el ambito
pedido, respetando un cupo por hora.

Corre con:  python test_movil_nota_nueva.py
"""
import unittest

import movil as mv


def _story(titular, ciudad="Guayaquil", hours=0.2, n_outlets=1, es_local=True):
    return {"titular": titular, "es_local": es_local, "ciudad": ciudad,
            "n_outlets": n_outlets, "outlets": ["El Universo"], "hours": hours,
            "temas": [], "fuentes": [{"link": "https://x/" + titular[:10]}]}


class TestNotaNueva(unittest.TestCase):
    def _conf(self, **over):
        conf = dict(mv.DEFAULTS)
        conf.update(avisos_nota_nueva=True, nota_nueva_limite_hora=2)
        conf.update(over)
        return conf

    def test_apagado_por_defecto_no_dispara(self):
        conf = dict(mv.DEFAULTS)  # avisos_nota_nueva=False (default)
        estado = {"historias": [], "temas": {}}
        cands = mv.detectar([_story("Nota X")], {}, estado, conf)
        self.assertFalse(any(c.get("tipo") == "nota_nueva" for c in cands))

    def test_nota_de_una_sola_fuente_dispara_si_esta_prendido(self):
        conf = self._conf()
        estado = {"historias": [], "temas": {}}
        cands = mv.detectar([_story("Nota nueva de Guayaquil")], {}, estado, conf)
        nn = [c for c in cands if c.get("tipo") == "nota_nueva"]
        self.assertEqual(len(nn), 1)

    def test_respeta_el_ambito_guayaquil(self):
        conf = self._conf(nota_nueva_ambito="guayaquil")
        estado = {"historias": [], "temas": {}}
        cands = mv.detectar([_story("Nota de Quito", ciudad="")], {}, estado, conf)
        self.assertFalse(any(c.get("tipo") == "nota_nueva" for c in cands))

    def test_nota_vieja_no_dispara(self):
        conf = self._conf()
        estado = {"historias": [], "temas": {}}
        cands = mv.detectar([_story("Nota vieja", hours=5)], {}, estado, conf)
        self.assertFalse(any(c.get("tipo") == "nota_nueva" for c in cands))

    def test_cupo_por_hora_se_respeta(self):
        conf = self._conf(nota_nueva_limite_hora=2)
        estado = {"historias": [], "temas": {}}
        stories = [_story("Nota %d" % i) for i in range(5)]
        cands = mv.detectar(stories, {}, estado, conf)
        nn = [c for c in cands if c.get("tipo") == "nota_nueva"]
        self.assertEqual(len(nn), 2, "no deberia superar el cupo por hora aunque haya mas notas nuevas")

    def test_cupo_se_acumula_entre_corridas_dentro_de_la_misma_hora(self):
        conf = self._conf(nota_nueva_limite_hora=2)
        estado = {"historias": [], "temas": {}}
        mv.detectar([_story("Primera")], {}, estado, conf)
        # simular que ya se avisaron 2 en esta hora
        hora_actual = estado["nota_nueva_horaria"]["hora"]
        estado["nota_nueva_horaria"] = {"hora": hora_actual, "n": 2}
        cands = mv.detectar([_story("Otra distinta")], {}, estado, conf)
        self.assertFalse(any(c.get("tipo") == "nota_nueva" for c in cands),
                          "con el cupo de la hora ya gastado no deberia disparar mas")

    def test_historia_fuerte_no_se_pisa_con_nota_nueva(self):
        conf = self._conf()
        estado = {"historias": [], "temas": {}}
        s = _story("Historia grande", n_outlets=3)  # >= min_medios (2)
        cands = mv.detectar([s], {}, estado, conf)
        tipos = {c.get("tipo") for c in cands}
        self.assertIn("nueva", tipos)
        self.assertNotIn("nota_nueva", tipos)


if __name__ == "__main__":
    unittest.main()
