# -*- coding: utf-8 -*-
"""
Base de contraste oficial (Fase 3, 2026-09-23/24): documentos y boletines
oficiales para contrastar con lo que dicen las noticias, aparte de SERCOP y
Google Fact Check Tools (que ya existian). Solo libreria estandar.

Dos piezas:
  1. CONSTITUCION: el texto completo de la Constitucion del Ecuador de 2008,
     indexado por numero de articulo, para poder citar "Art. N" en un
     contraste. Fuente: Wikisource (es.wikisource.org), una transcripcion
     verificada colaborativamente -- NO es el PDF del Registro Oficial
     original, se lo etiqueta como tal en cualquier resultado (mejor una
     fuente secundaria verificable que ninguna, pero hay que ser honesto
     sobre que no es el documento primario escaneado). Se construye UNA VEZ
     (o cuando se pide a mano con reconstruir_constitucion()) y se guarda en
     constitucion.json -- la Constitucion no cambia todos los dias, no hace
     falta re-descargarla en cada corrida del monitor.
  2. BOLETINES OFICIALES: RSS reales de instituciones publicas ecuatorianas
     que SI tienen feed (probado a mano uno por uno, ver FUENTES abajo):
     Asamblea Nacional, INEC, Banco Central, Registro Oficial. Cacheados en
     oficial_cache.json con su propia frecuencia (mucho mas espaciada que
     las noticias -- estas instituciones publican pocas veces al dia, no
     hace falta chequear cada 1 minuto).

Probadas y SIN RSS publico en la URL mas obvia (HTTP 200 pero HTML, no XML):
Fiscalia General del Estado, Corte Constitucional, Contraloria General, CNE.
Funcion Judicial: error de conexion. Quedan fuera por ahora -- si aparece una
URL real de RSS/API para alguna, agregarla a FUENTES.
"""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Monitor-Noticias/1.0; personal research)"
TIMEOUT = 15

last_error = None


# ------------------------- Constitucion (Wikisource) -------------------------

CONSTITUCION_PATH = os.path.join(HERE, "constitucion.json")
# Titulos reales de la Constitucion de 2008 en Wikisource (confirmado en vivo
# con la API de prefixsearch, 2026-09-23/24) -- son sub-paginas, no una sola.
_TITULOS_WIKISOURCE = [
    "Constitución de Ecuador de 2008/TÍTULO I",
    "Constitución de Ecuador de 2008/TÍTULO II",
    "Constitución de Ecuador de 2008/TÍTULO III",
    "Constitución de Ecuador de 2008/TÍTULO IV",
    "Constitución de Ecuador de 2008/TÍTULO V",
    "Constitución de Ecuador de 2008/TÍTULO VI",
    "Constitución de Ecuador de 2008/TÍTULO VII",
    "Constitución de Ecuador de 2008/TÍTULO VIII",
    "Constitución de Ecuador de 2008/TÍTULO IX",
]


def _wikisource_wikitext(titulo):
    url = ("https://es.wikisource.org/w/api.php?action=query&prop=revisions&rvprop=content"
           "&rvslots=main&format=json&titles=" + urllib.parse.quote(titulo))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read())
    for _pid, page in data.get("query", {}).get("pages", {}).items():
        if "revisions" not in page:
            return ""
        return page["revisions"][0]["slots"]["main"]["*"]
    return ""


def _limpiar_wikitext(texto):
    texto = re.sub(r"'''|''", "", texto)
    texto = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    return texto.strip()


def reconstruir_constitucion():
    """Descarga y reindexa la Constitucion completa desde Wikisource. Tarda
    unos segundos (9 paginas). Se llama a mano cuando hace falta, NO en cada
    corrida del monitor -- ver construir_constitucion_si_hace_falta()."""
    global last_error
    last_error = None
    articulos = {}
    for titulo in _TITULOS_WIKISOURCE:
        try:
            wt = _wikisource_wikitext(titulo)
        except Exception as e:
            last_error = "wikisource %s (%s)" % (type(e).__name__, titulo)
            continue
        partes = re.split(r"'''Art\.\s*(\d+)\.?-?'''", wt)
        for i in range(1, len(partes), 2):
            num = partes[i]
            cuerpo = partes[i + 1] if i + 1 < len(partes) else ""
            articulos[num] = _limpiar_wikitext(cuerpo)[:1500]
    if not articulos:
        return None
    payload = {
        "ts": time.time(),
        "fuente": "es.wikisource.org (transcripcion verificada, no el PDF oficial escaneado)",
        "n_articulos": len(articulos),
        "articulos": articulos,
    }
    tmp = CONSTITUCION_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, CONSTITUCION_PATH)
    return payload


def _cargar_constitucion():
    try:
        with open(CONSTITUCION_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


CONSTITUCION_MAX_DIAS = 180  # se reconstruye sola si el cache tiene mas de esto


def construir_constitucion_si_hace_falta():
    """Se llama desde el monitor (una vez al arrancar, o desde el hilo
    trabajador) -- si constitucion.json no existe o esta vencida (180 dias:
    la Constitucion casi no cambia, pero puede haber enmiendas), la
    reconstruye. Nunca rompe la corrida si Wikisource falla."""
    cache = _cargar_constitucion()
    if cache and (time.time() - cache.get("ts", 0)) < CONSTITUCION_MAX_DIAS * 86400:
        return cache
    nuevo = reconstruir_constitucion()
    return nuevo or cache  # si fallo la reconstruccion, seguir usando lo viejo si habia


def articulo(numero):
    """Texto de UN articulo por numero (str o int). None si no esta
    indexado (revisar reconstruir_constitucion(), la cobertura no es
    100% -- algunos articulos con formato raro en Wikisource no se
    detectan, ver Pendientes)."""
    cache = _cargar_constitucion()
    if not cache:
        return None
    art = cache["articulos"].get(str(numero))
    if art is None:
        return None
    return {"numero": str(numero), "texto": art, "fuente": cache.get("fuente")}


def buscar_constitucion(query, limite=5):
    """Busca articulos de la Constitucion por texto libre (todas las
    palabras de 4+ letras deben aparecer). Devuelve una lista de
    {numero, texto, fuente} -- vacia si no hay indice todavia o nada
    coincide (nunca inventa un articulo)."""
    cache = _cargar_constitucion()
    if not cache:
        return []
    palabras = [w for w in re.findall(r"[a-záéíóúñ]{4,}", query.lower())]
    if not palabras:
        return []
    out = []
    for num, texto in cache["articulos"].items():
        low = texto.lower()
        if all(p in low for p in palabras):
            out.append({"numero": num, "texto": texto, "fuente": cache.get("fuente")})
    out.sort(key=lambda a: int(a["numero"]))
    return out[:limite]


# ------------------------- Boletines oficiales (RSS reales) -------------------------

# Cada URL probada a mano con fetch()+parse real antes de agregarla (2026-09-24).
# "frecuencia_seg" bien espaciado a proposito: estas instituciones publican
# pocas veces al dia, chequear cada 1 min (como las noticias) seria abusivo
# y no trae nada nuevo la enorme mayoria de las veces.
FUENTES = [
    {"nombre": "Asamblea Nacional", "url": "https://www.asambleanacional.gob.ec/es/rss.xml",
     "frecuencia_seg": 3600},
    {"nombre": "INEC", "url": "https://www.ecuadorencifras.gob.ec/feed/",
     "frecuencia_seg": 21600},
    {"nombre": "Banco Central del Ecuador", "url": "https://www.bce.fin.ec/feed/",
     "frecuencia_seg": 21600},
    {"nombre": "Registro Oficial", "url": "https://www.registroficial.gob.ec/feed/",
     "frecuencia_seg": 3600},
    # Probadas SIN RSS publico en la URL obvia (HTTP 200 pero HTML, no XML):
    # Fiscalia General (fiscalia.gob.ec/feed/), Corte Constitucional
    # (corteconstitucional.gob.ec/feed/), Contraloria General
    # (contraloria.gob.ec/feed/), CNE (cne.gob.ec/feed/). Funcion Judicial:
    # error de conexion (funcionjudicial.gob.ec/feed/). Si aparece una URL
    # real para alguna, agregarla aca.
]

OFICIAL_CACHE_PATH = os.path.join(HERE, "oficial_cache.json")


def _cargar_cache():
    try:
        with open(OFICIAL_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_cache(cache):
    tmp = OFICIAL_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, OFICIAL_CACHE_PATH)


def _parse_rss_simple(raw):
    """Parser minimo (solo lo que hace falta aca: titulo/link/fecha/resumen)
    -- evita importar monitor.py (dependencia circular: monitor ya importa
    modulos como este) y no necesita la clasificacion por tema/junk que
    hace parse_feed() para noticias."""
    from xml.etree import ElementTree as ET
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


def actualizar(respetar_frecuencia=True):
    """Chequea cada fuente de FUENTES (respetando su frecuencia_seg propia,
    igual que collect() de monitor.py con los feeds de noticias) y actualiza
    oficial_cache.json. Nunca rompe si una institucion no responde."""
    global last_error
    last_error = None
    cache = _cargar_cache()
    ahora = time.time()
    for f in FUENTES:
        entry = cache.get(f["url"], {})
        if respetar_frecuencia and (ahora - entry.get("ultimo_fetch", 0)) < f["frecuencia_seg"]:
            continue
        try:
            req = urllib.request.Request(f["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
            items = _parse_rss_simple(raw)
            cache[f["url"]] = {"nombre": f["nombre"], "ultimo_fetch": ahora,
                                "ultimo_ok": ahora, "items": items}
        except Exception as e:
            last_error = "%s (%s)" % (type(e).__name__, f["nombre"])
            entry["ultimo_fetch"] = ahora
            cache[f["url"]] = entry
    _guardar_cache(cache)
    return cache


def buscar_oficial(query, limite=8):
    """Busca en los boletines oficiales ya cacheados (nunca dispara una
    consulta nueva -- ver actualizar(), que corre aparte) por texto libre.
    Devuelve {institucion, titulo, link, fecha}. Vacio si no hay cache
    todavia o nada coincide."""
    cache = _cargar_cache()
    palabras = [w for w in re.findall(r"[a-záéíóúñ]{4,}", query.lower())]
    out = []
    for entry in cache.values():
        for it in entry.get("items", []):
            blob = (it["titulo"] + " " + it.get("resumen", "")).lower()
            if not palabras or any(p in blob for p in palabras):
                out.append({"institucion": entry.get("nombre", "?"), "titulo": it["titulo"],
                            "link": it["link"], "fecha": it.get("fecha", "")})
    return out[:limite]


def estado():
    """Resumen honesto de que hay disponible ahora mismo -- para el panel
    de salud de fuentes y para que el Asistente sepa si vale la pena
    consultar."""
    cache = _cargar_cache()
    const = _cargar_constitucion()
    return {
        "constitucion": {"disponible": bool(const), "n_articulos": const.get("n_articulos", 0) if const else 0},
        "boletines": {f["nombre"]: len((cache.get(f["url"]) or {}).get("items", [])) for f in FUENTES},
    }
