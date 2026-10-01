# -*- coding: utf-8 -*-
"""
youtube_canales.py -- Fase 24 (B2): comentarios de YouTube en los canales de
medios de Guayaquil, usando de verdad la cuota gratis (10.000 unidades/dia).

Antes: 3 videos y 20 comentarios una vez por hora (una fraccion minima de la
cuota). Ahora, cada CADA_MIN minutos y para cada canal de youtube_canales.json:
  - videos recientes del canal: playlistItems de la lista de subidas (1 unidad;
    la lista de subidas es "UU" + el id del canal, sin llamada extra);
  - comentarios de cada video de las ultimas VIDEO_HORAS horas:
    commentThreads order=time (1 unidad por pagina).
Ahi comenta la gente del barrio. Cada comentario pasa por el MISMO filtro de
Comunidad (persona, de Guayaquil, nombra un problema) y por su propia fecha.
Si el video es de Guayaquil (lo dice el titulo), el comentario se asume de
Guayaquil y toma el sector del titulo cuando no nombra uno propio.

Ademas, BUSQUEDAS_DIA busquedas por barrio + problema (search: 100 unidades
cada una). Todo dentro de UNIDADES_DIA, visible en el panel.

Canales verificados en vivo el 2026-09-30 (channels?forHandle, nombre y pais
comprobados): El Universo, Ecuavisa, RTS, DiarioExtraEc. Pendientes de
encontrar (la busqueda de canales estaba limitada ese dia): Expreso,
Teleamazonas, TC Television, Gama TV. youtube_canales.json es editable.

Standalone: importa comunidad (filtro) y nada de monitor.py.
"""
import datetime as dt
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CANALES_PATH = os.path.join(HERE, "youtube_canales.json")
ESTADO_PATH = os.path.join(HERE, "youtube_estado.json")
API = "https://www.googleapis.com/youtube/v3"
UA = "Spike/1.0 (monitor de noticias personal)"

CADA_MIN = float(os.environ.get("MONITOR_YT_CANALES_MIN", "20"))
UNIDADES_DIA = int(os.environ.get("MONITOR_YT_UNIDADES_COMUNIDAD", "4000"))  # parte de las 10.000 para Comunidad
VIDEO_HORAS = float(os.environ.get("MONITOR_YT_VIDEO_HORAS", "36"))
VIDEOS_POR_CANAL = 6
COMENTARIOS_POR_VIDEO = 100
BUSQUEDAS_DIA = int(os.environ.get("MONITOR_YT_BUSQUEDAS_DIA", "8"))

_PLANTILLA = {
    "_ayuda": ("Canales de YouTube de medios de Guayaquil cuyos comentarios lee Comunidad. 'verificado': true = "
               "el id se comprobo en vivo (nombre y pais). Para agregar uno: su id de canal (empieza con UC). "
               "'activo': false para apagarlo sin borrarlo."),
    "canales": [
        {"nombre": "El Universo", "id": "UCLwBAR1YA6bQRNVCLYOM6Sg", "usuario": "@eluniversocom", "verificado": True, "activo": True},
        {"nombre": "Ecuavisa", "id": "UCRUV3nUNSc-xpBrTwQOCQQg", "usuario": "@ecuavisa", "verificado": True, "activo": True},
        {"nombre": "RTS", "id": "UCRZXwgQXvT-Hm-7XiKAwMxA", "usuario": "@rtsec", "verificado": True, "activo": True},
        {"nombre": "Diario Extra", "id": "UCb4WHdnja-OjVo8OKuc2n-Q", "usuario": "@diarioextraec", "verificado": True, "activo": True},
    ],
    "pendientes": ["Expreso", "Teleamazonas", "TC Television", "Gama TV"],
}
_LOCK = threading.RLock()
last_error = None


def _clave():
    return os.environ.get("MONITOR_YT_KEY", "").strip()


def canales():
    try:
        with open(CANALES_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        d = _PLANTILLA
        try:
            with open(CANALES_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    except Exception:
        d = {}
    return [c for c in (d.get("canales") or []) if c.get("id") and c.get("activo", True)]


def _hoy():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _estado():
    try:
        with open(ESTADO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar(e):
    tmp = ESTADO_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(tmp, ESTADO_PATH)


def unidades_hoy():
    return int(((_estado().get("unidades") or {}).get(_hoy())) or 0)


def _gastar(unidades):
    with _LOCK:
        e = _estado()
        u = e.setdefault("unidades", {})
        u[_hoy()] = int(u.get(_hoy(), 0)) + unidades
        for k in sorted(u)[:-14]:
            del u[k]
        _guardar(e)


def _get(ruta, params, unidades):
    global last_error
    # Revision de Codex: revisar y reservar en el mismo candado, si no dos
    # pasadas a la vez podian pasar el control con cuota para una sola.
    with _LOCK:
        if unidades_hoy() + unidades > UNIDADES_DIA:
            last_error = "presupuesto de unidades de YouTube para Comunidad usado hoy (%d)" % UNIDADES_DIA
            return None
        _gastar(unidades)  # YouTube cobra la unidad aunque la respuesta sea un error
    url = "%s/%s?%s" % (API, ruta, urllib.parse.urlencode(dict(params, key=_clave())))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        last_error = "%s HTTP %s" % (ruta, e.code)
        return None
    except Exception as e:
        last_error = "%s %s" % (ruta, type(e).__name__)
        return None


def _iso(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def videos_recientes(canal_id, ahora=None):
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    d = _get("playlistItems", {"part": "snippet", "playlistId": "UU" + canal_id[2:], "maxResults": VIDEOS_POR_CANAL}, 1)
    out = []
    for it in (d or {}).get("items") or []:
        sn = it.get("snippet") or {}
        vid = (sn.get("resourceId") or {}).get("videoId")
        f = _iso(sn.get("publishedAt"))
        if vid and f and (ahora - f).total_seconds() <= VIDEO_HORAS * 3600:
            out.append({"id": vid, "titulo": sn.get("title") or "", "fecha": f.isoformat()})
    return out


def comentarios(video_id):
    d = _get("commentThreads", {"part": "snippet", "videoId": video_id, "order": "time",
                                "maxResults": COMENTARIOS_POR_VIDEO, "textFormat": "plainText"}, 1)
    out = []
    for it in (d or {}).get("items") or []:
        top = ((it.get("snippet") or {}).get("topLevelComment") or {})
        sn = top.get("snippet") or {}
        texto = (sn.get("textDisplay") or "").strip()
        if texto:
            out.append({"autor": sn.get("authorDisplayName") or "", "texto": texto[:500],
                        "fecha": sn.get("publishedAt") or "",
                        "url": "https://www.youtube.com/watch?v=%s&lc=%s" % (video_id, top.get("id", "")),
                        "likes": int(sn.get("likeCount") or 0)})
    return out


def _a_comunidad(com, video, ahora):
    import comunidad
    del_gye = comunidad.es_de_guayaquil(video["titulo"])
    barrio = comunidad.detectar_barrio(video["titulo"]) if del_gye else None
    posts = [comunidad.normalizar_post("youtube", c["autor"], c["texto"], c["url"], c["fecha"], ahora=ahora,
                                       asumir_gye=del_gye, barrio_defecto=barrio) for c in com]
    return [p for p in posts if p]


def _barrios_busqueda():
    """Barrios de Comunidad para buscar en YouTube, sin los nombres ruidosos
    (Centro, Kennedy...) que traerian videos de cualquier parte."""
    import comunidad
    ruidosos = getattr(comunidad, "_BARRIOS_RUIDOSOS", set())
    return sorted(b for b in comunidad.BARRIOS if b not in ruidosos and len(b) >= 5)


def buscar_barrio(barrio, ahora=None):
    """search.list (100 unidades): videos recientes que nombran el barrio y
    Guayaquil, los mas nuevos primero."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    desde = (ahora - dt.timedelta(hours=VIDEO_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = _get("search", {"part": "snippet", "q": '"%s" Guayaquil' % barrio, "type": "video", "order": "date",
                        "publishedAfter": desde, "regionCode": "EC", "relevanceLanguage": "es", "maxResults": 5}, 100)
    out = []
    for it in (d or {}).get("items") or []:
        sn = it.get("snippet") or {}
        vid = (it.get("id") or {}).get("videoId")
        f = _iso(sn.get("publishedAt"))
        if vid and f:
            out.append({"id": vid, "titulo": sn.get("title") or "", "fecha": f.isoformat()})
    return out


def _toca_busqueda(e, ahora):
    # YouTube tiene un limite propio de "busquedas por dia" (aparte de las
    # unidades) que tambien gasta el Pulso social; si respondio 429, no se
    # insiste hasta manana.
    if e.get("busqueda_bloqueada") == _hoy():
        return False
    hechas = int((e.get("busquedas") or {}).get(_hoy(), 0))
    if BUSQUEDAS_DIA <= 0 or hechas >= BUSQUEDAS_DIA:
        return False
    ult = _iso(e.get("ultima_busqueda"))
    return not ult or (ahora - ult).total_seconds() >= 24 * 3600 / BUSQUEDAS_DIA


def pasada(ahora=None, forzar=False):
    """Hilo de Comunidad. Devuelve (publicaciones_para_comunidad, texto_estado)."""
    global last_error
    last_error = None
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    if not _clave():
        return [], "sin MONITOR_YT_KEY"
    e = _estado()
    ult = _iso(e.get("ultima"))
    if not forzar and ult and (ahora - ult).total_seconds() < CADA_MIN * 60:
        return [], "todavia no toca"
    vistos = set(e.get("comentarios_vistos") or [])
    posts, n_videos, n_com = [], 0, 0
    for c in canales():
        for v in videos_recientes(c["id"], ahora):
            n_videos += 1
            com = [x for x in comentarios(v["id"]) if x["url"] not in vistos]
            com = [x for x in com if _iso(x["fecha"]) and (ahora - _iso(x["fecha"])).total_seconds() <= VIDEO_HORAS * 3600]
            n_com += len(com)
            vistos.update(x["url"] for x in com)
            posts += _a_comunidad(com, v, ahora)
    # Fase 24 (B2): una busqueda por barrio cada 24/BUSQUEDAS_DIA horas (100
    # unidades cada una), rotando la lista de barrios de Comunidad.
    busqueda = None
    if _toca_busqueda(e, ahora):
        barrios = _barrios_busqueda()
        if barrios:
            idx = int(e.get("busqueda_idx") or 0) % len(barrios)
            barrio = barrios[idx]
            videos = buscar_barrio(barrio, ahora)
            bloqueada = "search HTTP 429" in (last_error or "")
            busqueda = {"barrio": barrio, "idx": idx if bloqueada else idx + 1, "videos": len(videos),
                        "bloqueada": bloqueada}
            import comunidad
            for v in videos:
                n_videos += 1
                com = [x for x in comentarios(v["id"]) if x["url"] not in vistos]
                com = [x for x in com if _iso(x["fecha"]) and (ahora - _iso(x["fecha"])).total_seconds() <= VIDEO_HORAS * 3600]
                n_com += len(com)
                vistos.update(x["url"] for x in com)
                del_gye = comunidad.es_de_guayaquil(v["titulo"]) or barrio.lower() in v["titulo"].lower()
                posts += [p for p in (comunidad.normalizar_post("youtube", c["autor"], c["texto"], c["url"], c["fecha"],
                                                                ahora=ahora, asumir_gye=del_gye, barrio_defecto=barrio)
                                      for c in com) if p]
    with _LOCK:
        e = _estado()
        e["ultima"] = ahora.isoformat()
        if busqueda and busqueda["bloqueada"]:
            e["busqueda_bloqueada"] = _hoy()
        elif busqueda:
            e["ultima_busqueda"] = ahora.isoformat()
            e["busqueda_idx"] = busqueda["idx"]
            b = e.setdefault("busquedas", {})
            b[_hoy()] = int(b.get(_hoy(), 0)) + 1
            for k in sorted(b)[:-14]:
                del b[k]
        e["comentarios_vistos"] = list(vistos)[-5000:]
        res = e.setdefault("resultados", {}).setdefault(_hoy(), {"pasadas": 0, "videos": 0, "comentarios": 0, "utiles": 0})
        res["pasadas"] += 1
        res["videos"] += n_videos
        res["comentarios"] += n_com
        res["utiles"] += len(posts)
        for k in sorted(e["resultados"])[:-14]:
            del e["resultados"][k]
        _guardar(e)
    return posts, "youtube canales: %d videos, %d comentarios nuevos, %d utiles (%d unidades hoy)%s%s" % (
        n_videos, n_com, len(posts), unidades_hoy(),
        (" -- busqueda por barrio: %s, %d videos" % (busqueda["barrio"], busqueda["videos"])) if busqueda else "",
        (" -- %s" % last_error) if last_error else "")


def estado_dashboard():
    e = _estado()
    return {"canales": [{"nombre": c["nombre"], "verificado": c.get("verificado", False)} for c in canales()],
            "unidades_hoy": unidades_hoy(), "unidades_dia": UNIDADES_DIA, "cada_min": CADA_MIN,
            "hoy": (e.get("resultados") or {}).get(_hoy()), "ultima": e.get("ultima"), "ultimo_error": last_error,
            "busquedas_hoy": int((e.get("busquedas") or {}).get(_hoy(), 0)), "busquedas_dia": BUSQUEDAS_DIA,
            "busqueda_bloqueada_hoy": e.get("busqueda_bloqueada") == _hoy()}
