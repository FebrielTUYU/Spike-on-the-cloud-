# -*- coding: utf-8 -*-
"""
Fase 9, Problema B3 -- medir de verdad si hace falta otro modelo de IA, o si
alcanzaba con arreglar el bug de la huella (B1)/el orden de cupo (B2).

Antes de cambiar de modelo, Fernando marca a mano 40 historias reales (30
locales, 10 internacionales) para que el programa calcule una precision real
-- palabras clave vs IA (categoria y ambito) y que porcentaje de las
Lecturas editoriales de verdad describen la noticia.

CÓMO USARLO (dos pasos, uno por uno):
  1. python evaluar_ia.py generar
     Crea evaluacion_ia.csv con 40 historias reales de data.json, ya con lo
     que el programa calculo (categoria/ambito por PALABRAS CLAVE, por IA, y
     la Lectura editorial). Solo lo abrís en Excel/LibreOffice/Google
     Sheets y llenás 3 columnas por fila: "categoria_correcta" (la categoria
     que VOS dirías que es), "ambito_correcto" ("local" o "internacional"),
     y "lectura_correcta" ("si" si la Lectura IA de verdad habla de ESTA
     noticia, "no" si parece hablar de otra cosa). Dejalas en blanco si no
     estás seguro de una fila puntual -- esas se ignoran al calcular.
  2. python evaluar_ia.py evaluar
     Lee evaluacion_ia.csv y muestra: cuantas veces acertó la clasificacion
     por PALABRAS CLAVE solas, cuantas veces acertó (o corrigió bien) la IA,
     y que porcentaje de Lecturas editoriales realmente describen la nota.

No golpea Ollama ni la red -- solo lee data.json/ia_cache.json (ya
calculados) y aplica themes_for()/classify_section() (las mismas funciones
que el pipeline real, solo lectura) para reconstruir la clasificacion PURA
por palabras clave sin el candado de la IA encima.
"""
import csv
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "evaluacion_ia.csv")
DATA_PATH = os.path.join(HERE, "data.json")
IA_CACHE_PATH = os.path.join(HERE, "ia_cache.json")

FIELDS = ["link", "titular", "resumen", "categoria_keywords", "categoria_ia",
          "categoria_correcta", "ambito_keywords", "ambito_ia", "ambito_correcto",
          "lectura_ia", "lectura_correcta"]

N_LOCAL = 30
N_INTL = 10


def _cargar_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def generar():
    import monitor as m  # se importa aca (no arriba) para no pagar el costo si solo se va a "evaluar"

    data = _cargar_json(DATA_PATH, {})
    ia_cache = _cargar_json(IA_CACHE_PATH, {})
    historias = data.get("historias", [])
    if not historias:
        print("No hay data.json con historias todavia -- corré el Monitor al menos una vez antes.")
        return

    locales = [h for h in historias if h.get("es_local")]
    intl = [h for h in historias if not h.get("es_local")]
    random.shuffle(locales)
    random.shuffle(intl)
    muestra = locales[:N_LOCAL] + intl[:N_INTL]
    if len(muestra) < (N_LOCAL + N_INTL):
        print("Aviso: solo hay %d historias disponibles (se pedian %d) -- se usa lo que hay." %
              (len(muestra), N_LOCAL + N_INTL))

    filas = []
    for h in muestra:
        f0 = (h.get("fuentes") or [{}])[0]
        link = f0.get("link") or h.get("titular", "")
        titular, resumen = h.get("titular", ""), h.get("resumen", "")
        # Categoria/ambito por PALABRAS CLAVE puras (sin el candado de la IA
        # encima) -- reconstruido con las mismas funciones del pipeline real.
        temas_kw = sorted(m.themes_for(titular + " " + resumen, "auto"))
        cat_kw = ",".join(temas_kw) or "otros"
        ambito_kw = "local" if m.is_ecuador(titular + " " + resumen) else "internacional"
        cat_ia = ",".join(h.get("temas") or []) or "otros"
        ambito_ia = "local" if h.get("es_local") else "internacional"
        lectura = h.get("ia") or ""
        filas.append({
            "link": link, "titular": titular, "resumen": resumen,
            "categoria_keywords": cat_kw, "categoria_ia": cat_ia, "categoria_correcta": "",
            "ambito_keywords": ambito_kw, "ambito_ia": ambito_ia, "ambito_correcto": "",
            "lectura_ia": lectura, "lectura_correcta": "",
        })

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(filas)
    print("Listo: %s (%d filas, %d locales + %d internacionales)." %
          (CSV_PATH, len(filas), min(N_LOCAL, len(locales)), min(N_INTL, len(intl))))
    print("Abrilo en Excel/LibreOffice/Sheets y llená categoria_correcta, "
          "ambito_correcto y lectura_correcta (si/no) -- dejá en blanco lo que no estés seguro.")


def evaluar():
    if not os.path.exists(CSV_PATH):
        print("No existe %s todavia -- corré primero: python evaluar_ia.py generar" % CSV_PATH)
        return
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    if not filas:
        print("El CSV esta vacio.")
        return

    def _pct(aciertos, total):
        return "%d/%d (%.0f%%)" % (aciertos, total, 100.0 * aciertos / total) if total else "sin datos"

    cat_kw_ok = cat_kw_total = 0
    cat_ia_ok = cat_ia_total = 0
    amb_kw_ok = amb_kw_total = 0
    amb_ia_ok = amb_ia_total = 0
    lect_si = lect_total = 0
    for row in filas:
        correcta = (row.get("categoria_correcta") or "").strip()
        if correcta:
            cat_kw_total += 1
            if correcta in (row.get("categoria_keywords") or "").split(","):
                cat_kw_ok += 1
            cat_ia_total += 1
            if correcta in (row.get("categoria_ia") or "").split(","):
                cat_ia_ok += 1
        amb_correcto = (row.get("ambito_correcto") or "").strip().lower()
        if amb_correcto:
            amb_kw_total += 1
            if amb_correcto == (row.get("ambito_keywords") or "").strip().lower():
                amb_kw_ok += 1
            amb_ia_total += 1
            if amb_correcto == (row.get("ambito_ia") or "").strip().lower():
                amb_ia_ok += 1
        lect_correcta = (row.get("lectura_correcta") or "").strip().lower()
        if lect_correcta in ("si", "sí", "no"):
            lect_total += 1
            if lect_correcta in ("si", "sí"):
                lect_si += 1

    print("Resultado sobre %d filas marcadas (de %d en el CSV):" % (
        max(cat_kw_total, amb_kw_total, lect_total), len(filas)))
    print()
    print("Categoria (tema):")
    print("  palabras clave solas: %s" % _pct(cat_kw_ok, cat_kw_total))
    print("  con la IA encima:     %s" % _pct(cat_ia_ok, cat_ia_total))
    print()
    print("Ambito (Ecuador/Mundo):")
    print("  palabras clave solas: %s" % _pct(amb_kw_ok, amb_kw_total))
    print("  con la IA encima:     %s" % _pct(amb_ia_ok, amb_ia_total))
    print()
    print("Lectura editorial (¿describe de verdad esta noticia?):")
    print("  %s de las lecturas marcadas SI corresponden a la nota" % _pct(lect_si, lect_total))
    print()
    if lect_total and lect_si / lect_total < 0.7:
        print("Con menos de 7 de cada 10 lecturas correctas, vale la pena revisar si el bug de la "
              "huella (Problema B1, historias que cambian de titular representante) explica la "
              "mayoria de los casos marcados 'no' antes de pensar en cambiar de modelo.")
    elif lect_total:
        print("Con la mayoria de lecturas corrigiendo bien, el problema principal parece haber sido "
              "el desfase de contenido (B1), no la calidad del modelo en si.")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("generar", "evaluar"):
        print(__doc__)
        return
    if sys.argv[1] == "generar":
        generar()
    else:
        evaluar()


if __name__ == "__main__":
    main()
