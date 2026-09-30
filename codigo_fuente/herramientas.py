# -*- coding: utf-8 -*-
"""
Herramientas de SOLO LECTURA sobre los datos YA CALCULADOS del monitor, para
el Asistente de IA (Bloque 2, Parte F). Solo libreria estandar de Python 3.

Mismo principio de siempre (Parte B, "el codigo recupera, la IA solo
redacta"): estas funciones NUNCA llaman a una API externa en vivo (Trends/
GDELT/SERCOP/Wikipedia/redes) -- leen lo que el pipeline normal (run_fast/
enrich_pass) ya guardo en data.json/history.json/saved.json/notas.json y los
*_cache.json. Evita que usar el chat dispare llamadas nuevas a fuentes con
rate-limit (GDELT, Trends) o agregue latencia impredecible: el asistente
responde siempre sobre el ULTIMO estado conocido del monitor, el mismo que ya
ve el dashboard.

Cada funcion devuelve estructuras chicas y acotadas (listas con limite,
textos recortados): son el MATERIAL que despues arma el prompt del modelo,
no el archivo entero. El agente (agente.py) las expone al modelo como
"herramientas" que puede pedir invocar.
"""
import datetime as dt
import json
import os
import re
import unicodedata

from feeds import KEYWORDS

HERE = os.path.dirname(os.path.abspath(__file__))

# Palabras demasiado cortas/genericas para servir como señal de busqueda por
# si solas (mismo umbral >=4 letras que usa tokens() en monitor.py para este
# mismo tipo de filtro por palabras significativas).
_STOPWORDS_Q = {
    "para", "esta", "este", "estos", "estas", "sobre", "hoy", "que", "quien",
    "como", "cuando", "donde", "cual", "cuales", "algo", "algun", "alguna",
    "tras", "desde", "hasta", "entre", "mas", "menos", "muy", "dijo", "dice",
}


def _norm_q(s):
    """Minusculas + sin tildes + sin puntuacion -- version liviana y local de
    monitor.norm() (herramientas.py es standalone a proposito, no importa
    monitor.py, ver el docstring de arriba)."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def _tokens_q(texto):
    return {t for t in _norm_q(texto).split() if len(t) >= 4 and t not in _STOPWORDS_Q}


def _coincide_texto_libre(q, titular, resumen):
    """Reemplaza la subcadena literal (`q.lower() in blob`) por un match por
    PALABRAS -- bug real (Fernando): el Asistente no encontraba una nota
    real y reciente ('Una mujer fue baleada tras retirar USD 2.000... en el
    centro de Guayaquil') porque el modelo nunca reproduce el titular exacto
    y la nota dice 'baleada', no 'asesinato' (la palabra que uso Fernando en
    su pregunta) -- la subcadena completa jamas aparecia tal cual. Ahora
    alcanza con que la MAYORIA de las palabras significativas (>=4 letras)
    de la consulta aparezcan en el titular+resumen (sin tildes, por eso
    _norm_q en los dos lados) -- si la consulta tiene 1-2 palabras utiles,
    con 1 sola coincidencia alcanza; con 3 o mas, se exige al menos la
    mitad. Sin ninguna palabra util en la consulta (ej. solo stopwords),
    cae de respaldo a la subcadena literal de siempre, para no romper una
    consulta corta y exacta que ya funcionaba."""
    qt = _tokens_q(q)
    blob = _norm_q((titular or "") + " " + (resumen or ""))
    if not qt:
        return _norm_q(q) in blob
    hits = sum(1 for t in qt if t in blob)
    minimo = 1 if len(qt) <= 2 else max(1, (len(qt) + 1) // 2)
    return hits >= minimo

# BUG REAL encontrado probando el ciclo de herramientas en vivo (Bloque 2):
# el modelo que decide que consultar no siempre reproduce el nombre EXACTO
# del catalogo de temas (ej. paso "carceles" en vez de "Carceles") aunque el
# prompt le muestre la lista -- mismo problema que ya resolvio ia.py para la
# clasificacion por lotes (_TEMA_LOOKUP). Se normaliza minuscula/espacios
# antes de comparar en cualquier funcion que reciba un 'tema'.
_TEMA_LOOKUP = {t.strip().lower(): t for bank in KEYWORDS.values() for t in bank}


def _normalizar_tema(tema):
    if not tema:
        return tema
    return _TEMA_LOOKUP.get(str(tema).strip().lower(), tema)


def _cargar(nombre, default):
    try:
        with open(os.path.join(HERE, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _historias():
    return (_cargar("data.json", {}) or {}).get("historias", [])


def _clave(h):
    f0 = (h.get("fuentes") or [{}])[0]
    return (f0.get("link") or h.get("titular") or "")[:180]


def _resumen_historia(h):
    # Fase 6, pendiente 3 (Bloque 2): antes esto mandaba campos "crudos" del
    # dato (ej. veredicto_contraste="pendiente", veredicto_texto="Todavia no
    # procesado") que el modelo terminaba citando casi textual en la
    # respuesta final como si fuera informacion real -- se filtra aca, antes
    # de armar el material, en vez de confiar en que el prompt le diga al
    # modelo que ignore un valor sin contenido real.
    v = h.get("veredicto") or {}
    veredicto_real = v.get("estado") not in (None, "", "pendiente")
    return {
        "clave": _clave(h),
        "titular": h.get("titular"),
        "seccion": h.get("seccion"),
        "temas": h.get("temas") or [],
        "ambito": h.get("ambito"),
        "ciudad": h.get("ciudad") or None,
        "medios": h.get("outlets") or [],
        "n_outlets": h.get("n_outlets"),
        "resumen": h.get("resumen"),
        "interpretacion_ia": h.get("ia") or None,
        "horas_desde_publicada": h.get("hours"),
        "interes": h.get("interes"),
        "demanda_busqueda": h.get("demanda"),
        "veredicto_contraste": v.get("estado") if veredicto_real else None,
        "veredicto_texto": v.get("texto") if veredicto_real else None,
        "n_contratos_sercop": len(h.get("contratos") or []),
        "n_verificaciones_factcheck": len(h.get("factcheck") or []),
    }


# ------------------------- 1. historias del feed -------------------------

def buscar_historias(tema=None, ambito=None, seccion=None, medio=None, q=None,
                      dias=None, veredicto=None, limite=15):
    """Busca historias del feed actual por tema, ambito (local/internacional),
    seccion (politica/economia/seguridad/sociedad/general), medio (nombre o
    parte del nombre de un outlet), texto libre (q, busca en titular+resumen),
    antiguedad maxima en dias, y 'veredicto' del sector Contraste ("coincide",
    "contradice", "sin_datos" o "pendiente") -- usar veredicto="contradice"
    para preguntas del tipo "hay contradicciones entre medios" en vez de
    adivinar con otra herramienta (el propio monitor YA calcula ese veredicto
    por historia, cruzando contexto+SERCOP+FactCheck, ver Contraste). Devuelve
    resumenes cortos, ordenados por interes (mas relevante primero). 'limite'
    acota cuantos devuelve (evita saturar el contexto del modelo)."""
    tema = _normalizar_tema(tema)
    # Tolerante a sinonimos comunes que el modelo puede usar en vez de los
    # dos valores reales ("local"/"internacional") -- mismo motivo que
    # _normalizar_tema: el prompt lo pide bien pero un modelo chico no
    # siempre lo respeta al pie de la letra.
    if ambito:
        al = str(ambito).strip().lower()
        ambito = "local" if al in ("local", "ecuador", "guayaquil") else (
                  "internacional" if al in ("internacional", "mundo", "exterior") else ambito)
    out = []
    for h in _historias():
        if tema and tema not in (h.get("temas") or []):
            continue
        if ambito and h.get("ambito") != ambito:
            continue
        if seccion and h.get("seccion") != seccion:
            continue
        if medio:
            ml = medio.lower()
            if not any(ml in (o or "").lower() for o in (h.get("outlets") or [])):
                continue
        if dias is not None:
            horas = h.get("hours")
            if horas is None or horas > float(dias) * 24:
                continue
        if q and not _coincide_texto_libre(q, h.get("titular", ""), h.get("resumen", "")):
            continue
        if veredicto and (h.get("veredicto") or {}).get("estado") != veredicto:
            continue
        out.append(h)
    out.sort(key=lambda h: -(h.get("interes") or 0))
    return [_resumen_historia(h) for h in out[:limite]]


def detalle_historia(clave):
    """Trae el detalle COMPLETO de una historia por su clave (la que devuelve
    buscar_historias/buscar_guardadas) o por titular exacto: contexto
    verificado (Wikipedia/GDELT), veredicto de Contraste con sus citas,
    contratos SERCOP y verificaciones FactCheck asociadas. Usar despues de
    buscar_historias/buscar_guardadas para profundizar en UNA nota puntual."""
    fuentes = [("data.json_historias", _historias()), ("saved.json", _cargar("saved.json", []))]
    for _, items in fuentes:
        for h in items:
            if _clave(h) == clave or h.get("titular") == clave:
                ctx = h.get("contexto") or {}
                v = h.get("veredicto") or {}
                veredicto_real = v.get("estado") not in (None, "", "pendiente")
                return {
                    "clave": _clave(h),
                    "titular": h.get("titular"),
                    "resumen": h.get("resumen"),
                    "medios": h.get("outlets") or [],
                    "fuentes": [{"medio": f.get("outlet"), "titulo": f.get("title"),
                                 "link": f.get("link"), "fecha": f.get("date")}
                                for f in (h.get("fuentes") or [])],
                    "interpretacion_ia": h.get("ia") or None,
                    "contexto_verificado": (ctx.get("texto")
                        if ctx.get("texto") not in (None, "", "sin contexto disponible", "analizando…")
                        else None),
                    "entidades_verificadas": [
                        {"nombre": e.get("nombre"), "extracto": e.get("extracto"), "url": e.get("url")}
                        for e in (ctx.get("entidades") or [])
                    ],
                    "tambien_aparecio_antes": ctx.get("previas") or [],
                    # Fase 11 (v2): los 4 bloques nuevos de contexto.py -- el
                    # Asistente puede citarlos igual que cualquier otro dato
                    # ya verificado (cada afirmacion ya trae sus propios ids
                    # de fuente, validados en codigo antes de guardarse).
                    "antecedentes": ctx.get("antecedentes") or [],
                    "actores": ctx.get("actores") or [],
                    "que_es_nuevo": ctx.get("que_es_nuevo") or [],
                    "que_falta_saber": ctx.get("que_falta_saber") or [],
                    "limitaciones_contexto": ctx.get("limitaciones") or None,
                    "veredicto_contraste": v.get("estado") if veredicto_real else None,
                    "veredicto_texto": v.get("texto") if veredicto_real else None,
                    "veredicto_citas": (v.get("citas") or []) if veredicto_real else [],
                    "contratos_sercop": [
                        {"entidad": c.get("entidad"), "objeto": c.get("objeto"),
                         "monto": c.get("monto"), "fecha": c.get("fecha")}
                        for c in (h.get("contratos") or [])[:8]
                    ],
                    "verificaciones_factcheck": [
                        {"calificacion": fc.get("textualRating") or fc.get("calificacion"),
                         "verificador": fc.get("publisher") or fc.get("verificador"),
                         "titulo": fc.get("title") or fc.get("titulo"), "url": fc.get("url")}
                        for fc in (h.get("factcheck") or [])[:5]
                    ],
                }
    return None


# ------------------------- 2. Guardadas y notas (contenido de Fernando) -------------------------

def buscar_guardadas(q=None, limite=20):
    """Busca entre las historias que Fernando guardo a mano para reportaje
    (saved.json). 'q' filtra por texto libre en titular+resumen; sin 'q'
    devuelve las guardadas mas recientes."""
    items = _cargar("saved.json", [])
    items = sorted(items, key=lambda h: h.get("_guardado_ts") or "", reverse=True)
    out = []
    for h in items:
        if q and not _coincide_texto_libre(q, h.get("titular", ""), h.get("resumen", "")):
            continue
        r = _resumen_historia(h)
        r["guardado_el"] = h.get("_guardado_ts")
        out.append(r)
        if len(out) >= limite:
            break
    return out


def buscar_notas(q=None):
    """Busca entre las notas personales que Fernando escribio sobre una
    historia o un tema (notas.json). 'q' filtra por texto libre; sin 'q'
    devuelve todas."""
    notas = _cargar("notas.json", {})
    out = []
    for clave, n in notas.items():
        if q and not _coincide_texto_libre(q, n.get("titular", ""), n.get("texto", "")):
            continue
        out.append({"clave": clave, "titular": n.get("titular") or None,
                     "texto": n.get("texto"), "fecha": n.get("ts")})
    out.sort(key=lambda n: n.get("fecha") or "", reverse=True)
    return out


# ------------------------- 3. demanda / cobertura / pulso social por tema -------------------------

def tendencia_tema(tema):
    """Para UN tema del catalogo (ej. 'Carceles', 'Ejecutivo', 'Empleo'):
    cuanto se busca en Google Trends/Wikipedia (demanda, 0-100 relativo),
    volumen y tono de cobertura de prensa (GDELT) si hay dato, y el pulso
    social ya calculado (sentimiento, polarizacion, volumen de posts) si se
    consulto ese tema en la ultima pasada. Cualquier campo puede venir null
    si esta fuente no tuvo dato esta corrida -- eso NO es un error, es
    honesto: hay que decirlo asi, no inventar un numero."""
    tema = _normalizar_tema(tema)
    d = _cargar("data.json", {})
    gdelt = (d.get("gdelt") or {}).get(tema)
    social = (d.get("social") or {}).get(tema)
    # Misma cuenta que demandaTema() en dashboard_template.html: promedio de
    # los ultimos 7 puntos completos (se excluye el ultimo, que puede venir
    # parcial), sobre la serie cruda 'v' de DATA.tendencias[tema].
    serie = ((d.get("tendencias") or {}).get(tema) or {}).get("v") or []
    if serie:
        cola = serie[-8:-1] if len(serie) > 1 else serie
        demanda_tema = round(sum(cola) / len(cola)) if cola else None
    else:
        demanda_tema = None
    return {
        "tema": tema,
        "demanda_busqueda_0_100": demanda_tema,
        "fuente_demanda": d.get("fuente_interes"),
        "estado_demanda": d.get("estado_interes"),
        "cobertura_prensa_gdelt": ({"volumen_serie": gdelt.get("vol"), "tono": gdelt.get("tone")}
                                    if gdelt else None),
        "estado_gdelt": d.get("estado_gdelt"),
        "pulso_social": ({"n_posts": social.get("n_posts"), "n_personas": social.get("n_personas"),
                           "n_medios": social.get("n_medios"), "sentimiento": social.get("sentimiento"),
                           "polarizacion": social.get("polarizacion"),
                           "temas_recurrentes": social.get("temas_recurrentes"),
                           "resumen_discusion": social.get("resumen"),
                           "ambito": social.get("ambito")}
                          if social else None),
        "estado_social": d.get("estado_social"),
    }


def angulos_reportaje(ambito=None, limite=8):
    """Fase 6, pendiente 1 (Bloque 2): temas con brecha entre INTERES PUBLICO
    (demanda de busqueda o conversacion en redes, la que sea mayor) y
    COBERTURA de medios (cuantas historias del feed actual tocan ese tema) --
    exactamente la misma logica que ya usa el panel Oportunidades
    (renderGap() en el dashboard), para que el Asistente pueda responder
    "que angulo de reportaje me recomendarias" cruzando el dato el mismo en
    vez de tener que inferirlo el solo llamando tendencia_tema tema por tema.

    'ambito': None/"" (todos), "local" (Ecuador/Guayaquil) o "internacional".
    Devuelve una lista ordenada por brecha descendente (mas desatendido
    primero), cada item con {tema, interes_publico_0_100, cobertura_actual,
    brecha, señal (de donde sale el interes), notas_ya_publicadas (hasta 3,
    para que el Asistente pueda citarlas si ya hay algo escrito)}. Nunca
    inventa un tema sin dato: si ningun tema tiene ni demanda ni pulso social
    esta corrida, devuelve lista vacia con 'nota' explicando por que."""
    d = _cargar("data.json", {})
    historias = d.get("historias") or []
    if ambito == "local":
        H = [h for h in historias if h.get("es_local")]
    elif ambito == "internacional":
        H = [h for h in historias if h.get("internacional")]
    else:
        H = historias

    cov = {}
    for h in H:
        for t in (h.get("temas") or []):
            cov[t] = cov.get(t, 0) + 1
    cov_max = max([1] + list(cov.values()))

    tend = d.get("tendencias") or {}
    def _demanda(t):
        serie = (tend.get(t) or {}).get("v") or []
        if not serie:
            return None
        cola = serie[-8:-1] if len(serie) > 1 else serie
        return round(sum(cola) / len(cola)) if cola else None

    social_all = d.get("social") or {}
    soc = {}
    for t, s in social_all.items():
        amb = s.get("ambito")
        if ambito == "local" and amb not in ("ecuador", "guayaquil"):
            continue
        if ambito == "internacional" and amb != "internacional":
            continue
        if s.get("n_posts"):
            soc[t] = s
    soc_max = max([1] + [soc[t].get("n_posts", 0) for t in soc])
    def _social(t):
        s = soc.get(t)
        return round(100 * s["n_posts"] / soc_max) if s else None

    temas = set(tend) | set(soc) | set(cov)
    filas = []
    for t in temas:
        db, ds = _demanda(t), _social(t)
        if db is None and ds is None:
            continue  # sin ninguna señal de interes esta corrida -- no se inventa
        interes = max(x for x in (db, ds) if x is not None)
        c = cov.get(t, 0)
        brecha = round(interes - 100 * c / cov_max)
        senal = ("busqueda %s/100 y redes %s/100" % (db, ds)) if (db is not None and ds is not None) \
            else ("redes %s/100 (relativo, sin dato de busqueda esta corrida)" % ds) if ds is not None \
            else ("busqueda %s/100" % db)
        notas = [{"titular": h.get("titular"), "link": (h.get("fuentes") or [{}])[0].get("link")}
                 for h in H if t in (h.get("temas") or [])][:3]
        filas.append({"tema": t, "interes_publico_0_100": interes, "cobertura_actual": c,
                      "brecha": brecha, "señal": senal, "notas_ya_publicadas": notas})
    filas.sort(key=lambda r: r["brecha"], reverse=True)
    if not filas:
        return {"angulos": [], "nota": "ningun tema tiene demanda de busqueda ni pulso social esta corrida"}
    return {"angulos": filas[:limite]}


def comparar_periodo(tema=None, dias_atras=7):
    """Compara la cobertura de HOY contra hace 'dias_atras' dias, usando el
    historial de corridas (history.json: una foto de conteos por
    seccion/ambito/tema en cada pasada del feed desde que el monitor esta
    corriendo). Si 'tema' se especifica, compara solo ese tema (cuantas
    historias tenia entonces vs. ahora); sin 'tema', compara la distribucion
    completa por tema. Si el historial no llega tan atras (el monitor no
    lleva corriendo esa cantidad de dias), devuelve el punto MAS VIEJO
    disponible y lo dice explicitamente en 'nota'."""
    tema = _normalizar_tema(tema)
    hist = _cargar("history.json", [])
    if not hist:
        return {"error": "sin historial todavia"}
    ahora = hist[-1]
    objetivo = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=float(dias_atras))

    def _ts(snap):
        try:
            return dt.datetime.fromisoformat(snap.get("ts", "").replace("Z", "+00:00"))
        except Exception:
            return None

    candidatos = [(s, _ts(s)) for s in hist]
    candidatos = [(s, t) for s, t in candidatos if t is not None and t <= dt.datetime.now(dt.timezone.utc)]
    if not candidatos:
        return {"error": "sin historial con fecha valida"}
    pasado, pasado_ts = min(candidatos, key=lambda st: abs(st[1] - objetivo))
    nota = None
    if pasado_ts > objetivo:
        nota = ("el monitor no tiene historial de hace %s dias todavia -- se compara "
                "contra el punto mas viejo disponible (%s)" % (dias_atras, pasado.get("ts")))
    if tema:
        return {"tema": tema, "ahora": (ahora.get("temas") or {}).get(tema, 0),
                "hace_dias": (pasado.get("temas") or {}).get(tema, 0),
                "fecha_comparada": pasado.get("ts"), "nota": nota}
    return {"ahora_por_tema": ahora.get("temas") or {}, "hace_dias_por_tema": pasado.get("temas") or {},
            "fecha_comparada": pasado.get("ts"), "nota": nota}


def buscar_contratos_sercop(termino):
    """Busca contratos publicos (SERCOP, Contrataciones Abiertas) ya
    consultados por el monitor para un termino (ej. un ministerio, una
    entidad, un tema). Solo revisa lo que YA esta en cache (no dispara una
    consulta nueva a SERCOP) -- si el termino nunca se busco en una corrida
    anterior, devuelve una lista vacia con 'consultado=False', no un error."""
    cache = _cargar("sercop_cache.json", {})
    terms = cache.get("terms") or {}
    tl = termino.lower()
    coincidencias = {k: v for k, v in terms.items() if tl in k.lower()}
    if not coincidencias:
        return {"consultado": False, "contratos": []}
    contratos = []
    for _, lst in coincidencias.items():
        for c in (lst or [])[:10]:
            contratos.append({"entidad": c.get("entidad"), "objeto": c.get("objeto"),
                               "monto": c.get("monto"), "fecha": c.get("fecha")})
    return {"consultado": True, "contratos": contratos[:15]}


# ------------------------- Fase 3: base de contraste oficial -------------------------

try:
    import oficial as _oficial
except Exception:
    _oficial = None


def buscar_constitucion(termino):
    """Busca articulos de la Constitucion del Ecuador de 2008 por texto
    libre (ej. 'libertad de expresion', 'debido proceso'). Fuente: una
    transcripcion verificada (Wikisource), NO el PDF oficial escaneado --
    aclarar eso si se cita. Devuelve una lista de {numero, texto, fuente}
    (vacia si el indice todavia no se construyo o nada coincide -- nunca
    inventa un articulo)."""
    if not _oficial:
        return []
    return _oficial.buscar_constitucion(termino)


def buscar_boletines_oficiales(termino):
    """Busca en los boletines YA CACHEADOS de instituciones publicas
    ecuatorianas (Asamblea Nacional, INEC, Banco Central, Registro Oficial)
    por texto libre -- datos oficiales para contrastar cifras/afirmaciones
    de una noticia (ej. una cifra de inflacion, un anuncio legislativo).
    Nunca dispara una consulta nueva. Vacio si no hay cache todavia o nada
    coincide."""
    if not _oficial:
        return []
    return _oficial.buscar_oficial(termino)


# ------------------------- Fase 5: declaraciones con el pasado -------------------------

try:
    import declaraciones as _decl
except Exception:
    _decl = None


def buscar_declaraciones(actor):
    """Busca declaraciones YA REGISTRADAS de un actor (persona con cargo
    publico, ej. 'Daniel Noboa', 'el ministro de Salud') -- que dijo, cuando,
    segun que medio, y si alguna quedo marcada como POSIBLE CONTRADICCION con
    algo que ese mismo actor dijo antes (nunca 'falso': la calificacion final
    es de Fernando, el programa solo señala que vale la pena verificar).
    Registro propio (declaraciones.json) que NO se purga con las noticias
    viejas del feed, asi que puede traer declaraciones de hace semanas o
    meses aunque la nota original ya no este en Noticias. Nunca dispara una
    consulta nueva. Vacio si el actor no tiene declaraciones registradas
    todavia (el registro recien empieza a llenarse de a poco, pasada por
    pasada del trabajador)."""
    if not _decl:
        return []
    return _decl.de_actor(actor)


# Catalogo de herramientas para el agente (agente.py): nombre -> (funcion, descripcion de args).
# La descripcion es la que se le muestra al modelo en el prompt del ciclo de
# herramientas -- mismo criterio de siempre, texto claro en vez de un schema
# JSON formal (un modelo de 3B sigue mejor instrucciones en prosa simple que
# un JSON-schema estricto, ver PREFER/formato de prompts en ia.py).
HERRAMIENTAS = {
    "buscar_historias": buscar_historias,
    "detalle_historia": detalle_historia,
    "buscar_guardadas": buscar_guardadas,
    "buscar_notas": buscar_notas,
    "tendencia_tema": tendencia_tema,
    "angulos_reportaje": angulos_reportaje,
    "comparar_periodo": comparar_periodo,
    "buscar_contratos_sercop": buscar_contratos_sercop,
    "buscar_constitucion": buscar_constitucion,
    "buscar_boletines_oficiales": buscar_boletines_oficiales,
    "buscar_declaraciones": buscar_declaraciones,
}
