# -*- coding: utf-8 -*-
"""
FactCheck -- verificaciones periodisticas relacionadas con una historia, via
Google Fact Check Tools API (claims:search). Solo stdlib.

Busca afirmaciones que algun verificador (ClaimReview: Chequeado, Maldita.es,
AFP Factual, etc.) ya reviso, relacionadas con el titular o la entidad
principal de una nota. Gratis, pero necesita clave (MONITOR_FACTCHECK_KEY) y
que el proyecto de Google Cloud tenga HABILITADA la "Fact Check Tools API" --
es una API DISTINTA de YouTube Data API v3, aunque las dos usen una clave de
Google Cloud: una clave que sirve para YouTube puede no servir para esta si
no se habilito por separado (o si esta restringida solo a YouTube).
"""

import os, json, urllib.request, urllib.parse, urllib.error

UA = "MonitorNoticias/1.0 (proyecto estudiantil de periodismo)"
KEY = os.environ.get("MONITOR_FACTCHECK_KEY", "")
BASE = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
last_error = None


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def buscar(query, language_code="es", max_results=5):
    """Busca ClaimReview relacionados con 'query' (titular o entidad). Devuelve
    una lista de {claim, calificacion, verificador, url, fecha}, o [] si no
    hay nada, no hay clave, o la consulta esta vacia.

    Un HTTP 403 aqui casi siempre significa que falta HABILITAR 'Fact Check
    Tools API' en el proyecto de Google Cloud, o que la clave esta
    restringida a otra API (ej. solo YouTube Data API v3) -- se deja bien
    explicito en last_error porque NO es un bug del codigo, es config de la
    consola de Google Cloud."""
    global last_error
    last_error = None
    if not KEY or not (query or "").strip():
        return []
    try:
        params = {"query": query.strip()[:200], "languageCode": language_code,
                  "pageSize": max_results, "key": KEY}
        data = _get(BASE + "?" + urllib.parse.urlencode(params))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            last_error = ("HTTP 403: revisa que 'Fact Check Tools API' este "
                          "HABILITADA en tu proyecto de Google Cloud (es distinta de "
                          "YouTube Data API v3), o que MONITOR_FACTCHECK_KEY no este "
                          "restringida a otra API. No es un bug del codigo.")
        else:
            last_error = "HTTP %s" % e.code
        return []
    except Exception as e:
        last_error = type(e).__name__
        return []

    out = []
    for c in (data.get("claims") or []):
        texto = (c.get("text") or "").strip()
        for r in (c.get("claimReview") or []):
            out.append({
                "claim": texto[:280],
                "calificacion": (r.get("textualRating") or "").strip(),
                "verificador": ((r.get("publisher") or {}).get("name") or "").strip(),
                "url": r.get("url", ""),
                "fecha": (r.get("reviewDate") or c.get("claimDate") or "")[:10],
            })
    return out[:max_results]
