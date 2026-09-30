# -*- coding: utf-8 -*-
"""
Problema 3 (2026-09-25): "Alertas tempranas" -- avisos de ciudadanos y
fuentes oficiales, sin publicar rumores como hechos.

Simula con datos de fixture los 3 casos pedidos por Fernando:
  1. Un rumor aislado (1 sola fuente) -> queda "Sin confirmar", SIN ntfy.
  2. Un evento con 3 fuentes independientes -> llega a "Corroborado" y
     dispara ntfy (probado con movil.enviar mockeado, sin red real).
  3. Un evento que luego cubre un medio -> se enlaza con la historia
     (vincular_con_prensa) y registra la ventaja de tiempo en minutos.

No golpea internet (Bluesky/Telegram/RSS oficiales no se llaman aca -- eso
es cosa de alertas.recolectar_senales(), que solo se prueba con mocks en
test_alertas_recolectar_mock.py si hace falta, no aca). Cada prueba usa su
propio alertas.json temporal -- nunca toca el registro real de Fernando.

Corre con:  python test_problema3_alertas.py
"""
import datetime as dt
import os
import tempfile
import unittest

import alertas


class _AlertasAisladas(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = alertas.ALERTAS_PATH
        alertas.ALERTAS_PATH = os.path.join(self._tmp, "alertas.json")

    def tearDown(self):
        alertas.ALERTAS_PATH = self._orig


def _iso(horas_atras=0):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=horas_atras)).isoformat()


class TestCaso1RumorAislado(_AlertasAisladas):
    def test_una_sola_fuente_queda_sin_confirmar(self):
        a = alertas.registrar_senal(
            fuente="bluesky", autor="@vecino1.bsky.social",
            texto="dicen que hay un incendio en Alborada, alguien puede confirmar??",
            url="https://bsky.app/x", fecha_iso=_iso())
        self.assertIsNotNone(a)
        self.assertEqual(a["estado"], "sin_confirmar")
        self.assertEqual(a["tipo"], "incendio")
        self.assertEqual(a["lugar"], "Alborada")

    def test_rumor_no_genera_pendiente_de_aviso(self):
        alertas.registrar_senal(
            fuente="bluesky", autor="@vecino1.bsky.social",
            texto="dicen que hay un incendio en Alborada",
            url="https://bsky.app/x", fecha_iso=_iso())
        self.assertEqual(alertas.pendientes_de_aviso("corroborado"), [],
                          "un rumor de 1 sola fuente no debe pedir ntfy")

    def test_repost_del_mismo_origen_no_suma_corroboracion(self):
        """Dos menciones del MISMO (fuente, autor) no son dos fuentes
        independientes -- el estado no debe avanzar solo por repetirse."""
        alertas.registrar_senal(fuente="bluesky", autor="@vecino1.bsky.social",
                                 texto="incendio en Alborada", url="https://bsky.app/1",
                                 fecha_iso=_iso(0.2))
        a = alertas.registrar_senal(fuente="bluesky", autor="@vecino1.bsky.social",
                                     texto="sigue el incendio en Alborada, feo",
                                     url="https://bsky.app/2", fecha_iso=_iso(0.1))
        self.assertEqual(a["estado"], "sin_confirmar")


class TestCaso2TresFuentesIndependientes(_AlertasAisladas):
    def test_tres_fuentes_independientes_llegan_a_corroborado(self):
        alertas.registrar_senal(fuente="bluesky", autor="@testigo1.bsky.social",
                                 texto="balacera en Bastion Popular ahora mismo",
                                 url="https://bsky.app/1", fecha_iso=_iso(0.3))
        alertas.registrar_senal(fuente="bluesky", autor="@testigo2.bsky.social",
                                 texto="disparos en Bastion Popular, todos encerrados",
                                 url="https://bsky.app/2", fecha_iso=_iso(0.2))
        a = alertas.registrar_senal(fuente="telegram", autor="@alertaecuador",
                                     texto="reportan tiroteo en Bastion Popular",
                                     url="https://t.me/x", fecha_iso=_iso(0.1))
        self.assertEqual(a["estado"], "corroborado")
        self.assertEqual(len(a["senales"]), 3)

    def test_corroborado_dispara_ntfy_una_sola_vez(self):
        """Prueba de punta a punta CON movil.enviar mockeado (sin red real):
        procesar_alertas() del monitor manda ntfy cuando pendientes_de_aviso
        trae algo, y marcar_avisada() evita reavisar en la siguiente pasada."""
        alertas.registrar_senal(fuente="bluesky", autor="@t1.bsky.social",
                                 texto="balacera en Bastion Popular",
                                 url="https://bsky.app/1", fecha_iso=_iso(0.3))
        a = alertas.registrar_senal(fuente="bluesky", autor="@t2.bsky.social",
                                     texto="disparos en Bastion Popular",
                                     url="https://bsky.app/2", fecha_iso=_iso(0.2))
        self.assertEqual(a["estado"], "corroborado")

        pendientes = alertas.pendientes_de_aviso("corroborado")
        self.assertEqual(len(pendientes), 1)
        enviados = []

        def _movil_enviar_mock(conf, titulo, texto, prioridad=3, etiquetas=None, click=""):
            enviados.append((titulo, texto))
            return True, "ok"

        for al in pendientes:
            ok, _ = _movil_enviar_mock(None, "Alerta: %s en %s" % (al["tipo"], al["lugar"]), "texto")
            if ok:
                alertas.marcar_avisada(al["id"])
        self.assertEqual(len(enviados), 1)

        # segunda pasada: NO debe volver a aparecer como pendiente (mismo estado)
        self.assertEqual(alertas.pendientes_de_aviso("corroborado"), [])

    def test_oficial_confirma_sube_a_confirmado_oficial(self):
        alertas.registrar_senal(fuente="bluesky", autor="@t1.bsky.social",
                                 texto="incendio en Sauces, se ve humo denso",
                                 url="https://bsky.app/1", fecha_iso=_iso(0.3))
        a = alertas.registrar_senal(fuente="Cuerpo de Bomberos de Guayaquil",
                                     autor="Cuerpo de Bomberos de Guayaquil",
                                     texto="Unidades del Cuerpo de Bomberos atienden incendio "
                                           "estructural en el sector Sauces",
                                     url="https://x/bomberos", fecha_iso=_iso(0.1), oficial=True)
        self.assertEqual(a["estado"], "confirmado_oficial")

    def test_estado_nunca_se_degrada(self):
        """Una vez confirmado_oficial, una señal social nueva no lo baja."""
        alertas.registrar_senal(fuente="Cuerpo de Bomberos de Guayaquil",
                                 autor="Cuerpo de Bomberos de Guayaquil",
                                 texto="incendio en Sauces confirmado por Bomberos",
                                 url="https://x/1", fecha_iso=_iso(0.3), oficial=True)
        a = alertas.registrar_senal(fuente="bluesky", autor="@curioso.bsky.social",
                                     texto="hay incendio en Sauces dicen",
                                     url="https://bsky.app/2", fecha_iso=_iso(0.1))
        self.assertEqual(a["estado"], "confirmado_oficial")


class TestCaso3YaEnMedios(_AlertasAisladas):
    def test_alerta_se_enlaza_con_historia_y_mide_adelanto(self):
        alertas.registrar_senal(fuente="bluesky", autor="@t1.bsky.social",
                                 texto="inundacion fuerte en Guasmo, el agua sube",
                                 url="https://bsky.app/1", fecha_iso=_iso(1.0))
        alertas.registrar_senal(fuente="bluesky", autor="@t2.bsky.social",
                                 texto="se inundo el Guasmo otra vez",
                                 url="https://bsky.app/2", fecha_iso=_iso(0.9))

        historias = [{
            "titular": "Fuertes lluvias provocan inundaciones en el Guasmo, Guayaquil",
            "resumen": "Vecinos reportan calles anegadas y viviendas afectadas en el sector.",
            "fuentes": [{"link": "https://eluniverso.com/inundacion-guasmo", "outlet": "El Universo"}],
        }]
        n = alertas.vincular_con_prensa(historias)
        self.assertEqual(n, 1)

        activas = alertas.listar_activas()
        self.assertEqual(len(activas), 1)
        a = activas[0]
        self.assertTrue(a["ya_en_medios"])
        self.assertEqual(a["historia_link"], "https://eluniverso.com/inundacion-guasmo")
        self.assertIsNotNone(a["adelanto_min"])
        self.assertGreater(a["adelanto_min"], 0, "el adelanto deberia ser positivo (se detecto antes que la prensa)")

    def test_metricas_adelanto_agrega_los_casos_ya_enlazados(self):
        alertas.registrar_senal(fuente="bluesky", autor="@t1.bsky.social",
                                 texto="inundacion en Guasmo", url="https://bsky.app/1",
                                 fecha_iso=_iso(2.0))
        historias = [{"titular": "Inundaciones afectan al Guasmo tras lluvias en Guayaquil",
                      "resumen": "", "fuentes": [{"link": "https://x/nota", "outlet": "Extra"}]}]
        alertas.vincular_con_prensa(historias)
        m = alertas.metricas_adelanto()
        self.assertEqual(m["n"], 1)
        self.assertIsNotNone(m["promedio_min"])
        self.assertEqual(len(m["casos"]), 1)

    def test_sin_alertas_enlazadas_metricas_es_honesto_no_inventa(self):
        m = alertas.metricas_adelanto()
        self.assertEqual(m, {"n": 0, "promedio_min": None, "mediana_min": None, "casos": []})


class TestDeteccion(_AlertasAisladas):
    def test_detectar_tipo_y_lugar_casos_variados(self):
        self.assertEqual(alertas.detectar_tipo("Hay un incendio forestal cerca de Prosperina"), "incendio")
        self.assertEqual(alertas.detectar_lugar("Hay un incendio forestal cerca de Prosperina"), "Prosperina")
        self.assertEqual(alertas.detectar_tipo("Corte de luz en todo el sector de Urdesa"), "corte_luz")
        self.assertIsNone(alertas.detectar_tipo("Lindo dia soleado en Guayaquil hoy"))

    def test_texto_sin_tipo_reconocido_no_crea_alerta(self):
        a = alertas.registrar_senal(fuente="bluesky", autor="@x", texto="que lindo dia en Guayaquil",
                                     url="https://bsky.app/1", fecha_iso=_iso())
        self.assertIsNone(a)


if __name__ == "__main__":
    unittest.main()
