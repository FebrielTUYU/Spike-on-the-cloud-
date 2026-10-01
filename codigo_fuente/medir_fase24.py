# -*- coding: utf-8 -*-
"""
medir_fase24.py -- foto de las metricas de la Fase 24 sobre los datos REALES
(solo lee). Uso: python medir_fase24.py [etiqueta]  -> imprime y agrega la
foto a pruebas/mediciones_fase24.jsonl para comparar antes/despues.
"""
import collections
import datetime as dt
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def _leer(nombre, defecto):
    try:
        with open(os.path.join(AQUI, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def foto(etiqueta=""):
    d = _leer("data.json", {})
    H = d.get("historias") or []
    n = len(H) or 1
    g = _leer("ia_gasto.json", {})
    r = _leer("ia_router_estado.json", {})
    hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    reg = _leer("historias_registro.json", {})
    con_emb = sum(1 for v in reg.values() if isinstance(v, dict) and v.get("embedding"))
    vered = collections.Counter((h.get("veredicto") or {}).get("estado") for h in H)
    vered_ia = collections.Counter((h.get("veredicto_ia") or {}).get("estado") for h in H)
    usos = {}
    for dia, pms in (r.get("dias") or {}).items():
        for pm, u in pms.items():
            usos.setdefault(dia, {})[pm] = {"pedidos": u.get("pedidos"), "ok": u.get("ok"), "errores": u.get("errores")}
    I = [h for h in H if h.get("ambito") == "internacional"]
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(), "etiqueta": etiqueta, "data_generado": d.get("generado"),
        "historias": len(H),
        "pct_ia": round(100.0 * sum(1 for h in H if h.get("ia")) / n, 1),
        "pct_contexto": round(100.0 * sum(1 for h in H if h.get("contexto") not in (None, {})) / n, 1),
        "pct_veredicto_ia_hecho": round(100.0 * sum(1 for h in H if (h.get("veredicto_ia") or {}).get("estado") not in (None, "pendiente")) / n, 1),
        "embeddings_registro": "%d/%d" % (con_emb, len(reg)),
        "pct_embeddings_registro": round(100.0 * con_emb / (len(reg) or 1), 1),
        "gasto_pagado_por_dia": {k: v for k, v in sorted((g.get("dias") or {}).items())[-3:]},
        "gasto_pagado_por_modulo_hoy": (g.get("modulos") or {}).get(hoy),
        "ia_gratis_por_dia": usos,
        "pct_general": round(100.0 * sum(1 for h in H if h.get("seccion") == "general") / n, 1),
        "sin_temas": sum(1 for h in H if not h.get("temas")),
        "internacional": len(I),
        "veredicto": dict(vered), "veredicto_ia": dict(vered_ia),
        "mapa": (d.get("mapa") or {}).get("estado"),
        "comunidad_10h": (d.get("comunidad") or {}).get("total_publicaciones"),
    }


if __name__ == "__main__":
    f = foto(sys.argv[1] if len(sys.argv) > 1 else "")
    print(json.dumps(f, ensure_ascii=False, indent=1))
    os.makedirs(os.path.join(AQUI, "pruebas"), exist_ok=True)
    with open(os.path.join(AQUI, "pruebas", "mediciones_fase24.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(f, ensure_ascii=False) + "\n")
