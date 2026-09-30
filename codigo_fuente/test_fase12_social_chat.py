# -*- coding: utf-8 -*-
"""
Fase 12 (pedido de Fernando): dos correcciones.

1) Pulso social desfasado -- SOCIAL_TTL/SOCIAL_HIST_TTL estaban en 6 HORAS por
   defecto, aunque el trabajador (enrich_pass) reintenta cada ~20s
   (MONITOR_WORKER_PAUSA) -- el panel quedaba congelado horas enteras. Bajados
   a 10/20 minutos respectivamente (ver monitor.py para el detalle completo).

2) Chat del Asistente: no hacia scroll con respuestas largas (bug real de
   flexbox, .chatlog sin min-height:0 dentro de .chatwidget) y no se podia
   seleccionar texto (causa real: la ventana nativa de pywebview se creaba
   sin text_select=True -- nunca fue un bug de CSS, no habia ninguna regla
   "user-select" en dashboard_template.html).

Corre con:  python test_fase12_social_chat.py
"""
import unittest

import monitor


class TestSocialTTLsMenosAgresivos(unittest.TestCase):
    def test_social_ttl_por_debajo_de_15_minutos(self):
        self.assertLessEqual(monitor.SOCIAL_TTL, 15 * 60,
                              "SOCIAL_TTL deberia estar en el orden de minutos, no de horas")

    def test_social_hist_ttl_por_debajo_de_30_minutos(self):
        self.assertLessEqual(monitor.SOCIAL_HIST_TTL, 30 * 60,
                              "SOCIAL_HIST_TTL deberia estar en el orden de minutos, no de horas")

    def test_ninguno_de_los_dos_es_cero(self):
        # un TTL de 0 golpearia las redes en cada pasada del trabajador (cada
        # ~20s) -- sigue siendo un cache real, solo que mucho mas corto.
        self.assertGreater(monitor.SOCIAL_TTL, 0)
        self.assertGreater(monitor.SOCIAL_HIST_TTL, 0)


class TestVentanaNativaPermiteSeleccionDeTexto(unittest.TestCase):
    def test_create_window_pide_text_select(self):
        # Fase 16: create_window() ahora abre con el esqueleto de carga
        # (html=_ESQUELETO_HTML) en vez de la URL directa -- el texto exacto
        # cambio, pero text_select=True sigue siendo parte de esa misma
        # llamada (ver monitor.py, dentro de serve()).
        with open("monitor.py", encoding="utf-8") as f:
            src = f.read()
        self.assertIn('webview.create_window("Spike", html=_ESQUELETO_HTML, text_select=True)', src,
                      "la ventana nativa deberia pedir text_select=True (pywebview lo deshabilita por defecto)")


class TestChatCSS(unittest.TestCase):
    def setUp(self):
        with open("dashboard_template.html", encoding="utf-8") as f:
            self.html = f.read()

    def test_chatlog_tiene_min_height_cero(self):
        self.assertIn(".chatlog{flex:1;min-height:0;overflow-y:auto", self.html,
                      ".chatlog necesita min-height:0 para poder encogerse y scrollear dentro de .chatwidget")

    def test_chatmsg_permite_seleccion_de_texto(self):
        self.assertIn("user-select:text", self.html)
        self.assertIn("-webkit-user-select:text", self.html)


if __name__ == "__main__":
    unittest.main()
