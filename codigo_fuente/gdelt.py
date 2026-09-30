# -*- coding: utf-8 -*-
"""
GDELT DOC 2.0 — cobertura mediatica y TONO por tema (solo stdlib).

GDELT es un proyecto academico gratuito, SIN clave y sin bloqueos. Escanea miles
de medios (no tus ~20 feeds) y da, por termino y en el tiempo:
  - VOLUMEN: cuanto lo cubre la prensa (intensidad, %).
  - TONO: que tan positiva/negativa es esa cobertura (negativo = malo).
Filtra por idioma (sourcelang:spanish) y pais (sourcecountry:ecuador).

Doc: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""

import re, json, random, time, threading, urllib.request, urllib.parse, urllib.error

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
UA = "MonitorNoticias/1.0 (proyecto estudiantil periodismo)"
PAUSA = 0.5   # pausa extra entre temas. El espaciado real (>=5.5 s entre
              # consultas, lo que pide GDELT por IP) lo impone _esperar_turno().
              # Antes era 1.5 s a secas y casi todo terminaba en 429 (medido:
              # gdelt_cache.json nunca llegaba a escribirse).
last_error = None

# Nombres propios de 2+ palabras capitalizadas ("Daniel Noboa", "Corte Nacional
# de Justicia"), tolerando conectores minusculos entre medio. Aproximado (sin
# libreria de NLP): sirve para escanear TITULARES de articulos, no prosa larga.
_NOMBRE_RE = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la|los|las|y|d[ae])\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
    r"|\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+\b"
)


_turno = threading.Lock()
_ultima = [0.0]

def _esperar_turno():
    """Espaciado GLOBAL entre consultas a GDELT: ahora hay dos hilos que lo usan
    (tendencias por tema y co-menciones del contexto) y el limite de GDELT es
    por IP, no por hilo."""
    with _turno:
        falta = 5.5 - (time.time() - _ultima[0])
        if falta > 0:
            time.sleep(falta)
        _ultima[0] = time.time()


def _get(url, timeout=25):
    # reintenta una vez si GDELT responde 429 (demasiadas consultas)
    for intento in range(2):
        _esperar_turno()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace").strip()
            if not raw or raw[0] not in "{[":
                raise ValueError("respuesta no-JSON de GDELT")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento == 0:
                time.sleep(12); continue
            raise


_ULTIMAS_FECHAS = []

def _timeline(query, mode, days, timeout=30):
    """Serie de valores de un timeline de GDELT (TimelineVol o TimelineTone).
    Deja las fechas de cada punto en _ULTIMAS_FECHAS (para el eje del grafico)."""
    q = urllib.parse.urlencode({"query": query, "mode": mode, "format": "json",
                                "timespan": "%dd" % days, "timelinesmooth": 3})
    data = _get(BASE + "?" + q, timeout=timeout)
    tl = data.get("timeline") or []
    if not tl:
        return []
    pts = tl[0].get("data", [])
    _ULTIMAS_FECHAS[:] = [_fecha_corta(pt.get("date", "")) for pt in pts]
    return [pt.get("value", 0) for pt in pts]


def _fecha_corta(d):
    # GDELT: "20260922T120000Z" -> "22/09 12h"
    d = str(d or "")
    if len(d) >= 11 and d[8] == "T":
        return "%s/%s %sh" % (d[6:8], d[4:6], d[9:11])
    return d[:10]


def interest(theme_term, geo="", days=21):
    """theme_term = {tema: 'termino de busqueda'}.
    Devuelve {tema: {"vol":[...], "tone": float|None, "tone_series":[...]}}.
    'vol' = intensidad de cobertura; 'tone' = tono promedio (negativo = cobertura negativa)."""
    global last_error
    last_error = None
    out, errs = {}, []
    extra = " sourcelang:spanish" + ((" sourcecountry:" + geo) if geo else "")
    # BUG REAL (Fernando, 2026-09-23: "Mercado de cobertura sigue mostrando
    # solo Politica"): 'theme_term' llega en el MISMO orden alfabetico
    # SIEMPRE (viene de sorted(...) en monitor.py), y este bucle corta en el
    # primer HTTP 429. Con GDELT rate-limited casi toda corrida, eso
    # significa que los temas que van DESPUES del primero que falla nunca
    # llegan a intentarse -- ni esta pasada ni ninguna otra, porque el orden
    # nunca cambia. Confirmado en vivo: gdelt_cache.json llevaba dias sin
    # acumular mas de 1-2 temas pese al arreglo de "no pisar el cache" (ese
    # arreglo evita perder lo que se consigue, pero si el orden nunca rota,
    # casi nunca se consigue nada nuevo). Se mezcla el orden en cada llamada
    # para que, en el tiempo, todos los temas tengan chance de ser
    # los primeros (los que mas probabilidad tienen de responder antes de
    # que el rate limit corte la pasada).
    items = list(theme_term.items())
    random.shuffle(items)
    for i, (tema, term) in enumerate(items):
        try:
            if i:
                time.sleep(PAUSA)
            q = term + extra
            vol = _timeline(q, "TimelineVol", days)
            if not vol:
                continue
            fechas = list(_ULTIMAS_FECHAS)
            time.sleep(PAUSA)
            tone = _timeline(q, "TimelineTone", days)
            out[tema] = {"vol": vol, "fechas": fechas,
                         "tone": round(sum(tone) / len(tone), 2) if tone else None,
                         "tone_series": tone}
        except urllib.error.HTTPError as e:
            errs.append("HTTP %s" % e.code)
            if e.code == 429:
                # Bloqueado por exceso de consultas: seguir insistiendo con los
                # temas que faltan solo alarga el bloqueo (y antes tenia a la IA
                # esperando detras). Se corta aca y se reintenta mas tarde
                # (enfriamiento en monitor.get_gdelt).
                break
        except Exception as e:
            errs.append(type(e).__name__)
    # BUG REAL (Frente C): antes 'last_error' solo se guardaba si TODOS los
    # temas fallaban (`if not out and errs`) -- un exito PARCIAL (ej. 1 de 19
    # temas, el resto con HTTP 429) quedaba con last_error=None, y monitor.py
    # reportaba "ok" a secas sin dejar rastro de que 18 temas habian fallado.
    # Ahora se guarda el primer error siempre que hubo alguno, sea parcial o
    # total, para que get_gdelt() en monitor.py pueda armar un estado honesto
    # (cuantos temas de cuantos, y por que fallo el resto).
    if errs:
        last_error = errs[0]
    return out


# ------------------------- co-menciones (Parte B: contexto por entidad) -------------------------

def articulos(query, geo="", maxrecords=15, days=30, timeout=30):
    """Modo lista de articulos del DOC 2.0 (mode=ArtList): titulares recientes
    que mencionan 'query'. Aproximado y liviano (no trae el texto completo del
    articulo, solo metadatos) -- alcanza para escanear co-menciones."""
    global last_error
    last_error = None
    extra = " sourcelang:spanish" + ((" sourcecountry:" + geo) if geo else "")
    try:
        q = urllib.parse.urlencode({"query": query + extra, "mode": "ArtList",
                                    "format": "json", "maxrecords": maxrecords,
                                    "timespan": "%dd" % days, "sort": "hybridrel"})
        data = _get(BASE + "?" + q, timeout=timeout)
        return data.get("articles") or []
    except urllib.error.HTTPError as e:
        last_error = "HTTP %s" % e.code
    except Exception as e:
        last_error = type(e).__name__
    return []


def comenciones(entidad, geo="", maxrecords=15, top=5):
    """Para 'entidad' (la principal de una historia), busca articulos recientes
    que la mencionen y extrae OTROS nombres propios que aparecen en esos
    titulares (coincidencia por frecuencia). Son 'pistas por verificar', no
    hechos: dos nombres en el mismo titular no prueban una relacion, solo que
    la prensa los cubrio junto. Devuelve una lista de hasta 'top' nombres,
    sin incluir a la propia entidad."""
    return contexto_prensa(entidad, geo=geo, maxrecords=maxrecords, top_nombres=top,
                            top_titulares=0)["comenciones"]


def contexto_prensa(entidad, geo="", maxrecords=15, top_nombres=5, top_titulares=4):
    """Una sola busqueda en GDELT (ArtList) que alimenta DOS cosas a la vez,
    para no duplicar la llamada de red (GDELT ya es propenso a 429):
      - 'comenciones': otros nombres propios que aparecen junto a 'entidad'
        en esos titulares (igual que antes, ver comenciones()).
      - 'titulares': los titulares REALES mas recientes que mencionan a
        'entidad', con fecha -- material para explicar la SITUACION (que esta
        pasando alrededor del hecho, no solo quien es la entidad). Son datos
        verificados (titulares que de verdad publico la prensa), no un
        resumen inventado; el modelo los usa como evidencia, nunca los
        reemplaza por su propio conocimiento (bug real de Carney/Mamdani,
        ver monitor.py)."""
    arts = articulos(entidad, geo=geo, maxrecords=maxrecords)
    if not arts:
        return {"comenciones": [], "titulares": []}
    ent_norm = entidad.strip().lower()
    conteo = {}
    titulares_todos = []
    for a in arts:
        titulo = (a.get("title") or "").strip()
        if not titulo:
            continue
        fecha = (a.get("seendate") or "")[:8]  # GDELT: YYYYMMDDHHMMSS
        fecha_fmt = ("%s-%s-%s" % (fecha[:4], fecha[4:6], fecha[6:8])) if len(fecha) == 8 else ""
        titulares_todos.append({"titulo": titulo, "fecha": fecha_fmt, "url": a.get("url", "")})
        for m in _NOMBRE_RE.findall(titulo):
            nombre = m.strip()
            if not nombre or nombre.lower() == ent_norm or nombre.lower() in ent_norm:
                continue
            conteo[nombre] = conteo.get(nombre, 0) + 1
    top_nombres_ = sorted(conteo, key=lambda n: conteo[n], reverse=True)[:top_nombres]
    # mas recientes primero (fecha vacia al final, no rompe el orden de las que si tienen)
    titulares_todos.sort(key=lambda t: t["fecha"], reverse=True)
    return {"comenciones": top_nombres_, "titulares": titulares_todos[:max(top_titulares, 0)]}
