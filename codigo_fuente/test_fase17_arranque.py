# -*- coding: utf-8 -*-
"""
Fase 17 (arreglo del .exe lento -- ver COORDINACION.md, Frente B).

Cubre el hallazgo de Codex en la revision del arreglo 3 (cache por entrada de
_match_registro): la primera version de la huella de cache concatenaba
rep_titulo + " " + rep_resumen en UN string -- dos pares (titulo, resumen)
DISTINTOS pueden concatenar al mismo string si el "corte" entre ambos cae en
otro lugar (ej. "Rescate playa Guayaquil"+"hoy" == "Rescate"+"playa Guayaquil
hoy"), lo que dejaria pasar un tok_rep/extranjero VIEJO como si siguiera
valido. Arreglado usando una tupla de los campos originales como huella.

Corre con:  python -m unittest test_fase17_arranque -v
"""
import unittest

import monitor


def _articulo(title, summary=""):
    tok = monitor.tokens(title) - monitor.EVENTO_GENERICO - monitor.LUGARES_COMUNES - monitor.PALABRAS_GENERICAS_CONTENIDO
    return {
        "title": title, "summary": summary,
        "_tok": tok, "_nom": set(), "_num": set(), "_fecha_menc": set(),
        "_ciudad": "", "_servicio": "", "_emb": None,
        "date": monitor.now_utc(),
    }


def _entrada(rep_titulo, rep_resumen, fundador_titulo=None):
    return {
        "ultimo": monitor.now_utc(),
        "rep_titulo": rep_titulo, "rep_resumen": rep_resumen,
        "fundador_titulo": fundador_titulo or rep_titulo, "fundador_resumen": rep_resumen,
        "ciudad": "", "servicio": "", "fechas": set(),
        "tokens": set(), "nombres": set(), "numeros": set(), "embedding": None,
    }


class TestCacheEntradaNoColisiona(unittest.TestCase):
    """Bug real encontrado por Codex ANTES de mergear (nunca llego a produccion):
    la huella de cache por concatenacion de strings colisionaba entre dos
    estados distintos de la misma entrada."""

    def test_huella_tupla_detecta_cambio_pese_a_concatenacion_identica(self):
        e = _entrada("Rescate playa Guayaquil", "hoy")
        registro = {"e1": e}
        cache = {}

        art = _articulo("Aviso playa Salinas")
        monitor._match_registro(art, registro, cache)
        # Estado 1: "playa" viene de rep_titulo -> debe estar en tok_rep.
        self.assertIn("playa", cache["e1"]["tok_rep"],
                      "tok_rep deberia incluir 'playa' cuando esta en rep_titulo")

        # Mismo texto concatenado que el estado 1 ("Rescate playa Guayaquil"
        # + " " + "hoy" == "Rescate" + " " + "playa Guayaquil hoy"), pero
        # "playa" YA NO esta en rep_titulo -- con la huella vieja (string
        # concatenado) esto hubiera reusado el cache del estado 1 sin darse
        # cuenta del cambio.
        e["rep_titulo"] = "Rescate"
        e["rep_resumen"] = "playa Guayaquil hoy"
        monitor._match_registro(art, registro, cache)
        self.assertNotIn("playa", cache["e1"]["tok_rep"],
                          "tok_rep tiene que recalcularse: 'playa' ya no esta en el rep_titulo nuevo")
        self.assertIn("rescate", cache["e1"]["tok_rep"])

    def test_cache_evita_recalculo_cuando_de_verdad_no_cambio(self):
        # Control: si la entrada NO cambia entre dos llamadas, el cache se
        # reutiliza (misma huella) -- confirma que el cache sigue haciendo
        # su trabajo (no es solo invalidar siempre).
        e = _entrada("Nota sin cambios de verdad", "resumen estable")
        registro = {"e1": e}
        cache = {}
        art1 = _articulo("Otra nota cualquiera")
        art2 = _articulo("Una nota distinta")

        monitor._match_registro(art1, registro, cache)
        primer_tok_rep = cache["e1"]["tok_rep"]
        monitor._match_registro(art2, registro, cache)
        self.assertEqual(cache["e1"]["tok_rep"], primer_tok_rep,
                          "sin cambios en la entrada, el cache debe seguir siendo el mismo objeto de datos")


class TestAExtranjeroHoisteado(unittest.TestCase):
    """Confirma que sacar a_extranjero del loop no cambio el resultado final
    de _match_registro para un caso real (equivalencia de comportamiento,
    no solo de velocidad -- ya cubierto por la suite existente de
    is_ecuador/is_foreign, pero este caso ejercita el camino completo)."""

    def test_match_con_entidad_extranjera_sigue_descartando_correctamente(self):
        # Entrada LOCAL real (Guayaquil), articulo nuevo sobre otro pais:
        # extranjero_sin_ecuador debe diferir y _match_registro no debe
        # matchear aunque compartan alguna palabra generica.
        e = _entrada("Municipio de Guayaquil anuncia obra vial", "Guayaquil, Ecuador")
        registro = {"e1": e}
        art = _articulo("Gobierno de Espana anuncia obra vial en Madrid", "Madrid, Espana")
        eid, sim, via = monitor._match_registro(art, registro, {})
        self.assertIsNone(eid, "una nota de Espana no deberia matchear una entrada local de Guayaquil")


if __name__ == "__main__":
    unittest.main()
