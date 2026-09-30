# -*- coding: utf-8 -*-
"""
Escucha social (social listening) desde FUENTES PUBLICAS y abiertas — solo stdlib.

Sin cuentas, sin tokens de usuario, sin pasar por los bloqueos de Meta/X:
  - Bluesky : endpoint XRPC PUBLICO (sin token). Es el termometro principal.
  - Reddit  : endpoint publico .json (best-effort; puede dar 403/429).
  - YouTube : Data API v3 CON clave (MONITOR_YT_KEY, gratis hasta 10.000
    unidades/dia). Si no hay clave, se salta limpio (no rompe nada).
  - Telegram: preview publico t.me/s/<canal> (sin clave, sin cuenta), sobre
    una lista de canales elegida a mano (MONITOR_TG_CANALES, vacia por
    defecto). A diferencia de las tres de arriba es BROADCAST (la voz del
    canal, no opinion ciudadana) -- sirve para el eje de seguridad y la
    recencia. MONITOR_NO_TELEGRAM=1 lo apaga.
Salida unificada (dataclass SocialPost) lista para el analisis OSINT con Ollama.

Todas las senales de aqui son RELATIVAS (likes, reposts, comentarios de LO QUE
SE CAPTO con estas consultas puntuales) -- nunca representan "cuanta gente" o
"cuantas personas" opinan de un tema; eso seria una extrapolacion que esta
herramienta no puede respaldar.
"""

import os, re, json, time, html, unicodedata, datetime as dt, urllib.request, urllib.parse, urllib.error
from dataclasses import dataclass, field, asdict

UA = "NewsDashboard-Bot/1.0 (proyecto estudiantil de periodismo; contacto: local)"
last_error = None
# Misma razon que en ia.py: sin num_ctx, Ollama usa el default del modelo
# (32768), que desperdicia VRAM y empuja parte del modelo a CPU en GPUs chicas.
IA_CTX = int(os.environ.get("MONITOR_IA_CTX", "4096"))
# BUG REAL (Frente A): la "mejor" publicacion de un tema podia ser de anios
# atras -- Bluesky con sort=top rankea por engagement de TODA la historia del
# termino, sin ventana de tiempo, asi que un post viejo con muchos likes le
# gana facil a la conversacion reciente real. Filtro de recencia GLOBAL: se
# aplica nativo en cada fuente (mas barato: no se trae ni se paga lo viejo) Y
# como respaldo centralizado en recolectar() (ver _es_reciente), por si una
# fuente no filtra perfecto.
SOCIAL_DIAS = int(os.environ.get("MONITOR_SOCIAL_DIAS", "1"))
# Fase 21 (pedido de Fernando, 2026-09-30: "estas recogiendo muchas noticias
# viejas y tweets o videos viejos de hace 2 o 3 dias... quiero que no cojas otra
# cosa que las cosas que se publican en las ultimas 10 horas"): ventana UNICA en
# HORAS para todo lo que entra como nuevo desde redes. SOCIAL_DIAS (bajado de 7 a
# 1) solo acota lo que se PIDE a cada API (su filtro nativo es por dia); el corte
# real es VENTANA_H, re-aplicado sobre el resultado en recolectar().
VENTANA_H = float(os.environ.get("MONITOR_VENTANA_H", "10"))

# ------------------------- alcance geografico (Problema 1) -------------------------
# Antes TODO el pulso social usaba un solo subreddit fijo (r/ecuador) y
# YouTube siempre con regionCode=EC/relevanceLanguage=es, sin importar si el
# TEMA era internacional -- el panel "Pulso social" no tenia alcance Mundo
# de verdad, todo terminaba acotado a Ecuador. Ahora cada fuente recibe el
# 'ambito' del tema (guayaquil/ecuador/internacional, el mismo que ya decide
# tema_ambito_map en monitor.py) y ajusta su consulta:
#  - Reddit: subreddits por ambito (r/ecuador para Ecuador/Guayaquil -- no
#    existe un subreddit de Guayaquil con actividad real confirmada, se deja
#    configurable por si Fernando quiere probar uno --, r/worldnews+r/europe
#    para Internacional via la sintaxis multi-subreddit nativa de Reddit
#    "r/sub1+sub2").
#  - YouTube: regionCode/relevanceLanguage solo para Ecuador/Guayaquil (asi
#    prioriza contenido en espanol de la region); Internacional no los fija,
#    para no perder creadores que opinan en otros idiomas.
REDDIT_SUB_POR_AMBITO = {
    "guayaquil": os.environ.get("MONITOR_REDDIT_SUB_GYE", "ecuador"),
    "ecuador": os.environ.get("MONITOR_REDDIT_SUB_EC", "ecuador"),
    "internacional": os.environ.get("MONITOR_REDDIT_SUB_INTL", "worldnews+europe"),
}
YT_REGION_POR_AMBITO = {
    "guayaquil": {"regionCode": "EC", "relevanceLanguage": "es"},
    "ecuador": {"regionCode": "EC", "relevanceLanguage": "es"},
    "internacional": {},  # sin regionCode/relevanceLanguage: no acota idioma/region
}

def _iso_completo(valor):
    """Fase 18 (P1-7): fecha COMPLETA con hora, en ISO UTC. Antes cada fuente
    guardaba solo 'YYYY-MM-DD' (se recortaba con [:10]) -- sin hora no se
    puede decir "hace 20 min" ni distinguir un post de esta tarde de uno de
    anoche, y una alerta de ayer quedaba igual que una de hoy. Acepta ISO
    (con 'Z' o con offset), epoch (segundos) o 'YYYY-MM-DD' (se deja asi:
    no se inventa una hora que la fuente no dio). '' si no se puede leer."""
    if valor in (None, ""):
        return ""
    try:
        if isinstance(valor, (int, float)):
            return dt.datetime.fromtimestamp(float(valor), dt.timezone.utc).isoformat(timespec="seconds")
        v = str(valor).strip()
        if len(v) == 10:
            dt.datetime.strptime(v, "%Y-%m-%d")
            return v
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        return ""


def _fecha_dt(fecha):
    f = _iso_completo(fecha)
    if not f:
        return None
    if len(f) == 10:
        return dt.datetime.strptime(f, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(f)


def _es_reciente(fecha, dias=None, horas=None):
    """True si 'fecha' esta dentro de los ultimos 'dias' dias (u 'horas'
    horas, si se pasa). Acepta ISO completo o 'YYYY-MM-DD'. Sin fecha valida =
    no se puede CONFIRMAR que sea reciente = se descarta: mejor perder una
    publicacion real sin fecha clara que mostrar una vieja como si fuera de
    ahora (mismo criterio de 'ante la duda' que el resto del proyecto)."""
    f = _fecha_dt(fecha)
    if f is None:
        return False
    delta = dt.datetime.now(dt.timezone.utc) - f
    if horas is not None:
        return -3600 <= delta.total_seconds() <= horas * 3600
    return 0 <= delta.days <= (dias if dias is not None else SOCIAL_DIAS)


@dataclass
class SocialPost:
    fuente: str                       # "bluesky" | "reddit" | "youtube"
    texto: str = ""
    autor: str = ""
    url: str = ""
    likes: int = 0
    reposts: int = 0                  # reposts (bsky) o upvotes (reddit)
    comentarios_n: int = 0
    ratio: float = 0.0                # upvote_ratio de Reddit (0..1); 0 si no aplica
    fecha: str = ""
    comentarios: list = field(default_factory=list)  # top comentarios (texto)
    tipo: str = "persona"             # "persona" | "medio" (ver es_cuenta_medio)
    canal: str = ""                   # YouTube: canal del video donde se comento
    canal_tipo: str = ""              # YouTube: "medio" | "creador" (ver _yt_canales_info, Problema 1)
    canal_subs: object = None         # YouTube: suscriptores del canal (int) o None si los oculta/no aplica

    def dict(self):
        return asdict(self)


# ------------------------- ¿persona o medio? -------------------------
# Pedido real (2026-09-22): "el pulso social mide lo que los MEDIOS dicen, no
# lo que dice la gente". En Bluesky buena parte de lo captado eran cuentas de
# medios/noticieros republicando sus notas. Heuristica por nombre de cuenta:
# no es perfecta (un periodista con cuenta personal cuenta como persona), pero
# separa lo grueso. Los COMENTARIOS de YouTube se cuentan como personas aunque
# el video sea de un medio (se guarda el canal para que se vea donde fue).
_MEDIO_HINTS = ("noticia", "news", "diario", "periodico", "prensa", "radio", "tv",
                "television", "canal", "media", "medio", "informa", "noticiero",
                "magazine", "revista", "press", "agencia", "online", "digital",
                "ecuavisa", "teleamazonas", "tctelevision", "gamavision", "rts",
                "eluniverso", "elcomercio", "expreso", "primicias", "extra",
                "lahora", "vistazo", "planv", "gkcity", "wambra", "confirmado",
                "larepublica", "elmercurio", "cronica", "pichincha", "oficial",
                "municipio", "alcaldia", "ministerio", "gobierno", "asamblea")

def es_cuenta_medio(*nombres):
    t = _sin_acentos(" ".join(n or "" for n in nombres)).lower()
    t = re.sub(r"[^a-z0-9]", "", t)
    return any(h in t for h in _MEDIO_HINTS)


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ------------------------- Bluesky (XRPC publico, sin token) -------------------------

# Nota: "public.api.bsky.app" empezo a devolver 403 en busquedas sin sesion
# (Bluesky restringio ese subdominio). "api.bsky.app" sigue siendo publico,
# sin cuenta ni token, y responde igual. Ver bluesky-social/bsky-docs#332.
BSKY = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"

def _bsky_url(uri, handle):
    # at://did/app.bsky.feed.post/<rkey>  ->  https://bsky.app/profile/<handle>/post/<rkey>
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    return "https://bsky.app/profile/%s/post/%s" % (handle, rkey) if rkey else ""

def bluesky_buscar(query, limit=25, dias=None):
    """Publicaciones publicas de Bluesky que mencionan 'query', con likes/reposts.
    'dias' (Frente A, def. SOCIAL_DIAS): usa el parametro nativo 'since' de la
    API (probado en vivo: SI existe y filtra server-side) para no traer ni
    pagar por publicaciones viejas -- antes 'sort=top' rankeaba por engagement
    de TODA la historia del termino, sin ventana de tiempo, y una publicacion
    de anios atras con muchos likes le ganaba a la conversacion real de ahora."""
    global last_error
    dias = SOCIAL_DIAS if dias is None else dias
    try:
        desde = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
        q = urllib.parse.urlencode({"q": query, "limit": min(limit, 100), "sort": "top", "since": desde})
        data = _get(BSKY + "?" + q)
        out = []
        for p in data.get("posts", []):
            rec = p.get("record", {}) or {}
            author = p.get("author", {}) or {}
            out.append(SocialPost(
                fuente="bluesky",
                texto=(rec.get("text") or "")[:500],
                autor=author.get("handle", ""),
                url=_bsky_url(p.get("uri", ""), author.get("handle", "")),
                likes=int(p.get("likeCount", 0) or 0),
                reposts=int(p.get("repostCount", 0) or 0),
                comentarios_n=int(p.get("replyCount", 0) or 0),
                fecha=_iso_completo(rec.get("createdAt") or p.get("indexedAt") or ""),
                tipo="medio" if es_cuenta_medio(author.get("handle", ""),
                                                 author.get("displayName", "")) else "persona",
            ))
        return out
    except urllib.error.HTTPError as e:
        last_error = "bluesky HTTP %s" % e.code
    except Exception as e:
        last_error = "bluesky %s" % type(e).__name__
    return []


# ------------------------- Reddit (.json publico, best-effort) -------------------------

def _reddit_t(dias):
    """Reddit solo acepta baldes fijos (hour/day/week/month/year/all) en 't',
    no un numero de dias arbitrario -- se usa el balde mas chico que cubra
    'dias' (Frente A). Antes estaba fijo en 'month' sin importar
    MONITOR_SOCIAL_DIAS (def. 7): traia hasta un mes de posts."""
    if dias <= 1: return "day"
    if dias <= 7: return "week"
    if dias <= 30: return "month"
    if dias <= 365: return "year"
    return "all"

def reddit_buscar(query, subreddit="", limit=10, con_comentarios=3, dias=None):
    """Posts de Reddit que mencionan 'query'. subreddit p.ej. 'ecuador' (sin r/).
    Trae los top comentarios de los primeros 'con_comentarios' posts."""
    global last_error
    dias = SOCIAL_DIAS if dias is None else dias
    t = _reddit_t(dias)
    try:
        if subreddit:
            base = "https://www.reddit.com/r/%s/search.json" % urllib.parse.quote(subreddit)
            params = {"q": query, "restrict_sr": 1, "sort": "relevance",
                      "t": t, "limit": limit, "raw_json": 1}
        else:
            base = "https://www.reddit.com/search.json"
            params = {"q": query, "sort": "relevance", "t": t,
                      "limit": limit, "raw_json": 1}
        data = _get(base + "?" + urllib.parse.urlencode(params))
        out = []
        for i, ch in enumerate(data.get("data", {}).get("children", [])):
            d = ch.get("data", {})
            permalink = d.get("permalink", "")
            post = SocialPost(
                fuente="reddit",
                texto=((d.get("title") or "") + " " + (d.get("selftext") or ""))[:500].strip(),
                autor=d.get("subreddit_name_prefixed", "") or ("u/" + str(d.get("author", ""))),
                url="https://www.reddit.com" + permalink if permalink else (d.get("url") or ""),
                likes=int(d.get("ups", 0) or 0),
                reposts=int(d.get("ups", 0) or 0),
                comentarios_n=int(d.get("num_comments", 0) or 0),
                ratio=float(d.get("upvote_ratio", 0) or 0),
                fecha=_iso_completo(d.get("created_utc")) if d.get("created_utc") else "",
            )
            if i < con_comentarios and permalink:
                post.comentarios = _reddit_comentarios(permalink)
                time.sleep(1)  # gentil con Reddit
            out.append(post)
        return out
    except urllib.error.HTTPError as e:
        last_error = "reddit HTTP %s" % e.code
    except Exception as e:
        last_error = "reddit %s" % type(e).__name__
    return []

def _reddit_comentarios(permalink, top=5):
    try:
        data = _get("https://www.reddit.com" + permalink + ".json?limit=%d&sort=top&raw_json=1" % top)
        coms = data[1].get("data", {}).get("children", []) if len(data) > 1 else []
        out = []
        for c in coms:
            body = (c.get("data", {}) or {}).get("body")
            if body:
                out.append(body[:300])
            if len(out) >= top:
                break
        return out
    except Exception:
        return []


# ------------------------- YouTube (Data API v3, con clave) -------------------------

# A diferencia de Bluesky/Reddit, YouTube SI requiere clave (gratis, cuota
# diaria). Se salta limpio si no esta configurada -- el resto del programa
# sigue funcionando igual, como cuando Reddit da 403.
YT_KEY = os.environ.get("MONITOR_YT_KEY", "")
YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YT_COMMENTS = "https://www.googleapis.com/youtube/v3/commentThreads"
# Cuota 10.000 unidades/dia: search.list cuesta 100 (!), commentThreads.list
# cuesta 1. Por eso se pide POCOS videos por busqueda (barato en unidades
# porque search.list cuesta lo mismo traiga 1 o 50 resultados, pero mas
# videos = mas llamadas a commentThreads despues) y MUCHOS comentarios por
# video (comentarios es la parte casi gratis de la cuota).
YT_MAX_VIDEOS = 5
YT_MAX_COMENTARIOS = 30
# Fase 21: 30 -> 2 dias. Videos viejos traian comentarios viejos (y el video
# en si aparecia en el panel). Los comentarios igual se cortan a VENTANA_H.
YT_DIAS = int(os.environ.get("MONITOR_YT_DIAS", "2"))
YT_CHANNELS = "https://www.googleapis.com/youtube/v3/channels"

def _yt_comment_url(video_id, comment_id):
    return "https://www.youtube.com/watch?v=%s&lc=%s" % (video_id, comment_id) if comment_id \
        else "https://www.youtube.com/watch?v=%s" % video_id

def _yt_canales_info(channel_ids):
    """channels.list (part=snippet,statistics) para el LOTE de canales de una
    busqueda (hasta 50 ids en una sola llamada, 1 unidad de cuota -- barato).
    Devuelve {channelId: {"nombre":.., "subs": int|None, "tipo": "medio"|"creador"}}.

    Problema 1 ("separar canales de medios de los de creadores"): el nombre
    del canal via 'es_cuenta_medio' (mismas palabras clave que Bluesky:
    "noticias"/"TV"/"diario"/nombres de medios ecuatorianos conocidos) es la
    señal PRINCIPAL -- confiable y ya probada en Bluesky. La cantidad de
    suscriptores se trae y se expone (Fernando pidio poder verla), pero NO
    decide sola el tipo: un creador independiente grande tambien puede tener
    cientos de miles de suscriptores, así que usarla como regla dura
    clasificaria mal. 'verificado' no esta expuesto en la Data API v3 publica
    de forma confiable (el campo que existia se descontinuo), por eso no se
    usa como señal aparte -- el nombre ya cubre los casos claros de medios
    verificados (su nombre de canal es el nombre del medio)."""
    if not channel_ids:
        return {}
    out = {}
    ids = list(dict.fromkeys(channel_ids))  # sin duplicados, preserva orden
    try:
        for i in range(0, len(ids), 50):  # channels.list acepta hasta 50 ids por llamada
            lote = ids[i:i + 50]
            params = {"part": "snippet,statistics", "id": ",".join(lote), "key": YT_KEY}
            data = _get(YT_CHANNELS + "?" + urllib.parse.urlencode(params))
            for it in data.get("items", []):
                cid = it.get("id", "")
                sn = it.get("snippet", {}) or {}
                st = it.get("statistics", {}) or {}
                nombre = sn.get("title", "")
                subs = None if st.get("hiddenSubscriberCount") else st.get("subscriberCount")
                out[cid] = {"nombre": nombre, "subs": int(subs) if subs is not None else None,
                            "tipo": "medio" if es_cuenta_medio(nombre) else "creador"}
    except Exception:
        pass  # sin datos de canal no es fatal: se sigue con "creador" por defecto
    return out

def youtube_buscar(query, max_videos=YT_MAX_VIDEOS, max_comentarios=YT_MAX_COMENTARIOS, dias=None,
                    regionCode="EC", relevanceLanguage="es"):
    """Busca videos de los ultimos YT_DIAS dias sobre 'query' y trae los
    comentarios de cada uno (commentThreads.list, order=relevance).
    order=relevance TAMBIEN en la busqueda de videos (no order=date): probado
    en vivo que 'date' trae los mas nuevos pero casi sin comentarios todavia
    (recien publicados), mientras que 'relevance' -- ya acotado a YT_DIAS --
    trae los que de verdad generaron conversacion. Se salta limpio si no hay
    MONITOR_YT_KEY.

    'regionCode'/'relevanceLanguage' (Problema 1, alcance por ambito): None
    para no acotar esa dimension (asi Internacional no pierde creadores en
    otros idiomas/regiones) -- monitor.py los pasa segun el ambito del tema
    via social.YT_REGION_POR_AMBITO.

    Cada SocialPost trae 'canal' (nombre del canal del video) y, nuevo,
    'canal_tipo' ("medio"/"creador", ver _yt_canales_info) y 'canal_subs'
    (suscriptores, o None si el canal los oculta) -- asi el dashboard puede
    separar de verdad "lo que dice la gente" (comentarios en canales de
    creadores/personas) de "lo que dicen los medios" (canales de medios),
    ademas de que CADA comentario individual ya se clasifica persona/medio
    segun si lo escribio el propio canal.

    'dias' (Frente A, def. SOCIAL_DIAS): YT_DIAS (30) solo filtra que el VIDEO
    exista hace poco -- no dice nada de CUANDO se escribio el comentario que
    termina mostrandose. order=relevance en comentarios puede traer uno viejo
    de un video de hace un mes. Se filtra cada comentario por su propio
    'publishedAt' antes de aceptarlo."""
    global last_error
    dias = SOCIAL_DIAS if dias is None else dias
    if not YT_KEY:
        return []
    try:
        desde = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=YT_DIAS)
        params = {"part": "snippet", "q": query, "type": "video",
                  "order": "relevance",
                  "publishedAfter": desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "maxResults": max_videos, "key": YT_KEY}
        if relevanceLanguage:
            params["relevanceLanguage"] = relevanceLanguage
        if regionCode:
            params["regionCode"] = regionCode
        data = _get(YT_SEARCH + "?" + urllib.parse.urlencode(params))
        videos = [it["id"]["videoId"] for it in data.get("items", [])
                  if it.get("id", {}).get("videoId")]
        canal_de = {it["id"]["videoId"]: (it.get("snippet", {}) or {}).get("channelTitle", "")
                    for it in data.get("items", []) if it.get("id", {}).get("videoId")}
        canal_id_de = {it["id"]["videoId"]: (it.get("snippet", {}) or {}).get("channelId", "")
                       for it in data.get("items", []) if it.get("id", {}).get("videoId")}
    except urllib.error.HTTPError as e:
        last_error = "youtube search HTTP %s" % e.code
        return []
    except Exception as e:
        last_error = "youtube search %s" % type(e).__name__
        return []

    canales_info = _yt_canales_info(list(canal_id_de.values()))

    out = []
    for vid in videos:
        cinfo = canales_info.get(canal_id_de.get(vid, ""), {})
        try:
            cparams = {"part": "snippet", "videoId": vid, "order": "relevance",
                       "maxResults": max_comentarios, "textFormat": "plainText", "key": YT_KEY}
            cdata = _get(YT_COMMENTS + "?" + urllib.parse.urlencode(cparams))
            for item in cdata.get("items", []):
                top = (item.get("snippet", {}) or {}).get("topLevelComment", {}) or {}
                sn = top.get("snippet", {}) or {}
                texto = (sn.get("textDisplay") or "").strip()
                if not texto:
                    continue
                fecha = _iso_completo(sn.get("publishedAt") or "")
                if not _es_reciente(fecha, dias):
                    continue  # comentario viejo en un video que sigue elegible: se descarta
                out.append(SocialPost(
                    fuente="youtube",
                    texto=texto[:500],
                    autor=sn.get("authorDisplayName", ""),
                    url=_yt_comment_url(vid, top.get("id", "")),
                    likes=int(sn.get("likeCount", 0) or 0),
                    reposts=0,
                    comentarios_n=int((item.get("snippet", {}) or {}).get("totalReplyCount", 0) or 0),
                    fecha=fecha,
                    # comentario de una persona; si lo escribio el propio canal, es el medio
                    tipo="medio" if (sn.get("authorDisplayName", "").lstrip("@").lower()
                                     == canal_de.get(vid, "").lower()) else "persona",
                    canal=canal_de.get(vid, ""),
                    canal_tipo=cinfo.get("tipo", "creador"),
                    canal_subs=cinfo.get("subs"),
                ))
        except urllib.error.HTTPError as e:
            # comentarios desactivados en ESE video (403/404) u otro error puntual:
            # se salta solo ese video, no aborta la busqueda entera
            last_error = "youtube comments HTTP %s" % e.code
            continue
        except Exception as e:
            last_error = "youtube comments %s" % type(e).__name__
            continue
    return out


# ------------------------- Telegram (preview publico t.me/s/, sin API) -------------------------
# Los canales de Telegram son BROADCAST (un emisor, muchos lectores) -- a
# diferencia de Bluesky/Reddit/YouTube no hay opinion ciudadana genuina aca,
# es la voz del canal. Sirve como eje de SEGURIDAD (canales de medios/fuentes
# ecuatorianas que suelen postear primero ahi) y de RECENCIA, NO reemplaza el
# pulso de opinion -- el dashboard lo etiqueta distinto (ver FUENTE_INFO en
# dashboard_template.html).
#
# Via STDLIB: se raspa el preview publico t.me/s/<canal> -- la pagina HTML
# que Telegram sirve SIN login para "embeber" un canal en otros sitios web.
# Se parsea con regex (no con una libreria de HTML: la estructura de esta
# pagina en particular es simple y estable, mismo criterio ya usado en
# gdelt.py para nombres propios). Esto NO es la API real de Telegram: no hay
# busqueda (se trae lo reciente del canal y se filtra localmente por
# palabra), no hay reply/forward counts, y las "vistas" son un conteo
# aproximado que el propio Telegram redondea (ej. "1.2K").
#
# Upgrade futuro anotado, NO implementado (decision pendiente de Fernando):
# Telethon (pip + api_id/api_hash de https://my.telegram.org) daria acceso a
# la API real de Telegram -- mensajes completos, reacciones, reply/forward
# counts -- pero deja de ser stdlib y pide credenciales de una cuenta real.

TG_CANALES = [c.strip().lstrip("@") for c in os.environ.get("MONITOR_TG_CANALES", "").split(",") if c.strip()]
# Palabras genericas que no sirven para filtrar contra canales ya curados a
# mano por Fernando (son de temas/seguridad de Ecuador de por si; que el
# texto diga "Ecuador" no dice nada sobre el TEMA puntual de la busqueda).
_TG_STOP = {"ecuador", "guayaquil", "noticias", "ultima", "ultimas", "informa", "informacion", "hora"}

_RE_TG_MSG = re.compile(r'<div class="tgme_widget_message[^"]*"[^>]*data-post="([^"]+)"', re.IGNORECASE)
_RE_TG_TEXT = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                         re.IGNORECASE | re.DOTALL)
_RE_TG_TIME = re.compile(r'<time[^>]*datetime="([^"]+)"', re.IGNORECASE)
_RE_TG_VIEWS = re.compile(r'<span class="tgme_widget_message_views">([^<]+)</span>', re.IGNORECASE)
_RE_TG_BR = re.compile(r'<br\s*/?>', re.IGNORECASE)
_RE_TG_TAGS = re.compile(r'<[^>]+>')

def _tg_texto(bloque_html):
    """Extrae el texto del mensaje de un bloque HTML de t.me/s/: <br> se
    convierte en salto de linea, el resto de tags (links, negrita, hashtags
    como <a>) se saca, y las entidades HTML (&amp;, &#39;, etc.) se
    decodifican."""
    m = _RE_TG_TEXT.search(bloque_html)
    if not m:
        return ""
    t = _RE_TG_BR.sub("\n", m.group(1))
    t = _RE_TG_TAGS.sub("", t)
    return html.unescape(t).strip()

def _tg_conteo(txt):
    """'1.2K'/'543'/'3.4M' -> entero aproximado (Telegram ya redondea el
    conteo real antes de mostrarlo, esto no pierde precision extra)."""
    t = (txt or "").strip().upper().replace(",", ".")
    try:
        if t.endswith("K"):
            return int(float(t[:-1]) * 1000)
        if t.endswith("M"):
            return int(float(t[:-1]) * 1000000)
        return int(t)
    except ValueError:
        return 0

def telegram_buscar(query, canales=None, limite_por_canal=20, dias=None):
    """Trae los ultimos posts de cada canal en 'canales' (MONITOR_TG_CANALES
    por defecto) desde su preview publico t.me/s/<canal>, y se queda con los
    que mencionan 'query'. Los canales NO tienen busqueda propia: se trae lo
    reciente de cada uno y se filtra localmente por palabra -- alcanza para
    el proposito de este panel ("que dice esta fuente sobre este tema"), no
    pretende ser una busqueda exhaustiva del historial del canal.

    Se salta limpio (lista vacia, sin marcar error) si MONITOR_NO_TELEGRAM=1
    o si no hay canales configurados -- MONITOR_TG_CANALES esta vacio por
    defecto a proposito, no hay una lista "segura" para adivinar, la elige
    Fernando a mano."""
    global last_error
    if os.environ.get("MONITOR_NO_TELEGRAM") == "1":
        return []
    canales = canales if canales is not None else TG_CANALES
    if not canales:
        return []
    dias = SOCIAL_DIAS if dias is None else dias
    palabras = [w for w in _sin_acentos(query).lower().split()
                if len(w) >= 4 and w not in _TG_STOP]
    out = []
    for canal in canales:
        try:
            req = urllib.request.Request(
                "https://t.me/s/%s" % urllib.parse.quote(canal),
                headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last_error = "telegram HTTP %s (%s)" % (e.code, canal)
            continue
        except Exception as e:
            last_error = "telegram %s (%s)" % (type(e).__name__, canal)
            continue

        matches = list(_RE_TG_MSG.finditer(raw))
        for i, m in enumerate(matches[-limite_por_canal:]):
            post_id = m.group(1)
            inicio = m.start()
            # siguiente mensaje en la lista COMPLETA (no en el slice recortado
            # de arriba), para no cortar el bloque de HTML por error
            idx_real = len(matches) - len(matches[-limite_por_canal:]) + i
            fin = matches[idx_real + 1].start() if idx_real + 1 < len(matches) else len(raw)
            bloque = raw[inicio:fin]

            texto = _tg_texto(bloque)
            if not texto:
                continue
            if palabras and not any(w in _sin_acentos(texto).lower() for w in palabras):
                continue
            tm = _RE_TG_TIME.search(bloque)
            fecha = _iso_completo(tm.group(1)) if tm else ""
            if not _es_reciente(fecha, dias):
                continue
            vm = _RE_TG_VIEWS.search(bloque)
            vistas = _tg_conteo(vm.group(1)) if vm else 0
            out.append(SocialPost(
                fuente="telegram",
                texto=texto[:500],
                autor="@" + canal,
                url="https://t.me/%s" % post_id if post_id else "https://t.me/s/%s" % canal,
                likes=vistas,  # el preview no expone reacciones: vistas es el unico conteo real
                reposts=0,     # el preview no expone reenvios
                fecha=fecha,
                tipo="medio",  # canal broadcast: nunca cuenta como voz ciudadana
            ))
    return out


# ------------------------- filtro de ruido -------------------------
# Sobre todo para YouTube: autopromocion ("mira el noticiero completo aqui
# 👉link"), reacciones de una palabra ("wow increible") o puro emoji. Se aplica
# UNA vez aqui (recolectar) para que tanto el panel del dashboard como
# analizar_osint() vean siempre los mismos posts limpios -- nunca se le manda
# ruido al modelo ni se muestra en la tarjeta.

_RUIDO_MIN_CHARS = 20  # letras/digitos reales minimos (sin emojis/links/signos)
_RE_LINK = re.compile(r"https?://\S+|www\.\S+")
_PROMO_HINTS = [
    "suscribete", "sigueme", "link en la bio", "clic aqui",
    "click aqui", "video completo", "completo aqui", "mira el noticiero",
    "mira el video", "ver el video completo", "descarga la app", "gana dinero",
    "promocion", "descuento", "oferta", "whatsapp", "contactanos",
    "escribeme", "envianos", "dm para",
]

def _sin_acentos(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def _es_ruido(texto, min_chars=_RUIDO_MIN_CHARS):
    """True si 'texto' aporta poco: muy corto una vez sacados emojis/links/
    signos, o autopromocion tipica de comentarios de YouTube. Heuristica de
    texto (sin libreria de NLP): no es perfecta, pero saca el ruido mas comun."""
    t = (texto or "").strip()
    if not t:
        return True
    sin_link = _RE_LINK.sub("", t)
    utiles = re.sub(r"[^\w]", "", sin_link, flags=re.UNICODE)
    if len(utiles) < min_chars:
        return True
    low = _sin_acentos(sin_link).lower()
    return any(h in low for h in _PROMO_HINTS)

def filtrar_ruido(posts, min_chars=_RUIDO_MIN_CHARS):
    """Devuelve solo los posts que aportan contenido real (ver _es_ruido)."""
    return [p for p in posts if not _es_ruido(p.texto, min_chars)]


# ------------------------- Mastodon (timeline publico de hashtag, sin token) -------------------------
# Mastodon NO tiene busqueda de texto libre sin autenticacion (a diferencia de
# Bluesky): /api/v2/search pide un token de cuenta en casi todas las
# instancias desde Mastodon 3.x. Lo que SI es publico y sin cuenta en la
# mayoria de instancias es la TIMELINE DE UN HASHTAG (GET
# /api/v1/timelines/tag/:hashtag) -- por eso 'query' se convierte a un
# hashtag razonable (sin espacios/acentos) antes de buscar. Es mas limitado
# que una busqueda de texto libre (solo atrapa posts que de verdad usaron ese
# hashtag), pero es real, gratis, y no requiere login -- mismo criterio que
# el resto de este modulo. Instancia por defecto: mastodon.social (la mas
# grande y con mas trafico en espanol/ingles); configurable por si Fernando
# prefiere otra con MONITOR_MASTODON_INSTANCIA.
MASTODON_INSTANCIA = os.environ.get("MONITOR_MASTODON_INSTANCIA", "mastodon.social")

def _mastodon_hashtag(query):
    """'medio ambiente Ecuador' -> 'medioambienteecuador' (Mastodon no separa
    hashtags por espacios; se junta todo, sin acentos, solo alfanumerico)."""
    t = _sin_acentos(query or "").lower()
    return re.sub(r"[^a-z0-9]", "", t)

def mastodon_buscar(query, instancia=None, limit=20, dias=None):
    """Publicaciones publicas recientes de la timeline de un hashtag derivado
    de 'query', desde una instancia de Mastodon (sin cuenta ni token).
    Se salta limpio (lista vacia) si el hashtag queda vacio o la instancia no
    responde -- best-effort, mismo trato que Reddit."""
    global last_error
    dias = SOCIAL_DIAS if dias is None else dias
    inst = instancia or MASTODON_INSTANCIA
    tag = _mastodon_hashtag(query)
    if not tag:
        return []
    try:
        url = "https://%s/api/v1/timelines/tag/%s?%s" % (
            inst, urllib.parse.quote(tag), urllib.parse.urlencode({"limit": limit}))
        data = _get(url)
        if not isinstance(data, list):
            return []
        out = []
        for p in data:
            texto_html = p.get("content", "") or ""
            texto = html.unescape(re.sub(r"<[^>]+>", " ", texto_html)).strip()
            if not texto:
                continue
            cuenta = p.get("account", {}) or {}
            out.append(SocialPost(
                fuente="mastodon",
                texto=texto[:500],
                autor=cuenta.get("acct", "") or cuenta.get("username", ""),
                url=p.get("url", "") or p.get("uri", ""),
                likes=int(p.get("favourites_count", 0) or 0),
                reposts=int(p.get("reblogs_count", 0) or 0),
                comentarios_n=int(p.get("replies_count", 0) or 0),
                fecha=_iso_completo(p.get("created_at") or ""),
                tipo="medio" if es_cuenta_medio(cuenta.get("acct", ""), cuenta.get("display_name", "")) else "persona",
            ))
        return out
    except urllib.error.HTTPError as e:
        last_error = "mastodon HTTP %s" % e.code
    except Exception as e:
        last_error = "mastodon %s" % type(e).__name__
    return []


# ------------------------- unificacion -------------------------

def recolectar(query, subreddit="ecuador", limite=15, youtube=True, dias=None, ambito=None, term_base=None):
    """Junta Bluesky + Reddit + YouTube (si hay MONITOR_YT_KEY y youtube=True)
    + Mastodon + Telegram (si hay MONITOR_TG_CANALES y no esta
    MONITOR_NO_TELEGRAM=1) para un termino, YA FILTRADO de ruido (ver
    filtrar_ruido) Y de antiguedad (Frente A, ver SOCIAL_DIAS/_es_reciente).
    Devuelve (posts, notas_de_error).

    'ambito' ("guayaquil"/"ecuador"/"internacional", Problema 1): si se pasa,
    PISA 'subreddit' con el/los subreddit(s) de REDDIT_SUB_POR_AMBITO y le
    pasa a YouTube el regionCode/relevanceLanguage de YT_REGION_POR_AMBITO --
    asi el pulso social tiene alcance real por ambito, no solo Ecuador
    siempre. Si no se pasa 'ambito' (compatibilidad), se usa 'subreddit' tal
    cual llegaba antes.

    'youtube=False' deja afuera la busqueda de YouTube para esta llamada
    puntual (monitor.py lo usa para no gastar cuota en cada tema, ver
    MONITOR_YT_MAX_BUSQ). Telegram no tiene ese limite -- el preview publico
    no es una API con cuota, es una pagina HTML gratis.

    'dias' se pasa a cada fuente (filtro nativo, mas barato: no se trae ni se
    paga lo viejo) Y ADEMAS se re-aplica aca como respaldo centralizado sobre
    el resultado combinado -- por si una fuente no filtra perfecto (ej. si
    Bluesky ignorara 'since' algun dia, o Reddit trae el balde 'week' entero
    aunque 'dias' pida 5). Bug real que motivo esto: la "mejor" publicacion de
    un tema podia ser de anios atras (Bluesky sort=top sin ventana de tiempo).

    'term_base' (Problema 1, bug real 2026-09-23): el termino SIN el sufijo
    de ambito que 'query' si lleva (ver _social_query en monitor.py) -- lo
    usa SOLO Mastodon, porque busca por HASHTAG y "carceles Ecuador" hashtag-
    ificado ("carcelesecuador") no matchea nada real (medido: 0 posts) contra
    "carceles" solo (20 posts). Si no se pasa, Mastodon usa 'query' tal cual
    (compatibilidad)."""
    global last_error
    dias = SOCIAL_DIAS if dias is None else dias
    if ambito:
        subreddit = REDDIT_SUB_POR_AMBITO.get(ambito, subreddit)
    yt_extra = YT_REGION_POR_AMBITO.get(ambito, {}) if ambito else {}
    posts, errs = [], []
    # 'last_error' se resetea ANTES de cada fuente: si no, una fuente que
    # devuelve vacio SIN fallar (0 resultados reales, no error) hereda por
    # error el ultimo mensaje que dejo la fuente anterior.
    last_error = None
    b = bluesky_buscar(query, limit=limite, dias=dias)
    if not b and last_error: errs.append(last_error)
    last_error = None
    r = reddit_buscar(query, subreddit=subreddit, limit=limite, dias=dias)
    if not r and last_error: errs.append(last_error)
    y = []
    if youtube and YT_KEY:
        last_error = None
        y = youtube_buscar(query, dias=dias, **yt_extra)
        if not y and last_error: errs.append(last_error)
    last_error = None
    # BUG REAL (Fernando, 2026-09-23, "pulso social sigue sin Guayaquil/
    # Ecuador"): Mastodon busca por HASHTAG, no texto libre -- pasarle el
    # 'query' YA con el sufijo de ambito ("carceles Ecuador", que arma
    # _social_query en monitor.py para Bluesky/YouTube) lo convertia en un
    # hashtag compuesto inventado ("carcelesecuador") que casi nadie usa de
    # verdad. Medido en vivo: "carceles Ecuador" -> 0 posts; "carceles" solo
    # -> 20 posts reales. 'term_base' (el termino SIN el sufijo de ambito,
    # que monitor.py ya tiene calculado) se usa aca en su lugar; el filtro
    # de ambito para Mastodon queda a cargo del respaldo por texto
    # (_post_es_foraneo en monitor.py), igual que ya se hacia con Bluesky/
    # Reddit cuando el termino solo no alcanza a acotar geografia.
    # Fase 18 (P1-7): Mastodon queda FUERA de los ambitos locales -- no hay
    # comunidad ecuatoriana ahi; medido el 2026-09-30, los 20 temas del Pulso
    # traian posts de Espana, Chile, Venezuela y Eslovaquia etiquetados como
    # "guayaquil". Sigue sirviendo para lo internacional.
    m = []
    if ambito not in ("ecuador", "guayaquil"):
        m = mastodon_buscar(term_base or query, dias=dias)
        if not m and last_error: errs.append(last_error)
    last_error = None
    t = telegram_buscar(query, dias=dias)
    if not t and last_error: errs.append(last_error)
    recientes = [p for p in (b + r + y + m + t)
                 if _es_reciente(p.fecha, dias) and _es_reciente(p.fecha, horas=VENTANA_H)]
    posts = filtrar_ruido(recientes)
    return posts, errs


# ------------------------- analisis OSINT con Ollama -------------------------

OLLAMA = "http://localhost:11434/api/generate"
_OSINT_PROMPT = (
    "Actua como analista OSINT. Te doy publicaciones y comentarios de redes sobre "
    "un tema. Responde SOLO un JSON valido con:\n"
    '{"sentimiento_general":"positivo|negativo|mixto",\n'
    ' "polarizacion":"alta|media|baja",\n'
    ' "temas_recurrentes":[strings],\n'
    ' "resumen_discusion":"1-2 lineas sintetizando la opinion publica"}.\n'
    "No inventes; basate solo en los textos.\n\nTEXTOS:\n%s"
)

def analizar_osint(posts, modelo="qwen2.5:3b", max_textos=40, timeout=120):
    """Manda los textos recolectados a Ollama y devuelve el dict OSINT, o None."""
    global last_error
    textos = []
    for p in posts[:max_textos]:
        textos.append("- " + p.texto)
        for c in p.comentarios[:3]:
            textos.append("   * " + c)
    if not textos:
        return None
    blob = "\n".join(textos)[:6000]
    try:
        data = json.dumps({"model": modelo, "prompt": _OSINT_PROMPT % blob,
                           "stream": False, "format": "json",
                           "options": {"temperature": 0.2, "num_predict": 240,
                                       "num_ctx": IA_CTX}}).encode("utf-8")
        req = urllib.request.Request(OLLAMA, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8", "replace"))
        return json.loads(out.get("response", "{}"))
    except Exception as e:
        last_error = "osint %s" % type(e).__name__
        return None


if __name__ == "__main__":  # prueba manual: python3 social.py "inseguridad Guayaquil"
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Ecuador"
    posts, errs = recolectar(q)
    por_fuente = {}
    for p in posts:
        por_fuente[p.fuente] = por_fuente.get(p.fuente, 0) + 1
    print("Recolectados %d posts %s (errores: %s)" % (len(posts), por_fuente, errs or "ninguno"))
    if not YT_KEY:
        print("(MONITOR_YT_KEY no esta configurada: YouTube se salto limpio)")
    if not TG_CANALES:
        print("(MONITOR_TG_CANALES no esta configurada: Telegram se salto limpio)")
    for p in posts[:8]:
        print(" [%s] %s | likes=%d reposts=%d coment=%d" %
              (p.fuente, p.texto[:70].replace("\n", " "), p.likes, p.reposts, p.comentarios_n))
    yts = [p for p in posts if p.fuente == "youtube"]
    if yts:
        print("\nEjemplos de YouTube:")
        for p in yts[:2]:
            print(" - %r (autor=%s, likes=%d)\n   %s" % (p.texto[:120], p.autor, p.likes, p.url))
