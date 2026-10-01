# -*- coding: utf-8 -*-
"""
Fase 18, P0-4 -- conectar senales.py (Fase 15), que nunca se enchufo.

Escrita DESDE LA ESPECIFICACION antes de tocar el codigo:
- monitor.py importa senales y arranca un hilo 'ciclo_senales' en serve().
- data.json["senales"] trae las senales activas; existe senales_estado.json.
- Las senales sirven para TODO Ecuador (no solo Guayaquil), Guayaquil primero.
- Sobre el data.json REAL de la corrida del 2026-09-30, una corrida normal da
  >= 1 senal (sin IA: la IA solo agrega primer_paso/desenlace).
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import monitor
import senales

AQUI = os.path.dirname(os.path.abspath(__file__))
AHORA = dt.datetime(2026, 9, 30, 0, 30, tzinfo=dt.timezone.utc)


def _h(link, ciudad, es_local, horas, interes=70, outlet="El Universo"):
    fecha = (AHORA - dt.timedelta(hours=horas)).isoformat()
    return {"titular": "Historia " + link, "ciudad": ciudad, "es_local": es_local, "interes": interes,
            "n_outlets": 1, "hours": horas, "temas": [],
            "fuentes": [{"link": link, "date": fecha, "outlet": outlet, "title": "Historia " + link}]}


class TestAlcanceEcuador(unittest.TestCase):
    def test_un_solo_medio_tambien_en_ecuador_y_guayaquil_primero(self):
        st = [_h("quito-1", "Quito", True, 8), _h("gye-1", "Guayaquil", True, 8), _h("mundo", "", False, 8)]
        r = senales.ciclo_senales(st, estado_path=os.path.join(tempfile.mkdtemp(), "e.json"), ahora=AHORA)
        ids = [s["historia_id"] for s in r["senales"] if s["tipo"] == "un_solo_medio"]
        self.assertEqual(ids, ["gye-1", "quito-1"])
        self.assertEqual([s["ambito"] for s in r["senales"] if s["tipo"] == "un_solo_medio"],
                         ["guayaquil", "ecuador"])


class TestCicloPersiste(unittest.TestCase):
    def test_escribe_estado_y_se_puede_releer(self):
        ruta = os.path.join(tempfile.mkdtemp(), "senales_estado.json")
        st = [_h("gye-2", "Guayaquil", True, 6)]
        senales.ciclo_senales(st, estado_path=ruta, ahora=AHORA)
        self.assertTrue(os.path.exists(ruta))
        activas = senales.activas(estado_path=ruta)
        self.assertEqual(len(activas), 1)
        # una segunda vuelta con lo mismo no duplica
        senales.ciclo_senales(st, estado_path=ruta, ahora=AHORA)
        self.assertEqual(len(senales.activas(estado_path=ruta)), 1)


class TestDatosReales(unittest.TestCase):
    def test_data_json_real_da_al_menos_una_senal(self):
        d = json.load(open(os.path.join(AQUI, "data.json"), encoding="utf-8"))
        ruta = os.path.join(tempfile.mkdtemp(), "e.json")
        gen = dt.datetime.fromisoformat(d.get("generado") or "2026-09-30T00:31:21+00:00")
        r = senales.ciclo_senales(d["historias"], demand=d.get("demanda_tema") or {}, estado_path=ruta, ahora=gen)
        self.assertGreaterEqual(len(r["senales"]), 1)


class TestConexionMonitor(unittest.TestCase):
    def test_monitor_importa_senales_y_arranca_hilo(self):
        self.assertIsNotNone(monitor.senales)
        src = open(os.path.join(AQUI, "monitor.py"), encoding="utf-8").read()
        self.assertIn("threading.Thread(target=senales_loop", src)

    def test_payload_trae_senales(self):
        ruta = os.path.join(tempfile.mkdtemp(), "e.json")
        senales.ciclo_senales([_h("gye-3", "Guayaquil", True, 6)], estado_path=ruta, ahora=AHORA)
        orig = senales.ESTADO_PATH
        senales.ESTADO_PATH = ruta
        try:
            p = monitor.senales_para_dashboard()
        finally:
            senales.ESTADO_PATH = orig
        self.assertEqual(len(p["senales"]), 1)
        self.assertIn("estado_senales", p)


if __name__ == "__main__":
    unittest.main()
