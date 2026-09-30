# -*- coding: utf-8 -*-
"""
Vistas de articulos de Wikipedia (es) como senal de INTERES publico — solo stdlib.

A diferencia de Google Trends, la API de Wikimedia es oficial, gratuita, sin clave
y estable. Mide cuanta gente lee un articulo por dia (proxy real de interes).

Robusto: resuelve el articulo correcto con la API de busqueda (por si el titulo
exacto no existe) y prueba las dos formas del endpoint de vistas. Si algo falla,
deja el motivo en wiki.last_error para poder diagnosticar.
"""

import json, datetime as dt, urllib.request, urllib.parse, urllib.error

UA = "MonitorNoticias/1.0 (proyecto estudiantil de periodismo; https://example.org)"
REST = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
APIPHP = "https://es.wikipedia.org/w/api.php"
SUMMARY = "https://es.wikipedia.org/api/rest_v1/page/summary/"
PROJECTS = ["es.wikipedia", "es.wikipedia.org"]  # se prueban en orden

last_error = None


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _resolve(term):
    """Devuelve el titulo del articulo mas relevante para 'term', o term si falla."""
    try:
        q = urllib.parse.urlencode({"action": "query", "list": "search",
                                    "srsearch": term, "srlimit": 1, "format": "json"})
        data = _get(APIPHP + "?" + q, timeout=15)
        hits = data.get("query", {}).get("search", [])
        return hits[0]["title"] if hits else term
    except Exception:
        return term


def _views(article, days=21):
    """Serie diaria de vistas; prueba las dos formas de 'project'. Lanza si ambas fallan."""
    end = dt.date.today() - dt.timedelta(days=1)   # el dia de hoy aun no esta consolidado
    start = end - dt.timedelta(days=days)
    art = urllib.parse.quote(article.replace(" ", "_"), safe="")
    err = None
    for proj in PROJECTS:
        url = "%s/%s/all-access/all-agents/%s/daily/%s/%s" % (
            REST, proj, art, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        try:
            data = _get(url)
            items = data.get("items", [])
            if items:
                return [int(it.get("views", 0)) for it in items]
        except urllib.error.HTTPError as e:
            err = "HTTP %s" % e.code
        except Exception as e:
            err = type(e).__name__
    if err:
        raise RuntimeError(err)
    return []


def resumen(entidad, busqueda=""):
    """Verifica una entidad (nombre propio) contra Wikipedia: si tiene pagina
    REAL, devuelve {"nombre": <titulo real>, "extracto": <1-2 lineas>}. Si NO
    tiene pagina, devuelve None -> asi se descartan las entidades que la IA
    pudo haber alucinado (Parte B: 'el codigo recupera, el modelo redacta').

    Por defecto (sin 'busqueda') NO usa la busqueda de texto libre para elegir
    el titulo: pide el titulo EXACTO tal cual viene en 'entidad'. Eso evita el
    peligro de que la busqueda devuelva el articulo mas parecido POR TEXTO
    aunque no sea la entidad real (probado: 'Comandante 7' -> encontraba el
    articulo de 'Comandante en jefe', un cargo generico, no la persona).

    'busqueda' (opcional, Capa 1 del bug de Carney): frase de desambiguacion
    armada con el CONTEXTO DE LA NOTA (tema, geografia, otras entidades --
    ver ia.extraer_entidades), ej. "Mark Carney primer ministro de Canada" en
    vez de solo "Carney". Si se da, se usa PRIMERO para encontrar el titulo
    correcto via la API de busqueda (_resolve, con mas contexto que reduce el
    riesgo de homonimos), y el fetch sigue siendo el mismo de siempre --
    titulo resuelto, verificado por su pagina real, nunca inventado. Bug real
    que motivo esto: pedir el titulo EXACTO "Carney" (apellido suelto, tal
    como lo extrajo la IA del texto) resolvia -- via una redireccion REAL de
    Wikipedia, no una busqueda difusa -- a "Carney (Michigan)", una villa de
    192 habitantes, en vez de Mark Carney, primer ministro de Canada: la
    nota trataba de su disputa arancelaria con Trump. La redireccion es
    autentica (no un error de busqueda), asi que el problema no era la
    verificacion sino el nombre de entrada -- de ahi que la Capa 1 sea
    desambiguar ANTES de verificar, no relajar la verificacion en si. Esta
    funcion sigue sin aceptar una pagina de tipo 'disambiguation'; la Capa 2
    (coherencia de dominio, ver ia.coincide_dominio) es el respaldo en
    monitor.py para descartar igual una pagina real pero fuera de tema."""
    if not entidad or not entidad.strip():
        return None
    entidad = entidad.strip()
    titulo = entidad
    if busqueda and busqueda.strip():
        resuelto = _resolve(busqueda.strip())
        if resuelto:
            titulo = resuelto
    try:
        url = SUMMARY + urllib.parse.quote(titulo.replace(" ", "_"), safe="")
        data = _get(url, timeout=12)
    except urllib.error.HTTPError:
        return None  # 404: no existe pagina (ni redireccion) con ese titulo
    except Exception:
        return None
    if data.get("type") == "disambiguation":
        return None  # nombre ambiguo (varias personas/lugares): no verifica nada concreto
    extracto = (data.get("extract") or "").strip()
    if not extracto:
        return None
    # 1-2 frases, acotado en longitud para no inflar el prompt de la IA despues
    frases = _split_frases(extracto)
    corto = " ".join(frases[:2])[:280]
    return {"nombre": data.get("title") or entidad, "extracto": corto,
            "url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")}


def _split_frases(texto):
    """Separador de frases simple (sin libreria de NLP): alcanza para cortar un
    extracto de Wikipedia en sus primeras 1-2 oraciones. No es perfecto con
    abreviaturas, pero esto es solo para armar un extracto corto, no para
    analisis fino."""
    partes = [p.strip() for p in texto.split(". ") if p.strip()]
    return [p if p.endswith(".") else p + "." for p in partes]


def interest(theme_term, days=21):
    """theme_term = {tema: 'termino o titulo'}. Resuelve el articulo y trae sus vistas.
    Devuelve {tema: {"avg": int, "series": [int...], "times": [str...]}}."""
    global last_error
    last_error = None
    out, errs = {}, []
    for tema, term in theme_term.items():
        try:
            title = _resolve(term)
            serie = _views(title)
            if serie:
                tail = serie[-5:]
                out[tema] = {"avg": round(sum(tail) / len(tail)),
                             "series": serie, "times": [""] * len(serie)}
        except Exception as e:
            errs.append(str(e))
    if not out and errs:
        last_error = errs[0]
    return out
