# -*- coding: utf-8 -*-
"""
Fase 9, Problema D / D3 (version Apify, 2026-09-25/26) -- X vía un actor de
terceros de Apify, sin cuenta logueada de X. Decision de Fernando (ver
CLAUDE.md, "Decisiones ya tomadas"): riesgo real registrado a proposito --
esto NO es un acceso autorizado por X, puede dejar de funcionar sin aviso si
X bloquea al actor, y cualquier dato que termine publicado debe verificarse
contra el tweet original antes de citarlo como un hecho. Sigue prohibido
usar una cuenta propia logueada o scrapear X directamente desde este
programa (la unica via es este actor de Apify).

Arquitectura de PROVEEDOR: xapi.py es solo el "hablador con Apify para X" --
sabe pedir tweets y calcular su costo, pero NO decide presupuesto ni
frecuencia por si solo. Eso es trabajo de `redes.py` (Fase 9, parte D3), el
orquestador COMPARTIDO entre X y TikTok (`tiktok.py`) que reparte un solo
presupuesto mensual entre las dos redes con ritmo diario dinamico. Este
modulo tampoco decide backend "oficial" -- BACKEND queda como interruptor
simple (hoy solo "apify" hace algo real; "oficial" es un stub sin logica,
guardado por si Fernando algun dia prefiere pagar la API oficial de X en vez
de Apify).

Solo libreria estandar (urllib/json), standalone -- salvo `social.py`, ya
standalone tambien, reusado SOLO para es_cuenta_medio().

Verificado en vivo el 2026-09-26 con la cuenta de Fernando (ver CLAUDE.md):
actor "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest",
$0.00025/tweet (plan FREE de Apify, $5 de credito gratis al mes), entrada
{"searchTerms":[...], "maxItems":20, "queryType":"Latest", "lang":"es"}
devolvio 20 tweets reales en ~25s con los campos documentados abajo. Costo
real reportado por Apify para esa corrida: $0 (ver CLAUDE.md, "hallazgo real"
-- puede ser un umbral de cortesia del actor antes de cobrar contra el
credito mensual, no confirmado del todo).
"""
import datetime as dt
import json
import os
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

try:
    import social  # SOLO para es_cuenta_medio() -- ya standalone, sin import circular
except Exception:
    social = None

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Monitor-Noticias/1.0 (uso personal, prueba de un mes via Apify)"
TIMEOUT_CORTO = 20
TIMEOUT_CORRIDA = 130  # una corrida real del actor midio ~25s; se deja margen generoso

APIFY_BASE = "https://api.apify.com/v2"

CONFIG_PATH = os.path.join(HERE, "x_config.json")
CACHE_PATH = os.path.join(HERE, "x_cache.json")
# Fase 18 (P1-5.2): cuentas que informan en tiempo real (ATM, ECU 911,
# Bomberos, Municipio...). Archivo EDITABLE por Fernando (no es un secreto).
CUENTAS_PATH = os.path.join(HERE, "x_cuentas_locales.json")  # cache OPERATIVO (ids vistos, tweets por historia) -- el gasto vive en redes.py

last_error = None

# "apify" es el UNICO backend activo hoy. "oficial" queda como stub -- nunca
# se activa solo, hay que poner MONITOR_X_BACKEND=oficial a proposito, y hoy
# no hace nada real (ver _backend_oficial_no_implementado abajo).
BACKEND = os.environ.get("MONITOR_X_BACKEND", "apify")

# ------------------------- Apify: actores verificados -------------------------
ACTOR_PRINCIPAL = "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest"
ACTOR_RESPALDO = "apidojo~tweet-scraper"
PRECIO_TWEET_PRINCIPAL = 0.00025
PRECIO_TWEET_RESPALDO = 0.0004


def _leer_token():
    """MONITOR_APIFY_TOKEN o x_config.json ({"apify_token": "..."}). El token
    NUNCA se imprime, ni en data.json, ni en last_error, ni en ninguna URL
    logueada -- todas las funciones de este modulo arman URLs con el token
    pero ningun mensaje de error las repite tal cual (ver _error_http). Es
    la MISMA cuenta/token que usa tiktok.py (ambas redes via Apify)."""
    tok = os.environ.get("MONITOR_APIFY_TOKEN", "").strip()
    if tok:
        return tok
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return (json.load(f).get("apify_token") or "").strip()
    except Exception:
        return ""


def activo():
    return BACKEND == "apify" and bool(_leer_token())


def costo_estimado(max_items, actor=ACTOR_PRINCIPAL):
    precio = PRECIO_TWEET_PRINCIPAL if actor == ACTOR_PRINCIPAL else PRECIO_TWEET_RESPALDO
    return max_items * precio


# ------------------------- cache OPERATIVO (ids vistos, tweets por historia) -------------------------
# El GASTO (dinero) vive en redes.py (redes_gasto.json, compartido con
# TikTok) -- esto es solo estado propio de X: que tweets ya se vieron, que
# tweets trajo cada historia la ultima vez, y la frecuencia de cada capa.

def _cargar_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_cache(cache):
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def _ids_vistos(clave):
    return set(_cargar_cache().get("vistos", {}).get(clave, []))


def _marcar_vistos(clave, ids):
    if not ids:
        return
    cache = _cargar_cache()
    vistos = cache.setdefault("vistos", {})
    actuales = set(vistos.get(clave, [])) | set(ids)
    vistos[clave] = list(actuales)[-500:]  # tope: no crecer sin limite
    _guardar_cache(cache)


def guardar_tweets_historia(link, tweets):
    cache = _cargar_cache()
    hs = cache.setdefault("historias", {})
    hs[link] = {"tweets": tweets, "ts": dt.datetime.now(dt.timezone.utc).isoformat()}
    _guardar_cache(cache)


def tweets_de_historia(link):
    return _cargar_cache().get("historias", {}).get(link, {}).get("tweets", [])


# ------------------------- llamada real a Apify (unico punto que golpea la red) -------------------------

def _error_http(e):
    """Nunca repite la URL (que lleva el token en la query) -- solo el
    codigo HTTP, con el motivo tipico de cada uno."""
    if e.code == 401:
        return "HTTP 401 (token de Apify invalido)"
    if e.code == 402:
        return "HTTP 402 (sin credito disponible en la cuenta de Apify)"
    if e.code == 429:
        return "HTTP 429 (limite de tasa de Apify)"
    return "HTTP %s" % e.code


def _run_actor(actor, input_dict, espera_seg=TIMEOUT_CORRIDA, tope_seguridad_usd=0.30):
    """Corre un actor de Apify de punta a punta (X o TikTok -- generico,
    tiktok.py tambien la usa): dispara la corrida de forma ASINCRONA con
    waitForFinish (asi Apify da el runId directo, a diferencia del endpoint
    sync-get-dataset-items, que NO lo devuelve -- se necesita para consultar
    el costo REAL despues). 'tope_seguridad_usd' viaja SIEMPRE como
    maxTotalChargeUsd -- una red de seguridad de Apify (nunca el control
    primario: ese lo hace redes.py ANTES de llamar aca, decidiendo si
    corresponde llamar y con que max_items). Devuelve (items,
    costo_real_o_None, run_id_o_None)."""
    global last_error
    token = _leer_token()
    params = {"token": token, "waitForFinish": str(espera_seg),
              "maxTotalChargeUsd": "%.4f" % max(tope_seguridad_usd, 0.001)}
    url = "%s/acts/%s/runs?%s" % (APIFY_BASE, actor, urllib.parse.urlencode(params))
    body = json.dumps(input_dict).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=espera_seg + 15) as r:
            run_data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        last_error = _error_http(e)
        return None, None, None
    except Exception as e:
        last_error = type(e).__name__
        return None, None, None

    data = run_data.get("data", {})
    run_id = data.get("id")
    dataset_id = data.get("defaultDatasetId")
    if not dataset_id:
        last_error = "Apify no devolvio defaultDatasetId (estado de la corrida: %s)" % (data.get("status") or "?")
        return None, None, run_id

    items_url = "%s/datasets/%s/items?token=%s" % (APIFY_BASE, dataset_id, urllib.parse.quote(token))
    try:
        with urllib.request.urlopen(items_url, timeout=TIMEOUT_CORTO) as r:
            items = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        last_error = _error_http(e)
        return None, None, run_id
    except Exception as e:
        last_error = "no se pudo leer el dataset: %s" % type(e).__name__
        return None, None, run_id

    # Costo REAL de la corrida -- best effort: si Apify no lo expone como se
    # espera, el llamador usa el costo ESTIMADO en su lugar.
    costo_real = None
    try:
        info_url = "%s/actor-runs/%s?token=%s" % (APIFY_BASE, run_id, urllib.parse.quote(token))
        with urllib.request.urlopen(info_url, timeout=TIMEOUT_CORTO) as r:
            info = json.loads(r.read().decode("utf-8")).get("data", {})
        costo_real = info.get("usageTotalUsd")
        if not isinstance(costo_real, (int, float)):
            costo_real = None
    except Exception:
        pass
    return items, costo_real, run_id


def _buscar(search_terms, max_items=20, query_type="Latest", lang="es", actor=ACTOR_PRINCIPAL,
            simular=False, tope_seguridad_usd=0.30):
    """Llamada de bajo nivel: NO decide presupuesto (eso ya lo decidio
    redes.py antes de llamar aca) -- solo ejecuta o simula. Devuelve (items,
    costo_real_o_estimado). 'search_terms': lista de strings."""
    global last_error
    last_error = None
    if BACKEND != "apify":
        last_error = "backend '%s' no implementado" % BACKEND
        return None, 0.0
    if not _leer_token():
        last_error = "desactivado: falta token de Apify (MONITOR_APIFY_TOKEN / x_config.json)"
        return None, 0.0
    costo_max = costo_estimado(max_items, actor)
    if simular:
        return {"_simulado": True, "_costo_proyectado": costo_max,
                "_search_terms": search_terms, "_max_items": max_items}, 0.0
    input_dict = {"searchTerms": search_terms, "maxItems": max_items, "queryType": query_type, "lang": lang}
    items, costo_real, _run_id = _run_actor(actor, input_dict, tope_seguridad_usd=tope_seguridad_usd)
    if items is None:
        return None, 0.0
    costo_final = costo_real if costo_real is not None else costo_max
    return items, costo_final


# ------------------------- capa 1: historias -------------------------

def buscar_historia(query, max_items=25, simular=False, tope_seguridad_usd=0.30):
    """Tweets de una historia puntual, lang:es, ordenado por 'Latest'.
    'query' ya viene armado por el llamador con las entidades de la
    historia (nombres/siglas/lugar), NUNCA con el nombre de una categoria."""
    return _buscar([query], max_items=max_items, simular=simular, tope_seguridad_usd=tope_seguridad_usd)


# ------------------------- capa 2: debate (respuestas a un tweet) -------------------------

def respuestas_de(conversation_id, max_items=30, simular=False, tope_seguridad_usd=0.30):
    """Respuestas al tweet mas respondido de una historia (el 'debate'),
    via 'conversation_id:<id>'. Si el actor principal no soporta ese
    operador (0 resultados o error), reintenta con el actor de RESPALDO
    (apidojo/tweet-scraper), que documenta 'conversationIds' en su input --
    mas caro ($0.0004/tweet), asi que solo se usa si el principal falla."""
    items, costo = _buscar(["conversation_id:%s" % conversation_id], max_items=max_items,
                            simular=simular, tope_seguridad_usd=tope_seguridad_usd)
    if simular:
        return items, costo
    if items:  # el operador funciono y trajo algo
        return items, costo
    if last_error and last_error.startswith("desactivado"):
        return items, costo  # sin token: el respaldo tampoco va a funcionar
    return _respuestas_de_respaldo(conversation_id, max_items, tope_seguridad_usd)


def _respuestas_de_respaldo(conversation_id, max_items=30, tope_seguridad_usd=0.30):
    global last_error
    if BACKEND != "apify" or not _leer_token():
        return None, 0.0
    costo_max = costo_estimado(max_items, ACTOR_RESPALDO)
    items, costo_real, _run_id = _run_actor(ACTOR_RESPALDO, {"conversationIds": [conversation_id], "maxItems": max_items},
                                             tope_seguridad_usd=tope_seguridad_usd)
    if items is None:
        return None, 0.0
    costo_final = costo_real if costo_real is not None else costo_max
    return items, costo_final


# ------------------------- capa 3: alertas Guayaquil -------------------------

def buscar_alertas_gye(terminos_tipo, barrios, max_items=10, simular=False, tope_seguridad_usd=0.30):
    """Una consulta combinando tipos de alerta + Guayaquil. Se arman
    terminos COMPUESTOS ('incendio Guayaquil', no sueltos) -- el unico
    formato probado en vivo con este actor (ver docstring del modulo);
    terminos SUELTOS corren el riesgo real de que el actor trate cada uno
    como busqueda INDEPENDIENTE y devuelva 'incendio' de cualquier pais.
    Dedup por id ya visto: un tweet que ya se proceso no vuelve a contarse."""
    terms = ["%s Guayaquil" % t for t in terminos_tipo[:8]]
    items, costo = _buscar(terms, max_items=max_items, query_type="Latest",
                            simular=simular, tope_seguridad_usd=tope_seguridad_usd)
    if simular or items is None:
        return items, costo
    vistos = _ids_vistos("alertas_gye")
    nuevos = [t for t in items if str(t.get("id", "")) not in vistos]
    _marcar_vistos("alertas_gye", [str(t.get("id", "")) for t in items])
    return nuevos, costo


# ------------------------- clasificacion de autores (persona/medio/institucion/politico) -------------------------
CUENTAS_INSTITUCION = {
    "emapagye", "municipioguayaquil", "alcaldiagye", "ecu911ecuador", "ecu911",
    "policiaecuador", "bomberosgye", "cuerpodebomberosgye", "prefecturaguayas",
    "inamhiecuador", "gestionriesgos_ec", "inocarecuador", "cnelep",
}
_PALABRAS_POLITICO = ("alcalde", "alcaldesa", "asambleista", "asambleísta", "concejal",
                       "prefecto", "prefecta", "ministro", "ministra", "candidato", "candidata")


def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def clasificar_autor(tweet):
    """persona/medio/institucion/politico. Usa social.es_cuenta_medio()
    (misma heuristica de siempre) + una lista editable de cuentas
    institucionales + palabras de cargo en la bio."""
    author = tweet.get("author") or {}
    username = author.get("userName") or ""
    name = author.get("name") or ""
    desc = _sin_acentos(author.get("description") or "").lower()
    if social and social.es_cuenta_medio(username, name):
        return "medio"
    if _sin_acentos(username).lower() in CUENTAS_INSTITUCION:
        return "institucion"
    if any(p in desc for p in _PALABRAS_POLITICO):
        return "politico"
    return "persona"


def _menciona_entidad(texto, entidades):
    t = _sin_acentos(texto or "").lower()
    return any(_sin_acentos(e).lower() in t for e in (entidades or []) if len(e) >= 3)


def fecha_iso(created_at):
    """'Sat Sep 26 00:44:19 +0000 2026' (formato clasico de X, confirmado en
    vivo) -> ISO 8601. Cadena vacia si no se pudo parsear."""
    try:
        d = dt.datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return d.isoformat()
    except Exception:
        return ""


def tweet_pertenece(tweet, entidades):
    """Filtro de pertenencia: si el AUTOR no dice ubicarse en Ecuador y el
    TEXTO no menciona ninguna entidad de la historia, se descarta."""
    author = tweet.get("author") or {}
    loc = _sin_acentos(author.get("location") or "").lower()
    if any(w in loc for w in ("ecuador", "guayaquil", "quito", "cuenca", " ec", "gye")):
        return True
    return _menciona_entidad(tweet.get("text", ""), entidades)


# ------------------------- Fase 18 (P1-5): consultas que encuentran lo que pasa AHORA -------------------------
# Diagnostico real (Fase 18): las alertas buscaban "corte_luz Guayaquil" y
# "corte_agua Guayaquil" (la CLAVE interna, con guion bajo -- no matchea nada
# en X), "inundacion" sin tilde, y 8 terminos repartidos en 10 tweets por
# hora (~1 por termino). Ahora: UNA consulta con OR, palabras reales con
# tilde, y 'since:' de las ultimas horas. Por si el actor no respeta 'since:',
# se vuelve a filtrar por createdAt al recibir.

def _since(horas, ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    return (ahora - dt.timedelta(hours=horas)).strftime("since:%Y-%m-%d_%H:%M:%S_UTC")


def _termino(t):
    t = (t or "").strip()
    return '"%s"' % t if " " in t else t


def _or(terminos):
    ts = [_termino(t) for t in terminos if t and t.strip()]
    if not ts:
        return ""
    return ts[0] if len(ts) == 1 else "(%s)" % " OR ".join(ts)


def consulta_alertas(terminos, lugar="Guayaquil", horas=2, ahora=None):
    return " ".join(x for x in (_or(terminos), _termino(lugar), _since(horas, ahora)) if x)


def cuentas_locales():
    """Lista de cuentas de x_cuentas_locales.json ([] si no existe)."""
    try:
        with open(CUENTAS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return [c for c in (data.get("cuentas") or []) if c.get("usuario") and c.get("activa", True)]


def consulta_cuentas(cuentas, horas=2, ahora=None):
    usuarios = ["from:%s" % c["usuario"].lstrip("@") for c in cuentas if c.get("usuario")]
    if not usuarios:
        return ""
    bloque = usuarios[0] if len(usuarios) == 1 else "(%s)" % " OR ".join(usuarios)
    return "%s %s" % (bloque, _since(horas, ahora))


def consulta_evento(evento, terminos, horas=2, ahora=None):
    """Busqueda REACTIVA para un evento en curso (historia madre): palabras
    del tipo de hecho + sectores de las notas. Sin sectores, la ciudad."""
    sectores = [x for x in (evento.get("sectores") or []) if x and x not in ("Norte", "Sur")]
    lugar = _or(sectores) if sectores else _termino(evento.get("lugar") or "Guayaquil")
    return " ".join(x for x in (_or(terminos), lugar, _since(horas, ahora)) if x)


def _dentro_de(tweet, horas):
    f = fecha_iso(tweet.get("createdAt", ""))
    if not f:
        return False
    d = dt.datetime.fromisoformat(f)
    return (dt.datetime.now(dt.timezone.utc) - d).total_seconds() <= horas * 3600


def buscar_consulta(consulta, clave_vistos, horas=2, max_items=15, simular=False, tope_seguridad_usd=0.30):
    """Una consulta ya armada. Devuelve (tweets NUEVOS de las ultimas 'horas',
    costo). Dedup por id (clave_vistos)."""
    items, costo = _buscar([consulta], max_items=max_items, query_type="Latest",
                            simular=simular, tope_seguridad_usd=tope_seguridad_usd)
    if simular or items is None:
        return items, costo
    recientes = [t for t in items if _dentro_de(t, horas)]
    vistos = _ids_vistos(clave_vistos)
    nuevos = [t for t in recientes if str(t.get("id", "")) not in vistos]
    _marcar_vistos(clave_vistos, [str(t.get("id", "")) for t in items])
    return nuevos, costo


def buscar_alertas(terminos, lugar="Guayaquil", horas=2, max_items=15, simular=False, tope_seguridad_usd=0.30):
    return buscar_consulta(consulta_alertas(terminos, lugar, horas), "alertas_gye", horas=horas,
                           max_items=max_items, simular=simular, tope_seguridad_usd=tope_seguridad_usd)


# ------------------------- backend "oficial" (stub) -------------------------
def _backend_oficial_no_implementado():
    return "backend 'oficial' es un stub -- no implementado (activo hoy: 'apify')"
