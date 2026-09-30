# -*- coding: utf-8 -*-
"""
Fase 9, parte D3 -- TikTok via Apify (mismo token/cuenta que X, ver xapi.py).
Standalone, pero reusa la mecanica de bajo nivel de xapi.py (token, correr un
actor + leer el dataset + costo real) para no duplicar esa parte -- ambos
hablan con la MISMA plataforma (Apify), solo cambia el actor.

Actores verificados en Apify el 2026-09-26 (plan FREE):
  - clockworks/tiktok-scraper: $0.0037 por video + $0.001 por inicio de
    actor. Input: searchQueries, resultsPerPage, searchSection. Los add-ons
    de filtro de fecha/pais cuestan $0.0013 extra por resultado -- NO se
    usan, se filtra la fecha en local con la fecha real del video.
  - clockworks/tiktok-comments-scraper: $0.00125 por comentario. Input:
    postURLs, commentsPerPost, maxRepliesPerComment.

No decide presupuesto ni frecuencia por si solo (eso lo hace redes.py, el
orquestador compartido con X) -- este modulo solo sabe "pedir videos" y
"pedir comentarios de un video", devolviendo items + costo real."""
import datetime as dt
import json
import os

import xapi  # reusa _leer_token/_run_actor/activo/_error_http -- misma cuenta de Apify

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "tiktok_cache.json")

last_error = None

ACTOR_VIDEOS = "clockworks~tiktok-scraper"
ACTOR_COMENTARIOS = "clockworks~tiktok-comments-scraper"
PRECIO_VIDEO = 0.0037
PRECIO_COMENTARIO = 0.00125
PRECIO_INICIO_ACTOR = 0.001  # cobro de inicio, aparte del precio por resultado


def activo():
    return xapi.activo()  # mismo token, misma cuenta de Apify


def costo_estimado_videos(n):
    return n * PRECIO_VIDEO + PRECIO_INICIO_ACTOR


def costo_estimado_comentarios(n):
    return n * PRECIO_COMENTARIO + PRECIO_INICIO_ACTOR


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


def _dias_desde(fecha_iso):
    try:
        f = dt.datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
        if f.tzinfo is None:
            f = f.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - f).days
    except Exception:
        return 9999


def buscar_videos(query, resultados=3, dias_max=7, simular=False):
    """Videos recientes (filtrados en LOCAL por fecha, sin el add-on pago de
    fecha -- ver docstring del modulo). Devuelve (videos, costo_real)."""
    global last_error
    last_error = None
    if not activo():
        last_error = "desactivado: falta token de Apify (mismo que X)"
        return None, 0.0
    if simular:
        return {"_simulado": True, "_costo_proyectado": costo_estimado_videos(resultados)}, 0.0
    input_dict = {"searchQueries": [query], "resultsPerPage": resultados, "searchSection": "video"}
    items, costo_real, _run_id = xapi._run_actor(ACTOR_VIDEOS, input_dict)
    if items is None:
        last_error = xapi.last_error
        return None, 0.0
    recientes = [v for v in items if _dias_desde(v.get("createTimeISO") or v.get("createTime", "")) <= dias_max]
    costo = costo_real if costo_real is not None else costo_estimado_videos(resultados)
    return recientes, costo


def guardar_videos_historia(link, videos):
    """Fase 9, D3-2.4 (integracion a Pulso social): igual que
    xapi.guardar_tweets_historia() -- get_social_historias() (monitor.py)
    lee esto para sumar los videos de ESTA historia al post de X/redes de
    siempre, sin tener que volver a pedirlos."""
    cache = _cargar_cache()
    hs = cache.setdefault("historias", {})
    existente = hs.get(link, {}).get("videos", [])
    urls_ya = {v.get("webVideoUrl") or v.get("url", "") for v in existente}
    nuevos = [v for v in videos if (v.get("webVideoUrl") or v.get("url", "")) not in urls_ya]
    hs[link] = {"videos": existente + nuevos, "ts": dt.datetime.now(dt.timezone.utc).isoformat()}
    _guardar_cache(cache)


def videos_de_historia(link):
    return _cargar_cache().get("historias", {}).get(link, {}).get("videos", [])


def guardar_comentarios_video(video_url, comentarios):
    cache = _cargar_cache()
    cache.setdefault("comentarios_texto", {})[video_url] = comentarios
    _guardar_cache(cache)


def comentarios_de_video(video_url):
    return _cargar_cache().get("comentarios_texto", {}).get(video_url, [])


def _comentarios_previos(video_url):
    return _cargar_cache().get("comentarios", {}).get(video_url, {})


def _guardar_comentarios_estado(video_url, n_comentarios_video):
    cache = _cargar_cache()
    cache.setdefault("comentarios", {})[video_url] = {
        "n_comentarios_conteo": n_comentarios_video,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _guardar_cache(cache)


def hace_falta_bajar_comentarios(video_url, n_comentarios_actual):
    """Problema D3-2.3: 'no vuelvas a bajar comentarios de un video si su
    conteo de comentarios no creció' -- barato (sin red), decide ANTES de
    gastar la llamada real."""
    previo = _comentarios_previos(video_url)
    return not previo or (n_comentarios_actual or 0) > previo.get("n_comentarios_conteo", 0)


def buscar_comentarios(video_url, n_comentarios_video=0, max_comentarios=20, simular=False):
    """Comentarios de UN video -- solo tiene sentido llamarla si
    hace_falta_bajar_comentarios() ya dijo que si (el llamador decide eso,
    aca solo se ejecuta). Devuelve (comentarios, costo_real)."""
    global last_error
    last_error = None
    if not activo():
        last_error = "desactivado: falta token de Apify (mismo que X)"
        return None, 0.0
    if simular:
        return {"_simulado": True, "_costo_proyectado": costo_estimado_comentarios(max_comentarios)}, 0.0
    input_dict = {"postURLs": [video_url], "commentsPerPost": max_comentarios, "maxRepliesPerComment": 0}
    items, costo_real, _run_id = xapi._run_actor(ACTOR_COMENTARIOS, input_dict)
    if items is None:
        last_error = xapi.last_error
        return None, 0.0
    _guardar_comentarios_estado(video_url, n_comentarios_video)
    costo = costo_real if costo_real is not None else costo_estimado_comentarios(max_comentarios)
    return items, costo


def clasificar_autor(item):
    """Reusa la MISMA logica que xapi.clasificar_autor (persona/medio/
    institucion/politico) -- TikTok trae 'authorMeta.name'/'authorMeta.nickName'
    en vez de 'author.userName', se adapta el dict al formato que espera
    xapi.clasificar_autor()."""
    author_meta = item.get("authorMeta") or {}
    tweet_like = {"author": {
        "userName": author_meta.get("name", ""),
        "name": author_meta.get("nickName", ""),
        "location": "",
        "description": author_meta.get("signature", ""),
    }}
    return xapi.clasificar_autor(tweet_like)
