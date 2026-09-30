# -*- coding: utf-8 -*-
"""
SERCOP — Contrataciones Abiertas de Ecuador (OCDS). Solo stdlib, gratis, sin clave.

Sirve para CONTRASTAR una noticia con documentacion oficial: dado un termino,
busca contratos publicos relacionados. NO inventa nada: trae registros oficiales
tal cual, para que el periodista los verifique. Son PISTAS ("posiblemente
relacionados"), no una afirmacion de que la noticia hable de ese contrato.

API: https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds?year=YYYY&search=<termino>
"""

import json, time, datetime as dt, urllib.request, urllib.parse, urllib.error

BASE = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/"
UA = "MonitorNoticias/1.0 (proyecto estudiantil periodismo)"
last_error = None


def _get(url, timeout=30):
    for intento in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento == 0:
                time.sleep(5); continue
            raise


def _norm(it):
    g = lambda *ks: next((str(it[k]) for k in ks if it.get(k) not in (None, "")), "")
    ocid = g("ocid")
    return {
        "ocid": ocid,
        "objeto": g("title", "description", "object", "objeto", "internal_type"),
        "entidad": g("buyer", "entity", "entidad", "contracting_process_entity", "buyer_name"),
        "monto": g("amount", "value", "monto", "valorTotal"),
        "fecha": g("date", "fecha", "period"),
        "link": ("https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/record?ocid="
                 + urllib.parse.quote(ocid)) if ocid else "",
    }


def buscar(term, years=None, limit=5):
    """Contratos publicos que mencionan 'term'. Lista de dicts o [] si falla."""
    global last_error
    last_error = None
    if not term:
        return []
    y0 = dt.date.today().year
    years = years or [y0]   # solo el ano actual: menos consultas, menos 429
    out = []
    try:
        for y in years:
            q = urllib.parse.urlencode({"year": y, "search": term, "page": 1})
            data = _get(BASE + "search_ocds?" + q)
            rows = data.get("data") if isinstance(data, dict) else None
            for it in (rows or []):
                if isinstance(it, dict):
                    out.append(_norm(it))
                    if len(out) >= limit:
                        return out
        return out
    except urllib.error.HTTPError as e:
        last_error = "HTTP %s" % e.code
        return out
    except Exception as e:
        last_error = type(e).__name__
        return out
