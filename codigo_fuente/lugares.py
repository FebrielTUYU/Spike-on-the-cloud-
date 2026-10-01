# -*- coding: utf-8 -*-
"""
lugares.py -- Fase 24 (B4): ubicar en el mapa las noticias de Guayaquil que no
nombran un sector pero si un LUGAR (el aeropuerto, un hospital, un estadio, un
malecon, un centro comercial) o una CALLE ("calle Rumichaca", "avenida
Francisco de Orellana").

Antes: 86 de 144 historias de Guayaquil (30-sep) quedaban fuera del mapa porque
mapa.py solo conocia sectores. Muchas hablan de la ciudad entera (eso se
cuenta aparte, honesto); otras si nombran un sitio concreto.

De donde salen las coordenadas: de OpenStreetMap via Nominatim, NUNCA escritas
a mano. Reglas de uso de Nominatim respetadas: maximo 1 pedido por segundo, un
User-Agent propio, resultados guardados en cache (nominatim_cache.json) para no
repetir pedidos, y busqueda acotada a la caja de Guayaquil (countrycodes=ec +
viewbox bounded): un resultado fuera de la caja se descarta.

Dos hilos:
  - hilo rapido (mapa.puntos, sin red): encontrar() solo LEE la cache; si el
    lugar todavia no esta resuelto, lo deja anotado como pendiente en memoria.
  - hilo de Comunidad (con red): resolver_pendientes() pide a Nominatim hasta
    N pendientes por vuelta, de a uno por segundo.

lugares_gye.json es editable (se crea solo la primera vez): nombre, alias
(como aparece en una nota, sin tildes ni mayusculas) y la consulta que se le
manda a Nominatim.
"""
import datetime as dt
import json
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LUGARES_PATH = os.path.join(HERE, "lugares_gye.json")
CACHE_PATH = os.path.join(HERE, "nominatim_cache.json")
API = "https://nominatim.openstreetmap.org/search"
UA = "Spike/1.0 (monitor de noticias personal de un estudiante de periodismo, Guayaquil)"
# Caja de Guayaquil + Samborondon + Duran (lon_min, lat_max, lon_max, lat_min).
CAJA = (-80.10, -1.95, -79.75, -2.35)
REINTENTO_DIAS = 7          # un "no encontrado" se vuelve a pedir recien a la semana
PAUSA_S = 1.1               # Nominatim: maximo 1 pedido por segundo
MAX_POR_VUELTA = int(os.environ.get("MONITOR_NOMINATIM_MAX", "8"))

_PLANTILLA = {
    "_ayuda": ("Lugares de Guayaquil que el mapa puede ubicar. 'alias': como aparece en una nota (sin tildes ni "
               "mayusculas). 'consulta': lo que se busca en OpenStreetMap. Las coordenadas NO van aca: las trae "
               "Nominatim y quedan en nominatim_cache.json."),
    "lugares": [
        {"nombre": "Aeropuerto Jose Joaquin de Olmedo", "consulta": "Aeropuerto Internacional José Joaquín de Olmedo, Guayaquil",
         "alias": ["aeropuerto de guayaquil", "aeropuerto jose joaquin de olmedo", "aeropuerto internacional jose joaquin de olmedo"]},
        {"nombre": "Terminal Terrestre", "consulta": "Terminal Terrestre Jaime Roldós Aguilera, Guayaquil",
         "alias": ["terminal terrestre"]},
        {"nombre": "Malecon 2000", "consulta": "Malecón Simón Bolívar, Guayaquil", "alias": ["malecon 2000", "malecon simon bolivar"]},
        {"nombre": "Malecon del Salado", "consulta": "Malecón del Salado, Guayaquil", "alias": ["malecon del salado"]},
        {"nombre": "ESPOL", "consulta": "Escuela Superior Politécnica del Litoral, Guayaquil",
         "alias": ["espol", "escuela superior politecnica del litoral"]},
        {"nombre": "Universidad de Guayaquil", "consulta": "Universidad de Guayaquil, Guayaquil",
         "alias": ["universidad de guayaquil"]},
        {"nombre": "Estadio Monumental", "consulta": "Estadio Monumental Isidro Romero Carbo, Guayaquil",
         "alias": ["estadio monumental", "monumental banco pichincha"]},
        {"nombre": "Estadio George Capwell", "consulta": "Estadio George Capwell, Guayaquil",
         "alias": ["estadio capwell", "george capwell"]},
        {"nombre": "Estadio Modelo", "consulta": "Estadio Modelo Alberto Spencer, Guayaquil",
         "alias": ["estadio modelo", "modelo alberto spencer"]},
        {"nombre": "Penitenciaria del Litoral", "consulta": "Penitenciaría del Litoral, Guayaquil",
         "alias": ["penitenciaria del litoral", "carcel del litoral"]},
        {"nombre": "Hospital Luis Vernaza", "consulta": "Hospital Luis Vernaza, Guayaquil",
         "alias": ["hospital luis vernaza", "luis vernaza"]},
        {"nombre": "Hospital Teodoro Maldonado Carbo", "consulta": "Hospital Teodoro Maldonado Carbo, Guayaquil",
         "alias": ["teodoro maldonado carbo"]},
        {"nombre": "Hospital de Los Ceibos", "consulta": "Hospital General del Norte de Guayaquil Los Ceibos",
         "alias": ["hospital los ceibos", "hospital de los ceibos", "hospital del iess los ceibos"]},
        {"nombre": "Hospital Abel Gilbert Ponton", "consulta": "Hospital Abel Gilbert Pontón, Guayaquil",
         "alias": ["abel gilbert", "hospital guayaquil abel gilbert"]},
        {"nombre": "Hospital Francisco Icaza Bustamante", "consulta": "Hospital Francisco de Icaza Bustamante, Guayaquil",
         "alias": ["icaza bustamante"]},
        {"nombre": "Puente de la Unidad Nacional", "consulta": "Puente de la Unidad Nacional, Guayaquil",
         "alias": ["puente de la unidad nacional", "puente de la unidad"]},
        {"nombre": "Puerto Santa Ana", "consulta": "Puerto Santa Ana, Guayaquil", "alias": ["puerto santa ana"]},
        {"nombre": "Parque Seminario", "consulta": "Parque Seminario, Guayaquil",
         "alias": ["parque seminario", "parque de las iguanas"]},
        {"nombre": "Museo Presley Norton", "consulta": "Museo Presley Norton, Guayaquil", "alias": ["presley norton"]},
        {"nombre": "Guayarte", "consulta": "Guayarte, Guayaquil", "alias": ["guayarte"]},
        {"nombre": "Mall del Sol", "consulta": "Mall del Sol, Guayaquil", "alias": ["mall del sol"]},
        {"nombre": "Mall del Sur", "consulta": "Mall del Sur, Guayaquil", "alias": ["mall del sur"]},
        {"nombre": "San Marino", "consulta": "San Marino Shopping, Guayaquil", "alias": ["san marino shopping", "centro comercial san marino"]},
        {"nombre": "Policentro", "consulta": "Policentro, Guayaquil", "alias": ["policentro"]},
        {"nombre": "City Mall", "consulta": "City Mall, Guayaquil", "alias": ["city mall"]},
        {"nombre": "Mercado de la Caraguay", "consulta": "Mercado Caraguay, Guayaquil", "alias": ["caraguay"]},
        {"nombre": "La Bahia", "consulta": "La Bahía, Guayaquil", "alias": ["la bahia de guayaquil", "bahia de guayaquil"]},
        {"nombre": "Florida Norte", "consulta": "Florida Norte, Guayaquil",
         "alias": ["florida norte", "sector de la florida", "sector la florida"]},
        {"nombre": "Isla Santay", "consulta": "Isla Santay", "alias": ["isla santay"]},
        {"nombre": "Cerro Blanco", "consulta": "Bosque Protector Cerro Blanco, Guayaquil", "alias": ["cerro blanco"]},
        {"nombre": "Puerto Maritimo", "consulta": "Puerto Marítimo Simón Bolívar, Guayaquil",
         "alias": ["puerto maritimo de guayaquil", "contecon"]},
    ],
}

_LOCK = threading.RLock()
_PENDIENTES = {}   # consulta -> nombre a mostrar (lo llena el hilo rapido, lo vacia el de Comunidad)
_cache_mem = None
_cache_mtime = None


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_lugares_mem = (None, None)


def lugares():
    """Lista editable (lugares_gye.json), releida solo si el archivo cambio: el
    mapa la consulta por cada historia en el hilo rapido."""
    global _lugares_mem
    try:
        m = os.path.getmtime(LUGARES_PATH)
    except OSError:
        m = None
    if m is not None and _lugares_mem[0] == m:
        return _lugares_mem[1]
    out = _leer_lugares()
    if m is None:
        try:
            m = os.path.getmtime(LUGARES_PATH)
        except OSError:
            m = None
    _lugares_mem = (m, out)
    return out


def _leer_lugares():
    try:
        with open(LUGARES_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        d = _PLANTILLA
        try:
            with open(LUGARES_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    except Exception:
        d = _PLANTILLA
    return [l for l in (d.get("lugares") or []) if l.get("nombre") and l.get("consulta")]


def _cache():
    """Cache de Nominatim, releida del disco solo si cambio (la escribe el otro hilo)."""
    global _cache_mem, _cache_mtime
    try:
        m = os.path.getmtime(CACHE_PATH)
    except OSError:
        return _cache_mem or {}
    if _cache_mem is None or m != _cache_mtime:
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                _cache_mem = json.load(f) or {}
            _cache_mtime = m
        except Exception:
            _cache_mem = _cache_mem or {}
    return _cache_mem


def _guardar_cache(c):
    global _cache_mem, _cache_mtime
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)
    _cache_mem, _cache_mtime = c, os.path.getmtime(CACHE_PATH)


def _contiene(texto_n, alias_n):
    return bool(alias_n) and re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(alias_n), texto_n) is not None


# "calle Rumichaca", "avenida Francisco de Orellana", "av. 9 de Octubre". El
# nombre: hasta 5 palabras que empiezan con mayuscula o son numeros/conectores.
_PREFIJO_CALLE = re.compile(r"(?i)\b(calle|avenida|av\.)\s+")
_CONECTOR = {"de", "del", "la", "las", "los"}
_NO_CALLE = {"principal", "secundaria", "central"}


def _es_nombre(palabra):
    return bool(re.match(r"^([A-ZÁÉÍÓÚÑ][\wáéíóúñ]*|\d+)$", palabra))


def calles_en(texto):
    """[(como se muestra, nombre para buscar)]. Lee palabra por palabra despues
    de "calle"/"avenida"/"av.": nombres propios o numeros, con "de/del/la" solo
    entre dos de ellos; corta en "y", en la puntuacion o en otra calle (asi
    "calle Rumichaca y la Av. 9 de Octubre" da las dos, no una sola)."""
    texto = texto or ""
    out = []
    for m in _PREFIJO_CALLE.finditer(texto):
        resto = re.split(r"[,.;:()\n]", texto[m.end():], maxsplit=1)[0]
        palabras = resto.split()
        nombre = []
        for k, w in enumerate(palabras[:8]):
            if _PREFIJO_CALLE.match(w + " ") or w.lower() == "y":
                break
            if _es_nombre(w):
                nombre.append(w)
            elif w.lower() in _CONECTOR and k + 1 < len(palabras) and _es_nombre(palabras[k + 1]):
                nombre.append(w)
            else:
                break
            if len(nombre) >= 5:
                break
        nombre = " ".join(nombre)
        # "calle 17" sola no sirve: hay una en cada ciudadela. Hace falta al
        # menos una palabra (no solo numeros).
        if not nombre or norm(nombre) in _NO_CALLE or not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3}", nombre):
            continue
        tipo = "Calle" if m.group(1).lower() == "calle" else "Avenida"
        # "avenida del Bombero": el nombre de la via incluye la palabra Avenida.
        buscar = ("%s %s" % (tipo, nombre)) if nombre.split()[0].lower() in _CONECTOR else nombre
        out.append(("%s %s" % (tipo, nombre), buscar))
    return out


def _resuelto(consulta):
    e = _cache().get(consulta)
    if e and e.get("lat") is not None:
        return (e["lat"], e["lon"])
    return None


def _anotar_pendiente(consulta, nombre):
    e = _cache().get(consulta)
    if e and e.get("lat") is None:
        f = e.get("ts")
        try:
            if f and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(f)).days < REINTENTO_DIAS:
                return  # ya se busco hace poco y no aparecio
        except Exception:
            pass
    with _LOCK:
        _PENDIENTES.setdefault(consulta, nombre)


def encontrar(texto):
    """(nombre, (lat, lon), metodo) del primer lugar con nombre del texto que ya
    tenga coordenadas en cache; None si no hay. Sin red: lo que falta queda
    pendiente para resolver_pendientes()."""
    tn = norm(texto)
    if not tn:
        return None
    hallado = None
    for l in lugares():
        if any(_contiene(tn, norm(a)) for a in (l.get("alias") or [])):
            c = _resuelto(l["consulta"])
            if c:
                return l["nombre"], c, "lugar"
            _anotar_pendiente(l["consulta"], l["nombre"])
    for calle, nombre_calle in calles_en(texto):
        consulta = "calle:%s" % nombre_calle
        c = _resuelto(consulta)
        if c and hallado is None:
            hallado = (calle, c, "calle")
        elif not c:
            _anotar_pendiente(consulta, calle)
    return hallado


def pendientes():
    with _LOCK:
        return dict(_PENDIENTES)


def _en_caja(lat, lon):
    lon_min, lat_max, lon_max, lat_min = CAJA
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _buscar(consulta):
    params = {"format": "jsonv2", "limit": "1", "countrycodes": "ec",
              "viewbox": ",".join(str(x) for x in CAJA), "bounded": "1"}
    if consulta.startswith("calle:"):
        # Calles: busqueda estructurada (la libre "Calle Rumichaca, Guayaquil"
        # no encuentra nada; street=Rumichaca&city=Guayaquil si, probado en vivo).
        params.update(street=consulta[6:], city="Guayaquil")
    else:
        params["q"] = consulta
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": UA, "Accept-Language": "es"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8")) or []


def resolver_pendientes(max_n=None, buscar=None, dormir=time.sleep):
    """Hilo de Comunidad: pide a Nominatim hasta max_n lugares pendientes, de a
    uno por segundo. Devuelve un texto con lo que hizo."""
    max_n = MAX_POR_VUELTA if max_n is None else max_n
    buscar = buscar or _buscar
    with _LOCK:
        cola = list(_PENDIENTES.items())[:max_n]
    if not cola:
        return "lugares: nada pendiente"
    c = dict(_cache())
    ok = no = err = 0
    for i, (consulta, nombre) in enumerate(cola):
        if i:
            dormir(PAUSA_S)
        ahora = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        try:
            res = buscar(consulta)
        except Exception as e:
            err += 1
            if "429" in str(e) or "403" in str(e):
                break  # Nominatim pide parar: se reintenta en la proxima vuelta
            continue
        r0 = res[0] if res else None
        lat = lon = None
        if r0:
            try:
                lat, lon = float(r0["lat"]), float(r0["lon"])
            except Exception:
                lat = lon = None
        # Una calle tiene que volver como via (category highway): la busqueda
        # libre de "Avenida 9 de Octubre" devolvia una iglesia (probado en vivo).
        es_calle = consulta.startswith("calle:")
        if r0 and lat is not None and _en_caja(lat, lon) and (not es_calle or r0.get("category") == "highway"):
            c[consulta] = {"nombre": nombre, "lat": round(lat, 5), "lon": round(lon, 5),
                           "osm": (r0.get("display_name") or "")[:160], "ts": ahora}
            ok += 1
        else:
            c[consulta] = {"nombre": nombre, "lat": None, "lon": None, "ts": ahora}
            no += 1
        with _LOCK:
            _PENDIENTES.pop(consulta, None)
    _guardar_cache(c)
    return "lugares: %d ubicados, %d no encontrados%s" % (ok, no, (", %d con error" % err) if err else "")
