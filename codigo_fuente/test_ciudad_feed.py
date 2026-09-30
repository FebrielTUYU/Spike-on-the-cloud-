# -*- coding: utf-8 -*-
"""
Prueba del Problema 1/5 (tercera ronda): "no estas acogiendo directamente
las del sector Guayaquil cuando precisamente los diarios nacionales tienen
secciones enteras dedicadas a la editorial de Guayaquil".

Un feed marcado con "ciudad":"Guayaquil" en feeds.py (una seccion editorial
real de un diario) debe forzar es_local=True/ciudad="Guayaquil" para TODOS
sus articulos, incluso si el texto no menciona la ciudad (notas
hiperlocales de un barrio puntual).

Corre con:  python test_ciudad_feed.py  (no golpea internet)
"""
import datetime as dt
import unittest

import monitor


class TestCiudadFeed(unittest.TestCase):
    def test_parse_feed_propaga_ciudad_feed(self):
        raw = (b'<?xml version="1.0"?><rss version="2.0"><channel>'
               b'<item><title>Remodelacion de la plazoleta de Ceibos genera cuestionamientos</title>'
               b'<link>https://example.com/1</link>'
               b'<pubDate>Wed, 23 Sep 2026 10:00:00 GMT</pubDate>'
               b'<description>Vecinos del sector piden mas mantenimiento.</description>'
               b'</item></channel></rss>')
        items = monitor.parse_feed(raw, "El Universo (Guayaquil)", "auto", ciudad_feed="Guayaquil")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["ciudad_feed"], "Guayaquil")

    def test_build_stories_usa_ciudad_feed_sin_texto_explicito(self):
        """Titular hiperlocal que NO menciona 'Guayaquil' en ningun lado --
        sin la señal de feed, quedaria mal clasificado (internacional)."""
        art = {
            "outlet": "El Universo (Guayaquil)", "seccion": "sociedad",
            "title": "Remodelacion de la plazoleta de Ceibos genera cuestionamientos",
            "link": "https://example.com/1", "date": monitor.now_utc(),
            "summary": "Vecinos del sector piden mas mantenimiento del espacio publico.",
            "image": "", "ciudad_feed": "Guayaquil",
        }
        self.assertFalse(monitor.is_ecuador(art["title"] + " " + art["summary"]),
                          "el texto de prueba no debe tener ninguna palabra clave de Ecuador (asi se prueba la señal de feed)")
        clusters = monitor.cluster([dict(art)])
        stories = monitor.build_stories(clusters)
        self.assertEqual(len(stories), 1)
        s = stories[0]
        self.assertTrue(s["es_local"])
        self.assertEqual(s["ciudad"], "Guayaquil")
        self.assertEqual(s["ambito"], "local")

    def test_sin_ciudad_feed_sigue_dependiendo_del_texto(self):
        """Compatibilidad: un feed SIN 'ciudad' (la mayoria) sigue
        clasificando por texto, como siempre."""
        art = {
            "outlet": "El Mundo", "seccion": "auto",
            "title": "La Union Europea debate nuevas sanciones contra Rusia",
            "link": "https://example.com/2", "date": monitor.now_utc(),
            "summary": "Los ministros se reunen en Bruselas.",
            "image": "", "ciudad_feed": "",
        }
        clusters = monitor.cluster([dict(art)])
        stories = monitor.build_stories(clusters)
        self.assertFalse(stories[0]["es_local"])


if __name__ == "__main__":
    unittest.main()
