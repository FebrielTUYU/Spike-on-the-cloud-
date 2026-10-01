# -*- coding: utf-8 -*-
"""
facebook.py -- Fase 20b: Facebook como voz de la gente de Guayaquil.

Pedido de Fernando (2026-09-30): "Encuentra una forma de poder integrar
whatsapp y facebook". Facebook no tiene una API abierta de busqueda (Meta Graph
API solo da paginas propias o con permiso del dueno). La unica via sin cuenta
propia logueada es la MISMA que ya se usa para X: actores de Apify que leen
paginas y grupos PUBLICOS, con el mismo token (x_config.json).

Que se lee (facebook_fuentes.json, editable a mano, se crea solo vacio):
  - "paginas": paginas publicas de Guayaquil (Municipio, medios locales,
    paginas de barrio). De sus ultimas publicaciones se leen los COMENTARIOS
    -- ahi es donde la gente se queja ("en mi barrio no pasa el recolector").
  - "grupos": grupos PUBLICOS de barrio/ciudadelas. Se leen las publicaciones.
Sin nada configurado, no se hace ninguna llamada ni se gasta nada.

Riesgo registrado a proposito (mismo criterio que X/Apify en la Fase 9): no es
un acceso autorizado por Meta, puede dejar de funcionar sin aviso, y los grupos
PRIVADOS no se pueden leer por esta via (ni se intenta).

NO verificado en vivo (la sesion donde se escribio no llegaba a Apify): los
nombres de los actores, sus campos de entrada/salida y el precio vienen de la
documentacion publica de Apify. Por eso el parseo es tolerante (varios nombres
de campo posibles) y el costo usa el REAL que reporta Apify cuando lo da.

Presupuesto PROPIO (redes_gasto.json, red "facebook"), aparte del de X/TikTok:
el credito gratis de Apify ($5/mes) ya lo usa X. Facebook necesita credito
aparte: MONITOR_FB_TOPE_MES_USD (def. 3.00).
"""
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FUENTES_PATH = os.path.join(HERE, "facebook_fuentes.json")

ACTOR_POSTS = os.environ.get("MONITOR_FB_ACTOR_POSTS", "apify~facebook-posts-scraper")
ACTOR_COMENTARIOS = os.environ.get("MONITOR_FB_ACTOR_COMENTARIOS", "apify~facebook-comments-scraper")
ACTOR_GRUPOS = os.environ.get("MONITOR_FB_ACTOR_GRUPOS", "apify~facebook-groups-scraper")
# Precio por resultado ESTIMADO (conservador, no verificado): solo decide si
# una corrida entra en el presupuesto antes de llamar. El gasto que se anota es
# el real de Apify si lo reporta.
PRECIO_ITEM = float(os.environ.get("MONITOR_FB_PRECIO_ITEM", "0.005"))
TOPE_MES_USD = float(os.environ.get("MONITOR_FB_TOPE_MES_USD", "3.00"))
CADA_MIN = float(os.environ.get("MONITOR_FB_MIN", "60"))
POSTS_POR_PAGINA = 2
COMENTARIOS_POR_POST = 25
POSTS_POR_GRUPO = 15

last_error = None

_PLANTILLA = {
    "_ayuda": ("Pega aqui URLs de Facebook PUBLICAS de Guayaquil. 'paginas': de sus ultimas "
               "publicaciones se leen los comentarios de la gente. 'grupos': grupos publicos de barrio, "
               "se leen las publicaciones. Ej.: https://www.facebook.com/MunicipioGuayaquil"),
    "paginas": [],
    "grupos": [],
}


def fuentes():
    """{'paginas': [...], 'grupos': [...]} -- crea el archivo de ejemplo si no existe."""
    try:
        with open(FUENTES_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        try:
            with open(FUENTES_PATH, "w", encoding="utf-8") as f:
                json.dump(_PLANTILLA, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        d = _PLANTILLA
    except Exception:
        d = {}
    limpiar = lambda xs: [u.strip() for u in (xs or []) if isinstance(u, str) and u.strip().startswith("http")]
    return {"paginas": limpiar(d.get("paginas")), "grupos": limpiar(d.get("grupos"))}


def activo():
    try:
        import xapi
        if not xapi.activo():
            return False
    except Exception:
        return False
    f = fuentes()
    return bool(f["paginas"] or f["grupos"])


# ------------------------- parseo tolerante -------------------------
def _primero(d, *claves):
    for c in claves:
        v = d
        for parte in c.split("."):
            v = v.get(parte) if isinstance(v, dict) else None
        if v:
            return v
    return None


def _fecha(v):
    if not v:
        return ""
    if isinstance(v, (int, float)):
        seg = v / 1000 if v > 1e11 else v
        return dt.datetime.fromtimestamp(seg, dt.timezone.utc).isoformat()
    try:
        d = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).isoformat()
    except Exception:
        return ""


def item_a_publicacion(item):
    """Un post o comentario de Apify -> {autor, texto, url, fecha}, o None."""
    if not isinstance(item, dict):
        return None
    texto = _primero(item, "text", "message", "postText", "commentText", "body")
    autor = _primero(item, "profileName", "authorName", "user.name", "author.name", "userName", "pageName",
                     "from.name")
    if not texto or not autor:
        return None
    return {"autor": str(autor), "texto": str(texto),
            "url": str(_primero(item, "commentUrl", "url", "postUrl", "facebookUrl", "link") or ""),
            "fecha": _fecha(_primero(item, "date", "time", "timestamp", "createdTime", "created_time",
                                     "publishedAt"))}


# ------------------------- presupuesto -------------------------
def _cabe(costo_max):
    try:
        import redes
        return redes.gasto_mes("facebook") + costo_max <= TOPE_MES_USD
    except Exception:
        return False


def _anotar(costo, motivo):
    try:
        import redes
        redes.registrar_gasto("facebook", costo, motivo)
    except Exception:
        pass


def _correr(actor, entrada, n_items, motivo):
    global last_error
    import xapi
    costo_max = n_items * PRECIO_ITEM
    if not _cabe(costo_max):
        last_error = "tope mensual de Facebook alcanzado (MONITOR_FB_TOPE_MES_USD=%.2f)" % TOPE_MES_USD
        return None
    items, costo_real, _ = xapi._run_actor(actor, entrada, tope_seguridad_usd=max(0.05, costo_max * 2))
    if items is None:
        last_error = xapi.last_error
        return None
    costo = costo_real if costo_real is not None else len(items) * PRECIO_ITEM
    _anotar(costo, motivo)
    return items


def recolectar(horas=48):
    """Red real (Apify), SOLO desde el hilo trabajador/comunidad. Devuelve
    (publicaciones, texto_estado). Publicaciones: dicts de item_a_publicacion
    con 'origen' (pagina o grupo)."""
    global last_error
    last_error = None
    if not activo():
        return [], "sin fuentes configuradas (facebook_fuentes.json) o sin token de Apify"
    f = fuentes()
    desde = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=horas)).strftime("%Y-%m-%d")
    out, partes = [], []
    if f["paginas"]:
        posts = _correr(ACTOR_POSTS, {"startUrls": [{"url": u} for u in f["paginas"]],
                                      "resultsLimit": POSTS_POR_PAGINA, "onlyPostsNewerThan": desde},
                        POSTS_POR_PAGINA * len(f["paginas"]), "fb_paginas") or []
        urls = [p for p in (_primero(x, "url", "postUrl", "facebookUrl") for x in posts) if p]
        if urls:
            coms = _correr(ACTOR_COMENTARIOS, {"startUrls": [{"url": u} for u in urls],
                                               "resultsLimit": COMENTARIOS_POR_POST},
                           COMENTARIOS_POR_POST * len(urls), "fb_comentarios") or []
            for c in coms:
                p = item_a_publicacion(c)
                if p:
                    p["origen"] = "comentario en pagina"
                    out.append(p)
        partes.append("paginas: %d posts, %d comentarios" % (len(posts), len(out)))
    if f["grupos"]:
        antes = len(out)
        items = _correr(ACTOR_GRUPOS, {"startUrls": [{"url": u} for u in f["grupos"]],
                                       "resultsLimit": POSTS_POR_GRUPO, "onlyPostsNewerThan": desde},
                        POSTS_POR_GRUPO * len(f["grupos"]), "fb_grupos") or []
        for it in items:
            p = item_a_publicacion(it)
            if p:
                p["origen"] = "grupo"
                out.append(p)
        partes.append("grupos: %d publicaciones" % (len(out) - antes))
    estado = "; ".join(partes)
    if last_error:
        estado += " (error: %s)" % last_error
    return out, estado
