# -*- coding: utf-8 -*-
"""
Fase 11 (v2) -- contexto de 4 bloques para que una historia local se entienda
sin venir siguiendo las noticias. Modulo standalone (no importa monitor.py,
mismo criterio que oficial.py/declaraciones.py/alertas.py: evita import
circular, y permite probar la generacion/validacion con la IA mockeada sin
levantar todo monitor.py). Solo libreria estandar + ia.py (el unico
transporte a Gemini del proyecto).

Diagnostico real que motiva este modulo (ver CLAUDE.md, Fase 11 v2, Paso 1):
_construir_contexto() en monitor.py armaba una sola oracion libre (maximo 45
palabras, sin estructura, sin citas verificables) a partir de bios de
Wikipedia + co-menciones de GDELT -- nunca antecedentes del propio registro
de historias, nunca contratos SERCOP, y sin ninguna validacion de fuentes
porque no habia nada estructurado que validar. Este modulo reemplaza esa
salida por 4 bloques (antecedentes/actores/que_es_nuevo/que_falta_saber +
limitaciones), cada afirmacion citando el id de una pieza de MATERIAL real
que monitor.py ya recupero (nunca al reves: la IA nunca busca nada sola,
solo redacta con lo que se le da -- mismo principio de toda Parte B).

monitor.py arma la lista de 'material' (ver _material_contexto en monitor.py)
con ids cortos (ej. "R1" un antecedente del registro, "A1" una aparicion de
un actor, "S1" un contrato SERCOP, "M1" un titular de otro medio de esta
misma historia) y se la pasa a construir(). La validacion de que cada
afirmacion cite un id REAL del material (no inventado) se hace ACA, en
codigo, nunca confiando solo en que el prompt lo pida.
"""
import ia

TIMEOUT = 90
# Bug real confirmado en vivo con la API real de Gemini (Fase 11 v2): con
# 900 tokens, el perfil PROFUNDO (gemini-3.1-pro-preview, con razonamiento
# interno) gastaba casi todo el presupuesto "pensando" antes de escribir el
# JSON visible, devolviendo una respuesta cortada a los 59 caracteres (JSON
# invalido). La tarea es mas compleja que otras llamadas al mismo perfil en
# este proyecto (4 bloques anidados con listas, no una sola frase) -- sube a
# 2500 para dejar margen real a pensamiento + la respuesta completa.
MAX_TOKENS = 2500

_PROMPT = """Sos un asistente de un periodista ecuatoriano. Tu tarea es armar el CONTEXTO de una \
historia para alguien que NO viene siguiendo las noticias -- que entienda en 30 segundos por que \
esta historia importa y que se podria investigar.

Tenes el TITULAR y RESUMEN de la historia (son los HECHOS tal como los cuenta la nota -- no los \
cambies ni les cambies los roles), y una lista de MATERIAL YA VERIFICADO, cada pieza con un id \
corto (ej. "R1", "A2", "S1"). Regla dura, no negociable: CADA afirmacion que escribas en \
"antecedentes", "que_es_nuevo" y "que_falta_saber" tiene que citar en su campo "fuentes" el id (o \
ids) EXACTOS de las piezas de material de donde sacaste ese dato -- nunca un id inventado, nunca \
una afirmacion sin ningun id. Lo mismo para "actores": cada actor cita en "apariciones" los ids del \
material donde aparecio (puede ser una lista vacia si el actor no tiene mas apariciones ademas de \
esta historia). NUNCA uses conocimiento general tuyo sobre Ecuador o el mundo que no este en el \
material -- si el material no alcanza para un bloque, ese bloque va vacio (lista []), nunca lo \
rellenes inventando.

Los 4 bloques:
- "antecedentes": que paso ANTES que ayuda a entender esta historia (usa el material de tipo \
antecedente -- historias relacionadas del registro propio del monitor). Si no hay ningun material \
de ese tipo, lista vacia.
- "actores": quienes estan involucrados (personas, organizaciones, instituciones -- NUNCA un medio \
de prensa ni un lugar geografico suelto como si fuera un actor) y en que otras piezas del material \
volvieron a aparecer.
- "que_es_nuevo": que aporta ESTA historia frente a lo que ya se sabia (usa el material de otros \
medios cubriendo el mismo hecho, o la diferencia contra los antecedentes si los hay).
- "que_falta_saber": preguntas concretas sin responder todavia y por que le importarian a un \
periodista investigando esto (esta es la oportunidad de reportaje) -- no hace falta que cada \
pregunta cite un id si es una pregunta genuina que surge de lo que el material NO dice, pero si te \
basas en un dato puntual del material para armar la pregunta, citalo.
- "limitaciones": en una frase, que no se pudo establecer con el material disponible.

Responde SOLO un JSON valido con esta forma EXACTA (sin texto antes ni despues):
{"antecedentes": [{"texto": "...", "fuentes": ["id", ...]}],
 "actores": [{"nombre": "...", "rol": "...", "apariciones": ["id", ...]}],
 "que_es_nuevo": [{"texto": "...", "fuentes": ["id", ...]}],
 "que_falta_saber": [{"pregunta": "...", "por_que_importa": "...", "fuentes": ["id", ...]}],
 "limitaciones": "..."}

Titular: %s
Resumen: %s

MATERIAL (id: descripcion):
%s
"""


def _sin_material():
    return {"antecedentes": [], "actores": [], "que_es_nuevo": [], "que_falta_saber": [],
            "limitaciones": "sin material verificado disponible para esta historia",
            "descartadas": 0}


def _validar(r, ids_validos):
    """Descarta en CODIGO (no solo por instruccion del prompt) cualquier
    afirmacion cuyos ids no existan de verdad en el material entregado.
    Registra cuantas se descartaron (pedido explicito: 'registra cuantas
    afirmaciones se descartaron')."""
    descartadas_total = 0

    def _limpiar(items, campo_ids):
        nonlocal descartadas_total
        limpio = []
        for it in (items or []):
            if not isinstance(it, dict):
                descartadas_total += 1
                continue
            ids = [i for i in (it.get(campo_ids) or []) if isinstance(i, str) and i in ids_validos]
            if not ids:
                descartadas_total += 1
                continue
            it2 = dict(it)
            it2[campo_ids] = ids
            limpio.append(it2)
        return limpio

    antecedentes = _limpiar(r.get("antecedentes"), "fuentes")
    actores = _limpiar(r.get("actores"), "apariciones")
    que_es_nuevo = _limpiar(r.get("que_es_nuevo"), "fuentes")
    # que_falta_saber: una pregunta genuina puede no citar ningun id (surge de
    # lo que el material NO dice) -- solo se descarta si trae ids y NINGUNO es
    # valido (eso si es una alucinacion real, un id inventado).
    que_falta_saber = []
    for it in (r.get("que_falta_saber") or []):
        if not isinstance(it, dict) or not it.get("pregunta"):
            descartadas_total += 1
            continue
        ids_crudos = it.get("fuentes") or []
        if ids_crudos:
            ids = [i for i in ids_crudos if isinstance(i, str) and i in ids_validos]
            if not ids:
                descartadas_total += 1
                continue
        else:
            ids = []
        it2 = dict(it)
        it2["fuentes"] = ids
        que_falta_saber.append(it2)

    return {
        "antecedentes": antecedentes,
        "actores": actores,
        "que_es_nuevo": que_es_nuevo,
        "que_falta_saber": que_falta_saber,
        "limitaciones": str(r.get("limitaciones", "") or "")[:300],
        "descartadas": descartadas_total,
    }


def construir(titular, resumen, material, forzado="", timeout=TIMEOUT, perfil=None):
    """material: lista de {"id": "R1", "texto": "...", ...}. Sin material, ni
    siquiera se llama a la IA (mismo principio que ia.contextualizar()).
    Devuelve el dict de 4 bloques + 'limitaciones' + 'descartadas', o None si
    la llamada a la IA fallo de verdad (distinto de un resultado vacio, que
    es valido -- lo decide el llamador si reintentar despues)."""
    if not material:
        return _sin_material()
    ids_validos = {m["id"] for m in material if m.get("id")}
    material_txt = "\n".join("%s: %s" % (m["id"], m["texto"]) for m in material if m.get("id"))
    prompt = _PROMPT % ((titular or "")[:200], (resumen or "")[:400], material_txt[:4000])
    r = ia._generar_json(prompt, perfil=perfil or ia.PERFIL_PROFUNDO, temperatura=0.2,
                          max_tokens=MAX_TOKENS, timeout=timeout)
    if r is None:
        return None
    return _validar(r, ids_validos)
