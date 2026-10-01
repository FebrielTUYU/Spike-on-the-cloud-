# -*- coding: utf-8 -*-
"""
pulso.py -- Fase 23 (B3): Pulso social ordenado POR RED (riel de redes a la
izquierda, como el panel de Porter que paso Fernando). Sin red ni IA: corre
en el hilo rapido y solo reordena lo que Spike ya junto.

Junta en una sola lista, por red, las publicaciones que hoy estaban
repartidas en varios lados:
  - escucha social por tema (data.json['social'][tema]['top']);
  - debate por historia (data.json['social_historias'], top + citas);
  - Comunidad Guayaquil (publicaciones de personas de las ultimas horas);
  - EmergenciasEc y su gente (X);
  - tweets pegados a historias (x_tweets) y senales de las alertas que vienen
    de una red (las de fuentes oficiales no son una red y no entran).

Por red arma lo que dibuja el dashboard, y NADA mas: volumen por hora, temas,
interacciones SOLO si la red las trae (si ninguna publicacion trae
me gusta/reposts/respuestas, el bloque no existe -- no se pone en cero),
barrios de Guayaquil (misma deteccion que Comunidad y el mapa, con el centro
aproximado del sector) y la tabla de publicaciones. Sin datos de seguidores
ni demografia: Spike no los tiene.
"""
import datetime as dt
import os
import re
import unicodedata

try:
    import comunidad as _com
except Exception:  # pragma: no cover
    _com = None
try:
    import mapa as _mapa
except Exception:  # pragma: no cover
    _mapa = None

REDES = ("x", "tiktok", "bluesky", "mastodon", "youtube", "facebook", "whatsapp", "reddit", "telegram")
# Fase 24 (B5, pedido de Fernando): Bluesky y Mastodon fuera del Pulso social y del riel.
FUERA_DEL_PULSO = {r for r, env in (("bluesky", "MONITOR_PULSO_BLUESKY"), ("mastodon", "MONITOR_PULSO_MASTODON"))
                   if os.environ.get(env, "0") != "1"}
ETIQUETA = {"x": "X", "tiktok": "TikTok", "bluesky": "Bluesky", "mastodon": "Mastodon", "youtube": "YouTube",
            "facebook": "Facebook", "whatsapp": "WhatsApp (importado)", "reddit": "Reddit",
            "telegram": "Telegram (canales)"}
EC = dt.timezone(dt.timedelta(hours=-5))
HORAS = 24          # ventana del grafico de volumen por hora
MAX_POR_RED = 250   # publicaciones por red que viajan en data.json (el filtro de ambito se aplica en el navegador)


def _parse(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _num(x):
    try:
        return int(x)
    except Exception:
        return None


def _barrio(texto, dado=None):
    if dado and (_com is None or dado != _com.SIN_SECTOR):
        return dado
    if _com is None or not texto:
        return None
    try:
        if not _com.es_de_guayaquil(texto):
            return None
        return _com.detectar_barrio(texto)
    except Exception:
        return None


def _post(red, autor, texto, url, fecha, origen, tema=None, ambito=None, likes=None, reposts=None,
          respuestas=None, tipo=None, barrio=None):
    red = (red or "").lower()
    if red not in REDES or red in FUERA_DEL_PULSO or not (texto or "").strip():
        return None
    return {"red": red, "autor": (autor or "").strip(), "texto": (texto or "").strip()[:400], "url": url or "",
            "fecha": fecha or "", "origen": origen, "tema": tema, "ambito": ambito,
            "likes": _num(likes), "reposts": _num(reposts), "respuestas": _num(respuestas),
            "tipo": tipo, "barrio": _barrio(texto, barrio)}


def reunir(social=None, social_historias=None, comunidad_recientes=None, emergencias=None, historias=None,
           alertas=None):
    """Lista unica de publicaciones (sin duplicados), cada una con su red."""
    out = []
    for tema, d in (social or {}).items():
        for p in (d or {}).get("top") or []:
            out.append(_post(p.get("fuente"), p.get("autor"), p.get("texto"), p.get("url"), p.get("fecha"),
                             "escucha por tema", tema=tema, ambito=d.get("ambito"), likes=p.get("likes"),
                             reposts=p.get("reposts"), tipo=p.get("tipo")))
    for d in (social_historias or {}).values():
        tit = (d or {}).get("titular")
        amb = d.get("ambito")
        for p in d.get("top") or []:
            out.append(_post(p.get("fuente"), p.get("autor"), p.get("texto"), p.get("url"), p.get("fecha"),
                             "debate de una historia", tema=tit, ambito=amb, likes=p.get("likes"),
                             reposts=p.get("reposts"), tipo=p.get("tipo")))
        for postura in d.get("posturas") or []:
            for p in postura.get("citas") or []:
                out.append(_post(p.get("fuente"), p.get("autor"), p.get("texto"), p.get("url"), p.get("fecha"),
                                 "debate de una historia", tema=tit, ambito=amb))
    for p in comunidad_recientes or []:
        out.append(_post(p.get("fuente"), p.get("autor"), p.get("texto"), p.get("url"), p.get("fecha"),
                         "comunidad Guayaquil", tema=p.get("categoria_label") or p.get("categoria"),
                         ambito="guayaquil", barrio=p.get("barrio"), tipo="persona"))
    for t in (emergencias or {}).get("tweets") or []:
        out.append(_post("x", t.get("autor"), t.get("texto"), t.get("url"), t.get("fecha"),
                         "EmergenciasEc y su gente", ambito="guayaquil", respuestas=t.get("respuestas")))
    for h in historias or []:
        for t in h.get("x_tweets") or []:
            a = t.get("autor") or ""
            out.append(_post("x", a if a.startswith("@") else "@" + a, t.get("texto"), t.get("url"), t.get("fecha"),
                             "tweets de una historia", tema=h.get("titular"),
                             ambito="guayaquil" if h.get("ciudad") == "Guayaquil" else (
                                 "internacional" if h.get("internacional") else "ecuador")))
    for a in alertas or []:
        for s in a.get("senales") or []:
            if s.get("oficial"):
                continue
            au = s.get("autor") or ""
            out.append(_post(s.get("fuente"), au if au.startswith("@") or s.get("fuente") != "x" else "@" + au,
                             s.get("texto"), s.get("url"), s.get("fecha"), "alertas de la gente",
                             tema=a.get("tipo"), ambito="guayaquil" if a.get("lugar") else "ecuador",
                             barrio=a.get("lugar") if a.get("lugar") and "sin precisar" not in a.get("lugar") else None))
    vistos, unicos = set(), []
    for p in out:
        if not p:
            continue
        k = (p["red"], p["url"] or _norm(p["autor"] + " " + p["texto"][:120]))
        if k in vistos:
            continue
        vistos.add(k)
        unicos.append(p)
    unicos.sort(key=lambda p: p["fecha"] or "", reverse=True)
    return unicos


def _resumen_red(posts, ahora):
    inicio = (ahora - dt.timedelta(hours=HORAS - 1)).astimezone(EC).replace(minute=0, second=0, microsecond=0)
    horas = [0] * HORAS
    etiquetas = [(inicio + dt.timedelta(hours=i)).strftime("%H") for i in range(HORAS)]
    sin_fecha = 0
    for p in posts:
        f = _parse(p["fecha"])
        if not f:
            sin_fecha += 1
            continue
        i = int((f.astimezone(EC) - inicio).total_seconds() // 3600)
        if 0 <= i < HORAS:
            horas[i] += 1
    temas = {}
    for p in posts:
        if p.get("tema"):
            temas[p["tema"]] = temas.get(p["tema"], 0) + 1
    con_inter = [p for p in posts if any(p.get(k) is not None for k in ("likes", "reposts", "respuestas"))]
    inter = None
    if con_inter:
        inter = {k: sum(p.get(k) or 0 for p in con_inter) for k in ("likes", "reposts", "respuestas")}
        inter["publicaciones_con_dato"] = len(con_inter)
        inter["top"] = sorted(con_inter, key=lambda p: -((p.get("likes") or 0) + (p.get("reposts") or 0)
                                                          + (p.get("respuestas") or 0)))[:6]
        if not any(inter[k] for k in ("likes", "reposts", "respuestas")):
            inter = None  # todas en cero: no dice nada
    barrios = {}
    for p in posts:
        if p.get("barrio"):
            barrios[p["barrio"]] = barrios.get(p["barrio"], 0) + 1
    donde = []
    for b, n in sorted(barrios.items(), key=lambda x: -x[1]):
        c = (_mapa.COORDS.get(b) if _mapa else None)
        donde.append({"barrio": b, "n": n, "lat": c[0] if c else None, "lon": c[1] if c else None,
                      "amplia": bool(_mapa and b in _mapa.ZONAS_AMPLIAS)})
    return {"n": len(posts), "por_hora": horas, "horas": etiquetas, "sin_fecha": sin_fecha,
            "temas": [{"tema": t, "n": n} for t, n in sorted(temas.items(), key=lambda x: -x[1])[:10]],
            "interacciones": inter, "donde": donde,
            "publicaciones": posts[:MAX_POR_RED]}


def armar(social=None, social_historias=None, comunidad_recientes=None, emergencias=None, historias=None,
          alertas=None, ahora=None):
    """data.json['pulso']: {'redes': [{red, etiqueta, n, ...}], 'total', 'generado'}.
    Solo aparecen las redes con al menos una publicacion."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    posts = reunir(social, social_historias, comunidad_recientes, emergencias, historias, alertas)
    redes = []
    for red in REDES:
        ps = [p for p in posts if p["red"] == red]
        if not ps:
            continue
        r = _resumen_red(ps, ahora)
        r.update({"red": red, "etiqueta": ETIQUETA.get(red, red),
                  "origenes": sorted({p["origen"] for p in ps})})
        redes.append(r)
    redes.sort(key=lambda r: -r["n"])
    coords = {}
    if _mapa is not None:
        for p in posts:
            b = p.get("barrio")
            if b and b in _mapa.COORDS:
                coords[b] = list(_mapa.COORDS[b])
    return {"redes": redes, "total": len(posts), "generado": ahora.isoformat(), "ventana_horas": HORAS,
            "coords": coords, "zonas_amplias": sorted(_mapa.ZONAS_AMPLIAS) if _mapa else []}
