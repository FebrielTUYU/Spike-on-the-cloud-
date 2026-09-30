# -*- coding: utf-8 -*-
"""
Cliente minimo de Google Trends (DEMANDA de busquedas) — solo stdlib.

NO es oficial: usa los mismos endpoints internos que la web de Trends. Puede
romperse, pedir captcha o devolver 429 si Google bloquea (mas probable desde
servidores; desde una PC residencial en Ecuador suele funcionar). Por eso TODO
falla en silencio: si algo sale mal, interest_over_time() devuelve {} y deja el
motivo en trends.last_error, y el resto del monitor sigue igual.

Valores: son un indice RELATIVO 0-100. Dentro de UNA misma llamada (hasta 5
terminos) los valores son comparables entre si; entre llamadas distintas, no
del todo. Sirven como senal de interes, no como numero absoluto de busquedas.
"""

import json, time, urllib.request, urllib.parse, urllib.error, http.cookiejar

BASE = "https://trends.google.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Monitor-Noticias/1.0"

last_error = None  # ultimo motivo de fallo (para el reporte)


def _opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA), ("Accept-Language", "es-EC,es;q=0.9")]
    return op


def _get_json(op, url, timeout=20):
    with op.open(url, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    # las respuestas de Trends traen basura antes del JSON, p.ej.  )]}',
    starts = [p for p in (raw.find("{"), raw.find("[")) if p != -1]
    if not starts:
        raise ValueError("respuesta sin JSON")
    return json.loads(raw[min(starts):])


# "today 1-m" (diario, 30 puntos) en vez de "now 7-d" (cada hora): en Ecuador
# el volumen por hora de terminos generales es tan bajo que Trends devolvia
# casi todo 0 con algun pico suelto -- graficos planos que no decian nada.
TIMEFRAME = "today 1-m"

def interest_over_time(terms, geo="EC", timeframe=TIMEFRAME, hl="es-EC", tz=300, max_points=56):
    """Devuelve {termino: {"avg": int, "series": [int...], "times": [str...]}} o {}.
    'avg' = promedio de las ultimas muestras (para brecha/tarjetas); 'series' = la
    curva completa de busquedas (para el grafico de linea). Hasta 5 terminos por
    llamada (comparables entre si)."""
    global last_error
    last_error = None
    terms = [t for t in terms if t][:5]
    if not terms:
        return {}
    try:
        op = _opener()
        # bootstrap de cookies (NID); una pausa corta baja la chance de 429
        try:
            op.open(BASE + "/?geo=" + urllib.parse.quote(geo), timeout=15).read()
            time.sleep(1.5)
        except Exception:
            pass

        comp = [{"keyword": t, "geo": geo, "time": timeframe} for t in terms]
        req = {"comparisonItem": comp, "category": 0, "property": ""}
        q = urllib.parse.urlencode({"hl": hl, "tz": tz, "req": json.dumps(req)})
        # el explore es el que suele dar 429: reintento una vez tras una espera
        explore = None
        for intento in range(2):
            try:
                explore = _get_json(op, BASE + "/trends/api/explore?" + q)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and intento == 0:
                    time.sleep(6); continue
                raise

        widget = next((w for w in explore.get("widgets", [])
                       if w.get("id") == "TIMESERIES"), None)
        if not widget:
            last_error = "sin widget TIMESERIES"
            return {}

        q2 = urllib.parse.urlencode({"hl": hl, "tz": tz,
                                     "req": json.dumps(widget["request"]),
                                     "token": widget["token"]})
        data = _get_json(op, BASE + "/trends/api/widgetdata/multiline?" + q2)
        # isPartial = el periodo EN CURSO (hoy/esta hora), todavia incompleto:
        # su valor es engañoso (bug real: el dashboard tomaba ese ultimo punto
        # como "la demanda actual" y mostraba 0 o un pico de 79 sin sentido).
        rows = [r for r in data.get("default", {}).get("timelineData", [])
                if r.get("value") and not r.get("isPartial")]
        if not rows:
            return {t: {"avg": 0, "series": [], "times": []} for t in terms}

        # submuestreo para no cargar cientos de puntos en el grafico
        if len(rows) > max_points:
            step = max(1, len(rows) // max_points)
            rows = rows[::step]

        out = {}
        for i, t in enumerate(terms):
            vals = [r["value"][i] for r in rows if len(r["value"]) > i]
            times = [r.get("formattedTime") or r.get("formattedAxisTime") or "" for r in rows]
            tail = vals[-7:]  # ultima semana completa
            out[t] = {
                "avg": round(sum(tail) / len(tail)) if tail else 0,
                "series": vals,
                "times": times,
            }
        return out
    except urllib.error.HTTPError as e:
        last_error = "HTTP %s" % e.code
        return {}
    except Exception as e:
        last_error = type(e).__name__
        return {}
