# -*- coding: utf-8 -*-
"""
Fase 24, Parte E -- contraste por afirmacion. Sin red ni IA.
Caso de aceptacion: el par del poste.
  - "Poste de energia ... provoco el retraso de las obras en La Alborada, segun
    el Municipio de Guayaquil" -> version unica del Municipio; falta la de CNEL.
  - "Retiro de poste permitira renovar el sistema sanitario" -> respaldada por
    medios que no la atribuyen al Municipio; el Municipio no cuenta como medio.
"""
import unittest

import contraste as C

MUNI = {"Municipio de Guayaquil"}


def _f(outlet, title, link=None):
    return {"outlet": outlet, "title": title, "link": link or outlet}


class TestPoste(unittest.TestCase):
    def test_declaracion_del_municipio_es_version_unica_y_falta_cnel(self):
        t = ("Poste de energía sobre línea de estructura subterránea provocó el retraso de las obras en La Alborada, "
             "según el Municipio de Guayaquil")
        h = {"titular": t, "tipo": "declaracion", "tipo_quien": "Municipio de Guayaquil",
             "fuentes": [_f("El Universo", t), _f("El Universo (Guayaquil)", t)]}
        r = C.evaluar_afirmacion(h, institucionales=MUNI, local=True)
        self.assertEqual(r["estado"], "version_unica")
        self.assertEqual(r["falta"], ["CNEL"])
        self.assertIn("Municipio de Guayaquil", r["texto"])
        self.assertEqual([c["tipo"] for c in r["citas"]], ["repite"])  # El Universo y su seccion: un solo medio

    def test_accion_respaldada_sin_contar_al_municipio(self):
        h = {"titular": "Retiro de poste permitirá renovar el sistema sanitario en la avenida Rodolfo Baquerizo Nazur",
             "tipo": "accion", "tipo_quien": "",
             "fuentes": [_f("Municipio de Guayaquil", "Renovación del sistema sanitario en la avenida Rodolfo Baquerizo"),
                         _f("Extra", "Retiran poste que frenaba obra de alcantarillado en la Alborada"),
                         _f("Expreso", "Obra sanitaria avanza tras el retiro de un poste en el norte")]}
        r = C.evaluar_afirmacion(h, institucionales=MUNI, local=True)
        self.assertEqual(r["estado"], "respaldada")
        tipos = {c["fuente"]: c["tipo"] for c in r["citas"]}
        self.assertEqual(tipos["Municipio de Guayaquil"], "institucion")
        self.assertEqual(r["confirman"], 1)  # dos medios: el primero no se confirma a si mismo


class TestCircularidad(unittest.TestCase):
    def test_solo_la_institucion_es_version_unica(self):
        h = {"titular": "Municipio inaugura nueva cancha en Pascuales", "tipo": "accion",
             "fuentes": [_f("Municipio de Guayaquil", "Municipio inaugura nueva cancha en Pascuales")]}
        self.assertEqual(C.evaluar_afirmacion(h, institucionales=MUNI)["estado"], "version_unica")

    def test_medio_que_copia_el_boletin_no_confirma(self):
        b = "Municipio inaugura nueva cancha deportiva en Pascuales para jovenes del sector"
        h = {"titular": b, "tipo": "accion",
             "fuentes": [_f("Municipio de Guayaquil", b), _f("Extra", "Municipio inaugura nueva cancha deportiva en Pascuales")]}
        r = C.evaluar_afirmacion(h, institucionales=MUNI)
        self.assertEqual(r["estado"], "version_unica")
        self.assertEqual([c.get("nota") for c in r["citas"] if c["fuente"] == "Extra"], ["copia el boletin de la institucion"])

    def test_un_medio_solo_es_sin_evidencia_y_dos_respaldan(self):
        uno = {"titular": "Hombre asesinado en Pascuales", "tipo": "accion", "fuentes": [_f("Extra", "Hombre asesinado")]}
        self.assertEqual(C.evaluar_afirmacion(uno)["estado"], "sin_evidencia")
        dos = dict(uno, fuentes=[_f("Extra", "Hombre asesinado"), _f("El Universo", "Matan a un hombre en Pascuales")])
        self.assertEqual(C.evaluar_afirmacion(dos)["estado"], "respaldada")

    def test_mismo_medio_con_otro_nombre_no_suma(self):
        h = {"titular": "Corte de agua en el sur", "tipo": "accion",
             "fuentes": [_f("Expreso", "Corte de agua en el sur"), _f("expreso.ec", "Corte de agua en el sur hoy")]}
        self.assertEqual(C.evaluar_afirmacion(h)["estado"], "sin_evidencia")

    def test_cifras_distintas_contradicen_con_las_dos_citas(self):
        h = {"titular": "Operativo en Socio Vivienda", "tipo": "accion",
             "fuentes": [_f("El Universo", "Operativo en Socio Vivienda deja 12 detenidos por extorsion"),
                         _f("Vistazo", "Operativo en Socio Vivienda deja 7 detenidos por extorsion")]}
        r = C.evaluar_afirmacion(h)
        self.assertEqual(r["estado"], "contradicha")
        self.assertEqual(len(r["citas"]), 2)


class TestEvidenciaExtra(unittest.TestCase):
    def test_comunidad_exige_tres_palabras_especificas(self):
        h = {"titular": "Acumulacion de desechos en la avenida 25 de Julio: recuperan espacio publico", "tipo": "accion",
             "fuentes": [_f("Expreso", "Acumulacion de desechos en la avenida 25 de Julio")]}
        posts = [{"autor": "@vecina", "texto": "Recuperan el espacio publico lleno de desechos y acumulacion de basura en la 25 de Julio"},
                 {"autor": "otro", "texto": "Robo en Guayaquil este martes 30 de septiembre en el municipio"}]
        r = C.evaluar_afirmacion(h, comunidad_posts=posts)
        com = [c for c in r["citas"] if c["tipo"] == "comunidad"]
        self.assertEqual([c["fuente"] for c in com], ["@vecina"])
        self.assertIn("Indicios", r["texto"])

    def test_falta_solo_en_guayaquil(self):
        h = {"titular": "Corte de agua potable afecta a 40 barrios", "tipo": "accion",
             "fuentes": [_f("El Comercio", "Corte de agua potable afecta a 40 barrios del sur de Quito")]}
        self.assertEqual(C.evaluar_afirmacion(h, local=False)["falta"], [])
        self.assertEqual(C.evaluar_afirmacion(h, local=True)["falta"], ["Interagua / EMAPAG"])

    def test_la_parte_que_encabeza_el_titular_ya_esta(self):
        h = {"titular": "ATM multa a bus que se paso el semaforo en rojo en Urdesa", "tipo": "accion",
             "fuentes": [_f("Expreso", "ATM multa a bus")]}
        self.assertEqual(C.evaluar_afirmacion(h, local=True)["falta"], [])


if __name__ == "__main__":
    unittest.main()
