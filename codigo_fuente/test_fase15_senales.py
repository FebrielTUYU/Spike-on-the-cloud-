from datetime import datetime, timedelta, timezone
import unittest

import senales


UTC = timezone.utc
AHORA = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def iso(dt):
    return dt.isoformat()


def historia(link, fecha, *, ciudad="Guayaquil", interes=75, titulo="Caso de prueba"):
    return {
        "link": link,
        "titular": titulo,
        "ciudad": ciudad,
        "es_local": ciudad == "Guayaquil",
        "interes": interes,
        "fuentes": [{"link": link, "date": iso(fecha), "title": titulo, "summary": "Resumen sintético"}],
    }


def entrada_registro(ciudad="Guayaquil", edades_horas=(50, 40, 30)):
    fuentes = [
        {"link": f"https://medio-{i}.test/nota", "date": iso(AHORA - timedelta(hours=h)),
         "title": f"Fuente {i}: operativo municipal", "summary": "El Municipio informó el operativo"}
        for i, h in enumerate(edades_horas, 1)
    ]
    return {"eid": "hist-reg-1", "ciudad": ciudad, "fuentes": fuentes,
            "ultimo": iso(AHORA - timedelta(hours=edades_horas[-1]))}


class DetectarAceleraTests(unittest.TestCase):
    def test_aceleracion_real_muestra_cantidad_observada(self):
        # Una fuente inicial hace 21 h y cinco incorporadas durante la última hora.
        fuentes = [{"link": "hist-acelera", "date": iso(AHORA - timedelta(hours=21))}]
        fuentes += [{"link": f"nueva-{i}", "date": iso(AHORA - timedelta(minutes=10 * i))} for i in range(5)]
        story = {"titular": "Operativo municipal", "ciudad": "Guayaquil",
                 "interes": 80, "fuentes": fuentes}
        resultado = senales.detectar_acelera([story], ahora=AHORA)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["tipo"], "acelera")
        self.assertIn("hist-acelera", resultado[0]["historia_id"])
        self.assertRegex(resultado[0]["por_que_ahora"], r"5")

    def test_ritmo_constante_no_señala(self):
        fuentes = [{"link": f"f-{i}", "date": iso(AHORA - timedelta(hours=2 * i))} for i in range(11)]
        story = {"link": "constante", "ciudad": "Guayaquil", "fuentes": fuentes}
        self.assertEqual(senales.detectar_acelera([story], ahora=AHORA), [])

    def test_aceleracion_fuera_de_guayaquil_no_señala(self):
        fuentes = [{"link": "base", "date": iso(AHORA - timedelta(hours=21))}]
        fuentes += [{"link": f"nueva-{i}", "date": iso(AHORA - timedelta(minutes=10 * i))} for i in range(5)]
        for ciudad in ("", "Quito"):
            with self.subTest(ciudad=ciudad):
                self.assertEqual(senales.detectar_acelera([{"link": "otra", "ciudad": ciudad,
                    "fuentes": fuentes}], ahora=AHORA), [])


class DetectarUnSoloMedioTests(unittest.TestCase):
    def _story(self, horas, interes=80, ciudad="Guayaquil"):
        return {"link": f"un-medio-{horas}", "titular": "Investigación local", "ciudad": ciudad,
                "interes": interes, "fuentes": [{"link": "medio-a", "date": iso(AHORA - timedelta(hours=horas))}]}

    def test_una_fuente_aislada_en_rango_y_con_interes_alto(self):
        out = senales.detectar_un_solo_medio([self._story(10)], ahora=AHORA)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["tipo"], "un_solo_medio")
        self.assertRegex(out[0]["por_que_ahora"], r"10")
        self.assertRegex(out[0]["por_que_ahora"], r"80")

    def test_fuera_de_ventana_o_bajo_interes_no_señala(self):
        for story in (self._story(1), self._story(70), self._story(10, interes=40)):
            with self.subTest(story=story):
                self.assertEqual(senales.detectar_un_solo_medio([story], ahora=AHORA), [])

    def test_otro_ambito_no_señala(self):
        self.assertEqual(senales.detectar_un_solo_medio([self._story(10, ciudad="Quito")], ahora=AHORA), [])


class DetectarSinResolverTests(unittest.TestCase):
    def test_silencio_significativo_sin_desenlace_confirmado_señala(self):
        entry = entrada_registro()
        out = senales.detectar_sin_resolver([entry], ia_fn=lambda material: {"hubo_desenlace": False, "cita": None}, ahora=AHORA)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["tipo"], "sin_resolver")

    def test_cita_literal_confirma_desenlace_y_suprime_señal(self):
        entry = entrada_registro()
        out = senales.detectar_sin_resolver([entry], ia_fn=lambda material: {
            "hubo_desenlace": True, "cita": "El Municipio informó el operativo"}, ahora=AHORA)
        self.assertEqual(out, [])

    def test_cita_inventada_no_puede_suprimir_señal(self):
        entry = entrada_registro()
        out = senales.detectar_sin_resolver([entry], ia_fn=lambda material: {
            "hubo_desenlace": True, "cita": "La ciudad anunció una solución definitiva"}, ahora=AHORA)
        self.assertEqual(len(out), 1)

    def test_sin_ia_una_fuente_o_fuente_reciente(self):
        vieja_una = entrada_registro(edades_horas=(30,))
        reciente = entrada_registro(edades_horas=(50, 40, 2))
        for entries in ([vieja_una], [reciente]):
            with self.subTest(entries=entries):
                self.assertEqual(senales.detectar_sin_resolver(entries, ahora=AHORA), [])
        # La especificación afirma que sin ia_fn la señal existe; se comprueba aparte.
        self.assertEqual(len(senales.detectar_sin_resolver([entrada_registro()], ahora=AHORA)), 1)

    def test_otro_ambito_no_señala(self):
        entry = entrada_registro(ciudad="Quito")
        self.assertEqual(senales.detectar_sin_resolver([entry], ahora=AHORA), [])


class DetectarActorRepetidoTests(unittest.TestCase):
    def _registro(self, fechas):
        return {"ana perez": [{"nombre": "Ana Pérez", "fecha": iso(AHORA - timedelta(days=d)),
                               "titular": f"Nota {i}", "link": link}
                              for i, (d, link) in enumerate(fechas, 1)]}

    def test_aparece_en_dos_historias_distintas_de_guayaquil(self):
        stories = [historia("https://a.test/1", AHORA - timedelta(hours=2)),
                   historia("https://b.test/2", AHORA - timedelta(hours=1))]
        out = senales.detectar_actor_repetido(self._registro([(1, "https://a.test/1"), (2, "https://b.test/2")]), stories, ahora=AHORA)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["tipo"], "actor_repetido")

    def test_mismo_link_no_cuenta_como_dos_historias(self):
        link = "https://a.test/1"
        stories = [historia(link, AHORA - timedelta(hours=2)), historia(link, AHORA - timedelta(hours=1))]
        reg = self._registro([(1, link), (2, link)])
        self.assertEqual(senales.detectar_actor_repetido(reg, stories, ahora=AHORA), [])

    def test_aparicion_fuera_de_guayaquil_no_cuenta(self):
        stories = [historia("https://a.test/1", AHORA - timedelta(hours=2)),
                   historia("https://b.test/2", AHORA - timedelta(hours=1), ciudad="Quito")]
        reg = self._registro([(1, "https://a.test/1"), (2, "https://b.test/2")])
        self.assertEqual(senales.detectar_actor_repetido(reg, stories, ahora=AHORA), [])

    def test_aparicion_fuera_de_ventana_no_cuenta(self):
        stories = [historia("https://a.test/1", AHORA - timedelta(hours=2)),
                   historia("https://b.test/2", AHORA - timedelta(hours=1))]
        reg = self._registro([(1, "https://a.test/1"), (10, "https://b.test/2")])
        self.assertEqual(senales.detectar_actor_repetido(reg, stories, dias=7, ahora=AHORA), [])

    def test_historias_no_guayaquil_no_generan_actor_repetido(self):
        cities = [historia("https://a.test/1", AHORA, ciudad="Quito"), historia("https://b.test/2", AHORA, ciudad="Quito")]
        self.assertEqual(senales.detectar_actor_repetido(self._registro([(1, "https://a.test/1"), (2, "https://b.test/2")]), cities, ahora=AHORA), [])


class PrimerPasoTests(unittest.TestCase):
    MATERIAL = "El Municipio informó el operativo de seguridad en el centro de Guayaquil."

    def test_texto_con_base_en_material_se_acepta_sin_modificar(self):
        respuesta = "Verifica qué alcance tuvo el operativo de seguridad en el centro."
        self.assertEqual(senales.generar_primer_paso({"tipo": "sin_resolver"}, self.MATERIAL,
                         lambda prompt: respuesta), respuesta)

    def test_texto_generico_o_sin_respuesta_se_descarta(self):
        for fn in (lambda prompt: "Investiga más y consulta fuentes confiables.", lambda prompt: None):
            with self.subTest(fn=fn):
                self.assertIsNone(senales.generar_primer_paso({"tipo": "sin_resolver"}, self.MATERIAL, fn))


class DeduplicarTests(unittest.TestCase):
    def test_clave_repetida_con_mismo_motivo_se_filtra(self):
        candidate = {"clave_dedupe": "acelera:hist-1", "por_que_ahora": "3 fuentes nuevas en la última hora"}
        vistas = {candidate["clave_dedupe"]: candidate["por_que_ahora"]}
        self.assertEqual(senales.deduplicar([candidate], vistas), [])

    def test_misma_clave_con_cambio_numerico_significativo_se_conserva(self):
        candidate = {"clave_dedupe": "acelera:hist-1", "por_que_ahora": "12 fuentes nuevas en la última hora"}
        vistas = {candidate["clave_dedupe"]: "3 fuentes nuevas en la última hora"}
        self.assertEqual(senales.deduplicar([candidate], vistas), [candidate])

    def test_clave_nueva_pasa_y_cambio_de_texto_sin_numero_no_es_significativo(self):
        new = {"clave_dedupe": "nueva", "por_que_ahora": "5 fuentes nuevas"}
        self.assertEqual(senales.deduplicar([new], {}), [new])
        self.assertFalse(senales._cambio_significativo("5 fuentes en la última hora", "5 fuentes durante la hora reciente"))

    def test_mismo_numero_no_es_cambio_significativo(self):
        self.assertFalse(senales._cambio_significativo("5 fuentes nuevas", "5 fuentes adicionales"))


if __name__ == "__main__":
    unittest.main()
