# -*- coding: utf-8 -*-
"""
evaluar_fase24.py -- Fase 24 (Parte 0): la medida de "mas preciso" para toda
la fase. Compara lo que Spike dice (un data.json) contra el conjunto revisado
a mano pruebas/evaluacion_fase24.csv.

Mide: exactitud de categoria, ambito, tipo (accion/anuncio/declaracion/dato),
ciudad y utilidad (util/basura), y pares mal unidos / mal separados.

Regla de Fernando: sin su visto bueno en el CSV (columna
revisado_por_fernando llena en TODAS las filas) no se reporta precision. Con
--borrador calcula igual pero lo marca como BORRADOR (solo para comparar
antes/despues mientras se trabaja; nunca como resultado).

Uso:
  python evaluar_fase24.py                       (usa data.json de esta carpeta)
  python evaluar_fase24.py --datos otra.json --borrador
Solo libreria estandar. No escribe nada.
"""
import csv
import itertools
import json
import os
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(AQUI, "pruebas", "evaluacion_fase24.csv")

# Taxonomia vieja (seccion de Spike antes de la Parte C2) -> la mas probable
# de la nueva. Es aproximada a proposito: con la taxonomia vieja no se puede
# acertar "obras_servicios" o "movilidad", y eso es justamente lo que se mide.
SECCION_VIEJA = {"politica": "politica", "economia": "economia", "seguridad": "seguridad",
                 "sociedad": "sociedad_cultura", "general": "general"}


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def cargar_csv(ruta=CSV_PATH):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# Lo que se puede editar desde la pagina de revision (revisar_evaluacion.html)
# y los valores validos de cada campo cerrado.
CATEGORIAS = ["politica", "economia", "empleo", "seguridad", "justicia", "obras_servicios", "movilidad",
              "riesgos_clima", "salud", "educacion", "sociedad_cultura", "entretenimiento_deporte"]
VALIDOS = {"categoria_esperada": CATEGORIAS + [""], "ambito_esperado": ["guayaquil", "ecuador", "mundo", ""],
           "tipo_esperado": ["accion", "anuncio", "declaracion", "dato", ""], "util_esperado": ["si", "no", ""],
           "revisado_por_fernando": ["si", ""]}
EDITABLES = set(VALIDOS) | {"ciudad_esperada", "grupo", "comentario_fernando"}


def guardar_revision(fila_id, cambios, ruta=CSV_PATH):
    """Cambia campos de UNA fila y reescribe el CSV (archivo temporal + os.replace).
    Devuelve (ok, mensaje)."""
    filas = cargar_csv(ruta)
    campos = list(filas[0].keys()) if filas else []
    if "comentario_fernando" not in campos:
        campos.append("comentario_fernando")
    fila = next((f for f in filas if str(f.get("id")) == str(fila_id)), None)
    if fila is None:
        return False, "fila %s no existe" % fila_id
    for k, v in (cambios or {}).items():
        if k not in EDITABLES:
            return False, "campo no editable: %s" % k
        v = str(v if v is not None else "").strip()[:300]
        if k in VALIDOS and v not in VALIDOS[k]:
            return False, "valor no valido para %s: %s" % (k, v)
        fila[k] = v
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for x in filas:
            w.writerow({c: x.get(c, "") for c in campos})
    os.replace(tmp, ruta)
    return True, "guardado"


def revisado(filas):
    return bool(filas) and all((f.get("revisado_por_fernando") or "").strip() for f in filas)


AMBIGUA = -1  # el mismo link o titular aparece en dos historias: la fila no se evalua


def _indice(historias):
    por_link, por_tit = {}, {}
    for i, h in enumerate(historias):
        for fu in h.get("fuentes") or []:
            if fu.get("link"):
                por_link[fu["link"]] = AMBIGUA if por_link.get(fu["link"], i) != i else i
        t = _norm(h.get("titular"))
        por_tit[t] = AMBIGUA if por_tit.get(t, i) != i else i
    return por_link, por_tit


def prediccion(h):
    """Lo que Spike dice de una historia, en el vocabulario del CSV."""
    if h is None:
        return None
    if h.get("ambito") == "internacional":
        amb = "mundo"
    else:
        amb = "guayaquil" if h.get("ciudad") == "Guayaquil" else "ecuador"
    cat = h.get("categoria") or SECCION_VIEJA.get(h.get("seccion"), h.get("seccion") or "")
    util = h.get("util")
    if isinstance(util, bool):
        util = "si" if util else "no"
    return {"categoria": cat, "ambito": amb, "tipo": h.get("tipo") or "",
            "ciudad": h.get("localidad") or h.get("ciudad") or "", "util": util or ""}


def _ciudad_ok(esperada, dicha, ambito):
    e, d = _norm(esperada), _norm(dicha)
    if ambito == "mundo":
        return None  # para el mundo no se mide ciudad
    if e.startswith("ecuador (nacional)"):
        return d in ("", "ecuador")
    return bool(d) and (d in e or e in d)


def evaluar(filas, historias):
    por_link, por_tit = _indice(historias)
    res = {k: {"ok": 0, "n": 0, "sin_dato": 0, "errores": []} for k in ("categoria", "ambito", "tipo", "ciudad", "util")}
    ubic = {}
    no_encontradas, ambiguas = [], []
    for f in filas:
        i = por_link.get(f.get("link")) if f.get("link") else None
        if i is None:
            i = por_tit.get(_norm(f.get("titular")))
        if i == AMBIGUA:
            ambiguas.append(f["id"])
            i = None
        ubic[f["id"]] = i
        if i is None:
            if f["id"] not in ambiguas:
                no_encontradas.append(f["id"])
            continue
        p = prediccion(historias[i])
        for campo in ("categoria", "ambito", "tipo", "util"):
            esp = (f.get("%s_esperad%s" % (campo, "a" if campo in ("categoria",) else "o")) or "").strip()
            if campo == "util":
                esp = (f.get("util_esperado") or "").strip()
            if not esp:
                continue
            if not p[campo]:
                res[campo]["sin_dato"] += 1
                continue
            res[campo]["n"] += 1
            if _norm(p[campo]) == _norm(esp):
                res[campo]["ok"] += 1
            else:
                res[campo]["errores"].append((f["id"], esp, p[campo], f["titular"][:70]))
        c = _ciudad_ok(f.get("ciudad_esperada"), p["ciudad"], (f.get("ambito_esperado") or "").strip())
        if c is not None and (f.get("ciudad_esperada") or "").strip():
            res["ciudad"]["n"] += 1
            if c:
                res["ciudad"]["ok"] += 1
            else:
                res["ciudad"]["errores"].append((f["id"], f.get("ciudad_esperada"), p["ciudad"], f["titular"][:70]))
    # agrupamiento: todos los pares de filas encontradas
    mal_separados, mal_unidos, pares_esperados = [], [], 0
    enc = [f for f in filas if ubic.get(f["id"]) is not None]
    grupo = {f["id"]: str(f.get("grupo") or "").strip() for f in enc}
    for a, b in itertools.combinations(enc, 2):
        ga, gb = grupo[a["id"]], grupo[b["id"]]
        if ga.endswith("?") or gb.endswith("?"):
            continue  # grupo dudoso: lo decide Fernando
        juntos_esperado = bool(ga) and ga == gb
        juntos_dicho = ubic[a["id"]] == ubic[b["id"]]
        pares_esperados += 1 if juntos_esperado else 0
        if juntos_esperado and not juntos_dicho:
            mal_separados.append((a["id"], b["id"]))
        elif juntos_dicho and not juntos_esperado:
            mal_unidos.append((a["id"], b["id"]))
    return {"metricas": res, "mal_separados": mal_separados, "mal_unidos": mal_unidos,
            "pares_esperados": pares_esperados, "no_encontradas": no_encontradas, "ambiguas": ambiguas,
            "filas": len(filas)}


def _pct(m):
    return "%.1f%% (%d de %d)" % (100.0 * m["ok"] / m["n"], m["ok"], m["n"]) if m["n"] else "sin dato"


def informe(r, borrador):
    lin = ["== Evaluacion Fase 24 %s ==" % ("(BORRADOR: el CSV todavia no tiene el visto bueno de Fernando)" if borrador else "")]
    lin.append("Filas: %d; no encontradas en estos datos: %d; ambiguas (link o titular repetido): %d"
               % (r["filas"], len(r["no_encontradas"]), len(r.get("ambiguas") or [])))
    for k in ("categoria", "ambito", "tipo", "ciudad", "util"):
        m = r["metricas"][k]
        extra = (" -- %d filas sin prediccion de Spike" % m["sin_dato"]) if m["sin_dato"] else ""
        lin.append("  %-9s %s%s" % (k, _pct(m), extra))
    lin.append("  agrupamiento: %d de %d pares que deberian ir juntos estan separados; %d pares unidos por error"
               % (len(r["mal_separados"]), r["pares_esperados"], len(r["mal_unidos"])))
    return "\n".join(lin)


def main(argv):
    ruta = os.path.join(AQUI, "data.json")
    borrador = "--borrador" in argv
    if "--datos" in argv:
        ruta = argv[argv.index("--datos") + 1]
    filas = cargar_csv()
    ok = revisado(filas)
    if not ok and not borrador:
        print("El CSV todavia no tiene el visto bueno de Fernando (columna revisado_por_fernando).")
        print("Sin eso no se reporta precision. Para comparar mientras se trabaja: --borrador")
        return 2
    historias = json.load(open(ruta, encoding="utf-8")).get("historias") or []
    r = evaluar(filas, historias)
    print(informe(r, borrador=not ok))
    if "--errores" in argv:
        for k, m in r["metricas"].items():
            for e in m["errores"]:
                print("   [%s] fila %s: esperado %s, Spike %s -- %s" % (k, e[0], e[1], e[2], e[3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
