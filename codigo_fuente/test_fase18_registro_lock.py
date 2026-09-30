# -*- coding: utf-8 -*-
"""
Fase 18, P0-1 -- carrera de escritura en historias_registro.json.

Escrita DESDE LA ESPECIFICACION (antes de tocar monitor.py): run_fast
(agrupar_con_memoria) y el trabajador (_embed_pendientes_registro) cargaban y
guardaban el mismo archivo sin lock -- ganaba el ultimo en escribir y borraba
lo del otro. Medido en el registro real: 190 llamadas a gemini-embedding-001 en
un dia, pero la cobertura de vectores no subia.

Prueba: dos hilos simulados, uno agrega articulos y otro agrega embeddings
(con una llamada "lenta" a la IA, como Gemini real). Al final tienen que
estar las DOS cosas. No golpea red: ia.embed se reemplaza.
"""
import datetime as dt
import os
import tempfile
import threading
import time
import unittest

import monitor


def _art(outlet, title, horas_atras=0):
    return {
        "outlet": outlet, "seccion": "auto", "title": title,
        "link": "https://%s/%s" % (outlet.replace(" ", ""), abs(hash(title))),
        "date": monitor.now_utc() - dt.timedelta(hours=horas_atras),
        "summary": "", "image": "", "ciudad_feed": "",
    }


class _IaFalsa:
    """Sustituto de ia.py: embed lento y determinista, sin red."""
    EMBED_MODEL = "falso-embed"
    EMBED_MODEL_MULTILINGUE = "falso-embed"

    def __init__(self, espera=0.0, al_primer_llamado=None):
        self.espera = espera
        self.llamados = 0
        self.al_primer_llamado = al_primer_llamado

    def embed_disponible(self, modelo=None):
        return True

    def embed(self, texto, timeout=30, modelo=None):
        self.llamados += 1
        if self.llamados == 1 and self.al_primer_llamado:
            self.al_primer_llamado.set()
        time.sleep(self.espera)
        # vector distinto por texto, para que no fusione nada por coseno
        h = abs(hash(texto))
        return [((h >> i) & 7) / 7.0 + 0.01 for i in range(8)]


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = (monitor.REGISTRO_PATH, monitor.ia, monitor.EMBED_MAX_NEW)
        monitor.REGISTRO_PATH = os.path.join(self._tmp, "historias_registro.json")

    def tearDown(self):
        monitor.REGISTRO_PATH, monitor.ia, monitor.EMBED_MAX_NEW = self._orig

    def _con_embedding(self):
        reg = monitor._cargar_registro()
        return sum(1 for e in reg.values() if e.get("embedding") and e.get("embedding_modelo") == "falso-embed")


TITULOS_BASE = [
    "Asamblea aprueba reforma al Codigo de la Niñez con penas de hasta 26 años",
    "Municipio de Guayaquil inaugura clinica de libros en la biblioteca",
    "ATM retiene vehiculo con placas adulteradas y multas por 41.070 dolares",
    "Interagua anuncia corte de agua en Urdesa y Kennedy para el jueves",
    "Bomberos controlan incendio de vivienda en el Guasmo sur",
    "CNEL programa mantenimiento electrico en Pascuales",
]


class TestDosHilos(_Base):
    def test_articulos_y_embeddings_sobreviven_ambos(self):
        monitor.ia = None
        monitor.agrupar_con_memoria([_art("Medio %d" % i, t, horas_atras=2) for i, t in enumerate(TITULOS_BASE)])
        self.assertEqual(len(monitor._cargar_registro()), len(TITULOS_BASE))

        empezo = threading.Event()
        monitor.ia = _IaFalsa(espera=0.3, al_primer_llamado=empezo)
        monitor.EMBED_MAX_NEW = 10

        hilo = threading.Thread(target=monitor._embed_pendientes_registro)
        hilo.start()
        self.assertTrue(empezo.wait(5))
        # Mientras el trabajador espera a la "IA", el hilo rapido publica
        # dos historias nuevas (no deberian bloquearse por la llamada lenta).
        t0 = time.time()
        monitor.agrupar_con_memoria([
            _art("Expreso", "Lluvias dejan calles anegadas en la Atarazana y Samanes"),
            _art("Extra", "Balacera en la Isla Trinitaria deja un herido"),
        ])
        bloqueo = time.time() - t0
        hilo.join(20)
        self.assertFalse(hilo.is_alive())

        reg = monitor._cargar_registro()
        titulos = {e["fundador_titulo"] for e in reg.values()}
        self.assertIn("Lluvias dejan calles anegadas en la Atarazana y Samanes", titulos,
                      "el trabajador piso las historias nuevas del hilo rapido")
        self.assertIn("Balacera en la Isla Trinitaria deja un herido", titulos)
        self.assertGreaterEqual(self._con_embedding(), len(TITULOS_BASE),
                                "el hilo rapido borro los embeddings del trabajador")
        # el hilo rapido no espera las llamadas a la IA (6 x 0.3s = 1.8s)
        self.assertLess(bloqueo, 1.5)

    def test_cobertura_sube_en_cada_pasada_y_no_vuelve_a_cero(self):
        monitor.ia = None
        monitor.agrupar_con_memoria([_art("Medio %d" % i, t, horas_atras=3) for i, t in enumerate(TITULOS_BASE)])
        monitor.ia = _IaFalsa()
        monitor.EMBED_MAX_NEW = 2
        cobertura = []
        for pasada in range(3):
            monitor._embed_pendientes_registro()
            # un run_fast entre pasadas del trabajador
            monitor.agrupar_con_memoria([_art("Nuevo %d" % pasada, "Nota distinta numero %d sobre Durán" % pasada)])
            cobertura.append(self._con_embedding())
        self.assertEqual(cobertura, [2, 4, 6])


if __name__ == "__main__":
    unittest.main()
