# -*- coding: utf-8 -*-
"""
Pruebas de la Fase 7 (2026-09-24), Pasos B-E: Asistente de casos.

No golpea Ollama (no esta corriendo de forma confiable en este entorno,
mismo criterio que test_fase5_declaraciones.py/test_evento.py): se
monkeypatchea ia._generar donde hace falta. El *wiring* completo (casos.py <->
monitor.py <-> ia.py/agente.py) tambien se probo en vivo con un servidor
real (`python monitor.py serve`) durante esta sesion, incluido el puente de
avisos (Paso D) contra datos REALES del feed (entidad "Donald Trump" en la
corrida del feed real del 2026-09-24) -- ver CLAUDE.md, seccion "Fase 7".

Cada test aisla casos.CASOS_DIR en un directorio temporal (setUp/tearDown),
mismo patron que ya usan test_fase5_declaraciones.py/test_oficial.py para
sus propios archivos, asi nunca toca la carpeta casos/ real de Fernando.

Corre con:  python test_fase7_casos.py
"""
import json
import os
import shutil
import tempfile
import unittest

import casos
import ia
import monitor as m


class _CasosAislados(unittest.TestCase):
    """Base: aisla casos.CASOS_DIR en un tmpdir por test."""

    def setUp(self):
        self._orig_dir = casos.CASOS_DIR
        self._tmp = tempfile.mkdtemp(prefix="casos_test_")
        casos.CASOS_DIR = os.path.join(self._tmp, "casos")

    def tearDown(self):
        casos.CASOS_DIR = self._orig_dir
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestCasosCRUD(_CasosAislados):
    def test_crear_y_listar(self):
        c = casos.crear_caso("Contratos de la Prefectura", "una investigacion")
        self.assertTrue(casos.existe_caso(c["id"]))
        lista = casos.listar_casos()
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["titulo"], "Contratos de la Prefectura")
        self.assertEqual(lista[0]["n_entidades"], 0)

    def test_entidades_agregar_quitar_dedup(self):
        c = casos.crear_caso("Caso X")
        casos.agregar_entidad(c["id"], "Juan Perez", "persona", ["JP", "Juanito"])
        casos.agregar_entidad(c["id"], "juan perez", "persona")  # mismo nombre, otra capitalizacion -> no duplica
        caso = casos.cargar_caso(c["id"])
        self.assertEqual(len(caso["entidades"]), 1)
        pares = dict(casos.entidades_y_alias(c["id"]))
        self.assertIn("Juan Perez", pares)
        self.assertIn("JP", pares)
        self.assertIn("Juanito", pares)
        casos.quitar_entidad(c["id"], "Juan Perez")
        self.assertEqual(casos.cargar_caso(c["id"])["entidades"], [])

    def test_entidad_en_caso_inexistente_lanza(self):
        with self.assertRaises(ValueError):
            casos.agregar_entidad("no-existe", "Alguien")

    def test_notas_round_trip(self):
        c = casos.crear_caso("Caso notas")
        n = casos.agregar_nota_caso(c["id"], "primera nota")
        casos.agregar_nota_caso(c["id"], "segunda nota")
        self.assertEqual(len(casos.cargar_notas_caso(c["id"])), 2)
        casos.borrar_nota_caso(c["id"], n["id"])
        restantes = casos.cargar_notas_caso(c["id"])
        self.assertEqual(len(restantes), 1)
        self.assertEqual(restantes[0]["texto"], "segunda nota")

    def test_nota_vacia_lanza(self):
        c = casos.crear_caso("Caso notas 2")
        with self.assertRaises(ValueError):
            casos.agregar_nota_caso(c["id"], "   ")

    def test_evidencia_round_trip(self):
        c = casos.crear_caso("Caso evidencia")
        it = casos.agregar_evidencia(c["id"], "historia", {"titular": "algo paso"}, "http://x")
        self.assertEqual(len(casos.cargar_evidencia(c["id"])), 1)
        casos.quitar_evidencia(c["id"], it["id"])
        self.assertEqual(casos.cargar_evidencia(c["id"]), [])

    def test_avisos_dedup_y_recorte(self):
        c = casos.crear_caso("Caso avisos")
        casos.agregar_aviso(c["id"], {"entidad": "X", "origen_key": "http://a", "texto": "t", "fuente": {}})
        self.assertTrue(casos.ya_avisado(c["id"], "X", "http://a"))
        self.assertFalse(casos.ya_avisado(c["id"], "X", "http://b"))
        # recorte: mas de AVISOS_MAX se corta, queda lo MAS NUEVO
        for i in range(casos.AVISOS_MAX + 10):
            casos.agregar_aviso(c["id"], {"entidad": "X", "origen_key": "http://%d" % i, "texto": "t", "fuente": {}})
        self.assertEqual(len(casos.cargar_avisos(c["id"])), casos.AVISOS_MAX)

    def test_hoy_en_casos_junta_todos_los_casos(self):
        c1 = casos.crear_caso("Caso 1")
        c2 = casos.crear_caso("Caso 2")
        casos.agregar_aviso(c1["id"], {"entidad": "A", "origen_key": "1", "texto": "t1", "fuente": {}})
        casos.agregar_aviso(c2["id"], {"entidad": "B", "origen_key": "2", "texto": "t2", "fuente": {}})
        hoy = casos.hoy_en_casos()
        self.assertEqual(len(hoy), 2)
        titulos = {a["caso_titulo"] for a in hoy}
        self.assertEqual(titulos, {"Caso 1", "Caso 2"})

    def test_tablero_sugerida_verificada_quitar(self):
        c = casos.crear_caso("Caso tablero")
        con = casos.agregar_conexion_sugerida(c["id"], "A", "B", "trabajo para", {"tipo": "chat"})
        self.assertEqual(con["estado"], "sugerida")
        t = casos.marcar_conexion(c["id"], con["id"], "verificada")
        self.assertEqual(t["conexiones"][0]["estado"], "verificada")
        with self.assertRaises(ValueError):
            casos.marcar_conexion(c["id"], con["id"], "algo_invalido")
        t2 = casos.quitar_conexion(c["id"], con["id"])
        self.assertEqual(t2["conexiones"], [])

    def test_borrar_caso(self):
        c = casos.crear_caso("Caso a borrar")
        self.assertTrue(casos.borrar_caso(c["id"]))
        self.assertFalse(casos.existe_caso(c["id"]))
        self.assertFalse(casos.borrar_caso(c["id"]))  # ya no existe, no rompe

    def test_existe_caso_rechaza_rutas_raras(self):
        # defensa basica: un id con separador de ruta no debe poder escapar de CASOS_DIR
        self.assertFalse(casos.existe_caso("../otra-carpeta"))
        self.assertFalse(casos.existe_caso(""))


class TestCasosIndice(_CasosAislados):
    def test_indexar_y_buscar_fragmentos_por_coseno(self):
        c = casos.crear_caso("Caso indice")
        casos.indexar_fragmentos(c["id"], "doc1", "archivo.txt", [
            {"posicion": 0, "texto": "sobre gatos", "embedding": [1.0, 0.0], "embedding_modelo": "modelo-prueba"},
            {"posicion": 1, "texto": "sobre perros", "embedding": [0.0, 1.0], "embedding_modelo": "modelo-prueba"},
            {"posicion": 2, "texto": "sin vector", "embedding": None},
        ])
        docs = casos.listar_documentos(c["id"])
        self.assertEqual(docs, [{"doc_id": "doc1", "nombre": "archivo.txt", "n_fragmentos": 3}])
        top = casos.buscar_fragmentos(c["id"], [1.0, 0.0], top_k=2, modelo_consulta="modelo-prueba")
        self.assertEqual(top[0]["texto"], "sobre gatos")

    def test_buscar_fragmentos_no_compara_entre_modelos_distintos(self):
        """Fase 10, parte B -- candado de espacio vectorial: un fragmento
        indexado con un modelo VIEJO (ej. nomic-embed-text, retirado con
        Ollama) nunca se compara contra una consulta del modelo ACTUAL,
        aunque la dimension coincida por casualidad."""
        c = casos.crear_caso("Caso candado de modelo")
        casos.indexar_fragmentos(c["id"], "doc1", "archivo.txt", [
            {"posicion": 0, "texto": "vector de modelo viejo", "embedding": [1.0, 0.0],
             "embedding_modelo": "modelo-viejo"},
        ])
        top = casos.buscar_fragmentos(c["id"], [1.0, 0.0], top_k=2, modelo_consulta="modelo-nuevo")
        self.assertEqual(top, [])

    def test_buscar_fragmentos_sin_indice(self):
        c = casos.crear_caso("Caso sin docs")
        self.assertEqual(casos.buscar_fragmentos(c["id"], [1.0, 0.0]), [])


class TestCasosIngesta(_CasosAislados):
    def test_extraer_texto_txt(self):
        p = os.path.join(self._tmp, "p.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("hola mundo " * 10)
        texto, motivo = casos.extraer_texto(p)
        self.assertIsNone(motivo)
        self.assertIn("hola mundo", texto)

    def test_extraer_texto_formato_no_soportado(self):
        p = os.path.join(self._tmp, "p.exe")
        with open(p, "wb") as f:
            f.write(b"\x00\x01")
        texto, motivo = casos.extraer_texto(p)
        self.assertIsNone(texto)
        self.assertIn("no soportado", motivo)

    def test_fragmentar_con_solape(self):
        texto = " ".join("palabra%d" % i for i in range(1200))
        frags = casos._fragmentar(texto, palabras_por_fragmento=500, solape=50)
        self.assertEqual(len(frags), 3)
        self.assertEqual(frags[0]["posicion"], 0)
        # el segundo fragmento debe empezar ANTES de donde termino el primero (el solape)
        primeras_palabras_frag2 = frags[1]["texto"].split()[:5]
        ultimas_palabras_frag1 = frags[0]["texto"].split()[-60:]
        self.assertTrue(any(p in ultimas_palabras_frag1 for p in primeras_palabras_frag2))

    def test_iniciar_ingesta_formato_no_soportado(self):
        c = casos.crear_caso("Caso ingesta")
        p = os.path.join(self._tmp, "malware.exe")
        with open(p, "wb") as f:
            f.write(b"\x00")
        doc_id, motivo = casos.iniciar_ingesta(c["id"], "malware.exe", p)
        self.assertIsNone(doc_id)
        self.assertIn("no soportado", motivo)

    def test_iniciar_y_procesar_ingesta_sin_ollama(self):
        """Sin ia (o con Ollama caido), procesar_ingesta debe terminar en
        'listo' igual -- con un aviso honesto de que faltan embeddings, nunca
        un error que tumbe la ingesta entera (mismo criterio que el resto del
        proyecto: mejor un hueco visible que perder el documento)."""
        orig_ia = casos.ia
        casos.ia = None
        try:
            c = casos.crear_caso("Caso ingesta 2")
            p = os.path.join(self._tmp, "doc.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("contenido de prueba " * 300)
            doc_id, motivo = casos.iniciar_ingesta(c["id"], "doc.txt", p)
            self.assertIsNotNone(doc_id)
            self.assertIsNone(motivo)
            self.assertEqual(casos.cargar_estado_docs(c["id"])[doc_id]["estado"], "en_cola")
            casos.procesar_ingesta(c["id"], doc_id, "doc.txt")
            estado = casos.cargar_estado_docs(c["id"])[doc_id]
            self.assertEqual(estado["estado"], "listo")
            self.assertGreater(estado["total"], 0)
            self.assertIsNotNone(estado["aviso"])  # avisa que faltan embeddings
            self.assertEqual(len(casos.listar_documentos(c["id"])), 1)
        finally:
            casos.ia = orig_ia

    def test_procesar_ingesta_archivo_faltante(self):
        c = casos.crear_caso("Caso ingesta 3")
        casos.actualizar_estado_doc(c["id"], "doc-fantasma", nombre="fantasma.txt", estado="en_cola")
        casos.procesar_ingesta(c["id"], "doc-fantasma", "fantasma.txt")
        self.assertEqual(casos.cargar_estado_docs(c["id"])["doc-fantasma"]["estado"], "error")


class TestMonitorPuenteAvisos(_CasosAislados):
    """Paso D: puente Dashboard -> Asistente, determinista (sin IA)."""

    def test_revisar_casos_avisos_historia_y_sercop_con_dedup(self):
        c = casos.crear_caso("Caso Acme")
        casos.agregar_entidad(c["id"], "Empresa Acme", "empresa", ["Acme"])
        stories = [
            {"titular": "La Empresa Acme firmo un contrato polemico", "resumen": "detalle",
             "fuentes": [{"link": "http://medio.com/nota1", "medio": "El Medio"}],
             "contratos": [{"ocid": "X1", "objeto": "obra vial con Acme", "link": "http://sercop/x1"}]},
            {"titular": "Noticia sin relacion alguna", "resumen": "nada que ver",
             "fuentes": [{"link": "http://medio.com/nota2", "medio": "El Medio"}]},
        ]
        m.revisar_casos_avisos(stories)
        avisos = casos.cargar_avisos(c["id"])
        self.assertEqual(len(avisos), 2)
        self.assertEqual({a["tipo"] for a in avisos}, {"historia", "contrato_sercop"})
        # segunda pasada con las MISMAS historias: no debe duplicar (el feed
        # rapido reconstruye 'stories' desde cero en cada pasada real)
        m.revisar_casos_avisos(stories)
        self.assertEqual(len(casos.cargar_avisos(c["id"])), 2)

    def test_revisar_casos_avisos_alias_corto_se_ignora(self):
        c = casos.crear_caso("Caso alias corto")
        casos.agregar_entidad(c["id"], "AB", "otro")  # 2 letras: demasiado corto para ser señal
        stories = [{"titular": "Una nota que por casualidad dice AB en el medio",
                    "resumen": "", "fuentes": [{"link": "http://x", "medio": "M"}]}]
        m.revisar_casos_avisos(stories)
        self.assertEqual(casos.cargar_avisos(c["id"]), [])

    def test_revisar_casos_avisos_sin_casos_no_hace_nada(self):
        # no debe lanzar ni tocar nada si no hay ningun caso creado
        m.revisar_casos_avisos([{"titular": "x", "resumen": "", "fuentes": []}])

    def test_pausa_trabajador_contador(self):
        self.assertFalse(m._trabajador_pausado())
        m._pausar_trabajador()
        m._pausar_trabajador()
        self.assertTrue(m._trabajador_pausado())
        m._reanudar_trabajador()
        self.assertTrue(m._trabajador_pausado())  # todavia queda 1 pausa activa
        m._reanudar_trabajador()
        self.assertFalse(m._trabajador_pausado())
        m._reanudar_trabajador()  # de mas: nunca debe quedar en negativo
        self.assertFalse(m._trabajador_pausado())


class TestMonitorDetalleYMaterial(_CasosAislados):
    def test_detalle_caso_trae_todo(self):
        c = casos.crear_caso("Caso detalle")
        casos.agregar_nota_caso(c["id"], "una nota")
        det = m._detalle_caso(c["id"])
        self.assertEqual(set(det.keys()),
                          {"id", "titulo", "descripcion", "fecha_creacion", "entidades",
                           "avisos", "notas", "evidencia", "tablero", "documentos", "docs_estado"})
        self.assertEqual(len(det["notas"]), 1)

    def test_material_caso_sin_documentos(self):
        c = casos.crear_caso("Caso material", "una descripcion")
        casos.agregar_entidad(c["id"], "Juan Perez")
        mat = m._material_caso(c["id"], "pregunta cualquiera")
        self.assertIn("Caso material", mat)
        self.assertIn("Juan Perez", mat)
        self.assertIn("todavia no tiene documentos", mat)

    def test_procesar_sugerencias_caso_sin_ollama_no_lanza(self):
        c = casos.crear_caso("Caso sugerencias")
        sug = m._procesar_sugerencias_caso(c["id"], "pregunta", "respuesta del chat")
        self.assertEqual(sug, {"entidades": [], "conexiones": []})

    def test_procesar_sugerencias_caso_con_ia_mockeada(self):
        c = casos.crear_caso("Caso sugerencias 2")

        def _gen_falso(*a, **k):
            return json.dumps({
                "entidades": [{"nombre": "Nueva Entidad", "tipo": "empresa"}],
                "conexiones": [{"origen": "A", "destino": "B", "tipo": "socios"}],
            })

        orig_generar = ia._generar
        ia._generar = _gen_falso
        try:
            sug = m._procesar_sugerencias_caso(c["id"], "pregunta", "respuesta")
        finally:
            ia._generar = orig_generar
        self.assertEqual(len(sug["entidades"]), 1)
        self.assertEqual(len(sug["conexiones"]), 1)
        # las sugerencias quedaron REALMENTE guardadas, como 'sugerida'
        caso = casos.cargar_caso(c["id"])
        self.assertEqual(caso["entidades"][0]["nombre"], "Nueva Entidad")
        tablero = casos.cargar_tablero(c["id"])
        self.assertEqual(tablero["conexiones"][0]["estado"], "sugerida")


if __name__ == "__main__":
    unittest.main(verbosity=2)
