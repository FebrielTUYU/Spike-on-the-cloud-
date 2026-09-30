# -*- coding: utf-8 -*-
"""
Problema 1 (2026-09-24): "noticias repetidas entre medios y entre corridas".

Reproduce el fallo original con datos reales (ver CLAUDE.md, diagnostico con
data.json en vivo: 'Circulaba con placas adulteradas...' vs 'Carro debia
41.000 en multas...') y confirma el arreglo: agrupar_con_memoria() compara
cada nota contra las historias YA EXISTENTES de historias_registro.json
(ultimas 72h), no solo contra las de la misma corrida -- y una tercera nota
con informacion nueva sobre el MISMO hecho aparece como "Actualizacion"
dentro de la misma tarjeta en vez de crear una nueva.

No golpea internet ni Ollama (embed_disponible() no se llama aca -- eso lo
prueba test_problema1_embeddings.py aparte, marcado para saltarse si Ollama
no esta disponible). Corre con:  python test_problema1_memoria.py
"""
import datetime as dt
import os
import tempfile
import unittest

import monitor


def _art(outlet, title, summary="", horas_atras=0, link=None):
    return {
        "outlet": outlet, "seccion": "auto", "title": title,
        "link": link or ("https://%s/%s" % (outlet, abs(hash(title)))),
        "date": monitor.now_utc() - dt.timedelta(hours=horas_atras),
        "summary": summary, "image": "", "ciudad_feed": "",
    }


class _RegistroAislado(unittest.TestCase):
    """Cada prueba usa su PROPIO historias_registro.json temporal -- nunca
    toca el registro real de Fernando."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_path = monitor.REGISTRO_PATH
        monitor.REGISTRO_PATH = os.path.join(self._tmp, "historias_registro.json")

    def tearDown(self):
        monitor.REGISTRO_PATH = self._orig_path


class TestMismoHechoEntreCorridas(_RegistroAislado):
    def test_dos_medios_en_corridas_distintas_se_unen_en_una_sola_tarjeta(self):
        """Caso real (data.json, 2026-09-24): El Universo (Guayaquil) y
        Expreso cubrieron la MISMA multa de transito con titulares que NO
        comparten nombre propio (solape de palabras 0.23, entre los dos
        umbrales) -- el hecho en comun es la CIFRA de la multa. Antes del
        arreglo, si un medio publicaba en una pasada y el otro en la
        siguiente (una vez que el primero salio de la ventana RSS de su
        feed), cluster() jamas los veia juntos: dos tarjetas de un solo
        medio cada una, para siempre."""
        # Corrida 1: solo El Universo trae la nota.
        pase1 = [_art("El Universo (Guayaquil)",
                       "Circulaba con placas adulteradas y acumulaba $ 41.070 en multas: "
                       "la ATM retuvo el vehiculo",
                       link="https://eluniverso.com/atm-multa-1")]
        stories1 = monitor.agrupar_con_memoria(pase1)
        self.assertEqual(len(stories1), 1)
        self.assertEqual(stories1[0]["n_outlets"], 1)

        # Corrida 2 (pasada distinta -- el articulo de El Universo YA NO
        # esta en 'articles', como pasaria si su feed lo roto fuera de la
        # ventana): Expreso publica la MISMA multa con otro angulo.
        pase2 = [_art("Expreso",
                       "Carro debia 41.000 en multas por carril de Metrovia: ATM lo "
                       "retiene por llevar placas adulteradas",
                       link="https://expreso.ec/atm-multa-2")]
        stories2 = monitor.agrupar_con_memoria(pase2)

        self.assertEqual(len(stories2), 1,
                          "las dos notas de la misma multa terminaron en tarjetas separadas")
        self.assertEqual(stories2[0]["n_outlets"], 2,
                          "la segunda corrida no sumo el medio nuevo a la historia existente")
        outlets = set(stories2[0]["outlets"])
        self.assertEqual(outlets, {"El Universo (Guayaquil)", "Expreso"})

    def test_tercera_nota_con_novedad_aparece_como_actualizacion_no_tarjeta_nueva(self):
        """Una tercera nota sobre el MISMO hecho, pero con una cifra nueva
        (indicio de 'informacion nueva': reaccion/consecuencia), debe quedar
        como 'Actualizacion' dentro de la misma tarjeta -- nunca crear una
        cuarta/segunda tarjeta separada."""
        pase1 = [_art("El Universo (Guayaquil)",
                       "Circulaba con placas adulteradas y acumulaba $ 41.070 en multas: "
                       "la ATM retuvo el vehiculo",
                       link="https://eluniverso.com/atm-multa-1")]
        monitor.agrupar_con_memoria(pase1)

        pase2 = [_art("Expreso",
                       "Carro debia 41.000 en multas por carril de Metrovia: ATM lo "
                       "retiene por llevar placas adulteradas",
                       link="https://expreso.ec/atm-multa-2")]
        monitor.agrupar_con_memoria(pase2)

        # Tercera corrida: el dueno reacciona (verbo de reaccion + cifra
        # nueva, $250 de multa adicional) -- misma multa, hecho nuevo.
        pase3 = [_art("El Comercio",
                       "Dueno del carro retenido por placas adulteradas responde a la "
                       "multa de la ATM: \"pagare los 41.070 pero no los 250 adicionales\"",
                       link="https://elcomercio.com/atm-multa-3")]
        stories3 = monitor.agrupar_con_memoria(pase3)

        self.assertEqual(len(stories3), 1,
                          "la reaccion del dueno debio quedar en la MISMA tarjeta, no crear una nueva")
        s = stories3[0]
        self.assertEqual(s["n_outlets"], 3)
        self.assertTrue(s["actualizaciones"], "la reaccion con informacion nueva no quedo registrada")
        self.assertIn("responde", s["actualizaciones"][-1]["titulo"].lower())

    def test_mismo_medio_mismo_titulo_con_link_distinto_no_se_duplica(self):
        """BUG REAL encontrado verificando en vivo (reinicio de serve con
        este mismo cambio): Google News arma el link de cada articulo con un
        token que puede cambiar entre lecturas del MISMO articulo -- como el
        registro ahora persiste entre pasadas (a diferencia de cluster(),
        que partia de cero), esto se acumulaba: 'Busqueda: Guayaquil'
        aparecio 3 veces como fuente de una sola historia."""
        base = _art("Busqueda: Guayaquil", "Marea alta llegara a 4 metros en Guayaquil este jueves",
                     link="https://news.google.com/rss/articles/TOKEN1")
        monitor.agrupar_con_memoria([base])
        otro_link = _art("Busqueda: Guayaquil", "Marea alta llegara a 4 metros en Guayaquil este jueves",
                          link="https://news.google.com/rss/articles/TOKEN2-DISTINTO")
        stories = monitor.agrupar_con_memoria([otro_link])
        self.assertEqual(len(stories), 1)
        outlets_de_esta_fuente = [f["outlet"] for f in stories[0]["fuentes"] if f["outlet"] == "Busqueda: Guayaquil"]
        self.assertEqual(len(outlets_de_esta_fuente), 1,
                          "el mismo medio+titulo con link distinto se duplico en 'fuentes'")

    def test_evento_distinto_no_se_fusiona(self):
        """Dos notas SIN relacion (control negativo) deben quedar en
        tarjetas separadas -- el registro no debe fusionar todo a ciegas."""
        pase1 = [_art("El Universo", "Gobierno de Ecuador anuncia subsidio focalizado al "
                                      "diesel para transporte pesado",
                       link="https://eluniverso.com/subsidio-diesel")]
        monitor.agrupar_con_memoria(pase1)
        pase2 = [_art("Extra", "Ecuador suma un nuevo dia de descanso: calendario de "
                                "feriados de 2026",
                       link="https://extra.ec/feriados-2026")]
        stories2 = monitor.agrupar_con_memoria(pase2)
        self.assertEqual(len(stories2), 2, "se fusionaron dos historias sin relacion real")


@unittest.skipUnless(monitor.ia is not None and monitor.ia.embed_disponible(),
                      "requiere Ollama + nomic-embed-text corriendo (embed_disponible() dio False)")
class TestReconciliacionPorEmbeddings(_RegistroAislado):
    """Cuando el parafraseo es tan fuerte que NO comparte ninguna palabra de
    contenido (sim_tok=0, el hilo rapido no tiene con que unirlas), la unica
    señal que queda es semantica -- exactamente el caso que pide el
    enunciado original ('dos medios cuentan lo mismo con palabras
    distintas'). agrupar_con_memoria() (hilo rapido, sin Ollama) NO debe
    unirlas todavia; _embed_pendientes_registro() (hilo trabajador, con
    Ollama REAL en esta PC) si debe reconciliarlas en la siguiente pasada."""

    def test_parafraseo_extremo_se_reconcilia_recien_con_embeddings_del_trabajador(self):
        pase1 = [_art("El Universo (Guayaquil)",
                       "Circulaba con placas adulteradas y acumulaba $ 41.070 en multas: "
                       "la ATM retuvo el vehiculo",
                       link="https://eluniverso.com/atm-multa-1")]
        stories1 = monitor.agrupar_con_memoria(pase1)
        self.assertEqual(len(stories1), 1)

        # Reescrita a proposito SIN ninguna palabra de contenido en comun
        # con el titular de arriba (confirmado: 0 tokens compartidos) --
        # solo la cifra de la multa sigue igual.
        pase2 = [_art("Expreso",
                       "Multa de $41.070 termina con un automotor inmovilizado tras "
                       "verificarse identificadores falsificados en circulacion",
                       link="https://expreso.ec/atm-multa-parafraseada")]
        stories2 = monitor.agrupar_con_memoria(pase2)
        self.assertEqual(len(stories2), 2,
                          "el hilo rapido (sin Ollama) fusiono un parafraseo que no deberia poder detectar")

        # Hilo trabajador: calcula embeddings + reconcilia.
        status = monitor._embed_pendientes_registro()
        self.assertIn("embeddings", status)

        registro = monitor._cargar_registro()
        self.assertEqual(len(registro), 1,
                          "el trabajador no fusiono el parafraseo aunque comparten la cifra y el sentido")
        entry = next(iter(registro.values()))
        self.assertEqual(len(entry["fuentes"]), 2)
        outlets = {f["outlet"] for f in entry["fuentes"]}
        self.assertEqual(outlets, {"El Universo (Guayaquil)", "Expreso"})


class TestNombresPropiosEspanolNoSeVacian(unittest.TestCase):
    def test_titular_espanol_con_dos_nombres_propios_no_se_trata_como_title_case_ingles(self):
        """BUG REAL corregido (Problema 1): 'Lavinia Valbonesi asumira la
        presidencia de ALMA en Nueva York' perdia TODA su senal de nombre
        propio porque el detector de Title Case ingles (umbral viejo >0.5)
        se disparaba con un nombre completo + 'Nueva York' (4 de 7 palabras
        capitalizadas, 57%)."""
        nom = monitor._nombres_propios("Lavinia Valbonesi asumira la presidencia de ALMA en Nueva York")
        self.assertIn("lavinia", nom)
        self.assertIn("valbonesi", nom)

    def test_title_case_ingles_autentico_sigue_excluido(self):
        """No debe romper el caso ya documentado: titulares en ingles con
        CASI todas las palabras capitalizadas siguen sin dar nombres
        propios de fiar."""
        nom = monitor._nombres_propios("5 Takeaways From Ari Emanuel's Memoir")
        self.assertEqual(nom, set())


if __name__ == "__main__":
    unittest.main()
