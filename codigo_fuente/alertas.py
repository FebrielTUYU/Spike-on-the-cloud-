# -*- coding: utf-8 -*-
"""
Alertas tempranas (Fase 8, 2026-09-25) -- avisos de ciudadanos y fuentes
oficiales de Ecuador/Guayaquil, para anticiparse a los medios SIN publicar
rumores como hechos. Modulo standalone (solo stdlib + social.py para
Bluesky/Telegram -- nunca importa monitor.py, mismo criterio que oficial.py/
declaraciones.py/casos.py para evitar import circular).

Investigacion de viabilidad hecha ANTES de escribir esto (ver CLAUDE.md,
Fase 8, para el detalle completo con evidencia real de esta sesion):
  - X/Twitter: NO se implementa. Ya no existe plan Basic fijo -- desde 2026
    es pago por uso ($0.015/post creado, $0.005/post LEIDO, tope 3M
    lecturas/mes antes de Enterprise; fuentes de terceros, la pagina oficial
    de precios de X devolvio 402 al intentar leerla). Scraping/login estan
    fuera por decision explicita del proyecto (viola terminos de servicio).
  - Bluesky: sin cuenta, sin token -- confirmado en vivo (api.bsky.app,
    2026-09-25, misma nota que social.py ya documenta: "public.api.bsky.app"
    empezo a pedir sesion, pero "api.bsky.app" SIGUE publico).
  - Telegram: se probaron 19 nombres de canal candidatos ademas de
    "alertaecuador" (ya conocido) -- NINGUNO nuevo resulto real (0/19).
    Confirma lo que ya documentaba el proyecto: adivinar nombres no
    funciona, MONITOR_TG_CANALES lo carga Fernando a mano.
  - Fuentes oficiales con RSS real (probado en vivo, HTTP 200 + XML valido):
    INAMHI (alertas meteorologicas), Secretaria Nacional de Gestion de
    Riesgos (bloqueaba curl sin User-Agent de navegador -- con uno real,
    200), INOCAR (via "?feed=rss2", no "/feed/"). Frecuencia de estas tres:
    boletines institucionales, no cada minuto -- se leen con su propio TTL,
    igual que oficial.py.
  - Instituto Geofisico (sismos): la pagina "Mapa Ultimos Sismos" no expone
    una URL de API/JSON visible en el HTML estatico (necesita inspeccionar
    trafico de red en un navegador real, no disponible en esta sesion) --
    PENDIENTE, no integrado.
  - CNEL (cortes programados): HTTP 503 sostenido en toda la sesion (con y
    sin User-Agent de navegador) -- posible mantenimiento o bloqueo, no se
    pudo verificar si tiene RSS/API en este momento. PENDIENTE.
  - Google Trends (picos de busqueda "incendio"/"balacera"+Guayaquil, etc.):
    NO integrado esta pasada (ver Pendientes) -- trends.py ya existe y el
    enganche es directo, pero se prioriazo dejar 3 fuentes reales
    funcionando de punta a punta antes de sumar una cuarta.

Estado de verificacion, NUNCA "verdadero": el programa solo mide
CORROBORACION (cuantas fuentes independientes coinciden en tipo+lugar+
ventana de tiempo, y si una fuente OFICIAL lo confirma) -- la verificacion
final la hace Fernando. Los 4 estados (orden creciente, nunca se degradan):
  1. sin_confirmar     -- una sola fuente.
  2. corroborado       -- 2+ fuentes independientes (distinto origen, no
                           reposts) coinciden, O 1 fuente social + 1 pico de
                           busqueda (si se engancha Trends mas adelante).
  3. confirmado_oficial -- lo dice una fuente oficial (ECU 911, Bomberos,
                           Gestion de Riesgos, INAMHI, INOCAR, IG, Municipio
                           -- via MONITOR_TG_CANALES si Fernando agrega esos
                           canales, o via las 3 fuentes RSS de arriba).
  4. ya_en_medios       -- ADEMAS de lo anterior (no lo reemplaza): una nota
                           de prensa real la cubrio -- se enlaza con la
                           historia y se mide cuantos MINUTOS se adelanto la
                           alerta a la prensa (metrica obligatoria pedida).
"""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

try:
    import social  # Bluesky/Telegram -- solo lectura, mismo modulo que ya usa el dashboard
except Exception:
    social = None

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT = 15

ALERTAS_PATH = os.path.join(HERE, "alertas.json")
ALERTAS_MAX_DIAS = int(os.environ.get("MONITOR_ALERTAS_MAX_DIAS", "14"))
# ventana para considerar dos senales "el mismo hecho" (mismo tipo+lugar):
# mas generosa que CLUSTER_MAX_HORAS de noticias porque una alerta ciudadana
# puntual (ej. un incendio) se resuelve en horas, no dias.
ALERTA_VENTANA_H = float(os.environ.get("MONITOR_ALERTA_VENTANA_H", "6"))
# Fase 18 (P1-6): nada viejo, nada mal enlazado. Una senal de mas de
# ALERTA_MAX_EDAD_H horas se descarta al recibirla; alerta e historia solo se
# enlazan si estan a <= ENLACE_MAX_H horas y el lugar es compatible. Caso real
# que motivo esto (alertas.json): la alerta de un vehiculo incendiado en La
# Atarazana (18-sep) quedo enlazada a "Incendio en vivienda del sur de
# Guayaquil" (29-sep); y alertas SIN lugar se enlazaban con notas de Estonia,
# Espana o Medellin porque sin lugar no se comparaba nada.
ALERTA_MAX_EDAD_H = float(os.environ.get("MONITOR_ALERTA_MAX_EDAD_H", os.environ.get("MONITOR_VENTANA_H", "10")))  # Fase 21: 24 -> 10 h
ENLACE_MAX_H = float(os.environ.get("MONITOR_ALERTA_ENLACE_H", "12"))

last_error = None


# ------------------------- deteccion: tipo de evento + lugar -------------------------

TIPO_KEYWORDS = {
    "incendio": ["incendio", "incendian", "incendiaron", "quemandose", "llamas", "voraz incendio"],
    "accidente": ["accidente de transito", "choque", "volcamiento", "atropello", "colision",
                  "accidente vial"],
    # Fase 18: "anegad" era un PREFIJO pero _hit exige palabra completa -- nunca
    # coincidia con "anegadas"/"anegado". Se listan las formas reales.
    "inundacion": ["inundacion", "inundaciones", "inundada", "inundadas", "inundado", "inundados",
                   "inunda", "anegada", "anegadas", "anegado", "anegados", "anegamiento",
                   "desborde", "aniego", "calles inundadas", "acumulacion de agua"],
    "balacera": ["balacera", "disparos", "tiroteo", "bala perdida", "rafaga de disparos",
                 "enfrentamiento armado"],
    "corte_luz": ["corte de luz", "sin luz", "apagon", "corte electrico", "falla electrica",
                  "sin energia electrica"],
    "corte_agua": ["corte de agua", "sin agua", "falla de agua", "corte del servicio de agua"],
    "protesta": ["protesta", "marcha", "bloqueo de via", "manifestantes", "paro nacional",
                 "cierre de via"],
    "sismo": ["sismo", "temblor", "terremoto", "replica sismica"],
}

# Sectores/ciudadelas/parroquias REALES de Guayaquil (nombres publicos, no
# inventados -- mismo criterio que CITIES["Guayaquil"] en monitor.py, que ya
# lista varios de estos). Frases completas o palabras poco ambiguas para
# evitar colisiones (mismo cuidado que EC_TERMS/CITIES: "kennedy" solo NO se
# agrega por la colision con JFK, se usa "kennedy norte"/"kennedy vieja").
BARRIOS_GYE = {
    "Alborada": ["alborada"], "Sauces": ["sauces"], "Kennedy": ["kennedy norte", "kennedy vieja"],
    "Urdesa": ["urdesa"], "Mapasingue": ["mapasingue"], "Guasmo": ["guasmo"],
    "Suburbio": ["suburbio oeste", "suburbio"], "Centro": ["centro de guayaquil"],
    "Ceibos": ["los ceibos", "ceibos"], "Samanes": ["samanes"],
    "Garzota": ["garzota"], "Bastion Popular": ["bastion popular"],
    "Flor de Bastion": ["flor de bastion"], "Isla Trinitaria": ["isla trinitaria"],
    "Pascuales": ["pascuales"], "Mucho Lote": ["mucho lote"],
    "Febres Cordero": ["febres cordero"], "Duran": ["duran"],
    "Samborondon": ["samborondon"], "Via a la Costa": ["via a la costa"],
    "Nueve de Octubre": ["9 de octubre", "nueve de octubre"],
    "Puerto Lisa": ["puerto lisa"], "Sergio Toral": ["sergio toral"],
    "Prosperina": ["prosperina"], "Monte Sinai": ["monte sinai"],
    # Fase 18 (P1-5): sectores reales de las lluvias del 29-sep que faltaban.
    "Atarazana": ["atarazana"], "Av. de las Americas": ["avenida de las americas", "av de las americas"],
    "Martha de Roldos": ["martha de roldos"], "Acacias": ["las acacias"],
    "Via a Daule": ["via a daule"], "Perimetral": ["via perimetral", "perimetral"],
}


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def _hit(term, blob):
    return re.search(r"\b" + re.escape(term) + r"\b", blob) is not None


# Un simulacro no es un evento real (caso real: el Simulacro Cantonal de sismo
# de Guayaquil llego a "corroborado" como alerta de sismo).
_NO_EVENTO = ("simulacro", "simulacros")


def detectar_tipo(texto):
    blob = _norm(texto)
    if any(_hit(w, blob) for w in _NO_EVENTO):
        return None
    for tipo, palabras in TIPO_KEYWORDS.items():
        if any(_hit(_norm(p), blob) for p in palabras):
            return tipo
    return None


def detectar_lugar(texto):
    blob = _norm(texto)
    for barrio, terminos in BARRIOS_GYE.items():
        if any(_hit(_norm(t), blob) for t in terminos):
            return barrio
    if _hit("guayaquil", blob):
        return "Guayaquil (sector sin precisar)"
    return None


# ------------------------- registro persistente (alertas.json) -------------------------

def _cargar():
    try:
        with open(ALERTAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar(registro):
    tmp = ALERTAS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False)
    os.replace(tmp, ALERTAS_PATH)


ESTADO_ORDEN = {"sin_confirmar": 0, "corroborado": 1, "confirmado_oficial": 2}
ESTADO_LABEL = {
    "sin_confirmar": "Sin confirmar",
    "corroborado": "Corroborado",
    "confirmado_oficial": "Confirmado oficial",
}


def _clave(tipo, lugar):
    return "%s|%s" % (tipo, lugar or "?")


def _recomputar_estado(alerta):
    """El estado NUNCA se degrada (una vez confirmado_oficial, sigue asi
    aunque una señal nueva sea mas debil) -- el programa mide corroboracion
    acumulada, no el ultimo dato."""
    oficial = any(s.get("oficial") for s in alerta["senales"])
    origenes = {(s["fuente"], s["autor"]) for s in alerta["senales"]}
    if oficial:
        nuevo = "confirmado_oficial"
    elif len(origenes) >= 2:
        nuevo = "corroborado"
    elif alerta.get("pico_busqueda") and len(origenes) >= 1:
        nuevo = "corroborado"
    else:
        nuevo = "sin_confirmar"
    actual = alerta.get("estado", "sin_confirmar")
    if ESTADO_ORDEN.get(nuevo, 0) > ESTADO_ORDEN.get(actual, 0):
        alerta["estado"] = nuevo
    return alerta["estado"]


def registrar_senal(fuente, autor, texto, url, fecha_iso, oficial=False, tipo=None, lugar=None):
    """Punto de entrada principal: procesa UNA señal (un post/bulletin) y la
    suma a una alerta existente (mismo tipo+lugar, dentro de
    ALERTA_VENTANA_H) o crea una nueva. Devuelve la alerta (dict) o None si
    el texto no describe ningun tipo de evento reconocido.

    Dedup por origen: un repost/mencion MAS del mismo (fuente, autor) dentro
    de la MISMA alerta no cuenta como una fuente independiente nueva (no
    hace avanzar el estado) -- pero SI se guarda como evidencia adicional."""
    tipo = tipo or detectar_tipo(texto)
    if not tipo:
        return None
    lugar = lugar if lugar is not None else detectar_lugar(texto)
    clave = _clave(tipo, lugar)
    registro = _cargar()

    ahora = dt.datetime.now(dt.timezone.utc)
    try:
        fecha = dt.datetime.fromisoformat(str(fecha_iso).replace("Z", "+00:00")) if fecha_iso else ahora
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=dt.timezone.utc)
    except Exception:
        fecha = ahora
    if (ahora - fecha).total_seconds() > ALERTA_MAX_EDAD_H * 3600:
        return None  # Fase 18 (P1-6): nada viejo

    # busca una alerta ABIERTA (misma clave, dentro de la ventana) para sumar
    # la señal ahi -- si no hay, crea una nueva.
    candidata = None
    for aid, a in registro.items():
        if a.get("clave") != clave:
            continue
        primera = dt.datetime.fromisoformat(a["primera_deteccion"])
        if abs((fecha - primera).total_seconds()) / 3600 <= ALERTA_VENTANA_H:
            candidata = a
            break

    señal = {"fuente": fuente, "autor": autor, "texto": texto[:400], "url": url,
              "fecha": fecha.isoformat(), "oficial": bool(oficial)}

    if candidata is None:
        aid = "%s-%d" % (clave.replace(" ", "_").replace("|", "_"), int(ahora.timestamp()))
        candidata = {
            "id": aid, "clave": clave, "tipo": tipo, "lugar": lugar,
            "primera_deteccion": fecha.isoformat(), "ultima_senal": fecha.isoformat(),
            "senales": [], "estado": "sin_confirmar", "pico_busqueda": False,
            "ya_en_medios": False, "historia_link": "", "historia_titulo": "",
            "ya_en_medios_ts": None, "adelanto_min": None, "avisado_hasta": "sin_confirmar",
        }
        registro[aid] = candidata

    ya_esta = any(s.get("fuente") == fuente and s.get("autor") == autor
                  and s.get("texto") == señal["texto"] for s in candidata["senales"])
    if not ya_esta:
        candidata["senales"].append(señal)
        if fecha.isoformat() > candidata.get("ultima_senal", ""):
            candidata["ultima_senal"] = fecha.isoformat()

    _recomputar_estado(candidata)
    _guardar(registro)
    return candidata


def marcar_pico_busqueda(tipo, lugar, ventana_ok=True):
    """Si Trends/Wikipedia detecta un pico de busqueda para un termino de
    este tipo+lugar (enganche pendiente, ver modulo docstring), marca la
    alerta abierta correspondiente para que cuente como señal de
    corroboracion adicional (1 fuente social + 1 pico de busqueda =
    corroborado, pedido explicito)."""
    clave = _clave(tipo, lugar)
    registro = _cargar()
    tocado = False
    for a in registro.values():
        if a.get("clave") == clave and not a.get("pico_busqueda"):
            a["pico_busqueda"] = bool(ventana_ok)
            _recomputar_estado(a)
            tocado = True
    if tocado:
        _guardar(registro)


# ------------------------- enlace con la prensa (Ya en medios) -------------------------

def vincular_con_prensa(historias):
    """Recorre las alertas activas (sin enlazar todavia) y las compara
    contra las HISTORIAS ya publicadas del feed normal (tipo+lugar en el
    titular/resumen, dentro de la ventana). Si una nota de prensa cubrio el
    mismo hecho, se enlaza (ya_en_medios=True) y se registra el ADELANTO en
    minutos (primera_deteccion -> ahora) -- la metrica obligatoria pedida.
    Nunca dispara red: 'historias' ya viene calculado por el pipeline
    normal. Devuelve cuantas alertas se enlazaron esta pasada."""
    registro = _cargar()
    cambiado = _revalidar_enlaces(registro)
    activas = [a for a in registro.values() if not a.get("ya_en_medios")]
    if not activas or not historias:
        if cambiado:
            _guardar(registro)
        return 0
    enlazadas = 0
    ahora = dt.datetime.now(dt.timezone.utc)
    for a in activas:
        for h in historias:
            if not _enlace_compatible(a, h):
                continue
            f0 = (h.get("fuentes") or [{}])[0]
            a["ya_en_medios"] = True
            a["historia_link"] = f0.get("link", "") or h.get("link", "")
            a["historia_titulo"] = h.get("titular", "")
            a["ya_en_medios_ts"] = ahora.isoformat()
            try:
                primera = dt.datetime.fromisoformat(a["primera_deteccion"])
                a["adelanto_min"] = round((ahora - primera).total_seconds() / 60, 1)
            except Exception:
                a["adelanto_min"] = None
            enlazadas += 1
            break
    if enlazadas or cambiado:
        _guardar(registro)
    return enlazadas


def _dt(iso):
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def _lugar_compatible(lugar, blob):
    if not lugar:
        return False  # sin lugar no hay nada que comparar: no se enlaza a ciegas
    if lugar == "Guayaquil (sector sin precisar)":
        return _hit("guayaquil", blob)
    terminos = BARRIOS_GYE.get(lugar, [lugar.lower()])
    return any(_hit(_norm(t), blob) for t in terminos)


def _enlace_compatible(a, h):
    """Fase 18 (P1-6): mismo tipo de hecho + lugar compatible + a <= ENLACE_MAX_H
    horas entre la ultima senal de la alerta y la nota mas nueva de la historia."""
    blob = _norm((h.get("titular", "") or "") + " " + (h.get("resumen", "") or ""))
    if detectar_tipo(blob) != a.get("tipo"):
        return False
    if not _lugar_compatible(a.get("lugar"), blob):
        return False
    t_alerta = _dt(a.get("ultima_senal") or a.get("primera_deteccion"))
    # historias sin hora (no pasa en el pipeline real, que siempre trae
    # 'newest'): se toman como del feed actual -- vincular_con_prensa solo
    # recibe las historias vivas de esta pasada.
    t_hist = _dt(h.get("newest")) or max((d for d in (_dt(f.get("date")) for f in (h.get("fuentes") or []))
                                          if d), default=None) or dt.datetime.now(dt.timezone.utc)
    if t_alerta is None:
        return False
    return abs((t_hist - t_alerta).total_seconds()) <= ENLACE_MAX_H * 3600


def _revalidar_enlaces(registro):
    """Deshace enlaces viejos que no cumplen las reglas de la Fase 18 (sin
    lugar, o el enlace se hizo mas de ENLACE_MAX_H horas despues de la
    ultima senal de la alerta). Devuelve True si cambio algo."""
    cambiado = False
    # alertas registradas antes de las reglas actuales cuyo texto ya no
    # describe un hecho real (ej. el simulacro de sismo) se borran.
    for aid in [k for k, a in registro.items()
                if a.get("senales") and not any(detectar_tipo(x.get("texto", "")) for x in a["senales"])]:
        del registro[aid]
        cambiado = True
    for a in registro.values():
        if not a.get("ya_en_medios"):
            continue
        t_alerta = _dt(a.get("ultima_senal") or a.get("primera_deteccion"))
        t_enlace = _dt(a.get("ya_en_medios_ts"))
        malo = not a.get("lugar") or t_alerta is None or t_enlace is None or \
            (t_enlace - t_alerta).total_seconds() > ENLACE_MAX_H * 3600
        if malo:
            a.update({"ya_en_medios": False, "historia_link": "", "historia_titulo": "",
                      "ya_en_medios_ts": None, "adelanto_min": None})
            cambiado = True
    return cambiado


# ------------------------- recoleccion de señales (hilo TRABAJADOR, con red) -------------------------

FUENTES_OFICIALES_RSS = [
    {"nombre": "INAMHI (alertas meteorologicas)", "url": "https://www.inamhi.gob.ec/feed/",
     "frecuencia_seg": 1800},
    {"nombre": "Secretaria Nacional de Gestion de Riesgos",
     "url": "https://www.gestionderiesgos.gob.ec/feed/", "frecuencia_seg": 1800},
    {"nombre": "INOCAR", "url": "https://www.inocar.mil.ec/web/?feed=rss2", "frecuencia_seg": 3600},
]

RSS_CACHE_PATH = os.path.join(HERE, "alertas_rss_cache.json")

_TERMINOS_BUSQUEDA = [t for palabras in TIPO_KEYWORDS.values() for t in palabras[:1]]


def _cargar_rss_cache():
    try:
        with open(RSS_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_rss_cache(cache):
    tmp = RSS_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, RSS_CACHE_PATH)


def _parse_rss_simple(raw):
    root = ET.fromstring(raw.lstrip())

    def tag(el):
        return el.tag.split("}")[-1]
    out = []
    for it in [e for e in root.iter() if tag(e) in ("item", "entry")]:
        title = link = date = summary = None
        for ch in it:
            t = tag(ch)
            if t == "title":
                title = (ch.text or "").strip()
            elif t == "link":
                link = (ch.text or "").strip() or ch.attrib.get("href")
            elif t in ("pubDate", "published", "updated", "date"):
                date = date or ch.text
            elif t in ("description", "summary", "encoded"):
                summary = summary or re.sub("<[^>]+>", "", ch.text or "").strip()
        if title:
            out.append({"titulo": title, "link": link or "", "fecha": date or "",
                        "resumen": (summary or "")[:280]})
    return out


def _fecha_rss(texto):
    """Fecha de un item RSS (RFC 822 o ISO) en ISO UTC; '' si no se lee."""
    if not texto:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(texto.strip())
    except Exception:
        d = _dt(texto.strip())
    if d is None:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat()


def _recolectar_oficiales():
    """Lee las 3 fuentes RSS oficiales confirmadas (ver docstring del
    modulo) y registra cada item nuevo como señal OFICIAL. Respeta
    frecuencia_seg propia (igual que oficial.py) -- estas instituciones
    publican pocas veces al dia."""
    global last_error
    cache = _cargar_rss_cache()
    ahora = time.time()
    nuevas = 0
    for f in FUENTES_OFICIALES_RSS:
        entry = cache.get(f["url"], {})
        if (ahora - entry.get("ultimo_fetch", 0)) < f["frecuencia_seg"]:
            continue
        vistos = set(entry.get("vistos", []))
        try:
            req = urllib.request.Request(f["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
            items = _parse_rss_simple(raw)
        except Exception as e:
            last_error = "%s (%s)" % (type(e).__name__, f["nombre"])
            entry["ultimo_fetch"] = ahora
            cache[f["url"]] = entry
            continue
        for it in items:
            if it["link"] in vistos:
                continue
            vistos.add(it["link"])
            r = registrar_senal(f["nombre"], f["nombre"], it["titulo"] + " " + it["resumen"],
                                 it["link"], _fecha_rss(it.get("fecha")), oficial=True)
            if r:
                nuevas += 1
        entry["ultimo_fetch"] = ahora
        entry["vistos"] = list(vistos)[-200:]
        cache[f["url"]] = entry
    _guardar_rss_cache(cache)
    return nuevas


def _recolectar_social():
    """Bluesky (sin cuenta) + Telegram (MONITOR_TG_CANALES, vacio por
    defecto) buscando los terminos de TIPO_KEYWORDS + 'Guayaquil'/'Ecuador'.
    Best-effort: si Bluesky/Telegram no responden, no rompe nada (mismo
    criterio que social.py)."""
    global last_error
    if social is None:
        return 0
    nuevas = 0
    for termino in _TERMINOS_BUSQUEDA:
        query = "%s Guayaquil" % termino
        try:
            posts = social.bluesky_buscar(query, limit=10, dias=1)
        except Exception as e:
            last_error = "bluesky %s" % type(e).__name__
            posts = []
        try:
            posts += social.telegram_buscar(termino, dias=1)
        except Exception as e:
            last_error = "telegram %s" % type(e).__name__
        for p in posts:
            # Fase 18 (P1-6): la fecha REAL del post (antes se pasaba "" y toda
            # senal quedaba fechada "ahora", aunque fuera de dias atras).
            if not getattr(p, "fecha", ""):
                continue
            r = registrar_senal("bluesky" if getattr(p, "fuente", "") == "bluesky" else p.fuente,
                                 p.autor, p.texto, p.url, p.fecha, oficial=False, tipo=None)
            if r:
                nuevas += 1
    return nuevas


# Fase 9, parte D3: X (via Apify) ya NO se recolecta desde aca -- lo hace
# redes.py (orquestador compartido X/TikTok, con su propio presupuesto y
# prioridad), que llama a registrar_senal() DIRECTAMENTE cuando encuentra un
# tweet de alerta (misma funcion, mismo criterio de dedup por (fuente,
# autor)). Tenerlo tambien aca hubiera pagado DOS VECES la misma llamada a
# Apify por pasada (bug real encontrado revisando el propio codigo antes de
# conectar D3: xapi.pasada() Y alertas._recolectar_x() llamaban las dos a
# xapi.buscar_alertas_gye() de forma independiente).


def recolectar_senales():
    """Punto de entrada del hilo TRABAJADOR (nunca run_fast -- hace llamadas
    de red reales). Devuelve un texto de estado honesto (cuantas señales
    nuevas de cada tipo de fuente). X/TikTok se reportan aparte (ver
    redes.pasada(), llamada desde monitor.py junto a esta funcion, nunca
    dentro de ella)."""
    global last_error
    last_error = None
    n_of = _recolectar_oficiales()
    n_soc = _recolectar_social()
    _purgar_viejas()
    return "oficiales: +%d, sociales: +%d%s" % (
        n_of, n_soc, (" (ultimo error: %s)" % last_error) if last_error else "")


def _purgar_viejas():
    registro = _cargar()
    corte = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=ALERTAS_MAX_DIAS)
    cambiado = False
    for aid in list(registro.keys()):
        try:
            ultima = dt.datetime.fromisoformat(registro[aid]["ultima_senal"])
        except Exception:
            continue
        if ultima < corte:
            del registro[aid]
            cambiado = True
    if cambiado:
        _guardar(registro)


# ------------------------- lectura para el dashboard / Asistente -------------------------

def pendientes_de_aviso(min_estado="corroborado"):
    """Alertas que llegaron (o subieron) a min_estado y todavia no se
    avisaron por ese escalon -- ntfy solo desde Corroborado hacia arriba
    (pedido explicito), y nunca dos veces por el mismo escalon."""
    registro = _cargar()
    umbral = ESTADO_ORDEN.get(min_estado, 1)
    out = []
    for a in registro.values():
        actual = ESTADO_ORDEN.get(a.get("estado", "sin_confirmar"), 0)
        avisado = ESTADO_ORDEN.get(a.get("avisado_hasta", "sin_confirmar"), 0)
        if actual >= umbral and actual > avisado:
            out.append(a)
    return out


def marcar_avisada(alerta_id):
    registro = _cargar()
    a = registro.get(alerta_id)
    if not a:
        return
    a["avisado_hasta"] = a.get("estado", "sin_confirmar")
    _guardar(registro)


def _iso_utc(s):
    """ISO normalizado a UTC para comparar como texto ('' si no se puede)."""
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        d = d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return ""


def listar_activas(min_estado="sin_confirmar"):
    """Alertas ordenadas por mas reciente primero, para el panel 'Alertas
    tempranas' del dashboard -- solo lectura, nunca dispara red."""
    registro = _cargar()
    umbral = ESTADO_ORDEN.get(min_estado, 0)
    # Fase 21: en el panel solo lo que tuvo una senal en las ultimas
    # ALERTA_MAX_EDAD_H horas (def. 10). El registro guarda mas dias para las
    # metricas de adelanto, pero eso ya no es "lo que pasa ahora".
    corte = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=ALERTA_MAX_EDAD_H)).isoformat()
    out = [a for a in registro.values() if ESTADO_ORDEN.get(a.get("estado"), 0) >= umbral
           and _iso_utc(a.get("ultima_senal")) >= corte]
    out.sort(key=lambda a: a.get("ultima_senal", ""), reverse=True)
    return out


def metricas_adelanto():
    """Minutos de adelanto real medidos (alertas que llegaron a 'ya en
    medios'), para el panel de Estadisticas -- lista vacia y honesta si
    todavia no hay ninguna."""
    registro = _cargar()
    vals = [a["adelanto_min"] for a in registro.values()
            if a.get("ya_en_medios") and a.get("adelanto_min") is not None]
    if not vals:
        return {"n": 0, "promedio_min": None, "mediana_min": None, "casos": []}
    vals_ordenados = sorted(vals)
    n = len(vals_ordenados)
    mediana = vals_ordenados[n // 2] if n % 2 else (vals_ordenados[n // 2 - 1] + vals_ordenados[n // 2]) / 2
    casos = [{"tipo": a["tipo"], "lugar": a.get("lugar"), "adelanto_min": a["adelanto_min"],
              "historia_titulo": a.get("historia_titulo", "")}
             for a in sorted(registro.values(), key=lambda a: a.get("ya_en_medios_ts") or "", reverse=True)
             if a.get("ya_en_medios")][:10]
    return {"n": n, "promedio_min": round(sum(vals) / n, 1), "mediana_min": round(mediana, 1),
            "casos": casos}
