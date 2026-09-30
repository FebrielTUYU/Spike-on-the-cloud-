# -*- coding: utf-8 -*-
"""
Prueba del problema 2 (Estadisticas: la cobertura solo mostraba Politica).

Corre con:  python test_categorias.py

No golpea internet ni Ollama: arma historias sinteticas con las 5 categorias
y falla si alguna categoria con notas aparece en 0 en el conteo (el sintoma
que reporto Fernando), o si normalizar_categoria no reduce una variante rara
(mayusculas, tilde, sinonimo, vacio) a una de las claves fijas del dashboard.
"""
import unittest
import monitor


class TestNormalizarCategoria(unittest.TestCase):
    def test_claves_ya_canonicas_quedan_igual(self):
        for c in monitor.CATEGORIAS_VALIDAS:
            self.assertEqual(monitor.normalizar_categoria(c), c)

    def test_variantes_se_normalizan(self):
        casos = {
            "Política": "politica",
            "POLITICA": "politica",
            "Económico": "economia",
            "económica": "economia",
            "Policial": "seguridad",
            "Social": "sociedad",
            "Otros": "general",
            "": "general",
            None: "general",
            "algo-que-no-existe": "general",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(monitor.normalizar_categoria(entrada), esperado)


class TestConteoPorCategoria(unittest.TestCase):
    def test_ninguna_categoria_con_notas_da_cero(self):
        """El bug real: una categoria con historias de verdad no puede
        aparecer con 0 en el conteo que alimenta Estadisticas."""
        stories = (
            [{"seccion": "politica"}] * 3
            + [{"seccion": "economia"}] * 2
            + [{"seccion": "Seguridad"}]       # variante con mayuscula, debe contar igual
            + [{"seccion": "social"}]          # sinonimo de sociedad
            + [{"seccion": "general"}]
        )
        cnt = monitor.contar_por_categoria(stories)
        con_notas = {"politica", "economia", "seguridad", "sociedad", "general"}
        for cat in con_notas:
            self.assertGreater(cnt[cat], 0, "categoria %r tiene notas pero salio en 0" % cat)

    def test_todas_las_claves_presentes_aunque_vacias(self):
        cnt = monitor.contar_por_categoria([])
        self.assertEqual(set(cnt.keys()), set(monitor.CATEGORIAS_VALIDAS))
        self.assertTrue(all(v == 0 for v in cnt.values()))


class TestClassifySectionFunnelaCategoriasValidas(unittest.TestCase):
    def test_classify_section_nunca_sale_de_categorias_validas(self):
        textos = [
            "El presidente Noboa envio a la Asamblea el proyecto de ley economica urgente",
            "La policia realizo un operativo contra el narcotrafico en Guayaquil",
            "El ministerio de salud reporto un brote en escuelas de la Sierra",
            "Texto sin ninguna palabra clave reconocible de ningun banco de temas",
        ]
        for t in textos:
            sec = monitor.classify_section(t) or "general"
            self.assertIn(monitor.normalizar_categoria(sec), monitor.CATEGORIAS_VALIDAS)


if __name__ == "__main__":
    unittest.main()
