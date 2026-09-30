# -*- coding: utf-8 -*-
"""
Fase 18 -- medicion antes/despues del agrupamiento y de "que es Guayaquil"
sobre un historias_registro.json REAL (no toca el archivo que se le pasa:
trabaja sobre una copia temporal).

Uso (desde codigo_fuente/):
    python pruebas/medir_fase18.py [ruta_registro]

Imprime, para el registro tal cual y para el registro reconstruido con las
reglas actuales (monitor.reconstruir_registro):
- historias visibles y cuantas son de Guayaquil
- historias de Guayaquil con OTRO lugar en el titular (ciudad de Ecuador que
  no es Gran Guayaquil, o lugar extranjero) y sin nombrar Gran Guayaquil
- historias de Guayaquil que contienen alguna fuente extranjera
- tarjetas de lluvias en Guayaquil por dia local
"""
import json
import os
import re
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import monitor  # noqa: E402

RX_LLUVIA = re.compile(r"lluvi|inund|anega|aguacero|acumulaci[oó]n de agua|calzada mojada", re.I)


def _otro_lugar(titulo):
    cs = monitor.ciudades_en(titulo)
    if any(c in monitor.GUAYAQUIL_AREA for c in cs):
        return False
    return bool([c for c in cs if c not in monitor.GUAYAQUIL_AREA]) or monitor.is_foreign(titulo)


def medir(stories):
    gye = [s for s in stories if s.get("ciudad") == "Guayaquil"]
    otro = [s for s in gye if _otro_lugar(s["titular"])]
    mezcla_ext = [s for s in gye if any(monitor.extranjero_sin_ecuador(f["title"]) for f in s["fuentes"])]
    lluvias = {}
    for s in gye:
        if RX_LLUVIA.search(s["titular"]) or (s.get("evento_en_curso") or {}).get("tipo") == "lluvias":
            dia = monitor._dia_local(s.get("newest"))
            lluvias[str(dia)] = lluvias.get(str(dia), 0) + 1
    return {"historias": len(stories), "guayaquil": len(gye),
            "gye_titular_otro_lugar": len(otro), "gye_con_fuente_extranjera": len(mezcla_ext),
            "tarjetas_lluvias_gye_por_dia": dict(sorted(lluvias.items())),
            "ejemplos_otro_lugar": [s["titular"][:90] for s in otro[:8]],
            "ejemplos_fuente_extranjera": [[f["title"][:70] for f in s["fuentes"]][:4] for s in mezcla_ext[:5]]}


def historias(ruta):
    monitor.REGISTRO_PATH = ruta
    reg = monitor._cargar_registro()
    return monitor.agrupar_eventos_en_curso(monitor.build_stories(monitor._registro_a_clusters(reg)))


def main():
    origen = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(AQUI), "historias_registro.json")
    tmp = tempfile.mkdtemp()
    copia = os.path.join(tmp, "historias_registro.json")
    shutil.copy2(origen, copia)
    monitor.ia = None
    monitor.REGISTRO_VERSION_PATH = os.path.join(tmp, "version.json")
    antes = medir(historias(copia))
    monitor.reconstruir_registro(verbose=True)
    despues = medir(historias(copia))
    print(json.dumps({"antes": antes, "despues": despues}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
