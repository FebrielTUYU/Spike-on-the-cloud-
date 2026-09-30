# -*- coding: utf-8 -*-
"""
Fase 5 (2026-09-23/24): Contraste de declaraciones con el pasado.

Registro local de declaraciones ATRIBUIDAS (quien, cargo, que dijo, fecha,
medio) extraidas de las notas por ia.extraer_declaracion() -- NO es un cache
recalculable como los demas *_cache.json: es un registro que NUNCA se purga
por MONITOR_MAX_DIAS (a diferencia de las historias del feed, que caducan a
los pocos dias). El objetivo es poder comparar lo que un mismo actor dice HOY
contra lo que dijo hace semanas o meses, aunque esa nota vieja ya haya salido
del feed y de data.json.

Solo stdlib. NO importa monitor.py (evita import circular, mismo criterio que
oficial.py) -- duplica aca las funciones minimas de normalizacion/tokens que
necesita en vez de importarlas.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DECLARACIONES_PATH = os.path.join(HERE, "declaraciones.json")

MAX_POR_ACTOR = 40      # declaraciones guardadas por actor (se recorta lo mas viejo, NUNCA por fecha de vencimiento)
MAX_TOTAL_ACTORES = 500  # limite de actores distintos, para que el archivo no crezca sin control

STOPWORDS = {
    "para", "esta", "este", "pero", "como", "mas", "con", "los", "las", "una", "uno",
    "por", "que", "del", "sus", "fue", "son", "han", "sera", "sido", "ecuador",
    "esto", "eso", "sobre", "hasta", "desde", "entre", "todo", "toda", "todos",
}


def _strip_accents(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def norm(s):
    s = _strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(texto):
    return {t for t in norm(texto).split() if len(t) >= 4 and t not in STOPWORDS}


def _actor_key(nombre):
    return norm(nombre or "")


def _cargar():
    try:
        with open(DECLARACIONES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar(reg):
    # mismo patron atomico que saved.json/notas.json/busquedas.json: archivo
    # temporal + os.replace, para no dejar el registro a medio escribir si el
    # programa se corta justo en el momento de guardar.
    tmp = DECLARACIONES_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False)
        os.replace(tmp, DECLARACIONES_PATH)
    except Exception:
        pass


def registrar(actor, cargo, texto, fecha, medio, link, historia_key=""):
    """Guarda una declaracion nueva bajo la clave normalizada del actor. No
    duplica si ya existe una declaracion con el mismo link para ese actor
    (re-procesos del trabajador, o dos pasadas sobre la misma historia, no la
    repiten). Si se llego al limite de actores DISTINTOS (MAX_TOTAL_ACTORES) y
    este actor es nuevo, se descarta -- mejor perder un actor nuevo que borrar
    el historial ya acumulado de actores conocidos."""
    key = _actor_key(actor)
    if not key or not (texto or "").strip():
        return
    reg = _cargar()
    if key not in reg and len(reg) >= MAX_TOTAL_ACTORES:
        return
    lst = reg.setdefault(key, [])
    if link and any(d.get("link") == link for d in lst):
        return
    lst.append({
        "actor": actor, "cargo": cargo or "", "texto": texto, "fecha": fecha or "",
        "medio": medio or "", "link": link or "", "historia_key": historia_key or "",
    })
    lst.sort(key=lambda d: d.get("fecha") or "")
    reg[key] = lst[-MAX_POR_ACTOR:]
    _guardar(reg)


def de_actor(actor, excluir_link=""):
    """Declaraciones YA registradas de 'actor' (mas recientes primero), sin
    contar la que se acaba de registrar (por link) -- mismo criterio que
    monitor.apariciones_previas() para entities.json."""
    reg = _cargar()
    lst = reg.get(_actor_key(actor), [])
    out = [d for d in lst if not (excluir_link and d.get("link") == excluir_link)]
    out.sort(key=lambda d: d.get("fecha") or "", reverse=True)
    return out


def candidatos_contradiccion(actor, texto_nuevo, fecha_nueva, excluir_link="", max_candidatos=3):
    """Filtro BARATO (sin IA, sin red): declaraciones ANTERIORES del MISMO
    actor que ADEMAS comparten 2+ palabras significativas (>=4 letras, sin
    stopwords) con la declaracion nueva -- mismo criterio que ya usa
    _factcheck_relevante en monitor.py para exigir relacion real, no solo
    coincidencia de actor (una persona habla de muchos temas distintos; sin
    este filtro, cualquier par de declaraciones del mismo actor pasaria al
    modelo caro sin ninguna relacion real entre ellas).

    Solo compara contra declaraciones con fecha ESTRICTAMENTE anterior (orden
    temporal real: 'nueva' contradice o no a lo que se dijo ANTES, nunca al
    reves). Solo los candidatos que salen de aca pasan al modelo pesado
    (ia.comparar_declaraciones), que es caro (~100s por llamada) -- este
    filtro es lo que hace viable llamarlo solo un puñado de veces por pasada,
    no sobre todo el registro."""
    tok_nuevo = tokens(texto_nuevo)
    if not tok_nuevo:
        return []
    previas = de_actor(actor, excluir_link=excluir_link)
    out = []
    for d in previas:
        if fecha_nueva and d.get("fecha") and d["fecha"] >= fecha_nueva:
            continue
        comunes = tok_nuevo & tokens(d.get("texto", ""))
        if len(comunes) >= 2:
            out.append(d)
    return out[:max_candidatos]


def estado():
    """Resumen honesto del tamaño del registro, para mostrar en el dashboard
    (mismo criterio que oficial.estado()/salud_fuentes: nunca ocultar si algo
    todavia esta vacio)."""
    reg = _cargar()
    total = sum(len(v) for v in reg.values())
    return {"actores": len(reg), "declaraciones": total}
