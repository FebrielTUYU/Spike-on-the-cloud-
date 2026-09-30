# -*- coding: utf-8 -*-
"""
Fase 9, Problema A -- agrupamiento con datos reales de la corrida 2026-09-25.

Dos baterias, con los titulares TEXTUALES reportados por Fernando/Cowork
(ver CLAUDE.md, seccion "Fase 9"):

- A2 (deben unirse): duplicados reales que quedaron en tarjetas separadas.
- A3 (NO deben unirse): fusiones erroneas -- mismo lugar/plantilla, hechos
  sin relacion.

No golpea internet ni Ollama. Corre con:  python test_fase9_agrupamiento.py
"""
import datetime as dt
import os
import tempfile
import unittest

import monitor

try:
    import ia
except Exception:
    ia = None


def _art(outlet, title, summary="", horas_atras=0, link=None):
    return {
        "outlet": outlet, "seccion": "auto", "title": title,
        "link": link or ("https://%s/%s" % (outlet, abs(hash(title)))),
        "date": monitor.now_utc() - dt.timedelta(hours=horas_atras),
        "summary": summary, "image": "", "ciudad_feed": "",
    }


class _RegistroAislado(unittest.TestCase):
    """Cada prueba usa su PROPIO historias_registro.json temporal -- nunca
    toca el registro real de Fernando (mismo patron que test_problema1_memoria.py)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_path = monitor.REGISTRO_PATH
        monitor.REGISTRO_PATH = os.path.join(self._tmp, "historias_registro.json")

    def tearDown(self):
        monitor.REGISTRO_PATH = self._orig_path

    def _pasadas(self, *titulos_por_pasada):
        """Simula N corridas separadas (como pasaria si cada medio publica en
        una pasada distinta del feed): cada elemento de titulos_por_pasada es
        (outlet, titulo[, resumen])."""
        stories = None
        for outlet_titulo in titulos_por_pasada:
            outlet, titulo = outlet_titulo[0], outlet_titulo[1]
            resumen = outlet_titulo[2] if len(outlet_titulo) > 2 else ""
            stories = monitor.agrupar_con_memoria([_art(outlet, titulo, resumen)])
        return monitor.agrupar_con_memoria([])  # relee el registro completo, sin agregar nada nuevo


class TestA2DuplicadosQueDebenUnirse(_RegistroAislado):
    @unittest.skipUnless(ia and ia.embed_disponible(),
                          "requiere Ollama + nomic-embed-text instalado (ver ia.embed_disponible)")
    def test_cjng_samborondon_via_embedding(self):
        """5 titulares reales del mismo operativo, redactados TAN distinto
        entre si (0.07 de Jaccard, sim nombre propio: solo comparten la
        sigla CJNG con casi cero overlap de palabras) que el hilo rapido
        (solo lexico, sin red) no los une -- exactamente el caso para el
        que existe la reconciliacion por embeddings del trabajador (A1)."""
        stories = self._pasadas(
            ("El Universo", "Tropas estadounidenses y Policía Nacional ejecutan allanamientos "
                             "en Samborondón y desarticulan presunta red vinculada al CJNG"),
            ("Extra", "Presunto cabecilla y financista vinculados al CJNG fueron capturados "
                      "en Samborondón"),
        )
        self.assertEqual(len(stories), 2,
                          "el hilo rapido (solo lexico) NO debe unirlas todavia -- eso es lo esperado")
        monitor._embed_pendientes_registro()
        stories_reconciliadas = monitor.agrupar_con_memoria([])
        self.assertEqual(len(stories_reconciliadas), 1,
                          "tras calcular embeddings, el trabajador debio reconciliar el parafraseo")

    def test_feriado_9_de_octubre_se_unen(self):
        stories = self._pasadas(
            ("Primicias", "¿El 9 de octubre es feriado nacional en Ecuador?"),
            ("Extra", "¿Habrá feriado el 9 de octubre de 2026?"),
        )
        self.assertEqual(len(stories), 1,
                          "misma pregunta de feriado, misma fecha mencionada -- debieron unirse")

    def test_biblioteca_clinica_de_libros_se_unen(self):
        stories = self._pasadas(
            ("Expreso", "Los libros rotos tienen una salida: una clínica para restaurarlos "
                        "en Guayaquil"),
            ("Municipio de Guayaquil", "La Biblioteca Municipal abrió una clínica para "
                                        "rescatar libros dañados"),
        )
        self.assertEqual(len(stories), 1,
                          "la clinica de libros de Expreso y Municipio debieron unirse")

    def test_jugador_desaparecido_localizado_queda_pendiente_caso_limite_real(self):
        """CASO LIMITE REAL, medido con Ollama real en esta sesion, NO
        resuelto: cero palabras/nombre/numero en comun (un titular usa el
        nombre legal completo, el otro lo describe como 'joven jugador del
        Deportivo Quito') -- ni la reconciliacion por embeddings alcanza:
        coseno medido = 0.617, MAS BAJO que el par de control totalmente
        NO relacionado 'jugador vs precio del dolar' (0.607-0.527) y muy por
        debajo del umbral (0.75). El modelo de embeddings no conecta
        'Pablo Emilio Rios Maza' con 'jugador del Deportivo Quito' -- haria
        falta una base de conocimiento (que jugadores pertenecen a que
        equipo) que este proyecto no tiene. Ademas, como ninguno de los dos
        titulares comparte nombre/numero, ni siquiera pasa el gate de
        'comparten entidad' que exige _embed_pendientes_registro() antes de
        mirar el coseno -- documentado como pendiente real, no resuelto en
        esta fase (ver CLAUDE.md, seccion Fase 9)."""
        stories = self._pasadas(
            ("Extra", "Pablo Emilio Ríos Maza fue localizado tras reporte de desaparición"),
            ("Primicias", "Localizan a joven jugador del Deportivo Quito que estaba desaparecido"),
        )
        self.assertEqual(len(stories), 2, "el hilo rapido no debe unirlas -- cero overlap lexico")
        if ia and ia.embed_disponible():
            monitor._embed_pendientes_registro()
            stories_tras_embed = monitor.agrupar_con_memoria([])
            self.assertEqual(len(stories_tras_embed), 2,
                              "documentado: este caso NO se resuelve ni con embeddings (ver docstring)")


class TestA3FusionesErroneasQueNoDebenUnirse(_RegistroAislado):
    def test_santa_elena_taxi_no_se_une_con_bus_accidentado(self):
        stories = self._pasadas(
            ("Extra", "Santa Elena: lo que se conoce del crimen de un taxista"),
            ("El Universo", "Bus con trabajadores cayó de un puente en la vía a la Costa, "
                             "en Santa Elena"),
        )
        self.assertEqual(len(stories), 2,
                          "un crimen y un accidente de bus SOLO comparten el lugar -- no son el mismo hecho")

    def test_cortes_luz_gye_no_se_une_con_cortes_agua_duran(self):
        stories = self._pasadas(
            ("Primicias", "Usuarios reportan cortes de luz en el norte de Guayaquil"),
            ("Extra", "Ciudadanos en Durán reportan cortes de agua"),
        )
        self.assertEqual(len(stories), 2, "cortes de luz y cortes de agua son hechos distintos")

    def test_juchitan_cjng_no_se_une_con_caso_blindado(self):
        stories = self._pasadas(
            ("Reuters", "Juez impone prisión preventiva a Miguel Sánchez, alcalde de Juchitán, "
                        "vinculado al CJNG"),
            ("El Universo", "Caso Blindado: Fiscalía solicita prisión preventiva para los procesados"),
        )
        self.assertEqual(len(stories), 2,
                          "un alcalde mexicano procesado y un caso ecuatoriano distinto no son el mismo hecho")

    def test_trump_xi_armonia_no_se_une_con_vetar_periodistas(self):
        stories = self._pasadas(
            ("NYT", "Trump y Xi Jinping proclaman la armonía entre Estados Unidos y China"),
            ("AP", "Casa Blanca amenaza con vetar a periodistas que cubren la Casa Blanca"),
        )
        self.assertEqual(len(stories), 2, "una cumbre y una amenaza a la prensa son hechos distintos")

    def test_portadas_y_noticieros_son_basura_antes_de_agrupar(self):
        """Los items 'indice del dia' nunca deberian llegar al agrupamiento --
        is_junk() los descarta en parse_feed(), antes de cluster()/registro."""
        self.assertTrue(monitor.is_junk("Portada 25 septiembre 2026", "", ""))
        self.assertTrue(monitor.is_junk(
            "Noticias, jueves 24 de septiembre del 2026 | 24 Horas", "", ""))
        self.assertTrue(monitor.is_junk(
            "Últimas noticias | 25 septiembre 2026 - Mediodía", "", ""))
        # no debe volverse tan agresivo que descarte una nota real de lluvias
        self.assertFalse(monitor.is_junk(
            "Guayaquil enfrenta el septiembre más lluvioso de los últimos años", "", ""))

    def test_pronosticos_misma_ciudad_distinta_fecha_no_se_unen(self):
        """Boletin con plantilla (Problema A3, pendiente de Fase 8): dos
        pronosticos de la MISMA ciudad, pero de dias distintos mencionados
        explicitamente en el titular, no son la misma historia."""
        stories = self._pasadas(
            ("Infobae", "Pronóstico del clima en Guayaquil este 24 de septiembre: "
                        "temperatura, lluvias y viento"),
            ("Infobae", "Pronóstico del clima en Guayaquil este 25 de septiembre: "
                        "temperatura, lluvias y viento"),
        )
        self.assertEqual(len(stories), 2,
                          "mismo formato, mismo lugar, pero dias DISTINTOS -- no es el mismo hecho")

    def test_pronosticos_distinta_ciudad_no_se_unen(self):
        stories = self._pasadas(
            ("Infobae", "Pronóstico del clima en Quito este 25 de septiembre: "
                        "temperatura, lluvias y viento"),
            ("Infobae", "Pronóstico del clima en Guayaquil este 25 de septiembre: "
                        "temperatura, lluvias y viento"),
        )
        self.assertEqual(len(stories), 2, "ciudades distintas -- no es el mismo hecho")


if __name__ == "__main__":
    unittest.main(verbosity=2)
