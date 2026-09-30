# -*- coding: utf-8 -*-
"""
Monitor de "mercado" de noticias — Ecuador (politica y economia).
Version 1 (MVP). Solo libreria estandar de Python 3. Sin dependencias.

Que hace:
  1. Lee los feeds RSS/Atom definidos en feeds.py.
  2. Deduplica notas repetidas.
  3. Agrupa (clusteriza) la misma historia contada por varios medios.
  4. Etiqueta cada historia con temas por palabras clave.
  5. Calcula PROMINENCIA (cuantos medios la levantaron, cuantas notas, que tan
     reciente). Las senales se guardan por separado, no en un solo puntaje.
  6. Genera un dashboard HTML autonomo (dashboard.html) y un data.json.

Uso:
  python3 monitor.py               # corre todo y regenera el dashboard
  MONITOR_SAMPLE=1 python3 monitor.py   # datos de ejemplo (sin internet, para probar)

Lo que v1 NO hace todavia (fase 1.5 / 2):
  - Demanda de busquedas (Google Trends): ver hueco marcado abajo.
  - Descubrimiento sobre datos del SERCOP: es otro programa (fase 2).
"""

import sys, os, json, re, html, random, unicodedata, datetime as dt
import time, threading, webbrowser, hashlib, math, difflib, contextlib
import urllib.request, urllib.error
import http.server, socketserver
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor  # stdlib: paralelizar fetch de feeds (I/O de red)

try:
    from feeds import FEEDS, KEYWORDS, TREND_TERMS, WIKI_TERMS
except Exception:
    print("No encuentro feeds.py en esta carpeta. Debe estar junto a monitor.py.")
    sys.exit(1)

# Fase 18 (P1-8): feeds/sitemaps que 'python monitor.py probar_sitemaps'
# confirmo que responden desde ESTA PC (feeds_extra.json, se genera solo).
FEEDS_EXTRA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feeds_extra.json")
try:
    with open(FEEDS_EXTRA_PATH, encoding="utf-8") as _f:
        _extra = [x for x in json.load(_f).get("feeds", []) if x.get("url")]
    _urls = {x["url"] for x in FEEDS}
    FEEDS = list(FEEDS) + [x for x in _extra if x["url"] not in _urls]
except Exception:
    pass

try:
    import trends  # cliente de Google Trends (demanda); opcional
except Exception:
    trends = None
try:
    import wiki    # vistas de Wikipedia (interes estable); opcional
except Exception:
    wiki = None
try:
    import gdelt   # cobertura mediatica + tono (GDELT); opcional
except Exception:
    gdelt = None
try:
    import sercop  # contratos publicos (SERCOP/OCDS) para contrastar; opcional
except Exception:
    sercop = None
try:
    import ia      # agente de IA local (Ollama) para entender contexto; opcional
except Exception:
    ia = None
try:
    import social  # escucha social (Bluesky/Reddit publicos) + OSINT con Ollama; opcional
except Exception:
    social = None
try:
    import factcheck  # Google Fact Check Tools (claims:search); opcional
except Exception:
    factcheck = None
try:
    import movil  # avisos al iPhone (ntfy) + acceso al dashboard desde el celular; opcional
except Exception:
    movil = None
try:
    import agente  # Asistente de IA (Bloque 2, Parte F): agente con herramientas sobre los datos; opcional
except Exception:
    agente = None
try:
    import oficial  # Base de contraste oficial (Fase 3): Constitucion + boletines institucionales; opcional
except Exception:
    oficial = None
try:
    import declaraciones as decl  # Fase 5: registro de declaraciones atribuidas, nunca purgado por MONITOR_MAX_DIAS; opcional
except Exception:
    decl = None
try:
    import casos  # Fase 7 (Pasos B-E): Asistente de casos -- documentos, entidades, avisos, chat por caso; opcional
except Exception:
    casos = None
try:
    import alertas  # Fase 8: alertas tempranas (ciudadanos + fuentes oficiales), nunca declara "verdadero"; opcional
except Exception:
    alertas = None
try:
    import contraste  # Fase 18 (P2-11): contraste rediseñado (documento oficial primero, hallazgo o nada); opcional
except Exception:
    contraste = None
try:
    import senales  # Fase 15/18 (P0-4): motor de senales -- escrito en la Fase 15, conectado recien ahora; opcional
except Exception:
    senales = None
try:
    import contexto  # Fase 11 (v2): contexto de 4 bloques (antecedentes/actores/que_es_nuevo/que_falta_saber); opcional
except Exception:
    contexto = None
try:
    import redes  # Fase 9, parte D3: orquestador de X+TikTok via Apify (xapi.py/tiktok.py) -- apagado sin token; opcional
except Exception:
    redes = None
try:
    import webview  # Fase 12: ventana nativa de escritorio (pywebview); opcional
except Exception:
    webview = None
import hmac, urllib.parse, http.cookies, base64, uuid

# Puerto real del servidor (lo fija serve); los avisos lo usan para armar el enlace
MOVIL_PUERTO = 8000

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------- Fase 17: log de arranque con tiempos por etapa -------------------------
# Pedido real de Fernando: el .exe (a diferencia de "python monitor.py") corre
# sin consola visible (--windows-console-mode=attach, Fase 16) -- un print()
# durante el arranque no lo ve nadie. Este archivo, junto al programa (mismo
# HERE que data.json/.env), es la UNICA forma de diagnosticar una carga lenta
# o colgada en el .exe. Se trunca UNA vez por proceso (la primera llamada), asi
# siempre refleja el ULTIMO arranque, no un historial que crece sin limite;
# despues de esa primera vez, se abre en modo "append" -- abrir en "w" en cada
# llamada hubiera perdido las lineas ya escritas por ESTE mismo proceso.
LOG_ARRANQUE_PATH = os.path.join(HERE, "arranque.log")
_log_arranque_truncado = False

def _log_arranque(linea):
    """Escribe una linea con timestamp real a arranque.log (nunca lanza: un
    fallo de disco en el log no puede tumbar el arranque real) y tambien la
    imprime (para cuando SI hay consola, ej. 'python monitor.py serve')."""
    global _log_arranque_truncado
    ts = dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    texto = "[%s] %s" % (ts, linea)
    print(texto)
    try:
        modo = "w" if not _log_arranque_truncado else "a"
        with open(LOG_ARRANQUE_PATH, modo, encoding="utf-8") as f:
            f.write(texto + "\n")
        _log_arranque_truncado = True
    except Exception:
        pass

@contextlib.contextmanager
def _medir_etapa(nombre):
    """Context manager chico: loguea INICIO/FIN + duracion de un bloque, sin
    cambiar su comportamiento (si el bloque lanza, se relanza tal cual
    despues de loguear cuanto tardo hasta el error -- no se traga ninguna
    excepcion que el llamador ya manejaba)."""
    t0 = time.time()
    _log_arranque("INICIO %s" % nombre)
    try:
        yield
    except Exception:
        _log_arranque("ERROR  %s (%.2fs)" % (nombre, time.time() - t0))
        raise
    else:
        _log_arranque("FIN    %s (%.2fs)" % (nombre, time.time() - t0))

UA = "Mozilla/5.0 (Monitor-Noticias/1.0; personal research)"
# 25s era demasiado: un solo feed colgado frenaba TODA la corrida esa cantidad
# de tiempo. Bajado a ~8s (configurable) porque ahora el fetch es en paralelo:
# un feed lento ya no bloquea a los demas, pero igual no debe demorar el ciclo.
TIMEOUT = int(os.environ.get("MONITOR_FEED_TIMEOUT", "8"))
# Antiguedad maxima de una historia para mostrarse (dias). Evita que columnas o
# notas viejas sigan apareciendo. Cambiable con MONITOR_MAX_DIAS.
MAX_AGE_DAYS = float(os.environ.get("MONITOR_MAX_DIAS", "3"))
# Umbral de "reciente" (horas). Dentro de este umbral, la historia va al feed
# principal (portada); mas vieja que esto pero todavia dentro de MAX_AGE_DAYS
# ya no se descarta -- pasa a la pestaña "Anteriores" (ver s["antigua"] en
# build_stories). Nada desaparece en silencio: solo se BOTA de verdad al pasar
# MAX_AGE_DAYS. Cambiable con MONITOR_FEED_FRESH_H.
FEED_FRESH_H = float(os.environ.get("MONITOR_FEED_FRESH_H", "10"))

# Medios internacionales (marcados con "intl": True en feeds.py): alimentan el
# apartado "Internacionales" con politica y economia DEL MUNDO (no solo Ecuador).
# Ser internacional es un EJE aparte de politica/economia: una historia puede
# ser politica Y ademas internacional si la publico un medio de afuera.
INTL_OUTLETS = {f["outlet"] for f in FEEDS if f.get("intl")}

STOPWORDS = set("""
a al algo alguna algunas alguno algunos ante antes como con contra cual cuando de del desde donde dos el
ella ellas ellos en entre era eran es esa esas ese eso esos esta estan estas este esto estos fue fueron ha
hace hasta hay la las le les lo los mas me mi mis mucho muy no nos o os para pero por porque que quien se
segun ser si sin sobre solo son su sus tan te tiene todo todos tras un una uno unos y ya sus tras cada
ecuador ecuatoriano ecuatoriana video foto fotos noticia noticias
""".split())

# BUG REAL confirmado en vivo (2026-09-23, cuarta pasada, Problema 4): en dias
# de un evento grande cubierto por muchos medios a la vez (ej. semana de la
# Asamblea General de la ONU), decenas de titulares DISTINTOS repiten las
# mismas palabras de SEDE/EVENTO ("Nueva York", "Asamblea General", "ONU")
# sin ser la misma historia -- el enlace por MAXIMO (single-linkage) de
# cluster() los encadena a todos en un solo grupo gigante. Reproducido con
# titulares reales: una nota de El Universo sobre Daniel Noboa/Ecuador en la
# ONU quedo agrupada con Delcy Rodriguez/Trump, Iran, Cuba y la realeza
# europea, solo por compartir "Nueva York"/"Asamblea General" -- y como el
# grupo mezclado SI mencionaba "Ecuador" en una nota, toda la historia (10
# medios, 8 internacionales) se clasifico como ambito local. Mismo mecanismo
# que ya se usa para "ecuador"/"ecuatoriano" arriba (palabras demasiado
# genericas para identificar una historia puntual): se excluyen de la
# comparacion de titulares en cluster() (word-overlap Y nombre propio
# compartido), sin tocar la clasificacion de tema/geografia en ningun otro
# lado.
EVENTO_GENERICO = set("""
nueva york onu asamblea general naciones unidas
""".split())

# Fase 9 (2026-09-25), Problema A3 -- "lugares ubicuos como nombre compartido":
# diagnostico real en historias_registro.json encontro entradas que mezclan
# hechos SIN relacion (ej. "Santa Elena: crimen de un taxista" fusionada con
# "Bus... cayo de un puente en la via a la Costa") porque el UNICO nombre
# propio en comun era el de una ciudad/provincia -- eso prueba que las dos
# notas son del mismo LUGAR, no del mismo HECHO. Mismo mecanismo que
# EVENTO_GENERICO (se resta de _tok/_nom antes de comparar, nunca decide
# ambito/geografia en ningun otro lado): topónimos ecuatorianos frecuentes,
# demasiado genericos para ser la señal que una dos notas.
LUGARES_COMUNES = set("""
guayaquil ecuador ecuatoriano ecuatoriana quito guayas samborondon duran
milagro daule cuenca manta machala loja esmeraldas ambato babahoyo costa
sierra oriente santa elena pichincha azuay manabi tungurahua chimborazo
""".split())

# Fase 14: términos demasiado genéricos para unir historias distintas.
PALABRAS_GENERICAS_CONTENIDO = set("""
menores casos parque lineal
""".split())

# Fase 18 (P0-2, "veto de plantilla"): palabras de FORMATO que se repiten en
# notas de hechos distintos -- "fechas y precios" (un show en Samborondon y
# otro en la CDMX), "ataque armado" (Guayaquil, Huaquillas y La Libertad el
# mismo dia), "corte de agua ... lista completa de zonas" (Guayaquil y
# Cartagena). Casos reales del 29-sep, pruebas/fase18_casos_reales.json. No se
# restan del solape (siguen sumando cuando HAY otra cosa en comun); lo que
# cambia es que por si solas ya no alcanzan como puente: hace falta ademas un
# nombre propio, una cifra, la misma ciudad o 2+ palabras especificas.
TOKENS_PLANTILLA = set("""
fechas fecha precios precio boletos entradas preventa horarios horario hora
ataque armado armada disparos balacera muere muerto muertos murieron asesinado
asesinada asesinan matan sicariato herido heridos
corte cortes agua servicio lista completa zonas sectores sector interrupcion
personas requeridas justicia detenidos detenido capturado capturados
lluvias lluvia pronostico clima temperatura semana hoy este esta
invierte invertira inversion millones dolares
aprehendidos aprehendido decomiso decomisan operativo operativos droga
""".split())

# Fase 9, Problema A2 -- siglas que _nombres_propios (pensada para palabras en
# Sentence/Title Case) no captaba: CJNG, ATM, CTE, BDE, DAC, INAMHI, CNEL, etc.
# La sigla suele ser justo la entidad puntual que comparten dos notas de la
# misma historia (ej. "CJNG" entre los 5 titulares del operativo de
# Samborondon). Se excluyen las genericas (aparecen en casi cualquier nota
# internacional/institucional, no identifican una historia puntual).
_SIGLAS_GENERICAS = set("""
eeuu onu otan ue ong pib fmi oea nato usa uk ee uu un
""".split())

def _siglas(titulo):
    """Secuencias de 3+ mayusculas (ignorando puntos, para agarrar 'EE.UU.'
    como 'EEUU'), sin las genericas de _SIGLAS_GENERICAS. Devuelve minusculas
    sin acentos, mismo formato que _nombres_propios(), para poder unirse al
    mismo set de 'nombres'."""
    limpio = (titulo or "").replace(".", "")
    siglas = re.findall(r"\b[A-ZÑ]{3,}\b", limpio)
    return {strip_accents(s).lower() for s in siglas if strip_accents(s).lower() not in _SIGLAS_GENERICAS}

_MESES_TEXTO = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
                "noviembre": 11, "diciembre": 12}
_FECHA_RX = re.compile(r"\b(\d{1,2})\s+de\s+(" + "|".join(_MESES_TEXTO) + r")\b")

# Fase 9 (Problema A3) -- caso real: "Usuarios reportan cortes de luz en el
# norte de Guayaquil" vs "Ciudadanos en Duran reportan cortes de agua" se
# fusionaban (sim=0.33, por encima del umbral general) porque "reportan"/
# "cortes"/"ciudadanos"/"usuarios" son vocabulario de PLANTILLA de cualquier
# corte de servicio -- el mismo fenomeno que el pronostico del clima, pero
# para cortes de luz/agua/gas. Igual que con la ciudad/fecha: mismo criterio
# (que utilidad) requerido para poder ser el mismo hecho.
_SERVICIOS_BASICOS = {
    "luz": "luz", "electricidad": "luz", "energia electrica": "luz",
    "agua": "agua", "agua potable": "agua",
    "gas": "gas",
    "internet": "internet", "telefono": "telefono", "telefonia": "telefono",
}

def servicio_mencionado(texto):
    blob = norm(texto)
    for term, canon in _SERVICIOS_BASICOS.items():
        if kw_hit(term, blob):
            return canon
    return ""

def fecha_mencionada(texto):
    """Fase 9, Problema A3 -- 'boletines con plantilla' (pronostico del clima,
    feriados, mareas, precio del dolar): la MISMA ciudad con distinta fecha
    EXPLICITA mencionada en el titular no es la misma historia, aunque
    compartan casi todo el resto del vocabulario (es la plantilla, no el
    hecho). Devuelve un set de fechas normalizadas 'DD-MM' (se ignora el año
    a proposito: 'el 9 de octubre' preguntado en dos corridas distintas sigue
    siendo la misma pregunta sobre el mismo feriado)."""
    blob = norm(texto)
    return {"%02d-%02d" % (int(d), _MESES_TEXTO[m]) for d, m in _FECHA_RX.findall(blob)}


# ------------------------- Fase 9, parte D3 (Problema 3): marco global ES/EN -------------------------
# Bug real confirmado con historias_registro.json real: la cumbre Trump-Xi
# quedaba repartida en historias SEPARADAS por idioma -- el agrupamiento
# compara palabras (nunca coinciden entre idiomas) y nomic-embed-text
# (entrenado sobre todo en ingles) no separa bien "mismo hecho en dos
# idiomas" de "hechos distintos que comparten las mismas 2 personas". En su
# momento (con nomic-embed-text) se midio que NO separa, y se adopto bge-m3
# como modelo APARTE solo para este matching cruzado de idioma.
# Fase 10, parte B (2026-09-26): recalibrado con datos reales de
# gemini-embedding-001 (Ollama/bge-m3 se retiraron en la migracion a la
# nube). Medido en vivo con LOS MISMOS titulares reales que ya usa
# test_fase9_multilingue.py (cumbre Trump-Xi, historias_registro.json real
# del 2026-09-26 -- mas confiables que un par inventado, son el par que este
# mismo proyecto ya trataba como caso de referencia):
#   - "Trump hosts Xi for state dinner..." (EN) vs. "Trump y Xi Jinping
#     exhiben unidad al cierre de la visita de Estado..." (ES) -- MISMO
#     hecho, cruzado de idioma: coseno 0.7404 (debe unirse).
#   - "Trump, Xi discuss Middle East war as Iran presses..." vs. la MISMA
#     nota en español de arriba -- comparten las DOS entidades pero son
#     hechos DISTINTOS (Medio Oriente/Iran vs. la visita de Estado): coseno
#     0.6639 (NO debe unirse).
# Hueco real MUCHO mas angosto de lo que se penso al principio (con pares
# propios mas largos había dado 0.6874/0.9070, pero estos titulares reales,
# mas cortos, achican el margen): solo 0.0765 entre ambos (0.6639 -> 0.7404).
# Se eligio 0.72 (margen real ~0.02-0.03 a cada lado) -- MAS BAJO que la
# primera estimacion (0.80) hecha con pares sinteticos propios, corregida
# con el dato real del proyecto. Dado el margen angosto, la seguridad real
# NO depende solo de este umbral: sigue haciendo falta 2+ entidades
# canonicas en comun (o 1 sola con coseno MUY alto) ANTES de siquiera
# llegar a este chequeo -- ver el `if len(comunes) >= 2 / elif ==1 and
# cos>=0.75` mas abajo, que ya filtraba esto desde la Fase 9. Ver CLAUDE.md,
# Fase 10 parte B, para la tabla completa de pares medidos (incluye tambien
# 2 pares sinteticos propios con mas margen, usados solo como referencia
# adicional, no como base del umbral final).
# gemini-embedding-001 resulto genuinamente multilingue (coseno 0.74-0.91
# para duplicados reales ES/EN medidos en esta sesion, ver tambien el par
# "Trump y Xi se reunen en Corea del Sur..."/"...meet in South Korea..." en
# CLAUDE.md) -- reemplaza a la vez a nomic-embed-text (intra-idioma,
# EMBED_SIM_UMBRAL abajo) y a bge-m3 (cruzado de idioma, este umbral): con
# el MISMO modelo para las dos tareas, _embed_multilingue_pendientes_registro()
# ya no pide un vector aparte, reusa el que calculo _embed_pendientes_registro()
# (ver comentario ahi) -- mitad del costo de embeddings de antes, mismo dato.
EMBED_SIM_UMBRAL_MULTILINGUE = float(os.environ.get("MONITOR_EMBED_SIM_MULTI", "0.72"))

# Palabras funcionales mas frecuentes de cada idioma en titulares de noticias
# (aproximado, sin libreria de deteccion de idioma -- alcanza para separar
# ES de EN en un titular de una linea, que es todo lo que hace falta aca).
_EN_STOPWORDS_TITULAR = set("""
the and for with from that this have has says say after over into its was
were are will new state states says said amid amid talks summit trump china
united states meeting leaders during than more than what how who why where
""".split())
_ES_STOPWORDS_TITULAR = set("""
que los las del con para por una como este esta tras dice dijo despues fue
son han sera nuevo nueva durante entre mientras quien donde por que estados
unidos reunion lideres cumbre
""".split())

def _detectar_idioma(texto):
    """'es' o 'en' -- heuristica barata por palabras funcionales, suficiente
    para un titular de una linea. Ante empate o texto muy corto, 'es' por
    default (la mayoria de los feeds de este proyecto son en español)."""
    palabras = norm(texto).split()
    if not palabras:
        return "es"
    en = sum(1 for p in palabras if p in _EN_STOPWORDS_TITULAR)
    es = sum(1 for p in palabras if p in _ES_STOPWORDS_TITULAR)
    return "en" if en > es and en >= 2 else "es"

# Equivalencias basicas de entidades entre idiomas (Problema D3-3): sin esto,
# "EE.UU." (ES) y "US"/"USA" (EN) nunca coinciden como la MISMA entidad
# aunque sean la misma cosa. Lista chica y curada (mismo criterio que
# LUGARES_COMUNES/_SIGLAS_GENERICAS) -- no pretende ser exhaustiva, cubre los
# casos reales mas frecuentes en cobertura internacional.
_EQUIV_ENTIDADES = {
    "eeuu": "eeuu", "ee uu": "eeuu", "us": "eeuu", "usa": "eeuu",
    "unitedstates": "eeuu", "estadosunidos": "eeuu",
    "onu": "onu", "un": "onu", "unitednations": "onu", "nacionesunidas": "onu",
    "otan": "otan", "nato": "otan",
    "ue": "ue", "eu": "ue", "unioneuropea": "ue", "europeanunion": "ue",
    "xi": "xi jinping", "xijinping": "xi jinping",
    "trump": "trump", "donaldtrump": "trump",
}

def _canon_entidad(nombre):
    """Normaliza un nombre/sigla a su forma canonica cruzada de idioma (ver
    _EQUIV_ENTIDADES). Si no esta en la lista, devuelve el nombre normalizado
    tal cual (sigue sirviendo para comparar dos apariciones del MISMO
    idioma, solo que sin el beneficio de la equivalencia)."""
    n = norm(nombre).replace(" ", "")
    return _EQUIV_ENTIDADES.get(n, norm(nombre))

def _entidades_canonicas(titulo):
    """Nombres propios + siglas (_nombres_propios ya incluye nombres cortos
    conocidos, ver _NOMBRES_CORTOS_CONOCIDOS) en su forma CANONICA (ver
    arriba) -- para comparar entidades entre un titular en ingles y uno en
    español."""
    crudos = _nombres_propios(titulo) - EVENTO_GENERICO
    return {_canon_entidad(n) for n in crudos}


# ------------------------- utilidades de texto -------------------------

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                    if unicodedata.category(c) != "Mn")

def norm(s):
    s = strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def tokens(title):
    return {t for t in norm(title).split() if len(t) >= 4 and t not in STOPWORDS}

def _nombre_se_solapa(nombre_mencionado, titulo_wiki):
    """Filtro barato y determinista (sin IA) previo/paralelo a
    ia.coincide_dominio(): si NINGUNA palabra (>=3 letras) del nombre que la
    nota menciona aparece en el titulo real de Wikipedia, es casi seguro un
    homonimo/dominio distinto (ej. 'Mamdani' contra el articulo 'Indios
    ugandeses' -- la comunidad etnica, no el politico). Bug real: en ese caso
    ia.coincide_dominio (el modelo chico, qwen2.5:3b) respondio 'coinciden'
    cuando NO coinciden -- un backstop determinista no reemplaza al chequeo
    de la IA, lo complementa: barato, sin llamada a red/modelo, y sirve de
    ultima barrera aunque el modelo se equivoque. Ante la duda (nombre sin
    palabras utiles para comparar) no bloquea -- mismo criterio de 'mejor un
    falso negativo que un falso positivo' que el resto de Parte B."""
    a = norm(nombre_mencionado)
    b = norm(titulo_wiki)
    palabras = [w for w in a.split() if len(w) >= 3]
    if not palabras:
        return True
    return any(w in b for w in palabras)

def kw_hit(word, blob):
    """Coincidencia de palabra clave por INICIO de palabra (no subcadena).
    Asi 'candidato' atrapa 'candidatos'/'candidata', pero 'eleccion' ya NO
    matchea 'seleccion' (futbol) ni 'voto' matchea 'devoto'."""
    return re.search(r"\b" + re.escape(norm(word)), blob) is not None

def geo_hit(term, blob):
    """Coincidencia de un termino GEOGRAFICO por palabra COMPLETA (limite al
    inicio Y al final), a diferencia de kw_hit (que solo exige el inicio, a
    proposito, para atrapar plurales de un tema: 'candidato'/'candidatos').
    Un nombre de lugar no necesita esa flexibilidad, y el prefijo suelto
    causaba colisiones reales -- probado en vivo: 'canar' (provincia Cañar)
    coincidia como PREFIJO dentro de 'canarias' (Islas Canarias, España), y
    'napo' (provincia/rio) dentro de 'napoleon'. Con limite en ambos extremos
    esas coincidencias desaparecen sin tocar la lista de terminos."""
    return re.search(r"\b" + re.escape(norm(term)) + r"\b", blob) is not None


# ------------------------- lectura de feeds -------------------------

def fetch(url, etag=None, last_modified=None):
    """Trae una URL. Fase 0 (velocidad): si se pasan etag/last_modified (de
    una lectura anterior, ver fetch_cache.json), los manda como
    If-None-Match/If-Modified-Since -- si el servidor contesta 304 (sin
    cambios desde la ultima vez), NO baja el cuerpo entero. Esto es lo que
    permite chequear un feed seguido sin gastar ancho de banda de mas cuando
    no publico nada nuevo. Devuelve (bytes_o_None, etag_nuevo,
    last_modified_nuevo, status_http)."""
    headers = {"User-Agent": UA}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read(), r.headers.get("ETag"), r.headers.get("Last-Modified"), 200
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag, last_modified, 304
        raise

# BUG REAL confirmado en vivo (2026-09-23, Fase 0 -- diagnostico de demora): CBC News
# manda la fecha con sigla de zona horaria ("Wed, 23 Sep 2026 13:06:11 EDT") en vez de
# offset numerico. Python's strptime con %Z SOLO reconoce un puñado fijo (basicamente
# UTC/GMT y el nombre de la zona local del sistema) -- "EDT"/"PST"/etc. fallan SIEMPRE,
# confirmado con una prueba directa. Resultado real medido: el 100% de las notas de CBC
# quedaban con date=None -- eso le da a esa historia el peor bonus de recencia posible
# en el ranking (0, igual que si fuera vieja) sin importar que tan nueva sea en realidad,
# y ademas nunca se marca "antigua" (hours=None tampoco pasa ese chequeo) -- las dos cosas
# mal, sin ningun error visible. Se traduce la sigla a un offset numerico ANTES de
# intentar los formatos (asi %z, confiable, la agarra en vez de depender de %Z).
_TZ_ABBREV = {
    "UT": "+0000", "GMT": "+0000", "UTC": "+0000",
    "EST": "-0500", "EDT": "-0400", "CST": "-0600", "CDT": "-0500",
    "MST": "-0700", "MDT": "-0600", "PST": "-0800", "PDT": "-0700",
    "BST": "+0100", "CET": "+0100", "CEST": "+0200",
}

def parse_date(text):
    if not text:
        return None
    text = text.strip()
    m = re.match(r"^(.*\d{2}:\d{2}:\d{2})\s+([A-Za-z]{2,4})$", text)
    if m and m.group(2).upper() in _TZ_ABBREV:
        text = m.group(1) + " " + _TZ_ABBREV[m.group(2).upper()]
    # "%Y-%m-%d %H:%M:%S" (sin zona horaria, ultimo recurso): se asume UTC por default
    # (ver mas abajo) -- riesgo conocido y documentado, no confirmado en los 44 feeds
    # actuales (todos traen offset explicito o sigla ya cubierta arriba), pero si un feed
    # nuevo manda HORA LOCAL sin decirlo, esto la tomaria como UTC y la "edad" calculada
    # saldria mal (tipicamente unas horas de error, no dias). Revisar aqui primero si
    # aparece un feed nuevo con fechas sistematicamente raras.
    fmts = ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]
    for f in fmts:
        try:
            d = dt.datetime.strptime(text, f)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            return d.astimezone(dt.timezone.utc)
        except ValueError:
            continue
    return None

def tag(el):
    return el.tag.split("}")[-1]  # quita namespace

# Lista corta a proposito (evitar colisiones: p.ej. NO se agrega "bolivar" suelto
# -- Simon Bolivar aparece constantemente en noticias de otros paises de America
# Latina, y confundiria mas de lo que arregla). Cubre: nombre del pais,
# presidentes recientes, TODAS las provincias con nombre poco ambiguo, y
# instituciones/siglas unicas de Ecuador (bajo riesgo de colision por ser siglas
# de 4+ letras o nombres compuestos, no sueltas de 2-3 letras tipo "cne"/"sri").
# Se sacaron 3 terminos que colisionaban aunque fueran palabra COMPLETA (geo_hit
# no alcanza a arreglar una frase generica real, solo evita el prefijo suelto):
# "sucre" (Sucre, capital de Bolivia, mucho mas frecuente en prensa que el uso
# historico de la moneda ecuatoriana), "los rios" ("los rios de <cualquier
# pais>" es frase comun) y "el oro" ("el oro alcanza un precio record..." es
# titular tipico de economia mundial). La provincia "El Oro" sigue detectandose
# por su capital "machala"; "Los Rios" queda cubierta por sus ciudades.
EC_TERMS = ["ecuador", "ecuatorian", "quito", "guayaquil", "guayas", "samborondon",
            "cuenca", "azuay", "galapagos", "noboa", "correa", "esmeraldas",
            "manta", "portoviejo", "manabi", "ambato", "tungurahua", "loja",
            "machala", "babahoyo", "quevedo", "santo domingo de los tsachilas",
            "cotopaxi", "chimborazo", "carchi", "imbabura", "canar",
            "santa elena", "napo", "pastaza", "morona santiago",
            "zamora chinchipe", "sucumbios", "orellana", "yasuni", "petroecuador",
            "asamblea nacional", "iess", "cfn", "senae", "dgac",
            # Fase 18 (P0-2/P0-3): ciudades/cantones reales que aparecian en
            # titulares del 29-sep sin que nada los reconociera como Ecuador
            # (Huaquillas, La Libertad de Santa Elena) -- sin esto, una nota de
            # Huaquillas no tenia ningun lugar propio y se pegaba a la de
            # Guayaquil por compartir "ataque armado".
            "huaquillas", "latacunga", "riobamba", "ibarra", "tulcan", "otavalo",
            "chone", "jipijapa", "montecristi", "pedernales", "atacames",
            "nueva loja", "lago agrio", "macas", "puyo", "daule"]

# Fase 17 (diagnostico de arranque lento -- ver COORDINACION.md, Frente B):
# EC_TERMS/FOREIGN_TERMS son listas FIJAS (nunca se les hace .append/+= en
# ningun lado, confirmado por grep) -- normalizar cada termino y armar su
# patron de regex con re.escape() en CADA llamada a is_ecuador()/is_foreign()
# (como hacia geo_hit() antes de este cambio) es trabajo 100% repetido: el
# patron de "ecuador" es siempre el mismo patron, llamada tras llamada.
# Perfilado con cProfile (caso real, ver bitacora): is_ecuador/is_foreign
# explicaban el 93.9% del tiempo de _match_registro() -- casi todo en volver
# a normalizar/escapar/armar estos mismos ~80 patrones una y otra vez.
# Compilados UNA sola vez al cargar el modulo; el patron resultante es
# byte-a-byte el mismo que armaba geo_hit(termino, blob), asi que el
# resultado de is_ecuador/is_foreign no cambia en nada, solo se deja de
# repetir el trabajo de construir el patron.
_EC_TERMS_RE = {t: re.compile(r"\b" + re.escape(norm(t)) + ("" if t == "ecuatorian" else r"\b"))
                for t in EC_TERMS}
# Fase 18: "ecuatorian" es un PREFIJO a proposito (ecuatoriano/a/os/as), pero
# con limite de palabra al final nunca coincidia con nada -- "narcotraficante
# ecuatoriano" no contaba como senal de Ecuador (bug real encontrado midiendo
# el caso Fito del 29-sep).

# "Asamblea Nacional" tambien es el nombre del parlamento de VENEZUELA, muy
# cubierto en prensa internacional (mucho mas que la ecuatoriana en medios de
# afuera). Si el texto menciona ademas Venezuela/Maduro, esa coincidencia sola
# ya no cuenta como señal de Ecuador -- se sigue evaluando el resto de EC_TERMS
# por si hay otra señal real. Sin este candado: "La Asamblea Nacional de
# Venezuela aprobo una ley respaldada por Maduro" quedaba marcada Ecuador.
_ASAMBLEA_AMBIGUA = ("venezuela", "maduro")

def is_ecuador(text):
    blob = norm(text)
    terms = EC_TERMS
    if _EC_TERMS_RE["asamblea nacional"].search(blob) and any(
            _FOREIGN_TERMS_RE[v].search(blob) for v in _ASAMBLEA_AMBIGUA):
        terms = [t for t in EC_TERMS if t != "asamblea nacional"]
    hit = [t for t in terms if _EC_TERMS_RE[t].search(blob)]
    if not hit:
        return False
    # BUG REAL (Fernando, 2026-09-23: "las de Colombia se mezclan con la de
    # Ecuador cuando la noticia no tiene nada que ver con Ecuador"): una nota
    # sobre Alvaro Uribe (Colombia) hablando del "Escudo de las Americas"
    # (alianza de seguridad de ~15 paises) quedaba marcada Ecuador SOLO
    # porque Ecuador es uno mas en la enumeracion de miembros -- ni siquiera
    # el foco de la nota. `geo_hit` exige palabra completa (no colisiona con
    # "Ecuatoriana Airlines" ni nada raro), el problema es otro: una simple
    # MENCION del nombre del pais, en medio de una lista larga de paises, no
    # es lo mismo que la nota SER sobre Ecuador. Si el texto enumera 3+
    # paises EXTRANJEROS distintos (senal fuerte de "lista/ranking/alianza
    # multilateral", ver _es_enumeracion_paises), un match SOLO por el
    # nombre del pais ("ecuador"/"ecuatorian") ya no alcanza -- se exige una
    # senal mas especifica (ciudad, institucion) para seguir contando como
    # local. Fuera de una enumeracion, el nombre del pais solo sigue
    # bastando (comportamiento de siempre, no se toca).
    if _es_enumeracion_paises(blob) and all(t in ("ecuador", "ecuatorian") for t in hit):
        return False
    return True

# Senales de que una nota es de OTRO pais (para separar Ecuador vs Mundo por el
# TEMA, no por el medio). Un diario ecuatoriano cubre el mundo todo el tiempo.
FOREIGN_TERMS = [
    "estados unidos", "eeuu", "ee.uu", "washington", "trump", "biden",
    "argentina", "buenos aires", "milei", "espana", "madrid", "mexico",
    "china", "beijing", "xi jinping", "rusia", "putin", "ucrania", "kiev",
    "israel", "gaza", "palestina", "hamas", "iran", "union europea", "bruselas",
    "francia", "paris", "alemania", "berlin", "reino unido", "londres",
    "japon", "tokio", "colombia", "bogota", "peru", "lima", "venezuela",
    "maduro", "chile", "brasil", "bolivia", "el salvador", "bukele", "nicaragua",
    "otan", "nato",
    # Problema 2 (2026-09-24): mas ciudades EXTRANJERAS especificas -- la
    # lista original cubria paises/capitales grandes pero se quedaba corta
    # con ciudades intermedias que si aparecen seguido en boletines
    # replicados (pronostico del tiempo, restricciones de transito). Caso
    # real encontrado revisando las historias de Guayaquil de esta sesion:
    # "Pico y Placa en Cali" (Colombia, restriccion vehicular) quedo
    # agrupada con boletines reales de Quito/Guayaquil -- "Cali" no
    # coincidia con NADA de la lista vieja, asi que el veto no la detectaba
    # aunque el texto sea inequivocamente de otro pais.
    "cali", "medellin", "guadalajara", "monterrey", "sao paulo", "rio de janeiro",
    "montevideo", "asuncion", "la paz", "caracas", "san jose de costa rica",
    "tegucigalpa", "managua", "ciudad de panama", "santo domingo de guzman",
    "la habana", "barcelona", "sevilla", "valencia", "miami", "houston",
    "los angeles", "toronto", "monteria", "barranquilla", "cartagena de indias",
    # Fase 18 (P0-2): casos reales del 29-sep que se fundian con historias de
    # Guayaquil porque el pais/ciudad no estaba en esta lista. "cartagena"
    # suelta es segura: Ecuador no tiene ninguna Cartagena. "santo domingo"
    # suelto NO se agrega (es provincia de Ecuador) -- solo "republica
    # dominicana".
    "cartagena", "cdmx", "ciudad de mexico", "republica dominicana",
    "puerto rico", "costa rica", "panama", "guatemala", "honduras", "cuba",
    "uruguay", "paraguay", "canada", "italia", "portugal", "lisboa",
    "nueva york", "new york", "chicago", "texas", "california",
    "turquia", "siria", "libano", "arabia saudita", "qatar", "india", "pakistan",
    "corea del sur", "corea del norte", "egipto", "santiago de chile",
]

# Fase 17: mismo criterio que _EC_TERMS_RE (ver el comentario grande ahi).
_FOREIGN_TERMS_RE = {t: re.compile(r"\b" + re.escape(norm(t)) + r"\b") for t in FOREIGN_TERMS}

def is_foreign(text):
    blob = norm(text)
    return any(p.search(blob) for p in _FOREIGN_TERMS_RE.values())

# Problema 2 (2026-09-24): "veto geografico" pedido por Fernando -- si el
# texto nombra un lugar EXTRANJERO y NINGUN lugar de Ecuador, la nota no
# puede quedar en Guayaquil ni en Ecuador, venga del feed que venga (ni
# siquiera la senal DURA de "ciudad_feed", ver build_stories) ni lo diga la
# IA (ver el candado en get_ia -> _apply). Bug real que esto corrige: el
# pronostico del clima de Sevilla (Espana) llegaba por el feed de busqueda
# "Guayaquil" (Google News) y el clustering lo fusiono con pronosticos
# REALES de Quito/Guayaquil -- como el feed de El Universo tenia
# "ciudad_feed"="Guayaquil" en el mismo grupo, esa senal forzaba ambito
# local sin que nada comparara el TEXTO de la nota de Sevilla. Con is_foreign
# exigiendo palabra completa (geo_hit) no hay riesgo de falso positivo por
# una coincidencia parcial.
def extranjero_sin_ecuador(text):
    return is_foreign(text) and not is_ecuador(text)


_DATELINE_RE = re.compile(
    r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .]{2,30}?(?:\s*\([^)]+\))?,\s*\d{1,2}\s*(?:de\s*)?"
    r"[A-Za-zÀ-ÿ]+\.?\s*[\-–]?\s*\(?(?:EFE|AFP|Reuters?|AP)\)?[.\-]\s*")


def _quitar_dateline(texto):
    return _DATELINE_RE.sub("", texto or "", count=1)

def _es_enumeracion_paises(blob, minimo=3):
    """True si el texto nombra 3+ paises EXTRANJEROS distintos (de
    FOREIGN_TERMS) -- senal de que es una lista/ranking/alianza multilateral
    (ej. "Argentina, Bolivia, Chile, Costa Rica, Ecuador, El Salvador..."),
    no una nota centrada en un pais puntual. La usa is_ecuador() para no
    contar una mencion suelta de "Ecuador" en una lista larga como senal de
    que la nota ES sobre Ecuador (ver bug real de Uribe/Escudo de las
    Americas, Decisiones ya tomadas)."""
    return sum(1 for p in _FOREIGN_TERMS_RE.values() if p.search(blob)) >= minimo


def _es_enumeracion_ciudades(text, minimo=3):
    blob = norm(text)
    # Fase 18: se cuentan AREAS, no ciudades -- "Guayaquil, Samborondon y
    # Duran" es un solo lugar (Gran Guayaquil), no una enumeracion.
    encontradas = {_area_de(ciudad) for ciudad, terminos in CITIES.items()
                   if any(geo_hit(t, blob) for t in terminos)}
    return len(encontradas) >= minimo

# Ciudades/provincias de Ecuador, para no perder de vista la cobertura LOCAL.
CITIES = {
    # "duran" (canton junto a Guayaquil) se saco de la lista originalmente
    # porque, como subcadena sin limite de palabra, matcheaba dentro de
    # "durante" -- ya no aplica (geo_hit exige palabra completa desde el
    # arreglo de canar/napo). PERO sigue sin agregarse: probando la Fase 1 en
    # vivo (2026-09-23/24), una busqueda de "Duran" trajo una nota real sobre
    # el futbolista colombiano Jhon Duran -- "Duran" tambien es un apellido
    # comun, palabra completa o no. "guayas"/"samborondon" ya cubren la zona
    # (Samborondon es contiguo a Duran, comparten cobertura de prensa).
    # Barrios/parroquias agregados en la Fase 1 (2026-09-23/24), evidencia real
    # de titulares del dia (ver feeds.py, fuentes de Guayaquil agregadas hoy):
    # todos en frase completa o palabras poco comunes sueltas, para minimizar
    # colision (ej. NO se agrega "kennedy" solo -- coincide con JFK/familia
    # Kennedy en prensa internacional -- se usa la frase completa).
    "Guayaquil": ["guayaquil", "guayas", "pascuales", "urdesa",
                  "isla trinitaria", "kennedy norte", "flor de bastion"],
    "Samborondon": ["samborondon"],
    "Duran": ["duran"],
    "Daule": ["daule"],
    "Quito": ["quito", "pichincha"],
    "Cuenca": ["cuenca", "azuay"],
    "Manta": ["manta", "portoviejo", "manabi"],
    "Ambato": ["ambato", "tungurahua"],
    "Machala": ["machala"],  # "el oro" se saco: colisiona con "el oro" (metal) de economia
    "Loja": ["loja"],
    "Esmeraldas": ["esmeraldas"],
    "Santo Domingo": ["santo domingo"],
    "Babahoyo": ["babahoyo", "quevedo"],  # provincia Los Rios (ver nota en EC_TERMS)
    # Fase 18 (P0-3): sin estas entradas, una nota de Santa Elena/Huaquillas/
    # Cotopaxi no tenia ciudad propia y heredaba "Guayaquil" de la seccion del
    # feed que la publico (casos reales del 29-sep).
    "Santa Elena": ["santa elena"],
    "Huaquillas": ["huaquillas"],
    "Latacunga": ["latacunga", "cotopaxi"],
    "Riobamba": ["riobamba", "chimborazo"],
    "Ibarra": ["ibarra", "imbabura"],
}

# Nombre con tilde para mostrar la localidad de Gran Guayaquil (chip).
LOCALIDAD_NOMBRE = {"Samborondon": "Samborondón", "Duran": "Durán", "Daule": "Daule"}


def ciudades_en(text):
    """Todas las ciudades de CITIES que nombra el texto (orden de CITIES).
    Fase 18 (P0-3): detect_city() devuelve solo la PRIMERA -- y como
    "Guayaquil" es la primera de la lista, un texto que nombra Guayaquil Y
    otra ciudad siempre salia Guayaquil."""
    blob = norm(text)
    return [c for c, terminos in CITIES.items() if any(geo_hit(t, blob) for t in terminos)]

GUAYAQUIL_AREA = [c.strip() for c in os.environ.get(
    "MONITOR_GUAYAQUIL_AREA", "Guayaquil,Samborondon,Duran,Daule").split(",") if c.strip()]


def _area_de(ciudad):
    return "Guayaquil" if ciudad in GUAYAQUIL_AREA else ciudad

def detect_city(text):
    blob = norm(text)
    for city, terms in CITIES.items():
        if any(geo_hit(t, blob) for t in terms):
            return city
    return ""

def ambito_de(blob):
    """Ecuador vs Mundo por el TEMA de la nota (no por quien la publica).
    Menciona Ecuador -> local (aunque tambien nombre otro pais: es relacion con
    Ecuador). Si no, internacional -- incluso cuando no hay una palabra clave
    de un pais extranjero especifico (is_foreign() es solo un chequeo
    explicito, ya no decide nada distinto).

    BUG REAL corregido aqui: antes, cuando ni is_ecuador() ni is_foreign()
    encontraban nada, el fallback miraba que medios publicaron la nota
    (outlets_local/outlets_intl) y, si eso tampoco alcanzaba, caia en 'local'
    a ciegas. Probado con una nota sobre el franquismo espanol (sin ninguna
    palabra de Ecuador) publicada por UN SOLO medio local -> el bug la
    clasificaba como Ecuador. El medio que publica NO dice de que trata la
    nota (un diario ecuatoriano cubre el mundo todo el tiempo), asi que ya no
    se usa como senal. Sin mencion real de Ecuador, se asume mundo: mejor una
    nota local rara sin palabra clave quede en 'internacional' (falso
    negativo) que inflar Ecuador con temas ajenos (falso positivo)."""
    if is_ecuador(blob):
        return "local"
    return "internacional"

# Basura que NO es noticia util: se descarta antes de entrar al tablero.
JUNK_TERMS = ["caricatura", "horoscopo", "zodiaco", "loteria", "loteria nacional",
              "sorteo", "resultados lotto", "defuncion", "defunciones", "obituario",
              "esquela", "farandula", "receta", "recetas", "tira comica", "crucigrama"]
JUNK_URL = ["/caricatura", "/horoscopo", "/loteria", "/sorteo", "/defuncion",
            "/obituario", "/farandula", "/espectaculos", "/deporte", "/futbol",
            "/recetas", "/viral", "/insolito",
            # OPINION / COLUMNAS / EDITORIAL: no son noticia, son criterio.
            "/opinion", "/columna", "/columnistas", "/editorial", "/blog", "/blogs",
            "/firmas", "/tribuna"]

# Problema 2 (2026-09-24, reporte de Fernando: "el pronostico del clima de
# Sevilla, Espana, salio en la seccion Guayaquil"): los pronosticos del
# tiempo de medios como Infobae siguen SIEMPRE el mismo formato de titular
# ("Pronostico del clima en <ciudad> este <fecha>: temperatura, lluvias y
# viento") -- una serie diaria por ciudad, ninguna es noticia de fondo, y
# cuando la ciudad es del extranjero no aporta nada a un monitor de Ecuador.
# Frases completas (no palabras sueltas: "clima"/"tiempo" solos aparecerian
# en coberturas reales de cambio climatico/clima politico).
WEATHER_TERMS = ["pronostico del clima", "pronostico del tiempo", "estado del tiempo",
                 "asi estara el clima", "prevision del tiempo", "prediccion del clima",
                 "prediccion del tiempo", "el tiempo hoy en"]

def _es_pronostico_clima(blob):
    return any(t in blob for t in WEATHER_TERMS)

# Fase 9 (Problema A3): "portadas"/resumenes de noticiero completo colandose
# al agrupamiento -- casos reales encontrados en historias_registro.json:
# "Portada 25 septiembre 2026" (El Norte), "Noticias, jueves 24 de septiembre
# del 2026 | 24 Horas", "Últimas noticias | 25 septiembre 2026 - Mediodía"
# (Euronews). No son una noticia puntual, son el indice/resumen del dia
# entero -- su titulo casi no tiene vocabulario propio, asi que cualquier
# nota real termina pareciendose "un poco" a ellos y, peor, ellos se pegan a
# lo que sea que ya este en el cluster (por compartir la fecha/el nombre del
# programa). Se descartan antes de llegar al tablero, igual que caricaturas/
# horoscopos.
_PORTADA_RX = re.compile(
    r"^(portada|edicion|resumen del dia|resumen semanal)\b"
    r"|\bultimas? noticias?\b.*\b(mediodia|manana|noche|tarde)\b"
    r"|\bnoticias?,?\s+(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b.*\d{4}"
    r"|\b24\s*horas\b$"
)

def _es_portada_o_noticiero(blob):
    return bool(_PORTADA_RX.search(blob))

def is_junk(title, summary, link):
    blob = norm(title + " " + summary)
    if any(j in blob for j in JUNK_TERMS):
        return True
    if _es_portada_o_noticiero(norm(title)):
        return True
    # Pronostico del clima de una ciudad EXTRANJERA (sin ninguna mencion de
    # Ecuador): ruido puro para este monitor, se descarta antes de que pueda
    # llegar a clasificarse o agruparse con nada. Un pronostico de una
    # ciudad ecuatoriana (o sin ciudad reconocible) sigue pasando -- ese SI
    # es contenido local util.
    if _es_pronostico_clima(blob) and is_foreign(blob) and not is_ecuador(blob):
        return True
    low = (link or "").lower()
    return any(u in low for u in JUNK_URL)

IMG_RX = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)

def find_image(it, raw_summary):
    """Saca una imagen del item RSS: media:content/thumbnail, enclosure, o <img> del texto."""
    for ch in it.iter():
        t = tag(ch)
        if t in ("thumbnail", "content"):
            u = ch.attrib.get("url", "")
            if u and re.search(r"\.(jpg|jpeg|png|webp)", u, re.I):
                return u
        if t == "enclosure":
            u = ch.attrib.get("url", "")
            ty = ch.attrib.get("type", "")
            if u and (ty.startswith("image") or re.search(r"\.(jpg|jpeg|png|webp)", u, re.I)):
                return u
    m = IMG_RX.search(raw_summary or "")
    return m.group(1) if m else ""

# Claves fijas que usa el dashboard (SEC_LABEL/SEC_CLS/CAT_ORDER en
# dashboard_template.html) -- cualquier "seccion" que no calce con una de
# estas se pierde en Estadisticas (aparece agrupada como "general" o, peor,
# con una clave que el dashboard no reconoce y nunca cuenta). Punto UNICO de
# normalizacion (pedido de Fernando: "una funcion que normalice las etiquetas
# en un solo lugar") para que ninguna fuente futura (IA, un feed nuevo con
# seccion mal escrita) pueda escribir una etiqueta fuera de este set.
CATEGORIAS_VALIDAS = ("politica", "economia", "seguridad", "sociedad", "general")
_CATEGORIA_SINONIMOS = {
    # OJO: las claves ya pasaron por norm() (sin acentos/mayusc) antes de
    # buscarse aqui -- una clave con tilde nunca puede matchear.
    "politico": "politica", "economico": "economia",
    "economica": "economia", "seguridad ciudadana": "seguridad", "policial": "seguridad",
    "judicial": "seguridad", "social": "sociedad", "sociales": "sociedad",
    "otros": "general", "otro": "general", "general": "general",
}

def normalizar_categoria(cat):
    """Convierte cualquier variante de etiqueta de categoria (mayusculas,
    tildes, sinonimo) a una de las claves fijas de CATEGORIAS_VALIDAS.
    Ante cualquier duda (etiqueta vacia o desconocida) cae en 'general' --
    nunca se pierde una nota por no encontrar su categoria."""
    if not cat:
        return "general"
    c = norm(str(cat)).strip()
    if c in CATEGORIAS_VALIDAS:
        return c
    return _CATEGORIA_SINONIMOS.get(c, "general")

def classify_section(text):
    """Para feeds generales: decide la categoria por palabras clave.
    Devuelve None si no cae en ninguna (el llamador la manda a 'general')."""
    blob = norm(text)
    scores = {}
    for sec, bank in KEYWORDS.items():
        n = 0
        for words in bank.values():
            n += sum(1 for w in words if kw_hit(w, blob))
        scores[sec] = n
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None

# Fase 9 (Problema A2): Google News RSS junta "Titulo real - Medio" en el
# propio <title> -- contar todo bajo el outlet ficticio "Busqueda: <lugar>"
# esconde que detras hay decenas de medios reales distintos (medido en
# data.json real: 167 items bajo un solo outlet, cuando el titulo mismo dice
# "... - El Universo", "... - Metro Ecuador", "... - eltelegrafo.com.ec", "...
# - Peru 21"). Sin esto, el mismo hecho contado por 5 medios reales cuenta
# como "1 medio" para el ranking/agrupamiento -- y el sufijo mete tokens
# basura (el nombre del medio) en _sim(). Se aplica SOLO a los outlets que
# son una busqueda de Google News (marcados con "google_news": True en
# feeds.py), nunca a un feed editorial real (ahi un guion en el titulo es
# parte genuino de la nota, no un sufijo de fuente).
_GOOGLE_NEWS_SUFFIJO_RX = re.compile(r"^(.*\S)\s+-\s+([^-]{2,40})$")

def _separar_medio_google_news(title, outlet_original):
    m = _GOOGLE_NEWS_SUFFIJO_RX.match(title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title, outlet_original

def parse_feed(raw, outlet, seccion, scope=None, ciudad_feed="", google_news=False):
    # 'ciudad_feed' (Problema 5/1, 2026-09-23 tercera ronda: "no estas
    # acogiendo directamente las del sector Guayaquil cuando precisamente los
    # diarios nacionales tienen secciones enteras dedicadas a la editorial de
    # Guayaquil"): algunos feeds de feeds.py SON literalmente la seccion
    # "Gran Guayaquil" de un diario (ej. El Universo) -- el medio YA
    # clasifico esa nota como Guayaquil al publicarla en esa seccion, no hace
    # falta que el TEXTO repita la palabra "Guayaquil" para saberlo (una nota
    # hiperlocal de un barrio puntual puede no mencionar la ciudad ni una
    # vez). build_stories() usa esto como señal DURA (no solo otra palabra
    # clave mas): si la seccion del feed ya dice Guayaquil, listo, es
    # Guayaquil -- no se necesita que ademas is_ecuador()/detect_city()
    # encuentren algo en el texto.
    out = []
    # Problema 5 (mas feeds): "El Norte" (elnorte.ec) manda un salto de linea
    # ANTES de "<?xml ...?>" -- el parser de ET es estricto y lo rechaza con
    # "XML or text declaration not at start of entity" aunque el resto del
    # documento sea XML valido. lstrip() en bytes saca ese espacio en blanco
    # inicial sin tocar el resto: mas robusto para cualquier feed futuro con
    # el mismo problema, no solo este.
    root = ET.fromstring(raw.lstrip())
    # RSS: channel/item ; Atom: entry
    items = [e for e in root.iter() if tag(e) in ("item", "entry")]
    for it in items:
        title = link = date = summary = None
        raw_html = ""
        for ch in it:
            t = tag(ch)
            if t == "title":
                title = (ch.text or "").strip()
            elif t == "link":
                link = (ch.text or "").strip() or ch.attrib.get("href")
            elif t in ("pubDate", "published", "updated", "date"):
                date = date or ch.text
            elif t in ("description", "summary", "encoded"):
                raw_html = raw_html or (ch.text or "")
                if not summary:
                    summary = re.sub("<[^>]+>", "", ch.text or "").strip()
        if not title:
            continue
        title = html.unescape(title)
        summary = html.unescape(summary or "")[:280]
        outlet_real = outlet
        if google_news:
            title, outlet_real = _separar_medio_google_news(title, outlet)
        if scope == "ec" and not is_ecuador(title + " " + summary):
            continue  # medio internacional: solo notas que mencionan Ecuador
        if is_junk(title, summary, link):
            continue  # caricaturas, horoscopos, deportes, defunciones, etc.
        sec = seccion
        if seccion == "auto":
            sec = classify_section(title + " " + summary) or "general"
            # ya no se descarta nada: lo que no encaja en una categoria va a "general"
        sec = normalizar_categoria(sec)  # punto unico: nunca una etiqueta fuera de CATEGORIAS_VALIDAS
        out.append({
            "outlet": outlet_real, "seccion": sec,
            "title": title,
            "link": link or "",
            "date": parse_date(date),
            "summary": summary,
            "image": find_image(it, raw_html),
            "ciudad_feed": ciudad_feed,
        })
    return out

def filtrar_por_ruta(arts, rutas):
    """Fase 18 (P1-9): de un feed GENERAL, se queda solo con los items cuya
    URL cae en una de 'rutas' (primer segmento del path, ej. 'mundo'), mas
    los que mencionan Ecuador."""
    rutas = {r.strip("/").lower() for r in rutas}
    out = []
    for a in arts:
        m = re.match(r"https?://[^/]+/([^/?#]+)/", a.get("link") or "")
        if (m and m.group(1).lower() in rutas) or is_ecuador(a["title"] + " " + (a.get("summary") or "")):
            out.append(a)
    return out


def probar_sitemaps(guardar=True):
    """Fase 18 (P1-8): prueba desde ESTA PC los candidatos de
    feeds.SITEMAPS_Y_FEEDS_CANDIDATOS e imprime cuales responden. Los que
    traen notas de las ultimas 48 h se guardan en feeds_extra.json (se suman
    a FEEDS al proximo arranque). Un candidato cuyo medio ya tiene feed
    propio se agrega igual: dedup() junta los repetidos por link."""
    try:
        from feeds import SITEMAPS_Y_FEEDS_CANDIDATOS as cands
    except Exception:
        print("feeds.py no tiene SITEMAPS_Y_FEEDS_CANDIDATOS")
        return []
    ok = []
    for f in cands:
        try:
            got, st, _ = _fetch_feed(f, {}, False)
        except Exception as e:
            got, st = [], type(e).__name__
        recientes = [a for a in got if a.get("date") and (now_utc() - a["date"]).total_seconds() < 48 * 3600]
        ultimo = max((a["date"] for a in got if a.get("date")), default=None)
        print("%-18s %-70s %-8s items=%-3d recientes48h=%-3d ultimo=%s" % (
            f["outlet"], f["url"][:70], st[:8], len(got), len(recientes),
            ultimo.isoformat()[:16] if ultimo else "-"))
        if st == "ok" and recientes:
            ok.append(f)
    if guardar:
        with open(FEEDS_EXTRA_PATH, "w", encoding="utf-8") as fh:
            json.dump({"_nota": "Generado por 'python monitor.py probar_sitemaps' (Fase 18). Borrar para desactivar.",
                       "generado": now_utc().isoformat(), "feeds": ok}, fh, ensure_ascii=False, indent=1)
        print("\n%d de %d candidatos responden; guardados en feeds_extra.json" % (len(ok), len(cands)))
    return ok


def parse_sitemap_news(raw, outlet, seccion, ciudad_feed="", scope=None):
    """Fase 18 (P1-8): "news sitemap" (sitemap-news.xml / news-sitemap.xml,
    formato estandar de Google News). Varios diarios lo actualizan antes que
    su RSS -- y algunos con el RSS muerto (Primicias, Ecuavisa) podrian
    tener sitemap vivo. Mismo formato de salida que parse_feed()."""
    root = ET.fromstring(raw.lstrip())
    out = []
    for u in [e for e in root.iter() if tag(e) == "url"]:
        link = title = date = None
        for ch in u.iter():
            t = tag(ch)
            if t == "loc" and not link:
                link = (ch.text or "").strip()
            elif t == "title" and not title:
                title = (ch.text or "").strip()
            elif t == "publication_date":
                date = (ch.text or "").strip()
            elif t == "lastmod" and not date:
                date = (ch.text or "").strip()
        if not title or not link:
            continue
        title = html.unescape(title)
        if scope == "ec" and not is_ecuador(title):
            continue
        if is_junk(title, "", link):
            continue
        d = None
        if date:
            try:
                d = dt.datetime.fromisoformat(date.replace("Z", "+00:00"))
                d = (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)
            except ValueError:
                d = parse_date(date)
        sec = seccion
        if seccion == "auto":
            sec = classify_section(title) or "general"
        out.append({"outlet": outlet, "seccion": normalizar_categoria(sec), "title": title, "link": link,
                    "date": d, "summary": "", "image": "", "ciudad_feed": ciudad_feed})
    return out


# ------------------------- Fase 0 (velocidad): cache de fetch por feed -------------------------
# fetch_cache.json (distinto de los *_cache.json de siempre: NO es solo un TTL
# fijo, guarda ETag/Last-Modified para peticion condicional Y los ultimos
# items parseados de cada feed, para poder REUSARLOS sin volver a pedir nada
# cuando todavia no le toca el turno a ese feed o el servidor dice 304).
FETCH_CACHE_PATH = os.path.join(HERE, "fetch_cache.json")

def _cargar_fetch_cache():
    try:
        with open(FETCH_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _guardar_fetch_cache(cache):
    tmp = FETCH_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, FETCH_CACHE_PATH)

def _serializar_articulo(a):
    a2 = dict(a)
    a2["date"] = a["date"].isoformat() if a.get("date") else None
    return a2

def _deserializar_articulo(a):
    a2 = dict(a)
    if a2.get("date"):
        try:
            a2["date"] = dt.datetime.fromisoformat(a2["date"])
        except ValueError:
            a2["date"] = None
    return a2

# Cada cuanto se chequea un feed por defecto si no pide una frecuencia propia
# ("frecuencia_seg" en su dict de feeds.py). Se deriva del mismo tick que usa
# el hilo rapido de serve() (MONITOR_FEED_MIN, ahora acepta fracciones de
# minuto -- ver serve()) para que "cada cuanto se chequea" y "cada cuanto se
# publica" sean un solo numero por defecto, no dos que se puedan desincronizar.
FEED_TICK_SEC = float(os.environ.get("MONITOR_FEED_MIN", "1")) * 60

def _fetch_feed(f, cache_entry, respetar_frecuencia=True):
    """Trae y parsea UN feed. Nunca lanza: devuelve (items, estado,
    cache_entry_nuevo) para que un feed roto no tumbe a los demas ni el hilo
    que lo pide.

    Fase 0 (velocidad):
    - 'respetar_frecuencia' (False en una corrida unica de `python
      monitor.py` sin `serve`: ahi SIEMPRE se trae todo fresco, no tiene
      sentido "esperar el turno" en un programa que corre una vez y termina)
      decide si se puede saltar el pedido de red porque todavia no paso la
      frecuencia propia del feed desde el ultimo intento -- en ese caso se
      reusan los ultimos items guardados en cache, sin tocar la red.
    - Peticion condicional (ETag/Last-Modified, ver fetch()): si el feed SI
      le toca turno pero el servidor dice 304 (nada nuevo), tambien se
      reusan los items guardados -- se ahorra bajar y parsear el cuerpo
      entero para nada."""
    cache_entry = dict(cache_entry or {})
    items_cache = [_deserializar_articulo(a) for a in (cache_entry.get("items") or [])]
    ahora = time.time()
    frecuencia = f.get("frecuencia_seg") or FEED_TICK_SEC
    if respetar_frecuencia and (ahora - cache_entry.get("ultimo_fetch", 0)) < frecuencia:
        return items_cache, "cache (esperando turno)", cache_entry

    try:
        data, etag, last_mod, status = fetch(f["url"], cache_entry.get("etag"), cache_entry.get("last_modified"))
    except urllib.error.HTTPError as e:
        cache_entry["ultimo_fetch"] = ahora
        return items_cache, "HTTP %s" % e.code, cache_entry
    except Exception as e:
        cache_entry["ultimo_fetch"] = ahora
        return items_cache, type(e).__name__, cache_entry

    cache_entry["ultimo_fetch"] = ahora
    if status == 304:
        cache_entry["etag"], cache_entry["last_modified"] = etag, last_mod
        return items_cache, "ok (304 sin cambios)", cache_entry

    if f.get("tipo") == "sitemap":
        got = parse_sitemap_news(data, f["outlet"], f["seccion"], f.get("ciudad", ""), f.get("scope"))
    else:
        got = parse_feed(data, f["outlet"], f["seccion"], f.get("scope"), f.get("ciudad", ""),
                          google_news=f.get("google_news", False))
    if f.get("rutas_permitidas"):
        got = filtrar_por_ruta(got, f["rutas_permitidas"])
    cache_entry["etag"], cache_entry["last_modified"] = etag, last_mod
    cache_entry["items"] = [_serializar_articulo(a) for a in got]
    cache_entry["ultimo_ok"] = ahora
    return got, "ok", cache_entry

def collect(respetar_frecuencia=True):
    """Trae TODOS los feeds en paralelo (son espera de red, no CPU): asi un feed
    lento no demora a los demas. El orden del reporte queda igual que antes
    (el de FEEDS en feeds.py), aunque las descargas terminen en otro orden.
    Fase 0: lee/actualiza fetch_cache.json (ETag + frecuencia propia por
    feed + ultimos items) -- ver _fetch_feed()."""
    fetch_cache = _cargar_fetch_cache()
    # Fase 18 (P1-8): ultimo sondeo OK de cada medio ANTES de esta pasada --
    # para medir latencia solo sobre lo que aparecio con el feed ya vigilado.
    prev_ok = {}
    for f in FEEDS:
        ok_ts = (fetch_cache.get(f["url"]) or {}).get("ultimo_ok")
        if ok_ts:
            prev_ok[f["outlet"]] = max(prev_ok.get(f["outlet"], 0), ok_ts)
    resultados = [None] * len(FEEDS)
    tiempos_feed = [0.0] * len(FEEDS)  # Fase 17: diagnostico, no cambia el resultado
    def _tarea(i, f):
        t0 = time.time()
        resultados[i] = _fetch_feed(f, fetch_cache.get(f["url"]), respetar_frecuencia)
        tiempos_feed[i] = time.time() - t0
    t_collect0 = time.time()
    with ThreadPoolExecutor(max_workers=min(20, len(FEEDS)) or 1) as ex:
        futs = [ex.submit(_tarea, i, f) for i, f in enumerate(FEEDS)]
        for fut in futs:
            fut.result()  # ya corrieron en paralelo; esto solo espera a que terminen todos
    articles, report = [], []
    cache_nuevo = dict(fetch_cache)
    for f, (got, status, entry_nuevo) in zip(FEEDS, resultados):
        cache_nuevo[f["url"]] = entry_nuevo
        articles.extend(got)
        report.append((f["outlet"], f["seccion"], len(got), status))
    _guardar_fetch_cache(cache_nuevo)
    # Fase 17 (diagnostico de arranque lento): un feed que se cuelga cerca de
    # su TIMEOUT (8s por defecto) o que devuelve un status de error se ve acá
    # -- 'collect' en run_fast ya mide el total, esto dice CUAL feed puntual
    # explica ese total si no es simplemente "44 feeds x unos ms cada uno".
    lentos = sorted(
        ((f["outlet"], t, st) for f, t, (_, st, _) in zip(FEEDS, tiempos_feed, resultados)),
        key=lambda x: -x[1])[:5]
    con_error = [(f["outlet"], t, st) for f, t, (_, st, _) in zip(FEEDS, tiempos_feed, resultados)
                 if st not in ("ok", "ok (304 sin cambios)", "cache (esperando turno)")]
    if lentos and lentos[0][1] > 3:
        _log_arranque("collect: feeds mas lentos -> " +
                       "; ".join("%s=%.2fs(%s)" % (o, t, st) for o, t, st in lentos))
    if con_error:
        _log_arranque("collect: %d feed(s) con error/timeout -> " % len(con_error) +
                       "; ".join("%s=%.2fs(%s)" % (o, t, st) for o, t, st in con_error[:10]))
    _log_arranque("collect: %d feeds en %.2fs (paralelo, max 20 hilos)" %
                  (len(FEEDS), time.time() - t_collect0))
    _registrar_first_seen(articles, prev_ok)
    return articles, report


# ------------------------- Fase 0 (velocidad): demora real por feed -------------------------
# latencia_cache.json: registro liviano (mismo patron que entities.json --
# "registro de apariciones", no un cache recalculable) de CUANDO publico cada
# medio una nota (segun su propio feed) vs. CUANDO la vimos nosotros por
# primera vez. Es la unica forma de medir la demora real en vez de adivinarla
# -- antes de esto, el proyecto no guardaba first_seen en ningun lado.
LATENCIA_PATH = os.path.join(HERE, "latencia_cache.json")
LATENCIA_MAX_DIAS = 7  # solo hace falta para las estadisticas recientes, no crecer sin limite

def _cargar_latencia():
    try:
        with open(LATENCIA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _guardar_latencia(reg):
    tmp = LATENCIA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False)
    os.replace(tmp, LATENCIA_PATH)

# Fase 18 (P1-8): un articulo cuenta para la latencia solo si su medio ya
# se habia sondeado con exito hace <= LATENCIA_VENTANA_MIN. Si no (arranque de
# la PC, feed caido), lo que llega es BACKLOG: "lo vimos" mide cuanto estuvo
# apagado el programa, no cuanto tarda el medio. Eso inflaba las medianas
# (El Universo 405 min, El Diario 666 min).
LATENCIA_VENTANA_MIN = float(os.environ.get("MONITOR_LATENCIA_VENTANA_MIN", "30"))


def _registrar_first_seen(articles, prev_ok_por_outlet=None):
    """Para cada articulo visto por PRIMERA VEZ (por link, clave estable):
    guarda cuando el medio dice que lo publico (pub_date, del propio feed),
    cuando lo vimos nosotros (first_seen, ahora) y si la medicion es VALIDA
    (feed ya vigilado, ver LATENCIA_VENTANA_MIN). Un link ya registrado no se
    vuelve a tocar -- 'primera vez que lo vimos' tiene que quedar fijo."""
    reg = _cargar_latencia()
    ahora = now_utc()
    nuevos = 0
    prev_ok_por_outlet = prev_ok_por_outlet or {}
    for a in articles:
        link = a.get("link")
        if not link or link in reg:
            continue
        prev = prev_ok_por_outlet.get(a["outlet"])
        reg[link] = {
            "outlet": a["outlet"],
            "pub_date": a["date"].isoformat() if a.get("date") else None,
            "first_seen": ahora.isoformat(),
            "valida": bool(prev and (ahora.timestamp() - prev) <= LATENCIA_VENTANA_MIN * 60),
        }
        nuevos += 1
    if nuevos:
        corte = ahora - dt.timedelta(days=LATENCIA_MAX_DIAS)
        reg = {k: v for k, v in reg.items()
               if v.get("first_seen") and dt.datetime.fromisoformat(v["first_seen"]) > corte}
        _guardar_latencia(reg)

def calcular_latencia_por_feed():
    """Demora real medida (no estimada): por medio, mediana/peor caso/cuantos
    articulos tardaron mas de 10 min en pasar de 'publicado' (pub_date del
    feed) a 'lo vimos' (first_seen). Solo cuenta articulos con pub_date real
    -- si el medio no manda fecha, no hay con que medir demora, no se
    inventa un numero. Una demora NEGATIVA es señal real de un problema
    (fecha del feed en el futuro respecto a cuando lo vimos -- casi siempre
    zona horaria mal interpretada), se deja tal cual, no se recorta a 0."""
    reg = _cargar_latencia()
    por_outlet, backlog = {}, {}
    for v in reg.values():
        if not v.get("pub_date"):
            continue
        if not v.get("valida"):
            # Fase 18: backlog tras un arranque (o registro de antes de este
            # cambio): no mide la demora del medio, se cuenta aparte.
            backlog[v["outlet"]] = backlog.get(v["outlet"], 0) + 1
            continue
        try:
            pub = dt.datetime.fromisoformat(v["pub_date"])
            visto = dt.datetime.fromisoformat(v["first_seen"])
        except Exception:
            continue
        por_outlet.setdefault(v["outlet"], []).append((visto - pub).total_seconds() / 60)
    out = {o: {"n": 0, "mediana_min": None, "peor_min": None, "mas_de_10min": 0,
               "sin_fecha": 0, "n_descartados_backlog": n} for o, n in backlog.items()}
    for outlet, demoras in por_outlet.items():
        ds = sorted(demoras)
        n = len(ds)
        mediana = ds[n // 2] if n % 2 else (ds[n // 2 - 1] + ds[n // 2]) / 2
        out[outlet] = {
            "n": n,
            "mediana_min": round(mediana, 1),
            "peor_min": round(max(ds), 1),
            "mas_de_10min": sum(1 for d in ds if d > 10),
            "sin_fecha": sum(1 for a in reg.values() if a["outlet"] == outlet and not a.get("pub_date")),
            "n_descartados_backlog": backlog.get(outlet, 0),
        }
    return out


# ------------------------- dedup + clustering -------------------------

def dedup(articles):
    """Quita repetidos: mismo enlace (aunque venga de dos feeds), mismo
    titular EXACTO del mismo medio, y titular CASI igual del mismo medio si
    ademas comparten la misma imagen. La imagen es corroboracion obligatoria
    para el chequeo difuso: un "boletin con plantilla" (ej. "Cortes de luz
    programados en Guayaquil para hoy" vs. "...en Quito para hoy") puede
    superar facil un ratio de similitud alto sin ser la misma nota -- sin
    exigir la misma imagen, ese caso real se deduplicaria por error. Los
    mismos hechos contados por MEDIOS distintos NO se quitan aqui: eso lo
    agrupa cluster()."""
    seen_key, seen_link, seen_by_outlet, out = set(), set(), {}, []
    for a in articles:
        link = (a.get("link") or "").split("?")[0].rstrip("/").lower()
        if link and link in seen_link:
            continue
        title = norm(a["title"])
        key = (a["outlet"], title[:80])
        if key in seen_key:
            continue
        image = a.get("image") or ""
        vistos_medio = seen_by_outlet.setdefault(a["outlet"], [])
        if image and any(
            seen_image == image
            and difflib.SequenceMatcher(None, title, seen_title).ratio() > 0.85
            for seen_title, seen_image in vistos_medio
        ):
            continue
        seen_key.add(key)
        if link:
            seen_link.add(link)
        vistos_medio.append((title, image))
        out.append(a)
    return out

def jaccard(x, y):
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)

# Nombres propios de un titular (para el agrupamiento, Problema 5: "casi todas
# las historias quedan con un solo medio"): palabras capitalizadas de 4+
# letras, SIN contar la primera palabra del titular (que arranca en mayuscula
# por gramatica, no porque sea un nombre propio -- "Cortes de luz a..." no
# aporta nada como "nombre propio" solo por ir primero). Aproximado (sin NLP),
# mismo criterio de costo que el resto del proyecto (ver _NOMBRE_RE en
# gdelt.py) -- alcanza para reforzar coincidencias reales entre titulares
# distintos de la MISMA historia (ej. los dos mencionan "Noboa" o "Guayaquil").
# Fase 9, parte D3 (Problema 3, marco global) -- BUG REAL encontrado
# escribiendo la prueba del caso Xi Jinping: _nombres_propios() (ver abajo)
# exige 4+ letras (1 mayuscula + 3 minusculas), asi que "Xi" (2 letras)
# nunca matchea -- "Trump hosts Xi..." solo aportaba "trump" como entidad,
# nunca "xi", perdiendo la señal que conecta ese titular con su version en
# español ("Xi Jinping"). Bajar el minimo general arriesgaria muchos falsos
# positivos (cualquier palabra corta capitalizada al azar); en cambio, lista
# chica y curada de nombres propios REALES de 2-3 letras frecuentes en
# cobertura internacional (mismo criterio que _SIGLAS_GENERICAS/
# LUGARES_COMUNES: excepcion puntual, no un mecanismo general).
_NOMBRES_CORTOS_CONOCIDOS = {"xi", "kim"}
_NOMBRES_CORTOS_RX = re.compile(r"\b([A-Z][a-z]{1,2})\b")

def _nombres_propios(titulo):
    """BUG REAL encontrado en vivo (Problema 5): los titulares en INGLES de
    varios medios (NYT, BBC, Guardian...) van en Title Case -- casi cada
    palabra capitalizada, no solo los nombres propios ("5 Takeaways From Ari
    Emanuel's Memoir"). Tratar toda palabra capitalizada como "nombre propio"
    ahi adentro no distingue una entidad real de una palabra comun como
    "Memoir"/"Takeaways"/"From", y produjo una union FALSA: un titular sobre
    el libro de Ari Emanuel termino en el mismo grupo que titulares sobre el
    libro de Charles Spencer/Princess Diana, solo porque ambos compartian
    'Memoir' y 'From' capitalizados. Se detecta si el titular PARECE Title
    Case (mayoria de palabras elegibles capitalizadas) y, si es asi, no se
    extrae ningun nombre propio de el -- mejor no dar el descuento de umbral
    ahi que dispararlo con palabras comunes.

    En espanol (sentence case: solo la primera palabra y los nombres propios
    van en mayuscula) SI se cuenta la primera palabra como candidata -- un
    titular que arranca con el lugar/persona ("Guayaquil amanecio con calles
    inundadas...") es un caso real y frecuente, no solo gramatica."""
    capitalizadas = re.findall(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{3,}", titulo or "")
    todas = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{4,}", titulo or "")
    # BUG REAL (Problema 1, 2026-09-24, caso real "Lavinia Valbonesi asumira
    # la presidencia de ALMA en Nueva York"): con el umbral viejo (>0.5) un
    # titular en ESPAÑOL con 2 nombres propios de 2 palabras cada uno (un
    # nombre completo + "Nueva York") ya juntaba 4 de 7 palabras
    # capitalizadas (57%) y se trataba como Title Case ingles, perdiendo
    # TODA la senal de nombre propio -- justo la que hubiera unido esa nota
    # con la de otro medio sobre el mismo nombramiento. Medido con los casos
    # reales de ambas familias: Title Case ingles autentico ("5 Takeaways
    # From Ari Emanuel's Memoir", "Netanyahu Lashes Out at Foes...") mide
    # 1.00 (todas las palabras elegibles capitalizadas); titulares en
    # espanol con 2-3 nombres propios reales miden 0.57-0.60. Subir el
    # umbral a 0.7 separa limpio los dos casos sin tocar el de siempre.
    # Fase 9 (Problema A2): las siglas (CJNG, ATM, INAMHI...) son una senal
    # aparte de las palabras Sentence/Title Case de arriba -- un acronimo
    # nunca es "Memoir"/"Takeaways" (el problema que motivo el bail-out de
    # Title Case ingles), asi que se suman SIEMPRE, incluso cuando el titular
    # completo se descarta por parecer Title Case ingles.
    siglas = _siglas(titulo)
    # Fase 9, parte D3 (Problema 3, marco global): nombres propios REALES de
    # 2-3 letras (Xi, Kim...) que el regex de arriba (minimo 4 letras) nunca
    # capta -- mismo criterio que las siglas: se suman SIEMPRE, lista chica y
    # curada (ver _NOMBRES_CORTOS_CONOCIDOS), no un mecanismo general.
    cortos = {mo.lower() for mo in _NOMBRES_CORTOS_RX.findall(titulo or "")
              if mo.lower() in _NOMBRES_CORTOS_CONOCIDOS}
    if len(capitalizadas) >= 3 and todas and len(capitalizadas) / len(todas) > 0.7:
        return siglas | cortos  # titular en Title Case (ingles): las palabras sueltas no son confiables, siglas/cortos si
    return {strip_accents(p).lower() for p in capitalizadas} | siglas | cortos

def _sim(x, y):
    """Parecido entre titulares. Ademas del Jaccard, si comparten >=4 palabras
    de contenido usa el coeficiente de solape (interseccion / titular mas corto):
    asi une la misma historia aunque un medio la titule largo y otro corto.
    Exigir 4 palabras comunes evita uniones por coincidencias sueltas."""
    if not x or not y:
        return 0.0
    inter = len(x & y)
    if inter == 0:
        return 0.0
    j = inter / len(x | y)
    if inter >= 4:
        return max(j, inter / min(len(x), len(y)))
    return j

# Problema 5 ("casi todas las historias quedan con un solo medio", medido:
# 402/420 con n_outlets==1): diagnostico con titulares reales de la corrida
# en vivo mostro pares que SI son la misma historia (mismo hecho, contado por
# dos medios de Guayaquil con titulares distintos) quedando JUSTO debajo del
# umbral -- ej. "Guayaquil amanecio con calles inundadas..." vs "Las lluvias
# anegan calles de Sauces y La Florida..." dio 0.27 contra un umbral de 0.30.
# En vez de bajar el umbral general (mas riesgo de uniones falsas en los
# ~370 titulares internacionales, que son la mayoria del corpus), se agrega
# un umbral MAS BAJO pero mas exigente en otro sentido: aplica solo si
# ademas comparten un nombre propio (persona/lugar/institucion) -- una senal
# fuerte de que es la MISMA historia, no solo el mismo tema general.
CLUSTER_THRESHOLD = 0.30
CLUSTER_THRESHOLD_CON_NOMBRE = 0.20
# Fase 9 (Problema A2): la via "palabras+contenido" (2+ palabras de contenido
# compartidas, sin nombre/numero/sigla) es la unica corroboracion para casos
# como la 'clinica de libros' (Expreso/Municipio): Jaccard 0.18, por debajo
# de 0.20, con solo 2 palabras reales en comun ('clinica', 'libros') pero
# suficientemente especificas para no ser ruido. Floor mas bajo SOLO para
# esta via -- las demas (nombre/numero/sigla) siguen exigiendo 0.20, ya
# tienen su propia corroboracion aparte.
CLUSTER_THRESHOLD_CONTENIDO = 0.15
# Ventana de tiempo (Problema 5, sugerencia de Fernando): dos notas solo se
# consideran la misma historia si estan a menos de esto de distancia -- evita
# unir por una coincidencia de palabras/nombre propio entre notas de dias
# distintos que casualmente comparten vocabulario (ej. dos incendios distintos
# en fechas separadas). Bastante mas generoso que FEED_FRESH_H (10h) porque
# la cobertura de un mismo hecho en outlets distintos puede salir escalonada.
CLUSTER_MAX_HORAS = float(os.environ.get("MONITOR_CLUSTER_MAX_H", "72"))

def _plantillas_incompatibles(a, b):
    """Fase 9 (Problema A3) -- 'boletines con plantilla': un pronostico del
    clima/feriado/marea/precio del dolar de la MISMA ciudad pero fecha
    EXPLICITA distinta, o de ciudades ecuatorianas distintas, comparte casi
    toda la plantilla de palabras (por eso pasaban el umbral) sin ser el
    mismo hecho. Veto DURO: si aplica, nunca son la misma historia sin
    importar cuanto compartan en palabras/nombres/numeros/embedding."""
    fa, fb = a.get("_fecha_menc"), b.get("_fecha_menc")
    if fa and fb and not (fa & fb):
        return True
    ca, cb = a.get("_ciudad"), b.get("_ciudad")
    if ca and cb and ca != cb:
        return True
    sa, sb = a.get("_servicio"), b.get("_servicio")
    if sa and sb and sa != sb:
        return True
    return False

def _mismo_hecho(a, b):
    """Decide si dos articulos pueden ser la MISMA historia: veto de
    'plantilla' (ver arriba) + ventana de tiempo + (parecido de titular por
    encima del umbral general, O umbral mas bajo si ademas comparten un
    nombre propio)."""
    if _plantillas_incompatibles(a, b):
        return 0.0
    da, db = a.get("date"), b.get("date")
    if da and db:
        horas = abs((da - db).total_seconds()) / 3600
        if horas > CLUSTER_MAX_HORAS:
            return 0.0
    sim = _sim(a["_tok"], b["_tok"])
    if sim >= CLUSTER_THRESHOLD:
        return sim
    if sim >= CLUSTER_THRESHOLD_CON_NOMBRE and (a["_nom"] & b["_nom"]):
        return sim
    return 0.0

def cluster(articles):
    # Enlace por MAXIMO: una nota se une al grupo si se parece a CUALQUIER
    # nota del grupo. Evita que el centroide (union de tokens) infle el
    # denominador y termine rechazando notas de la misma historia.
    for a in articles:
        # NOTA (Fase 9): cluster()/_mismo_hecho() son el agrupamiento SOLO
        # intra-pasada -- el pipeline real usa agrupar_con_memoria() (ver
        # ese modulo mas abajo), que SI resta LUGARES_COMUNES antes de armar
        # _tok/_nom. Restarlo tambien aca rompia el caso ya documentado y
        # probado de la inundacion de Guayaquil (Problema 5): el UNICO
        # nombre propio compartido entre los dos titulares reales era
        # "Guayaquil", y ese es justamente el caso donde SI es la misma
        # historia. cluster() se deja intacto (sigue con su propia bateria
        # de pruebas, test_cluster.py/test_cluster_evento_generico.py); la
        # exclusion de lugares ubicuos (para el caso contrario: Santa
        # Elena/bus, un lugar compartido SIN relacion real) vive donde
        # importa de verdad, en el registro persistente.
        a["_tok"] = tokens(a["title"]) - EVENTO_GENERICO  # solo el titular: evita unir por texto repetido del resumen
        a["_nom"] = _nombres_propios(a["title"]) - EVENTO_GENERICO
        a["_fecha_menc"] = fecha_mencionada(a["title"])
        a["_ciudad"] = detect_city(a["title"] + " " + (a.get("summary") or ""))
        a["_servicio"] = servicio_mencionado(a["title"])
    # mas reciente primero: el titular representativo es el mas nuevo
    articles.sort(key=lambda a: a["date"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                  reverse=True)
    clusters = []
    for a in articles:
        best, best_sim = None, 0.0
        for c in clusters:
            sim = max(_mismo_hecho(a, m) for m in c["articles"])
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim > 0:
            best["articles"].append(a)
        else:
            clusters.append({"articles": [a]})
    return _merge_close(clusters)

def _merge_close(clusters, threshold=0.5):
    """Segunda pasada: une grupos cuyos titulares quedaron casi iguales pero
    que la pasada avara (un solo recorrido) dejo separados. Reduce las
    'noticias que se repiten' que se ven como dos tarjetas de la misma historia."""
    merged = []
    for c in clusters:
        ctok = set().union(*[a["_tok"] for a in c["articles"]]) if c["articles"] else set()
        placed = False
        for m in merged:
            if jaccard(ctok, m["_tok"]) >= threshold:
                m["articles"].extend(c["articles"])
                m["_tok"] |= ctok
                placed = True
                break
        if not placed:
            merged.append({"articles": list(c["articles"]), "_tok": set(ctok)})
    return merged


# ------------------------- Problema 1 (2026-09-24): clustering persistente -------------------------
# Diagnostico real (con data.json/history.json de una corrida en vivo, 1113
# historias): cluster() SIEMPRE agrupa desde cero, solo contra los articulos
# QUE ESTE PASE trajo collect() -- nunca contra las historias que ya se
# publicaron en pasadas anteriores. Mientras el articulo original siga
# dentro de la ventana RSS de su medio (la mayoria de los feeds la mantienen
# horas/dias), sigue reapareciendo en cada pasada y cluster() lo puede
# volver a comparar -- pero en cuanto el feed lo rota fuera de su ventana
# (rotacion tipica: minutos u horas para un feed muy activo), esa nota
# DESAPARECE de "articles" para siempre; si otro medio publica la MISMA
# historia mas tarde, cluster() jamas los ve juntos y quedan como dos
# tarjetas de una sola fuente cada una.
#
# Pares reales encontrados en data.json (word-overlap por debajo del umbral,
# NO se unieron):
#   1. "Circulaba con placas adulteradas y acumulaba $41.070 en multas: la
#      ATM retuvo el vehiculo" (El Universo Guayaquil) vs "Carro debia
#      41.000 en multas por carril de Metrovia: ATM lo retiene por llevar
#      placas adulteradas" (Expreso) -- mismo auto, misma multa, sim=0.23
#      (entre los dos umbrales) SIN nombre propio compartido: el hecho que
#      comparten es una CIFRA ("41.000"/"41.070"), no un nombre.
#   2. "Lavinia Valbonesi asume liderazgo de ALMA..." (TC Television) vs
#      "Lavinia Valbonesi asumira la presidencia de ALMA en Nueva York" (El
#      Universo) -- BUG REAL en _nombres_propios(): el segundo titular tiene
#      4 palabras capitalizadas de 7 (68%, nombre completo + "Nueva York"),
#      suficiente para que el detector de "Title Case ingles" (pensado para
#      "5 Takeaways From Ari Emanuel's Memoir") lo tratara como titular en
#      ingles y le vaciara el set de nombres propios -- perdiendo la senal
#      que hubiera unido las dos notas. Corregido subiendo el umbral de
#      relacion de 0.5 a 0.7 (ver _nombres_propios): los casos reales de
#      Title Case ingles miden 1.00 (todas las palabras elegibles
#      capitalizadas), los titulares en espanol con 2-3 nombres propios
#      quedan muy por debajo (0.57-0.60 medido con estos mismos casos).
#   3. "Daniel Noboa se reune con Volodimir Zelenski en Nueva York..." (El
#      Universo) vs "Daniel Noboa arranca su agenda en la ONU..." (TC
#      Television) -- comparten "Noboa" pero cuentan hechos DISTINTOS del
#      mismo dia (reunion con Zelenski vs. apertura de agenda): exactamente
#      el caso "misma historia, informacion nueva" que pide Actualizacion en
#      vez de fusion ciega (ver _es_actualizacion).
#   4. "Lluvias y tormentas electricas... en Quito" (3 medios ya agrupados:
#      El Diario/El Universo/Expreso) vs "INAMHI alerta por lluvias
#      intensas... en la Costa" (TC Television) -- mismo evento
#      meteorologico contado desde el angulo oficial (alerta) vs. el
#      observado (lluvia real), sin nombre propio ni cifra compartida: caso
#      limite que se deja SIN fusionar a proposito (mejor no forzar una
#      union dudosa que inventar una).
#   5. Estructural (no un par puntual, confirmado leyendo collect()/
#      run_fast()): un medio que publica una nota y la rota de su feed antes
#      de que otro medio cubra el mismo hecho nunca vuelve a compararse
#      contra el mismo articulo -- cluster() no tiene memoria entre pasadas.
#
# Umbral de embeddings medido en vivo (Ollama real, nomic-embed-text, esta
# PC): coseno de 4 pares REALES arriba dio 0.7651/0.8605/0.7683/0.8191 (el
# "limite" del caso 4 tambien mide alto: 0.77). Un par CLARAMENTE distinto
# (control negativo, dos notas sin ninguna relacion) dio 0.6150/0.6377. PERO
# el titular de Sevilla contra el de Guayaquil (mismo FORMATO de pronostico
# del tiempo, ciudades distintas) tambien dio 0.7780 -- casi tan alto como
# los duplicados reales. Conclusion medida (no supuesta): la similitud de
# embeddings SOLA no alcanza para notas cortas con formato de plantilla
# (nomic-embed-text capta la ESTRUCTURA de la frase, no solo el contenido) --
# hace falta exigir ADEMAS un nombre propio o una cifra en comun (lo que
# pedia el enunciado original: "combinada con entidades en comun"). Con esa
# combinacion, el par Sevilla/Guayaquil (sin nombre propio ni cifra
# compartida) queda afuera aunque su coseno sea alto.
#
# Fase 10, parte B (2026-09-26): recalibrado con gemini-embedding-001 (nomic-
# embed-text se retiro con Ollama). Mismos 4 pares reales documentados arriba,
# medidos de nuevo con el modelo nuevo: 0.8203 (multa)/0.9329 (Valbonesi-ALMA)/
# 0.9137 (CJNG-Samborondon)/0.9070 (Trump-Xi ES/EN, ver EMBED_SIM_UMBRAL_MULTILINGUE
# mas abajo). Controles negativos sin relacion real: 0.5434/0.5515 -- bien
# separados. PERO el mismo patron de "boletin con plantilla" se repite con
# este modelo: Sevilla/Guayaquil (clima, ciudades distintas) dio 0.8451 --
# MAS ALTO que el peor caso real que si debe unirse (0.8203). Confirma que
# ningun umbral de coseno solo puede separar ese caso (con NINGUN modelo
# medido hasta ahora): el candado real sigue siendo el veto de ciudad/fecha/
# servicio ya existente en el codigo (ver _match_registro/_embed_pendientes_registro),
# el coseno es una señal MAS, nunca la unica. Subido de 0.75 a 0.80 (con
# margen real: el peor positivo mide 0.82, por encima del umbral).
EMBED_SIM_UMBRAL = float(os.environ.get("MONITOR_EMBED_SIM", "0.80"))
EMBED_MAX_NEW = int(os.environ.get("MONITOR_EMBED_MAX", "40"))  # embeddings nuevos por pasada del trabajador
REGISTRO_PATH = os.path.join(HERE, "historias_registro.json")
# Fase 18 (P0-1): run_fast (agrupar_con_memoria) y el trabajador
# (_embed_pendientes_registro / _embed_multilingue_... / _coherencia_...)
# cargaban y guardaban este MISMO archivo sin coordinarse -- ganaba el ultimo
# en escribir y borraba lo del otro (medido: 190 llamadas de embeddings en un
# dia sin que la cobertura subiera). Todo "cargar -> modificar -> guardar" del
# registro pasa ahora por este lock. El trabajador NUNCA lo retiene mientras
# espera a la IA: calcula afuera sobre una foto, y adentro del lock recarga el
# registro FRESCO y aplica solo sus campos.
_REGISTRO_LOCK = threading.RLock()
REGISTRO_MAX_HORAS = CLUSTER_MAX_HORAS  # misma ventana de 72h que ya usaba cluster() intra-pasada
# Fase 11 (v2): las historias LOCALES (Ecuador/Guayaquil) se retienen en el
# registro mas tiempo que las internacionales -- son la materia prima de los
# "antecedentes" del contexto nuevo (contexto.py), y 72h no alcanza para que
# una historia de hace 2 semanas sirva de antecedente. Las internacionales
# siguen en MAX_AGE_DAYS (72h/3 dias) de siempre: el pedido fue explicito en
# que esto NO cambia. Esto solo alarga cuanto tiempo una entrada del
# REGISTRO sigue viva para poder citarse como antecedente -- build_stories()
# sigue descartando del DASHBOARD todo lo mas viejo que MAX_AGE_DAYS, asi que
# una historia local vieja retenida aca no reaparece como tarjeta nueva.
REGISTRO_DIAS_LOCAL = float(os.environ.get("MONITOR_REGISTRO_DIAS_LOCAL", "90"))


def _es_local_entry(e):
    """Ambito de una entrada del registro, por el mismo criterio de texto que
    ya usa is_ecuador() en el resto del proyecto (mas la señal dura de
    'ciudad', que build_stories() ya fija por seccion editorial del feed) --
    NO hay un campo 'es_local' guardado en el registro hoy, se deriva del
    titulo igual que _es_internacional() (funcion hermana, definida dentro de
    _embed_multilingue_pendientes_registro para ese uso puntual)."""
    if e.get("ciudad"):
        return True
    texto = (e.get("rep_titulo", "") or "") + " " + (e.get("fundador_titulo", "") or "")
    return is_ecuador(texto)

def _es_anio(numero_str):
    """Fase 9 (Problema A3): '2026'/'1961'/'1930' se colaban en _numeros()
    como si compartir el AÑO probara que dos notas son el mismo hecho --
    casi cualquier par de notas de esta corrida menciona el año actual. Un
    numero de 4 digitos en el rango de años plausibles (1900-2099) se trata
    como fecha, no como cifra -- se extrae aparte, si hace falta, con
    fecha_mencionada()."""
    return len(numero_str) == 4 and 1900 <= int(numero_str) <= 2099

def _numeros(texto):
    """Numeros de 3+ digitos (separadores de miles/decimales opcionales), sin
    los separadores -- señal barata y fuerte de 'mismo hecho' cuando dos
    titulares distintos citan la MISMA cifra (caso real: multa de
    $41.000/$41.070, ver arriba). Los separadores se quitan para que
    '41.070'/'41070' cuenten como el mismo numero. Los años (ver _es_anio) se
    excluyen: comparten año casi todas las notas de una misma corrida, no es
    señal de nada."""
    return {m2 for m2 in (re.sub(r"[.,]", "", m) for m in re.findall(r"\d[\d.,]*\d|\b\d{3,}\b", texto or ""))
            if len(m2) >= 3 and not _es_anio(m2)}

def _cos_sim(u, v):
    if not u or not v or len(u) != len(v):
        return 0.0
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    return dot / (nu * nv) if nu and nv else 0.0

_VERBOS_NOVEDAD = ("desmiente", "desmintio", "responde", "respondio", "niega", "nego",
                    "confirma", "confirmo", "anuncia", "anuncio", "reacciona", "reacciono",
                    "rectifica", "rectifico", "aclara", "aclaro", "eleva", "elevo",
                    "actualiza", "actualizo", "revela", "revelo", "admite", "admitio",
                    "suma", "sumaron", "muere", "murio", "fallece", "fallecio")

def _es_actualizacion(nuevo_titulo, nuevo_resumen, entry):
    """Regla determinista, sin IA (pedido explicito: 'unos pocos segundos
    por nota'): la nota nueva trae informacion NUEVA sobre el mismo hecho si
    (a) menciona una cifra que la historia todavia no tenia, o (b) usa un
    verbo de reaccion/consecuencia que el titular representativo no tenia
    todavia. Si no hay señal de novedad, es la misma cobertura de siempre
    contada por otro medio -- se suma como fuente pero no genera una entrada
    en 'actualizaciones'."""
    nums_nuevo = _numeros(nuevo_titulo + " " + (nuevo_resumen or ""))
    if nums_nuevo - entry.get("numeros", set()):
        return True
    blob_nuevo = norm(nuevo_titulo)
    if any(kw_hit(v, blob_nuevo) for v in _VERBOS_NOVEDAD):
        blob_rep = norm(entry.get("rep_titulo", ""))
        if not any(kw_hit(v, blob_rep) for v in _VERBOS_NOVEDAD):
            return True
    return False

def _iso_a_dt(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None

def _cargar_registro():
    """Lee historias_registro.json (si existe) y reconstruye los datetime
    (se guardan como isoformat en disco). Un registro vacio/corrupto se trata
    como 'sin historial todavia', nunca rompe la corrida."""
    try:
        with open(REGISTRO_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    out = {}
    for eid, e in raw.items():
        try:
            out[eid] = {
                "creado": _iso_a_dt(e.get("creado")),
                "ultimo": _iso_a_dt(e.get("ultimo")),
                "rep_titulo": e.get("rep_titulo", ""),
                "rep_resumen": e.get("rep_resumen", ""),
                # Fase 9 (Problema A3, "deriva por rep_titulo"): titulo/resumen
                # del PRIMER articulo que creo la entrada, INMUTABLE despues de
                # eso (a diferencia de rep_titulo, que se actualiza al mas
                # nuevo cada vez) -- el ancla que evita que una cadena de
                # coincidencias parciales se aleje del hecho original. Entradas
                # viejas (de antes de este cambio) no lo tienen -- se cae a
                # rep_titulo, mismo comportamiento que antes para esas.
                "fundador_titulo": e.get("fundador_titulo") or e.get("rep_titulo", ""),
                "fundador_resumen": e.get("fundador_resumen") or e.get("rep_resumen", ""),
                # "ciudad" (Problema A3): se fija UNA vez, con la primera
                # deteccion no vacia, e inmutable de ahi en mas -- veto duro
                # de "boletin con plantilla" (ver _plantillas_incompatibles).
                "ciudad": e.get("ciudad", ""),
                "servicio": e.get("servicio", ""),
                "fechas": set(e.get("fechas") or []),
                "embedding_multi": e.get("embedding_multi"),
                "tokens": set(e.get("tokens") or []),
                "nombres": set(e.get("nombres") or []),
                "numeros": set(e.get("numeros") or []),
                "embedding": e.get("embedding"),
                # Fase 11 (v2), bug real confirmado: estos dos campos se
                # escribian en memoria (_embed_pendientes_registro/
                # _embed_multilingue_pendientes_registro) pero NUNCA se
                # guardaban ni se restauraban aca -- como _cargar_registro()
                # se llama de nuevo en CADA pasada (no solo al reiniciar el
                # proceso), el vector ya calculado sobrevivia bien, pero la
                # etiqueta del modelo se perdia siempre, asi que cada pasada
                # volvia a tratar TODAS las entradas como "pendientes" --
                # confirmado en vivo: con EMBED_MAX_NEW=40, la cobertura real
                # quedaba trabada en exactamente 40/981 (las mismas 40 mas
                # viejas, recalculadas sin necesidad en cada pasada; las
                # genuinamente nuevas nunca llegaban a tener turno).
                "embedding_modelo": e.get("embedding_modelo"),
                "embedding_multi_modelo": e.get("embedding_multi_modelo"),
                "fuentes": [dict(f_, date=_iso_a_dt(f_.get("date"))) for f_ in (e.get("fuentes") or [])],
                "actualizaciones": [dict(u, fecha=_iso_a_dt(u.get("fecha"))) for u in (e.get("actualizaciones") or [])],
                "coherencia_hash": e.get("coherencia_hash", ""),
            }
        except Exception:
            continue  # una entrada corrupta no debe tumbar el resto del registro
    return out

def _guardar_registro(registro):
    serial = {}
    for eid, e in registro.items():
        serial[eid] = {
            "creado": e["creado"].isoformat() if e.get("creado") else None,
            "ultimo": e["ultimo"].isoformat() if e.get("ultimo") else None,
            "rep_titulo": e.get("rep_titulo", ""),
            "rep_resumen": e.get("rep_resumen", ""),
            "fundador_titulo": e.get("fundador_titulo", ""),
            "fundador_resumen": e.get("fundador_resumen", ""),
            "ciudad": e.get("ciudad", ""),
            "servicio": e.get("servicio", ""),
            "fechas": sorted(e.get("fechas") or []),
            "embedding_multi": e.get("embedding_multi"),
            "tokens": sorted(e.get("tokens") or []),
            "nombres": sorted(e.get("nombres") or []),
            "numeros": sorted(e.get("numeros") or []),
            "embedding": e.get("embedding"),
            "embedding_modelo": e.get("embedding_modelo"),
            "embedding_multi_modelo": e.get("embedding_multi_modelo"),
            "fuentes": [dict(f_, date=f_["date"].isoformat() if f_.get("date") else None)
                        for f_ in e.get("fuentes", [])],
            "actualizaciones": [dict(u, fecha=u["fecha"].isoformat() if u.get("fecha") else None)
                                 for u in e.get("actualizaciones", [])],
            "coherencia_hash": e.get("coherencia_hash", ""),
        }
    tmp = REGISTRO_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(serial, f, ensure_ascii=False)
    os.replace(tmp, REGISTRO_PATH)


def _tam_registro_mb():
    """Peso real de historias_registro.json en disco (Fase 11 v2, pedido
    explicito: 'controla el tamano del archivo e informa cuanto pesa tras
    una corrida'). None si el archivo todavia no existe (primera corrida)."""
    try:
        return round(os.path.getsize(REGISTRO_PATH) / (1024 * 1024), 2)
    except OSError:
        return None

def _match_registro(art, registro, cache_entry=None):
    """Mejor entrada del registro (dentro de REGISTRO_MAX_HORAS) para este
    articulo: mismo criterio que _mismo_hecho() (palabras + nombre propio),
    mas dos señales nuevas que NUNCA llaman a red/Ollama (solo leen lo que ya
    esta en el registro): cifra compartida, y similitud de embeddings SI
    ambos lados ya tienen uno calculado (lo calcula el trabajador, nunca esta
    funcion -- ver _embed_pendientes_registro).

    'cache_entry' (Fase 17, diagnostico de arranque lento): dict opcional,
    compartido entre TODAS las llamadas de una misma pasada de
    _fusionar_en_registro (varios articulos nuevos se comparan contra las
    MISMAS entradas del registro) -- guarda, por eid, el resultado ya
    calculado de "es extranjero"/tokens de esa entrada, valido mientras
    e["rep_titulo"] no haya cambiado desde que se cacheo (se compara el
    texto exacto, no solo el eid, asi que un cambio real invalida solo y
    nunca deja pasar un valor viejo). Si no se pasa, se usa un dict nuevo
    (mismo comportamiento de antes, sin cache entre llamadas) -- asi no
    rompe a quien llame a esta funcion con la firma vieja de 2 argumentos."""
    if cache_entry is None:
        cache_entry = {}
    a_tok, a_nom, a_num = art["_tok"], art["_nom"], art["_num"]
    a_fecha = art.get("date") or now_utc()
    a_emb = art.get("_emb")
    a_fecha_menc = art.get("_fecha_menc") or set()
    a_ciudad = art.get("_ciudad") or ""
    a_servicio = art.get("_servicio") or ""
    # Fase 17 (diagnostico de arranque lento -- ver COORDINACION.md, Frente
    # B): a_extranjero depende SOLO de 'art', nunca de 'e' -- antes se
    # recalculaba en CADA vuelta del for de mas abajo (hasta ~1300 veces por
    # articulo, uno por cada entrada del registro dentro de la ventana de
    # 72h) para el MISMO resultado siempre. Perfilado con cProfile: esto
    # explicaba el 93.9% del tiempo de _fusionar_en_registro() en un caso
    # real (58 de 61.8 segundos, para 9 articulos). Sacarlo del loop no
    # cambia el resultado (es la misma cuenta, una sola vez en vez de N).
    a_extranjero = extranjero_sin_ecuador(art["title"] + " " + _quitar_dateline(art.get("summary") or ""))
    best_id, best_sim, best_via = None, 0.0, None
    for eid, e in registro.items():
        ultimo = e.get("ultimo")
        if ultimo and abs((a_fecha - ultimo).total_seconds()) / 3600 > REGISTRO_MAX_HORAS:
            continue
        # Fase 9 (Problema A3) -- veto de "boletin con plantilla": misma
        # ciudad con fecha explicita distinta, ciudades distintas, o
        # utilidad basica distinta (luz/agua/gas), nunca es la misma
        # historia por mas que compartan vocabulario/nombre/numero.
        e_fechas, e_ciudad, e_servicio = e.get("fechas", set()), e.get("ciudad", ""), e.get("servicio", "")
        if a_fecha_menc and e_fechas and not (a_fecha_menc & e_fechas):
            continue
        if a_ciudad and e_ciudad and a_ciudad != e_ciudad:
            continue
        if a_servicio and e_servicio and a_servicio != e_servicio:
            continue
        # Fase 17: e_extranjero/tok_rep/tok_fund dependen SOLO de 'e' -- para
        # la MISMA entrada, dan el mismo resultado sin importar cual sea el
        # articulo nuevo 'art' que se este evaluando. Sin este cache, con N
        # articulos nuevos comparados contra la MISMA entrada en una sola
        # pasada, se recalculaban N veces cada uno (perfilado: la segunda
        # mitad del costo de extranjero_sin_ecuador que quedaba tras sacar
        # a_extranjero del loop). tok_fund usa fundador_titulo, que es
        # INMUTABLE (Fase 9) -- una vez calculado para un eid, nunca se
        # invalida. tok_rep/e_extranjero SI pueden cambiar (rep_titulo se
        # actualiza cuando la entrada suma una fuente mas nueva) -- se
        # invalidan solos comparando el texto exacto contra el cacheado.
        # Nota: tok_fund se recalcula junto con los otros dos (no se cachea
        # "para siempre" pese a que fundador_titulo es inmutable) porque en
        # entradas viejas sin fundador_titulo el codigo cae a rep_titulo
        # (mutable, ver _cargar_registro) -- distinguir ambos casos no vale
        # la complejidad extra; invalidar los tres juntos sigue siendo
        # correcto y ya evita el grueso de la recomputacion redundante.
        #
        # BUG REAL encontrado por Codex en la revision de este mismo cambio
        # (antes de mergear): la huella original concatenaba rep_titulo +
        # " " + rep_resumen en UN string -- dos pares distintos pueden dar
        # el MISMO string concatenado si el "corte" entre titulo y resumen
        # cae en otro lado (ej. titulo="A B"+resumen="C" y titulo="A"+
        # resumen="B C" concatenan igual a "A B C"), lo que dejaria pasar un
        # tok_rep/extranjero viejo como si siguiera valido. Arreglado
        # usando una TUPLA de los campos originales como huella (nunca
        # colisiona entre pares distintos), en vez de un string armado.
        rep_titulo_e = e.get("rep_titulo", "") or ""
        rep_resumen_e = e.get("rep_resumen", "") or ""
        fundador_titulo_e = e.get("fundador_titulo", "") or rep_titulo_e
        huella_e = (rep_titulo_e, rep_resumen_e, fundador_titulo_e)
        c = cache_entry.get(eid)
        if c is not None and c["huella"] == huella_e:
            e_extranjero, tok_rep, tok_fund = c["extranjero"], c["tok_rep"], c["tok_fund"]
        else:
            # Fase 18 (P0-2): el veto mira el representante Y el fundador --
            # si cualquiera de los dos es "extranjero sin Ecuador" y el
            # articulo no (o al reves), no se fusionan.
            e_extranjero = (extranjero_sin_ecuador(rep_titulo_e + " " + rep_resumen_e),
                            extranjero_sin_ecuador(fundador_titulo_e + " " + _quitar_dateline(e.get("fundador_resumen", "") or "")))
            tok_rep = tokens(rep_titulo_e) - EVENTO_GENERICO - LUGARES_COMUNES
            tok_fund = tokens(fundador_titulo_e) - EVENTO_GENERICO - LUGARES_COMUNES
            cache_entry[eid] = {"huella": huella_e, "extranjero": e_extranjero,
                                 "tok_rep": tok_rep, "tok_fund": tok_fund}
        if a_extranjero != e_extranjero[0] or a_extranjero != e_extranjero[1]:
            continue
        # BUG REAL propio, encontrado escribiendo la prueba de la
        # "Actualizacion" (Problema 1): comparar contra el UNION acumulado
        # de tokens de TODAS las fuentes de la entrada (e["tokens"]) diluye
        # el Jaccard a medida que la historia suma medios -- una entrada con
        # 2 fuentes ya trae vocabulario de las dos, y una tercera nota real
        # sobre el MISMO hecho puede terminar bajo el umbral solo porque el
        # denominador crecio. _sim()/CLUSTER_THRESHOLD se calibraron para
        # comparar UN titular contra OTRO titular (como hace cluster()), no
        # contra una union creciente.
        #
        # Fase 9 (Problema A3, "deriva por rep_titulo"): comparar SOLO contra
        # el representante (el titular mas nuevo, que se va desplazando a
        # medida que la historia suma fuentes) permitia una cadena de
        # coincidencias parciales alejarse del hecho original -- A se une con
        # B, el representante pasa a ser B, C se une con B aunque C y A no
        # tengan nada que ver. Se compara tambien contra el NUCLEO
        # (fundador_titulo, el titular de la PRIMERA fuente, inmutable).
        # El anclaje solo se exige DURO (el MINIMO de ambas similitudes) para
        # la via "palabras" -- la unica SIN ninguna corroboracion aparte (es
        # la mas propensa a encadenar por vocabulario generico). Las vias
        # asistidas (nombre/numero/contenido compartido) ya tienen su propia
        # corroboracion especifica, asi que usan el MAXIMO contra los dos
        # anclajes: exigir el minimo ahi tambien rompia casos legitimos (una
        # tercera nota que se parece mas a la MAS VIEJA de las fuentes que a
        # la mas reciente, ej. la reaccion de un afectado citando de nuevo el
        # monto original en vez del angulo del segundo medio).
        # (tok_rep/tok_fund ya se calcularon/cachearon arriba, junto con e_extranjero.)
        sim_rep, sim_fund = _sim(a_tok, tok_rep), _sim(a_tok, tok_fund)
        sim_nucleo, sim_asistida = min(sim_rep, sim_fund), max(sim_rep, sim_fund)
        nom_e, num_e = e.get("nombres", set()), e.get("numeros", set())
        sim, via = 0.0, None
        if sim_nucleo >= CLUSTER_THRESHOLD:
            sim, via = sim_nucleo, "palabras"
        elif sim_asistida >= CLUSTER_THRESHOLD_CON_NOMBRE and (a_nom & nom_e):
            sim, via = sim_asistida, "palabras+nombre"
        elif sim_asistida >= CLUSTER_THRESHOLD_CON_NOMBRE and (a_num & num_e):
            sim, via = sim_asistida, "palabras+numero"
        # Caso real diagnosticado (Problema 1: multa de $41.070/$41.000, ver
        # comentario arriba del modulo): ningun nombre propio en comun
        # y las cifras difieren ($41.070 vs $41.000 -- montos reportados
        # distinto por cada medio), pero comparten 2+ palabras de CONTENIDO
        # reales ("placas", "adulteradas"). Aca si se exige el minimo (ambos
        # anclajes) porque esta via no tiene ninguna otra corroboracion.
        elif sim_asistida >= CLUSTER_THRESHOLD_CONTENIDO and min(len(a_tok & tok_rep), len(a_tok & tok_fund)) >= 2:
            sim, via = sim_asistida, "palabras+contenido"
        # Fase 18 (P0-2, veto de plantilla): las vias por palabras necesitan
        # un ancla real ademas del vocabulario de formato.
        if via is not None:
            reales = (a_tok & (tok_rep | tok_fund)) - TOKENS_PLANTILLA
            ancla = bool(a_nom & nom_e) or bool(a_num & num_e) or bool(a_ciudad and a_ciudad == e_ciudad)
            if len(reales) < 2 and not ancla:
                sim, via = 0.0, None
        e_emb = e.get("embedding")
        if a_emb and e_emb and ((a_nom & nom_e) or (a_num & num_e)):
            esim = _cos_sim(a_emb, e_emb)
            if esim >= EMBED_SIM_UMBRAL and esim > sim:
                sim, via = esim, "embedding+entidad"
        if sim > best_sim:
            best_id, best_sim, best_via = eid, sim, via
    return best_id, best_sim, best_via

def _fusionar_en_registro(articles, registro):
    """Mete los articulos de ESTA pasada en el registro persistente: cada uno
    se compara contra las historias YA EXISTENTES (no solo contra las de esta
    corrida) y se suma como fuente nueva (o 'actualizacion' si trae algo
    nuevo, ver _es_actualizacion) a la que matchea, o crea una entrada nueva
    si no matchea ninguna. Se procesa en orden ASCENDENTE de fecha para que
    una tanda de articulos nuevos del mismo evento (varios medios publicando
    casi a la vez, en la MISMA pasada) tambien se agrupen entre si -- se
    comparan contra el registro, que ya incluye las entradas recien creadas
    en esta misma llamada."""
    vistos = {f_["link"] for e in registro.values() for f_ in e.get("fuentes", []) if f_.get("link")}
    # BUG REAL encontrado verificando en vivo (reinicio de 'serve' con este
    # mismo cambio, 2026-09-24/25): "Busqueda: Guayaquil" (feed de Google
    # News) aparecio 3 veces como fuente de la MISMA historia -- Google News
    # arma el link con un token que puede cambiar entre lecturas del MISMO
    # articulo, asi que dedup()/el chequeo por link de arriba no lo agarran,
    # y como el registro AHORA persiste entre pasadas (a diferencia de
    # cluster(), que se recalculaba de cero), el problema se acumula en vez
    # de disolverse solo. Mismo criterio que dedup() (outlet + titulo
    # normalizado, no el link) como chequeo adicional antes de sumar una
    # fuente al registro.
    claves_fuente = {(eid, f_["outlet"], norm(f_["title"])[:80])
                      for eid, e in registro.items() for f_ in e.get("fuentes", [])}
    ordenados = sorted(articles, key=lambda a: a.get("date") or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    # Fase 17: cache compartido entre TODAS las llamadas a _match_registro()
    # de esta pasada -- varios articulos nuevos se comparan contra las
    # MISMAS entradas del registro, y lo que depende solo de la entrada
    # (extranjero/tokens del representante) no hace falta recalcularlo para
    # cada articulo. Se invalida solo (ver _match_registro) si una entrada
    # cambia de representante a mitad de esta misma pasada.
    cache_entry = {}
    for a in ordenados:
        link = a.get("link")
        if link and link in vistos:
            continue
        a["_tok"] = tokens(a["title"]) - EVENTO_GENERICO - LUGARES_COMUNES - PALABRAS_GENERICAS_CONTENIDO
        a["_nom"] = _nombres_propios(a["title"]) - EVENTO_GENERICO - LUGARES_COMUNES - PALABRAS_GENERICAS_CONTENIDO
        a["_num"] = _numeros(a["title"] + " " + (a.get("summary") or ""))
        a["_fecha_menc"] = fecha_mencionada(a["title"])
        _texto_geo = a["title"] + " " + _quitar_dateline(a.get("summary") or "")
        a["_ciudad"] = "" if _es_enumeracion_ciudades(_texto_geo) else detect_city(_texto_geo)
        a["_servicio"] = servicio_mencionado(a["title"])
        a["_emb"] = None  # el hilo rapido nunca calcula embeddings nuevos, solo lee los que ya hay
        eid, sim, via = _match_registro(a, registro, cache_entry)
        fuente = {"outlet": a["outlet"], "title": a["title"], "link": link,
                  "date": a.get("date"), "seccion": a.get("seccion", ""),
                  "summary": a.get("summary", ""), "image": a.get("image", ""),
                  "ciudad_feed": a.get("ciudad_feed", "")}
        if eid is not None and (eid, a["outlet"], norm(a["title"])[:80]) in claves_fuente:
            if link:
                vistos.add(link)  # mismo medio+titulo ya registrado en esa historia: no duplicar
            continue
        if eid is not None:
            e = registro[eid]
            if _es_actualizacion(a["title"], a.get("summary", ""), e):
                e.setdefault("actualizaciones", []).append({
                    "fecha": a.get("date"), "outlet": a["outlet"],
                    "titulo": a["title"], "link": link,
                })
            e["fuentes"].append(fuente)
            e["tokens"] = e.get("tokens", set()) | a["_tok"]
            e["nombres"] = e.get("nombres", set()) | a["_nom"]
            e["numeros"] = e.get("numeros", set()) | a["_num"]
            e["fechas"] = e.get("fechas", set()) | a["_fecha_menc"]
            if not e.get("ciudad") and a["_ciudad"]:
                e["ciudad"] = a["_ciudad"]  # se fija una vez, inmutable de ahi en mas (ver _match_registro)
            if not e.get("servicio") and a["_servicio"]:
                e["servicio"] = a["_servicio"]
            if a.get("date") and (not e.get("ultimo") or a["date"] > e["ultimo"]):
                e["ultimo"] = a["date"]
                e["rep_titulo"] = a["title"]
                e["rep_resumen"] = a.get("summary", "")
            claves_fuente.add((eid, a["outlet"], norm(a["title"])[:80]))
        else:
            base = link or a["title"]
            nid = hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:16]
            while nid in registro:
                nid += "x"
            registro[nid] = {
                "creado": a.get("date") or now_utc(),
                "ultimo": a.get("date") or now_utc(),
                "rep_titulo": a["title"], "rep_resumen": a.get("summary", ""),
                "fundador_titulo": a["title"], "fundador_resumen": a.get("summary", ""),
                "ciudad": a["_ciudad"], "servicio": a["_servicio"], "fechas": set(a["_fecha_menc"]),
                "tokens": set(a["_tok"]), "nombres": set(a["_nom"]), "numeros": set(a["_num"]),
                "embedding": None,
                "fuentes": [fuente], "actualizaciones": [],
            }
            claves_fuente.add((nid, a["outlet"], norm(a["title"])[:80]))
        if link:
            vistos.add(link)
    # purga: una entrada totalmente fuera de su ventana de retencion no vuelve
    # a aparecer en el dashboard de todos modos (build_stories ya la
    # descarta por "hours > MAX_AGE_DAYS*24" sin importar cuanto dure aca) --
    # se saca del registro para que no siga creciendo sin limite ni
    # compitiendo por matches inutiles. Fase 11 (v2): lo local (Ecuador/
    # Guayaquil) se retiene REGISTRO_DIAS_LOCAL (90 dias por defecto) para
    # servir de antecedente real; lo internacional sigue en MAX_AGE_DAYS (3
    # dias) de siempre, sin cambios -- pedido explicito de no tocarlo.
    corte_intl = now_utc() - dt.timedelta(days=MAX_AGE_DAYS)
    corte_local = now_utc() - dt.timedelta(days=REGISTRO_DIAS_LOCAL)
    for eid in list(registro.keys()):
        e = registro[eid]
        if not e.get("ultimo"):
            continue
        corte = corte_local if _es_local_entry(e) else corte_intl
        if e["ultimo"] < corte:
            del registro[eid]
    return registro

def _registro_a_clusters(registro):
    clusters = []
    for e in registro.values():
        arts = [dict(f_) for f_ in e.get("fuentes", [])]
        if not arts:
            continue
        clusters.append({"articles": arts, "actualizaciones": e.get("actualizaciones", []),
                         "creado": e.get("creado"), "fundador_titulo": e.get("fundador_titulo", "")})
    return clusters

def agrupar_con_memoria(articles):
    """Reemplaza cluster()+build_stories() en el pipeline en vivo (Problema 1,
    2026-09-24): compara cada nota nueva contra las HISTORIAS YA EXISTENTES
    de las ultimas REGISTRO_MAX_HORAS (72h por defecto, historias_registro.json),
    no solo contra las notas de esta misma corrida. cluster()/_merge_close()
    (agrupamiento SOLO intra-pasada, sin memoria entre corridas) se dejan
    intactas -- las siguen usando sus propias pruebas (test_cluster.py,
    test_cluster_evento_generico.py) -- el pipeline real (run_once/run_fast)
    usa esta funcion en su lugar."""
    with _REGISTRO_LOCK:
        registro = _cargar_registro()
        registro = _fusionar_en_registro(articles, registro)
        _guardar_registro(registro)
    clusters = _registro_a_clusters(registro)
    return build_stories(clusters)

REGISTRO_VERSION = "fase18"
REGISTRO_VERSION_PATH = os.path.join(HERE, "historias_registro_version.json")


def _registro_version():
    try:
        with open(REGISTRO_VERSION_PATH, encoding="utf-8") as f:
            return json.load(f).get("version")
    except Exception:
        return None


def reconstruir_registro(verbose=False, lote_horas=1):
    """Fase 18 (P0-2/P0-3): el registro guardado ya trae historias mal
    fundidas con las reglas viejas (Cartagena dentro de cortes de agua de
    Guayaquil, "fechas y precios", "ataque armado"...). Las reglas nuevas solo
    actuan sobre lo que llega DESPUES, asi que esas mezclas se quedarian para
    siempre. Esto re-procesa TODAS las fuentes guardadas, en orden de fecha y
    por lotes de 'lote_horas' (simula las pasadas reales), con las reglas
    actuales. Hace respaldo antes (historias_registro.json.bak-fase18-...).
    Los embeddings ya calculados se conservan cuando el texto coincide (no se
    vuelve a pagar Gemini por ellos). Devuelve (entradas_antes, entradas_despues)."""
    with _REGISTRO_LOCK:
        viejo = _cargar_registro()
        if os.path.exists(REGISTRO_PATH):
            bak = REGISTRO_PATH + ".bak-fase18-" + now_utc().strftime("%Y%m%d_%H%M%S")
            import shutil
            shutil.copy2(REGISTRO_PATH, bak)
        vectores = {}
        for e in viejo.values():
            if e.get("embedding") and e.get("embedding_modelo"):
                for texto in (e.get("fundador_titulo"), e.get("rep_titulo")):
                    if texto:
                        vectores.setdefault(texto.strip(), (e["embedding"], e["embedding_modelo"]))
        arts, vistos = [], set()
        for e in viejo.values():
            for f_ in e.get("fuentes", []):
                clave = (f_.get("outlet"), norm(f_.get("title", ""))[:80])
                if clave in vistos or not f_.get("title"):
                    continue
                vistos.add(clave)
                arts.append({"outlet": f_.get("outlet", ""), "title": f_.get("title", ""),
                             "link": f_.get("link"), "date": f_.get("date"),
                             "seccion": f_.get("seccion", ""), "summary": f_.get("summary", "") or "",
                             "image": f_.get("image", ""), "ciudad_feed": f_.get("ciudad_feed", "")})
        arts.sort(key=lambda a: a.get("date") or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
        nuevo, lote, inicio_lote = {}, [], None
        for a in arts:
            d = a.get("date")
            if lote and d and inicio_lote and (d - inicio_lote).total_seconds() > lote_horas * 3600:
                nuevo = _fusionar_en_registro(lote, nuevo)
                lote, inicio_lote = [], None
            if inicio_lote is None:
                inicio_lote = d
            lote.append(a)
        if lote:
            nuevo = _fusionar_en_registro(lote, nuevo)
        reusados = 0
        for e in nuevo.values():
            v = vectores.get(_texto_embedding(e))
            if v:
                e["embedding"], e["embedding_modelo"] = v
                reusados += 1
        _guardar_registro(nuevo)
        try:
            with open(REGISTRO_VERSION_PATH, "w", encoding="utf-8") as f:
                json.dump({"version": REGISTRO_VERSION, "ts": now_utc().isoformat(),
                           "antes": len(viejo), "despues": len(nuevo)}, f)
        except OSError:
            pass
    if verbose:
        print("registro reconstruido: %d -> %d entradas (%d articulos, %d embeddings reusados)" % (
            len(viejo), len(nuevo), len(arts), reusados))
    return len(viejo), len(nuevo)


def migrar_registro_si_hace_falta(verbose=False):
    """Una sola vez por instalacion: si el registro es de antes de la Fase
    18, se reconstruye con las reglas nuevas (ver reconstruir_registro)."""
    if _registro_version() == REGISTRO_VERSION or not os.path.exists(REGISTRO_PATH):
        return None
    _log_arranque("registro: reconstruyendo con reglas de Fase 18 (una sola vez)...")
    r = reconstruir_registro(verbose=verbose)
    _log_arranque("registro: reconstruido %d -> %d entradas" % r)
    return r


def _embed_pendientes_registro():
    """Trabajo del hilo TRABAJADOR (nunca run_fast): calcula embeddings para
    historias del registro que todavia no tienen uno (acotado a
    EMBED_MAX_NEW por pasada, mismo patron que IA_MAX_NEW/CONTEXTO_MAX) y,
    con eso, reconcilia duplicados que el hilo rapido dejo pasar por SOLO
    tener palabras/numeros en comun de forma parcial -- una vez que DOS
    entradas tienen embedding, coseno alto (EMBED_SIM_UMBRAL) Y comparten un
    nombre propio o una cifra, se fusionan (la mas nueva se absorbe en la mas
    vieja, para no romper la clave estable fuentes[0] que usan
    saved.json/notas.json). Nunca corre en run_fast: si no hay modelo de
    embeddings instalado, no hace nada (el resto del pipeline sigue con
    palabras/nombres/cifras nomas, sin romperse)."""
    if ia is None or not ia.embed_disponible():
        return "sin modelo de embeddings (%s)" % (getattr(ia, "EMBED_MODEL", "nomic-embed-text") if ia else "?")
    foto = _cargar_registro()
    if not foto:
        return "registro vacio"
    # Fase 10, parte B: candado de espacio vectorial -- un vector de OTRO
    # modelo (ej. nomic-embed-text, retirado con Ollama) o sin etiqueta
    # (registros de antes de este cambio) nunca se compara contra uno nuevo,
    # aunque por coincidencia tuviera la misma dimension. "pendientes" ahora
    # es "sin vector del modelo ACTUAL" (no solo "sin vector") -- asi los
    # vectores viejos se recalculan solos, una pasada a la vez, sin tocar el
    # archivo a mano (ver migracion real hecha en esta misma sesion: backup +
    # recalculo, documentado en CLAUDE.md).
    pendientes = [eid for eid, e in foto.items()
                  if _texto_embedding(e) and e.get("embedding_modelo") != ia.EMBED_MODEL]
    # Fase 18 (P0-1): las llamadas a la IA van AFUERA del lock (pueden tardar
    # segundos cada una) -- se guarda el texto exacto que se vectorizo para
    # aplicar el vector solo si la entrada sigue diciendo lo mismo.
    nuevos = {}
    for eid in pendientes[:EMBED_MAX_NEW]:
        texto = _texto_embedding(foto[eid])
        emb = ia.embed(texto)
        if emb:
            nuevos[eid] = (texto, emb)
    with _REGISTRO_LOCK:
        registro = _cargar_registro()
        calculados = 0
        for eid, (texto, emb) in nuevos.items():
            e = registro.get(eid)
            if e is None or _texto_embedding(e) != texto:
                continue  # la entrada cambio o se fusiono mientras tanto: se recalcula en otra pasada
            e["embedding"] = emb
            e["embedding_modelo"] = ia.EMBED_MODEL
            calculados += 1
        fusiones = _reconciliar_por_embedding(registro)
        if calculados or fusiones:
            _guardar_registro(registro)
    # formato "+N nuevas" a proposito (mismo patron que iastatus/cstatus/etc,
    # ver _RE_NUEVAS en enrich_pass): asi el trabajador no espera
    # MONITOR_WORKER_PAUSA completo si todavia queda backlog de embeddings.
    return "+%d nuevas (embeddings, pendientes: %d), +%d fusiones por parafraseo" % (
        calculados, max(0, len(pendientes) - calculados), fusiones)


def _texto_embedding(e):
    """Texto que se vectoriza por entrada. Fase 18 (P0-2): el titular
    FUNDADOR (inmutable), no el mas nuevo -- asi el vector no queda viejo
    cada vez que la historia suma un medio."""
    return (e.get("fundador_titulo") or e.get("rep_titulo") or "").strip()


def _reconciliar_por_embedding(registro):
    """Fusiona entradas duplicadas por coseno + entidad compartida (el
    cuerpo de lo que antes vivia dentro de _embed_pendientes_registro). Se
    llama SIEMPRE con _REGISTRO_LOCK tomado y sobre el registro recien
    recargado. Devuelve cuantas fusiones hizo."""
    fusiones = 0
    ids = [eid for eid, e in registro.items()
           if e.get("embedding") and e.get("embedding_modelo") == ia.EMBED_MODEL]
    absorbidos = set()
    for i in range(len(ids)):
        if ids[i] in absorbidos:
            continue
        ei = registro[ids[i]]
        for j in range(i + 1, len(ids)):
            if ids[j] in absorbidos:
                continue
            ej = registro[ids[j]]
            ua, ub = ei.get("ultimo"), ej.get("ultimo")
            if ua and ub and abs((ua - ub).total_seconds()) / 3600 > REGISTRO_MAX_HORAS:
                continue
            comparten = (ei.get("nombres", set()) & ej.get("nombres", set())) or \
                        (ei.get("numeros", set()) & ej.get("numeros", set()))
            if not comparten:
                continue
            # Fase 9 (Problema A3): mismo veto de "boletin con plantilla" que
            # _match_registro -- un coseno alto entre dos pronosticos del
            # clima de ciudades/fechas distintas (medido: 0.78, casi tan alto
            # como un duplicado real) no debe fusionarlos.
            fi, fj = ei.get("fechas", set()), ej.get("fechas", set())
            if fi and fj and not (fi & fj):
                continue
            ci, cj = ei.get("ciudad", ""), ej.get("ciudad", "")
            if ci and cj and ci != cj:
                continue
            si, sj = ei.get("servicio", ""), ej.get("servicio", "")
            if si and sj and si != sj:
                continue
            # Fase 18 (P0-2): mismo veto de lugar extranjero que _match_registro.
            if extranjero_sin_ecuador(ei.get("fundador_titulo", "")) != extranjero_sin_ecuador(ej.get("fundador_titulo", "")):
                continue
            if _cos_sim(ei["embedding"], ej["embedding"]) < EMBED_SIM_UMBRAL:
                continue
            # la mas vieja ("creado" mas chico) absorbe a la mas nueva -- asi
            # fuentes[0] (story_key/storyKey, clave de saved.json/notas.json)
            # sigue siendo la misma nota de siempre.
            if (ei.get("creado") or now_utc()) <= (ej.get("creado") or now_utc()):
                vieja, vieja_id, nueva, nueva_id = ei, ids[i], ej, ids[j]
            else:
                vieja, vieja_id, nueva, nueva_id = ej, ids[j], ei, ids[i]
            links_ya = {f_.get("link") for f_ in vieja["fuentes"]}
            for f_ in nueva["fuentes"]:
                if f_.get("link") not in links_ya:
                    vieja["fuentes"].append(f_)
                    links_ya.add(f_.get("link"))
            vieja.setdefault("actualizaciones", []).extend(nueva.get("actualizaciones", []))
            vieja["tokens"] = vieja.get("tokens", set()) | nueva.get("tokens", set())
            vieja["nombres"] = vieja.get("nombres", set()) | nueva.get("nombres", set())
            vieja["numeros"] = vieja.get("numeros", set()) | nueva.get("numeros", set())
            vieja["fechas"] = vieja.get("fechas", set()) | nueva.get("fechas", set())
            if not vieja.get("ciudad") and nueva.get("ciudad"):
                vieja["ciudad"] = nueva["ciudad"]
            if not vieja.get("servicio") and nueva.get("servicio"):
                vieja["servicio"] = nueva["servicio"]
            if nueva.get("ultimo") and (not vieja.get("ultimo") or nueva["ultimo"] > vieja["ultimo"]):
                vieja["ultimo"] = nueva["ultimo"]
                vieja["rep_titulo"] = nueva.get("rep_titulo", vieja.get("rep_titulo"))
                vieja["rep_resumen"] = nueva.get("rep_resumen", vieja.get("rep_resumen"))
            absorbidos.add(nueva_id)
            fusiones += 1
    for eid in absorbidos:
        del registro[eid]
    return fusiones


def _canon_set(nombres):
    """'nombres' de un registro (ya normalizados por _nombres_propios/_siglas)
    llevados a su forma canonica cruzada de idioma (ver _EQUIV_ENTIDADES)."""
    return {_EQUIV_ENTIDADES.get(n.replace(" ", ""), n) for n in (nombres or set())}


EMBED_MULTI_MAX_NEW = int(os.environ.get("MONITOR_EMBED_MULTI_MAX", "20"))
COHERENCIA_MAX_NEW = int(os.environ.get("MONITOR_COHERENCIA_MAX", "8"))  # entradas nuevas por pasada (Fase 14)

def _embed_multilingue_pendientes_registro():
    """Fase 9, parte D3 (Problema 3) -- reconciliacion cruzada de idioma:
    MISMO patron que _embed_pendientes_registro() (arriba), pero con una
    regla de fusion mas exigente en entidades: coseno alto POR SI SOLO no
    alcanza (a diferencia de la reconciliacion intra-idioma) porque
    'Trump'+'Xi' aparecen juntos en decenas de notas DISTINTAS por dia --
    hace falta 2+ entidades canonicas en comun, o 1 sola si el coseno es MUY
    alto. Acotado a entradas INTERNACIONALES (is_ecuador() da False sobre su
    texto) -- lo local de Ecuador no cambia con esta pasada, por pedido
    explicito.

    Fase 10, parte B: en su momento (Ollama) esto usaba un modelo APARTE
    (bge-m3) porque nomic-embed-text no separaba bien cruzado de idioma (ver
    comentario de EMBED_SIM_UMBRAL_MULTILINGUE). Verificado en vivo que
    gemini-embedding-001 SI es multilingue de por si (coseno 0.9070 para un
    duplicado real ES/EN) -- por eso ia.EMBED_MODEL_MULTILINGUE apunta al
    MISMO modelo que ia.EMBED_MODEL por defecto. Cuando son el mismo modelo,
    esta funcion REUSA el vector que ya calculo _embed_pendientes_registro()
    (mismo modelo + mismo texto = mismo vector -- pedirlo de nuevo duplicaria
    el costo sin ganar nada); si en el futuro se configuran modelos
    distintos (MONITOR_EMBED_MODEL != MONITOR_EMBED_MULTI_MODEL), sigue
    pidiendo un vector aparte como antes."""
    if ia is None or not ia.embed_disponible(ia.EMBED_MODEL_MULTILINGUE):
        return "sin modelo multilingue (%s)" % (getattr(ia, "EMBED_MODEL_MULTILINGUE", "bge-m3") if ia else "?")
    # Fase 18 (P0-1): foto sin lock para decidir que calcular; las llamadas a
    # la IA van afuera, y se aplican despues sobre el registro recargado.
    foto = _cargar_registro()
    if not foto:
        return "registro vacio"

    def _es_internacional(e):
        texto = (e.get("rep_titulo", "") or "") + " " + (e.get("fundador_titulo", "") or "")
        return not is_ecuador(texto)

    mismo_modelo = (ia.EMBED_MODEL_MULTILINGUE == ia.EMBED_MODEL)
    if mismo_modelo:
        # Se reusa "embedding"/"embedding_modelo" (el mismo campo que llena
        # _embed_pendientes_registro()) en vez de "embedding_multi" -- pero
        # esta funcion sigue siendo AUTOSUFICIENTE (no depende de que la otra
        # ya haya corrido antes en la misma pasada, mismo criterio que el
        # resto del proyecto para poder probar cada funcion del trabajador
        # por separado): si una entrada internacional todavia no tiene vector
        # del modelo actual, lo calcula ella misma aca, tageado igual --
        # cuando las dos funciones SI corren en la misma pasada (caso real de
        # enrich_pass), la que llega primero ya lo dejo listo y esta no
        # vuelve a pedirlo (sin duplicar costo).
        campo, campo_modelo, modelo_ok = "embedding", "embedding_modelo", ia.EMBED_MODEL
    else:
        campo, campo_modelo, modelo_ok = "embedding_multi", "embedding_multi_modelo", ia.EMBED_MODEL_MULTILINGUE
    pendientes = [eid for eid, e in foto.items()
                  if _texto_embedding(e) and _es_internacional(e)
                  and e.get(campo_modelo) != modelo_ok]
    nuevos = {}
    for eid in pendientes[:EMBED_MULTI_MAX_NEW]:
        texto = _texto_embedding(foto[eid])
        emb = ia.embed(texto) if mismo_modelo else ia.embed(texto, modelo=ia.EMBED_MODEL_MULTILINGUE)
        if emb:
            nuevos[eid] = (texto, emb)
    with _REGISTRO_LOCK:
        return _embed_multilingue_aplicar(nuevos, pendientes, campo, campo_modelo, modelo_ok,
                                          mismo_modelo, _es_internacional)


def _embed_multilingue_aplicar(nuevos, pendientes, campo, campo_modelo, modelo_ok, mismo_modelo, _es_internacional):
    """Parte "bajo lock" de _embed_multilingue_pendientes_registro (Fase 18,
    P0-1): recarga el registro fresco, aplica los vectores ya calculados y
    reconcilia. Siempre se llama con _REGISTRO_LOCK tomado."""
    registro = _cargar_registro()
    calculados = 0
    for eid, (texto, emb) in nuevos.items():
        e = registro.get(eid)
        if e is None or _texto_embedding(e) != texto:
            continue
        e[campo] = emb
        e[campo_modelo] = modelo_ok
        calculados += 1

    def _vec(e):
        if mismo_modelo:
            return e.get("embedding") if e.get("embedding_modelo") == ia.EMBED_MODEL_MULTILINGUE else None
        return e.get("embedding_multi") if e.get("embedding_multi_modelo") == ia.EMBED_MODEL_MULTILINGUE else None

    fusiones = 0
    ids = [eid for eid, e in registro.items() if _vec(e) and _es_internacional(e)]
    absorbidos = set()
    for i in range(len(ids)):
        if ids[i] in absorbidos:
            continue
        ei = registro[ids[i]]
        for j in range(i + 1, len(ids)):
            if ids[j] in absorbidos:
                continue
            ej = registro[ids[j]]
            ua, ub = ei.get("ultimo"), ej.get("ultimo")
            if ua and ub and abs((ua - ub).total_seconds()) / 3600 > REGISTRO_MAX_HORAS:
                continue
            canon_i, canon_j = _canon_set(ei.get("nombres")), _canon_set(ej.get("nombres"))
            comunes = canon_i & canon_j
            cos = _cos_sim(_vec(ei), _vec(ej))
            if len(comunes) >= 2:
                pass  # 2+ entidades en comun: suficiente corroboracion
            elif len(comunes) == 1 and cos >= 0.75:
                pass  # 1 sola entidad, pero coseno MUY alto
            else:
                continue
            if cos < EMBED_SIM_UMBRAL_MULTILINGUE:
                continue
            # mismo veto de "boletin con plantilla" que las otras reconciliaciones
            fi, fj = ei.get("fechas", set()), ej.get("fechas", set())
            if fi and fj and not (fi & fj):
                continue
            if (ei.get("creado") or now_utc()) <= (ej.get("creado") or now_utc()):
                vieja, vieja_id, nueva, nueva_id = ei, ids[i], ej, ids[j]
            else:
                vieja, vieja_id, nueva, nueva_id = ej, ids[j], ei, ids[i]
            links_ya = {f_.get("link") for f_ in vieja["fuentes"]}
            for f_ in nueva["fuentes"]:
                if f_.get("link") not in links_ya:
                    vieja["fuentes"].append(f_)
                    links_ya.add(f_.get("link"))
            vieja.setdefault("actualizaciones", []).extend(nueva.get("actualizaciones", []))
            vieja["tokens"] = vieja.get("tokens", set()) | nueva.get("tokens", set())
            vieja["nombres"] = vieja.get("nombres", set()) | nueva.get("nombres", set())
            vieja["numeros"] = vieja.get("numeros", set()) | nueva.get("numeros", set())
            vieja["fechas"] = vieja.get("fechas", set()) | nueva.get("fechas", set())
            if nueva.get("ultimo") and (not vieja.get("ultimo") or nueva["ultimo"] > vieja["ultimo"]):
                vieja["ultimo"] = nueva["ultimo"]
                # OJO: a diferencia de la reconciliacion intra-idioma, el
                # rep_titulo NO se pisa a ciegas con el mas nuevo -- eso lo
                # decide build_stories()/_titular_global() mirando TODAS las
                # fuentes por idioma (ver mas abajo), no solo la mas nueva.
            absorbidos.add(nueva_id)
            fusiones += 1
    for eid in absorbidos:
        del registro[eid]
    if calculados or fusiones:
        _guardar_registro(registro)
    return "+%d nuevas (embeddings multilingues, pendientes: %d), +%d fusiones cruzadas de idioma" % (
        calculados, max(0, len(pendientes) - calculados), fusiones)


def _dividir_entrada_registro(eid, e, grupos_idx, registro):
    """Fase 14 (Paso 2, 'evitar mezclas'): parte una entrada del registro en
    2+ entradas segun los grupos de indices de fuente que ya paso el candado
    de _coherencia_pendientes_registro (cada indice en EXACTAMENTE un grupo).
    El grupo que contiene la fuente FUNDADORA (fundador_titulo/fundador_resumen,
    la mas vieja) se queda con el MISMO eid -- mismo criterio que
    _embed_pendientes_registro (la mas vieja nunca cambia de identidad, para
    no romper la clave estable que usan saved.json/notas.json). Devuelve un
    dict {eid_o_nuevo: entrada_nueva} listo para volcar en 'registro'."""
    fuentes = e.get("fuentes") or []
    fundador_link = None
    for f_ in fuentes:
        if f_.get("title") == e.get("fundador_titulo") and (f_.get("summary") or "") == (e.get("fundador_resumen") or ""):
            fundador_link = f_.get("link")
            break
    if fundador_link is None and fuentes:
        fundador_link = min(fuentes, key=lambda f_: f_.get("date") or now_utc()).get("link")
    ids_usados = set(registro.keys())
    resultado = {}
    for grupo in grupos_idx:
        sub_fuentes = [fuentes[i] for i in grupo if 0 <= i < len(fuentes)]
        if not sub_fuentes:
            continue
        sub_ordenadas = sorted(sub_fuentes, key=lambda f_: f_.get("date") or now_utc())
        primero, ultimo_f = sub_ordenadas[0], sub_ordenadas[-1]
        tok, nom, num, fechas_menc = set(), set(), set(), set()
        ciudad, servicio = "", ""
        for f_ in sub_ordenadas:
            titulo, resumen = f_.get("title", ""), f_.get("summary") or ""
            texto_geo = titulo + " " + _quitar_dateline(resumen)
            tok |= tokens(titulo) - EVENTO_GENERICO - LUGARES_COMUNES - PALABRAS_GENERICAS_CONTENIDO
            nom |= _nombres_propios(titulo) - EVENTO_GENERICO - LUGARES_COMUNES - PALABRAS_GENERICAS_CONTENIDO
            num |= _numeros(titulo + " " + resumen)
            fechas_menc |= fecha_mencionada(titulo)
            if not ciudad:
                ciudad = "" if _es_enumeracion_ciudades(texto_geo) else detect_city(texto_geo)
            if not servicio:
                servicio = servicio_mencionado(titulo)
        nueva = {
            "creado": primero.get("date") or e.get("creado") or now_utc(),
            "ultimo": ultimo_f.get("date") or e.get("ultimo") or now_utc(),
            "rep_titulo": ultimo_f.get("title", ""), "rep_resumen": ultimo_f.get("summary", ""),
            "fundador_titulo": primero.get("title", ""), "fundador_resumen": primero.get("summary", ""),
            "ciudad": ciudad, "servicio": servicio, "fechas": fechas_menc,
            "tokens": tok, "nombres": nom, "numeros": num,
            "embedding": None, "embedding_modelo": None,
            "embedding_multi": None, "embedding_multi_modelo": None,
            "fuentes": sub_fuentes,
            "actualizaciones": [u for u in e.get("actualizaciones", [])
                                 if u.get("link") in {f_.get("link") for f_ in sub_fuentes}],
        }
        nueva["coherencia_hash"] = _hash_fuentes(nueva)
        if any(f_.get("link") == fundador_link for f_ in sub_fuentes):
            nid = eid  # el grupo con la fuente fundadora conserva el id de siempre
        else:
            base = (sub_fuentes[0].get("link") or sub_fuentes[0].get("title") or eid) + "|division"
            nid = hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:16]
            while nid in ids_usados or nid in resultado:
                nid += "x"
        ids_usados.add(nid)
        resultado[nid] = nueva
    return resultado


def _coherencia_pendientes_registro():
    """Fase 14 (Paso 2, 'evitar mezclas' -- verificacion de coherencia):
    revisa historias YA formadas con 3+ fuentes para detectar si mezclan 2+
    hechos distintos (mismo lugar/organizacion/vocabulario no alcanza para
    ser el mismo hecho, ver casos reales en pruebas/casos_geo_agrupamiento.json)
    y las divide. Acotado a COHERENCIA_MAX_NEW entradas por pasada (mismo
    patron que EMBED_MAX_NEW/CONTEXTO_MAX_NEW/VEREDICTO_MAX_NEW) -- nunca
    reprocesa todo el registro de una vez. Cachea por _hash_fuentes: si el
    conjunto de fuentes de una entrada no cambio desde la ultima
    verificacion, no se vuelve a llamar a la IA. Nunca corre en run_fast."""
    if ia is None or os.environ.get("MONITOR_NO_IA") == "1":
        return "desactivado"
    # Fase 18 (P0-1): la IA se consulta sobre una FOTO del registro, sin
    # lock; los resultados se aplican despues sobre el registro recargado y
    # solo si el conjunto de fuentes de esa entrada no cambio mientras tanto
    # (los indices de grupo se refieren a ESA lista de fuentes).
    foto = _cargar_registro()
    if not foto:
        return "registro vacio"
    candidatos = [eid for eid, e in foto.items()
                  if len(e.get("fuentes") or []) >= 3
                  and e.get("coherencia_hash") != _hash_fuentes(e)]
    candidatos.sort(key=lambda eid: len(foto[eid].get("fuentes") or []), reverse=True)
    respuestas = []
    for eid in candidatos[:COHERENCIA_MAX_NEW]:
        e = foto[eid]
        fuentes = e.get("fuentes") or []
        material = [{"id": str(i), "titulo": f_.get("title", ""), "resumen": (f_.get("summary") or "")[:220]}
                    for i, f_ in enumerate(fuentes)]
        respuestas.append((eid, _hash_fuentes(e), ia.verificar_coherencia(material, forzado=IA_MODEL)))
    with _REGISTRO_LOCK:
        return _coherencia_aplicar(respuestas, len(candidatos))


def _coherencia_aplicar(respuestas, n_candidatos):
    """Parte "bajo lock" de _coherencia_pendientes_registro (Fase 18, P0-1)."""
    registro = _cargar_registro()
    verificadas, divisiones = 0, 0
    for eid, hash_visto, r in respuestas:
        verificadas += 1
        e = registro.get(eid)
        if e is None or _hash_fuentes(e) != hash_visto:
            continue  # se fusiono/cambio mientras la IA pensaba: se revisa en otra pasada
        fuentes = e.get("fuentes") or []
        if r is None:
            continue  # no se cachea un fallo transitorio: se reintenta la proxima pasada
        if r.get("un_solo_hecho", True):
            e["coherencia_hash"] = _hash_fuentes(e)
            continue
        # Candado en CODIGO (no solo confiar en el prompt): cada indice de
        # fuente tiene que aparecer en EXACTAMENTE un grupo -- si el modelo
        # dejo alguno afuera, lo repitio, o invento un indice que no existe,
        # el resultado no es confiable y se descarta (mejor no dividir que
        # dividir mal y perder una fuente).
        try:
            grupos_idx = [[int(x) for x in g] for g in (r.get("grupos") or [])]
        except (TypeError, ValueError):
            grupos_idx = []
        todos = [i for g in grupos_idx for i in g]
        validos = (len(grupos_idx) >= 2 and sorted(todos) == list(range(len(fuentes)))
                   and len(set(todos)) == len(fuentes))
        if not validos:
            e["coherencia_hash"] = _hash_fuentes(e)  # se cachea igual: no reintentar en cada pasada
            continue
        nuevas = _dividir_entrada_registro(eid, e, grupos_idx, registro)
        if eid in nuevas:
            registro[eid] = nuevas.pop(eid)
        else:
            del registro[eid]
        registro.update(nuevas)
        divisiones += 1
    if verificadas:
        _guardar_registro(registro)
    return "+%d nuevas (coherencia, pendientes: %d), +%d divisiones" % (
        verificadas, max(0, n_candidatos - verificadas), divisiones)


# ------------------------- temas + prominencia -------------------------

def themes_for(text, seccion):
    """Etiqueta TODOS los temas que toca la nota, de cualquier categoria (multi-tema).
    Asi una nota politica que habla de salud tambien queda etiquetada como Salud."""
    blob = norm(text)
    found = []
    for bank in KEYWORDS.values():
        for theme, words in bank.items():
            if any(kw_hit(w, blob) for w in words):
                found.append(theme)
    return sorted(set(found))

def contar_por_categoria(stories):
    """Conteo de historias por categoria (seccion), en el orden fijo del
    dashboard. Un solo lugar para esta cuenta: la usan tanto el print de
    diagnostico en terminal (run_once/run_fast verbose) como la prueba en
    test_categorias.py, para que terminal y prueba nunca puedan divergir."""
    cnt = {c: 0 for c in CATEGORIAS_VALIDAS}
    for s in stories:
        cnt[normalizar_categoria(s.get("seccion"))] += 1
    return cnt

def imprimir_categorias(stories):
    cnt = contar_por_categoria(stories)
    print("Historias por categoria:")
    for c in CATEGORIAS_VALIDAS:
        marca = "  <-- 0 historias" if cnt[c] == 0 else ""
        print("  %-10s %4d%s" % (c, cnt[c], marca))
    return cnt

def _fmt_horas(segundos):
    """Antiguedad en segundos -> texto corto ('35 min', '2h', '3d'), para
    mostrar 'dato de hace X' en el dashboard (Problema 3: usar el ultimo
    dato bueno en vez de dejar un campo vacio cuando la fuente falla)."""
    if segundos is None:
        return None
    h = segundos / 3600
    if h < 1:
        return "%d min" % max(1, round(segundos / 60))
    if h < 48:
        return "%.0fh" % h
    return "%.0fd" % (h / 24)

def _peso_outlets(s):
    """Cuanto pesan los medios que cubren una historia para el ranking de
    interes -- Problema 4 (2026-09-23, cuarta pasada): antes un medio
    internacional pesaba EXACTAMENTE igual que uno local (s["n_outlets"] a
    secas), aunque 'outlets_intl' ya se calculaba en build_stories() y nunca
    se usaba para puntuar. Caso real confirmado: una nota sobre Delcy
    Rodriguez (VP de Venezuela) encabezaba el ambito Ecuador con 9 medios, 7
    de ellos internacionales y solo 2 locales.
    Solo para historias de ambito LOCAL (es_local=True, Ecuador/Guayaquil):
    los medios ecuatorianos pesan igual que antes (40 c/u), los
    internacionales pesan bastante menos (5 c/u, un octavo) -- siguen
    sumando (una nota de Ecuador SI puede traer cobertura internacional
    real), pero no alcanzan para encabezar solos sin cobertura local: 7
    medios internacionales (35 puntos) siguen pesando menos que 1 solo medio
    ecuatoriano (40 puntos). Para historias de ambito internacional no
    cambia nada: ahi la cobertura extranjera es justamente la señal que
    importa."""
    n_intl = len(s.get("outlets_intl") or [])
    if not s.get("es_local"):
        return s["n_outlets"] * 40
    n_local = s["n_outlets"] - n_intl
    return n_local * 40 + n_intl * 5

# Temas de "seguridad" que representan un hecho grave y puntual (no
# administrativo): un asesinato, un ataque armado, una masacre. Deliberadamente
# NO se incluye "Carceles" ni "Policia/Militar" del mismo banco de KEYWORDS
# (feeds.py) porque esos dos suelen ser notas institucionales/de rutina
# (un operativo, una reforma penitenciaria) y no siempre son un hecho grave
# puntual -- "Crimen/Violencia" y "Narcotrafico" si lo son casi siempre.
TEMAS_ALTO_IMPACTO = {"Crimen/Violencia", "Narcotrafico"}


def _bono_impacto(s):
    """Bono de ranking para sucesos de ALTO IMPACTO en Ecuador/Guayaquil --
    Fase 11 (pedido de Fernando: 'los sucesos locales criticos no estan
    recibiendo la prioridad adecuada'). _peso_outlets()+n_articles*6 premia
    CUANTA cobertura ya junto una historia, pero un hecho grave real (un
    asesinato, un ataque armado) puede tener un solo medio en los primeros
    minutos y quedar hundido bajo notas triviales con mas cobertura
    acumulada -- caso real confirmado: 'Una mujer fue baleada tras retirar
    USD 2.000... en el centro de Guayaquil' (temas=['Crimen/Violencia'],
    ambito local) rankeaba muy por debajo de coberturas internacionales de
    puro volumen. Solo aplica a historias LOCALES (Ecuador/Guayaquil) --
    para hechos graves en el exterior la cobertura internacional ya es la
    señal correcta, no hace falta este bono. Bono FIJO (no un multiplicador)
    para no descontrolar el resto del ranking ni forzar que una nota local
    de un solo medio supere siempre a una cobertura internacional masiva
    (eso seria mentir el orden, no priorizar) -- el bono la acerca al tope,
    no la garantiza ahi."""
    if not s.get("es_local"):
        return 0
    if TEMAS_ALTO_IMPACTO & set(s.get("temas") or []):
        return 150
    return 0

def _edad_mas_vieja(ts_por_clave):
    """De un dict {clave: timestamp unix}, la antiguedad en segundos del dato
    MAS VIEJO (el que mas urge refrescar). None si el dict viene vacio."""
    if not ts_por_clave:
        return None
    return time.time() - min(ts_por_clave.values())

def now_utc():
    return dt.datetime.now(dt.timezone.utc)

def _titular_global(fuentes_es, fuentes_en):
    """Fase 9, parte D3 (Problema 3): titular neutral para una historia de
    cobertura global (fuentes en ES Y EN) -- preferir SIEMPRE un titular real
    en español (el mas nuevo entre las fuentes ES). IMPORTANTE: esta funcion
    corre dentro de build_stories(), que se llama desde run_fast() (hilo
    RAPIDO -- nunca puede llamar a Ollama, invariante dura del proyecto) --
    por eso NUNCA pide una traduccion a la IA aca, aunque el pedido original
    lo mencionara como fallback ('si solo hay titulares en ingles'): ese caso
    no se da en la practica, porque el llamador (build_stories) solo activa
    'cobertura_global'/llama a esta funcion cuando YA hay fuentes en los dos
    idiomas (fuentes_es nunca esta vacio aca). Si algun dia hiciera falta
    traducir de verdad (fuentes_es vacio), tendria que hacerse en el hilo
    TRABAJADOR con su propio cache -- no implementado, ver Pendientes."""
    rep_es = max(fuentes_es, key=lambda f: f.get("date") or "")
    return rep_es["title"], False


def _ciudad_de_fuente(a):
    texto = a["title"] + " " + _quitar_dateline(a.get("summary") or "")
    ciudad_texto = "" if _es_enumeracion_ciudades(texto) else detect_city(texto)
    cf = a.get("ciudad_feed") or ""
    if cf:
        return ciudad_texto if (ciudad_texto and ciudad_texto != cf) else cf
    return ciudad_texto


def _ciudad_por_mayoria(ciudades):
    if not ciudades:
        return "", False
    conteo = {}
    for c in ciudades:
        conteo[c] = conteo.get(c, 0) + 1
    ciudad_top, n_top = max(conteo.items(), key=lambda kv: kv[1])
    discrepancia = len(conteo) > 1
    if n_top > len(ciudades) / 2:
        return ciudad_top, discrepancia
    return "", discrepancia


# Fase 18 (P0-2): horas desde la creacion para que una tarjeta diga "Nueva".
NUEVA_H = float(os.environ.get("MONITOR_NUEVA_H", "3"))

# Fase 18 (P0-3): senales de que una nota es NACIONAL (no de una ciudad),
# aunque la publique la seccion Guayaquil de un diario. Solo se mira el
# TITULAR, por frase o palabra completa.
NACIONAL_TERMS = ["ecuador", "ecuatorian", "noboa", "gobierno", "asamblea", "iva", "sri",
                  "cne", "presidente de la republica", "ministerio", "ministro", "ministra",
                  "a nivel nacional", "todo el pais", "codigo organico", "codigo de la ninez",
                  "decreto", "registro oficial", "corte constitucional", "fiscalia general",
                  "elecciones seccionales", "consulta popular", "banco central", "inec"]
_NACIONAL_RE = [re.compile(r"\b" + re.escape(norm(t)) + r"\b") for t in NACIONAL_TERMS]
# Subconjunto "fuerte": medidas de alcance nacional que siguen siendo
# nacionales aunque el titular nombre Guayaquil (caso real: "Daniel Noboa
# reduce el IVA al 8 % durante el feriado por la Independencia de Guayaquil").
NACIONAL_FUERTE = ["iva", "sri", "decreto", "registro oficial", "codigo organico",
                   "codigo de la ninez", "consulta popular", "elecciones seccionales",
                   "a nivel nacional", "todo el pais", "asamblea"]
_NACIONAL_FUERTE_RE = [re.compile(r"\b" + re.escape(norm(t)) + r"\b") for t in NACIONAL_FUERTE]


def es_nacional(titulo, fuerte=False):
    blob = norm(titulo)
    return any(p.search(blob) for p in (_NACIONAL_FUERTE_RE if fuerte else _NACIONAL_RE))


def build_stories(clusters):
    stories = []
    for c in clusters:
        arts = c["articles"]
        outlets = sorted({a["outlet"] for a in arts})
        outlets_intl = [o for o in outlets if o in INTL_OUTLETS]
        dates = [a["date"] for a in arts if a["date"]]
        newest = max(dates) if dates else None
        # Fase 18 (P0-2): representante = la nota FUNDADORA (la primera que
        # creo la historia), ya no la mas nueva. Antes, una historia vieja
        # "subia" con el titular de la ultima nota que se le pegaba y parecia
        # nueva; lo nuevo va en 'actualizaciones' con su hora.
        rep = None
        if c.get("fundador_titulo"):
            rep = next((a for a in arts if a["title"] == c["fundador_titulo"]), None)
        if rep is None:
            rep = min(arts, key=lambda a: a["date"] or dt.datetime.max.replace(tzinfo=dt.timezone.utc))
        seccion = rep["seccion"]
        blob = " ".join(a["title"] + " " + a["summary"] for a in arts)
        # Fase 14, bug real encontrado verificando en vivo: el fallback final
        # de ciudad (mas abajo, "ciudad = ... or detect_city(blob)") usaba
        # este mismo 'blob' crudo -- un dateline de agencia o una
        # enumeracion de ciudades en CUALQUIER fuente fusionada volvia a
        # colarse ahi aunque _ciudad_de_fuente()/_ciudad_por_mayoria() ya
        # hubieran dado el resultado correcto (vacio). blob_geo es la misma
        # union pero con el dateline de cada fuente limpio -- SOLO se usa
        # para decisiones de geografia, 'blob' sigue igual para
        # themes_for() (deteccion de tema, sin relacion con esto).
        blob_geo = " ".join(a["title"] + " " + _quitar_dateline(a.get("summary") or "") for a in arts)
        # AMBITO por TEMA de la nota (no por el medio): Ecuador vs Mundo.
        # EXCEPCION deliberada (Problema 5/1, tercera ronda): si el feed
        # mismo es la seccion "Gran Guayaquil" (o similar) de un diario, el
        # medio YA la clasifico como Guayaquil al publicarla ahi -- esa senal
        # es MAS confiable que buscar la palabra en el texto (una nota
        # hiperlocal puede no repetir el nombre de la ciudad). No contradice
        # "el ambito se decide por el tema, no por el medio" (la regla es
        # sobre secciones GENERALES tipo politica/mundo, no sobre una
        # seccion editorial que POR DEFINICION es de una ciudad puntual).
        # Problema 2: veto geografico -- se evalua sobre el titular/resumen
        # del REPRESENTANTE (rep), NO sobre el blob combinado de todas las
        # fuentes del grupo. Motivo (encontrado escribiendo la prueba con el
        # caso real): el blob combinado de un cluster mal armado (ver
        # Problema 1 -- p.ej. una nota de Sevilla agrupada por error con
        # notas reales de Guayaquil) SIEMPRE va a mencionar "Guayaquil"
        # porque alguna OTRA fuente del mismo grupo si es local -- el veto
        # sobre el blob entero nunca se disparaba, exactamente el bug que
        # se queria arreglar. Lo que Fernando ve en la tarjeta es
        # titular/resumen del REP (build_stories los arma de rep, mas
        # abajo) -- el veto tiene que mirar lo MISMO que se muestra, igual
        # criterio que ya usa el candado de la IA en get_ia/_apply (que
        # tambien compara contra s["titular"]+s["resumen"], es decir,
        # contra el rep, no contra un blob de grupo).
        rep_blob = rep["title"] + " " + (rep.get("summary") or "")
        ciudades_fuentes = [_ciudad_de_fuente(a) for a in arts]
        ciudad_mayoritaria, _discrepancia_ciudad = _ciudad_por_mayoria([c for c in ciudades_fuentes if c])
        # Fase 14, Paso 2 ("clasificacion con evidencia"): la discrepancia
        # cruda de arriba compara ciudades SIN normalizar por area
        # metropolitana -- Duran/Samborondon/Daule vs Guayaquil son la MISMA
        # area (ver GUAYAQUIL_AREA/_area_de) pero cuentan como "discrepancia"
        # si se comparan como strings crudos, marcando como ambiguos casos
        # que en realidad no lo son. Se recalcula aparte, normalizado, SOLO
        # para decidir que historias son candidatas al clasificador de
        # evidencia -- no cambia en nada el calculo de ciudad_mayoritaria/
        # ciudad de arriba.
        _, ciudad_discrepancia_real = _ciudad_por_mayoria(
            [_area_de(c) for c in ciudades_fuentes if c])
        veto = extranjero_sin_ecuador(_quitar_dateline(rep_blob)) or any(
            extranjero_sin_ecuador(a["title"] + " " + _quitar_dateline(a.get("summary") or "")) for a in arts)
        if veto:
            ambito = "internacional"
        elif ciudad_mayoritaria:
            ambito = "local"
        else:
            ambito = ambito_de(blob)
        es_local = ambito == "local"
        es_intl = ambito == "internacional"
        # ciudad_feed solo cuenta si sobrevivio al veto (es_local sigue
        # siendo True); si el veto la tumbo, no se usa como ciudad tampoco
        # -- evita el estado inconsistente "ambito=internacional pero
        # ciudad=Guayaquil".
        ciudad = (_area_de(ciudad_mayoritaria) if es_local and ciudad_mayoritaria else "") or \
                 (("" if _es_enumeracion_ciudades(blob_geo) else detect_city(blob_geo)) if es_local else "")
        # Fase 18 (P0-3): el titular que se muestra manda. Si nombra OTRA
        # ciudad/provincia (y no Gran Guayaquil), la historia no es de
        # Guayaquil; si es noticia NACIONAL (IVA, ley, Gobierno...), queda en
        # Ecuador sin ciudad aunque la haya publicado la seccion Guayaquil de
        # un diario.
        rep_texto_geo = rep["title"] + " " + _quitar_dateline(rep.get("summary") or "")
        rep_ciudades = ciudades_en(rep["title"])
        rep_gye = [c_ for c_ in rep_ciudades if c_ in GUAYAQUIL_AREA]
        if es_local and ciudad == "Guayaquil" and not rep_gye:
            otras = [c_ for c_ in rep_ciudades if c_ not in GUAYAQUIL_AREA]
            if otras:
                ciudad = otras[0]
            elif es_nacional(rep["title"]):
                ciudad = ""
        elif es_local and ciudad == "Guayaquil" and es_nacional(rep["title"], fuerte=True):
            ciudad = ""
        localidad = ""
        if ciudad == "Guayaquil":
            sub = [c_ for c_ in ciudades_en(rep_texto_geo) if c_ in GUAYAQUIL_AREA and c_ != "Guayaquil"]
            if sub and "Guayaquil" not in ciudades_en(rep["title"]):
                localidad = LOCALIDAD_NOMBRE.get(sub[0], sub[0])
        temas = themes_for(blob, seccion)
        # Base geografica por palabras clave (jerarquica): la IA la puede corregir
        # despues, con candado (ver _apply en get_ia).
        if es_local:
            geo = ["guayaquil", "ecuador"] if ciudad == "Guayaquil" else ["ecuador"]
        else:
            geo = ["internacional"]
        hours = (now_utc() - newest).total_seconds() / 3600 if newest else None
        creado = c.get("creado") or (min(dates) if dates else None)
        horas_creado = (now_utc() - creado).total_seconds() / 3600 if creado else None
        # se descarta de verdad solo mas alla de MAX_AGE_DAYS (columnas, notas
        # rezagadas). Entre FEED_FRESH_H y MAX_AGE_DAYS ya NO se descarta: queda
        # marcada "antigua" y la pestaña "Anteriores" del dashboard la muestra
        # aparte, para no perderla en silencio (ver FEED_FRESH_H arriba).
        if hours is not None and hours > MAX_AGE_DAYS * 24:
            continue
        antigua = hours is not None and hours > FEED_FRESH_H

        # PROMINENCIA: senales separadas (no colapsadas en la logica).
        n_outlets = len(outlets)
        n_articles = len(arts)
        recency_bonus = 0 if hours is None else max(0, 48 - hours) / 48  # 0..1
        score = n_outlets * 100 + n_articles * 10 + recency_bonus * 5
        image = next((a.get("image") for a in [rep] + arts if a.get("image")), "")

        # Fase 9, parte D3 (Problema 3): marco global ES/EN -- solo tiene
        # sentido para lo INTERNACIONAL (lo local de Ecuador es casi todo
        # español, no se toca). Si el cluster (ya fusionado por
        # _embed_multilingue_pendientes_registro, ver arriba) trae fuentes en
        # los dos idiomas, se arma un titular neutral preferido en español y
        # se listan las fuentes agrupadas por idioma para que Fernando vea
        # los dos angulos.
        fuentes_raw = list(arts)
        titular_final, es_traducido, cobertura_global, fuentes_por_idioma = rep["title"], False, False, None
        if es_intl:
            for a in fuentes_raw:
                a["_idioma"] = _detectar_idioma(a["title"])
            fuentes_es = [a for a in fuentes_raw if a["_idioma"] == "es"]
            fuentes_en = [a for a in fuentes_raw if a["_idioma"] == "en"]
            if fuentes_es and fuentes_en:
                cobertura_global = True
                titular_final, es_traducido = _titular_global(
                    [{"title": a["title"], "date": a["date"].isoformat() if a["date"] else None} for a in fuentes_es],
                    [{"title": a["title"], "date": a["date"].isoformat() if a["date"] else None} for a in fuentes_en])
                fuentes_por_idioma = {
                    "es": sorted([{"outlet": a["outlet"], "title": a["title"], "link": a["link"]} for a in fuentes_es],
                                 key=lambda f: f["title"]),
                    "en": sorted([{"outlet": a["outlet"], "title": a["title"], "link": a["link"]} for a in fuentes_en],
                                 key=lambda f: f["title"]),
                }

        stories.append({
            "titular": titular_final,
            "cobertura_global": cobertura_global,
            "es_traducido": es_traducido,
            "fuentes_por_idioma": fuentes_por_idioma,
            "seccion": seccion,
            "outlets": outlets,
            "n_outlets": n_outlets,
            "n_articles": n_articles,
            "internacional": es_intl,
            "es_local": es_local,
            "ambito": ambito,
            "ciudad": ciudad,
            # Fase 18 (P0-3): Samborondon/Duran/Daule cuentan como Gran
            # Guayaquil (ciudad="Guayaquil" para todos los filtros) pero
            # llevan su nombre aca para el chip de la tarjeta.
            "localidad": localidad,
            # Fase 18 (P0-2): "Nueva" solo si la historia se creo hace poco;
            # si solo se sumo una fuente, la tarjeta dice "Actualizacion".
            "creado": creado.isoformat() if creado else None,
            "horas_desde_creacion": round(horas_creado, 1) if horas_creado is not None else None,
            "es_nueva": bool(horas_creado is not None and horas_creado <= NUEVA_H),
            # Fase 14, Paso 2: True solo si las fuentes fusionadas mencionan
            # ciudades DISTINTAS (ya normalizadas por area metropolitana) --
            # la señal que usa get_geo_evidencia() para elegir que historias
            # son candidatas al clasificador con IA (nunca decide nada de
            # geografia por si sola, solo marca "esta vale la pena
            # verificar").
            "ciudad_discrepancia": bool(es_local and ciudad_discrepancia_real),
            "outlets_intl": outlets_intl,
            "temas": temas,
            "geo": geo,
            "resumen": (rep.get("summary") or "")[:200],
            "image": image,
            "newest": newest.isoformat() if newest else None,
            "hours": round(hours, 1) if hours is not None else None,
            "antigua": antigua,
            "score": round(score, 1),
            "recency": round(recency_bonus, 3),
            "demanda": None,   # se llena luego con Google Trends
            "interes": round(score, 1),  # se recalcula con demanda en run_once
            # ordenadas por fecha ASCENDENTE (la mas vieja primero): story_key()
            # (y su gemela en JS, storyKey()) usan fuentes[0].link como clave
            # estable de Guardadas/notas.json. Bug real posible (Problema 6,
            # sospecha de Fernando): si fuentes[0] fuera la nota MAS RECIENTE
            # (como quedaba antes, en el orden que arma cluster()), cada vez
            # que un medio nuevo cubre una historia en desarrollo la nota mas
            # nueva pasa a ser la [0] y la clave cambia -- una nota guardada
            # "se pierde" (queda huerfana bajo la clave vieja) justo en las
            # historias que mas vale la pena seguir. La fuente MAS VIEJA de un
            # grupo (la que arranco el cluster) casi no cambia entre corridas:
            # es la eleccion mas estable disponible sin agregar un id propio.
            "fuentes": sorted(
                ({"outlet": a["outlet"], "title": a["title"],
                  "link": a["link"], "date": a["date"].isoformat() if a["date"] else None}
                 for a in arts),
                key=lambda f: f["date"] or ""),
            # Problema 1 (2026-09-24): cuando agrupar_con_memoria() arma los
            # "clusters" desde historias_registro.json, cada uno trae sus
            # 'actualizaciones' (notas que sumaron informacion nueva sobre el
            # MISMO hecho, ver _es_actualizacion) -- se listan aca para que
            # el dashboard las muestre dentro de la misma tarjeta en vez de
            # crear una tarjeta nueva. cluster() (agrupamiento intra-pasada,
            # sin memoria, el que siguen usando test_cluster.py y afines)
            # nunca pone esta clave -- por eso el default es lista vacia.
            "actualizaciones": sorted(
                ({"outlet": u.get("outlet", ""), "titulo": u.get("titulo", ""),
                  "link": u.get("link", ""),
                  "fecha": u["fecha"].isoformat() if u.get("fecha") else None}
                 for u in c.get("actualizaciones", [])),
                key=lambda u: u["fecha"] or ""),
        })
    stories.sort(key=lambda s: s["score"], reverse=True)
    return stories


# ------------------------- evento en curso (Fase 18, P0-2.4) -------------------------
# Las lluvias de Guayaquil del 29-sep terminaron en ~10-18 tarjetas separadas
# (cada medio contaba un sector distinto: Av. de las Americas, el norte, la
# Atarazana, calzada mojada segun la ATM...). Ninguna comparte suficiente
# vocabulario con las otras para fusionarse -- y no deben fusionarse en el
# registro (son notas distintas), pero en la vista son UN evento. Esta capa
# las agrupa SOLO para mostrar: >=3 historias del mismo lugar (Gran
# Guayaquil cuenta como uno), del mismo tipo de hecho, el mismo dia local ->
# una historia madre con sub-actualizaciones por sector. No toca el registro
# ni gasta IA.
EVENTO_TIPOS = {
    "lluvias": ("Lluvias", ["lluvia", "lluvias", "inundacion", "inundaciones", "inunda", "anegad",
                             "aguacero", "acumulacion de agua", "calzada mojada", "marea alta",
                             "desborde", "desbordamiento"]),
    "cortes": ("Cortes de servicio", ["corte de agua", "cortes de agua", "corte de luz", "cortes de luz",
                                      "sin agua", "sin luz", "apagon", "corte electrico"]),
    "violencia": ("Violencia armada", ["balacera", "ataque armado", "disparos", "tiroteo", "sicariato"]),
    "protestas": ("Protestas", ["protesta", "planton", "marcha", "paro", "bloqueo de via"]),
}
_EVENTO_RE = {k: [re.compile(r"\b" + re.escape(norm(w))) for w in ws] for k, (_, ws) in EVENTO_TIPOS.items()}
EVENTO_MIN = int(os.environ.get("MONITOR_EVENTO_MIN", "3"))
_MESES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_SECTORES_EXTRA = {"Norte": ["norte de guayaquil", "el norte", "del norte"],
                   "Sur": ["sur de guayaquil", "el sur", "del sur"]}


def tipo_evento(titulo):
    blob = norm(titulo)
    for k, pats in _EVENTO_RE.items():
        if any(p.search(blob) for p in pats):
            return k
    return ""


def _sector_de(texto):
    blob = norm(texto)
    if alertas is not None:
        for nombre, terms in alertas.BARRIOS_GYE.items():
            if any(re.search(r"\b" + re.escape(norm(t)) + r"\b", blob) for t in terms):
                return nombre
    for nombre, terms in _SECTORES_EXTRA.items():
        if any(t in blob for t in terms):
            return nombre
    return ""


def _dia_local(iso):
    d = _iso_a_dt(iso) if isinstance(iso, str) else iso
    return (d - dt.timedelta(hours=5)).date() if d else None  # Guayaquil = UTC-5, sin horario de verano


def agrupar_eventos_en_curso(stories):
    """Devuelve una lista NUEVA de historias donde cada grupo de >=EVENTO_MIN
    historias locales (misma ciudad, mismo tipo de hecho, mismo dia local)
    se reemplaza por una historia madre. Las historias hijas quedan dentro,
    en 'sub_actualizaciones' (titular, hora, medios, sector, link)."""
    grupos = {}
    for i, s in enumerate(stories):
        if not s.get("es_local") or not s.get("ciudad") or s.get("evento_en_curso"):
            continue
        tipo = tipo_evento(s.get("titular", ""))
        dia = _dia_local(s.get("newest"))
        if not tipo or not dia:
            continue
        grupos.setdefault((s["ciudad"], tipo, dia), []).append(i)
    usados, madres = set(), []
    for (ciudad, tipo, dia), idx in grupos.items():
        if len(idx) < EVENTO_MIN:
            continue
        hijas = sorted((stories[i] for i in idx), key=lambda s: s.get("newest") or "")
        base = dict(max(hijas, key=lambda s: s.get("score", 0)))
        fuentes, links = [], set()
        for h in hijas:
            for f_ in h.get("fuentes", []):
                if f_.get("link") not in links:
                    links.add(f_.get("link"))
                    fuentes.append(f_)
        fuentes.sort(key=lambda f_: f_.get("date") or "")
        subs, sectores = [], []
        for h in hijas:
            sector = _sector_de(h.get("titular", "") + " " + (h.get("resumen") or ""))
            if sector and sector not in sectores:
                sectores.append(sector)
            subs.append({"titular": h.get("titular", ""), "fecha": h.get("newest"),
                         "outlets": h.get("outlets", []), "sector": sector,
                         "link": (h.get("fuentes") or [{}])[0].get("link", "")})
        outlets = sorted({o for h in hijas for o in h.get("outlets", [])})
        etiqueta = EVENTO_TIPOS[tipo][0]
        creados = [h.get("creado") for h in hijas if h.get("creado")]
        horas_c = [h.get("horas_desde_creacion") for h in hijas if h.get("horas_desde_creacion") is not None]
        base.update({
            "titular": "%s en %s — %d %s" % (etiqueta, ciudad, dia.day, _MESES_CORTO[dia.month - 1]),
            "resumen": "%d notas de %d medios%s." % (
                len(hijas), len(outlets), (". Sectores: " + ", ".join(sectores)) if sectores else ""),
            "fuentes": fuentes, "outlets": outlets, "n_outlets": len(outlets),
            "n_articles": sum(h.get("n_articles", 1) for h in hijas),
            "newest": max(h.get("newest") or "" for h in hijas) or None,
            "hours": min((h["hours"] for h in hijas if h.get("hours") is not None), default=None),
            "antigua": all(h.get("antigua") for h in hijas),
            "temas": sorted({t for h in hijas for t in h.get("temas", [])}),
            "score": max(h.get("score", 0) for h in hijas) + 10 * len(hijas),
            "interes": max(h.get("interes", 0) for h in hijas) + 10 * len(hijas),
            "actualizaciones": sorted(
                [u for h in hijas for u in h.get("actualizaciones", [])], key=lambda u: u.get("fecha") or ""),
            "sub_actualizaciones": subs,
            "creado": min(creados) if creados else None,
            "horas_desde_creacion": max(horas_c) if horas_c else None,
            "es_nueva": any(h.get("es_nueva") for h in hijas) and (max(horas_c) if horas_c else 0) <= NUEVA_H,
            "localidad": "",
            "evento_en_curso": {"tipo": tipo, "etiqueta": etiqueta, "lugar": ciudad, "dia": dia.isoformat(),
                                "n_historias": len(hijas), "sectores": sectores,
                                "desde": hijas[0].get("newest"), "hasta": hijas[-1].get("newest")},
        })
        usados.update(idx)
        madres.append(base)
    if not madres:
        return list(stories)
    out = [s for i, s in enumerate(stories) if i not in usados] + madres
    out.sort(key=lambda s: s.get("score", 0), reverse=True)
    return out


def _adjuntar_tweets_eventos(stories, max_tweets=6):
    """Fase 18 (P1-5.3): los tweets que trajo la busqueda reactiva de X
    (redes._pasada_eventos, hilo trabajador) se muestran DENTRO de la
    historia madre, con fecha y hora. Solo LEE x_cache.json (nunca red)."""
    xa = getattr(redes, "xapi", None) if redes is not None else None
    if xa is None:
        return
    for s in stories:
        if not s.get("evento_en_curso"):
            continue
        link = ((s.get("fuentes") or [{}])[0].get("link") or s.get("titular", ""))[:180]
        tw = xa.tweets_de_historia(link)
        if not tw:
            continue
        tw = sorted(tw, key=lambda t: xa.fecha_iso(t.get("createdAt", "")) or "", reverse=True)[:max_tweets]
        s["x_tweets"] = [{"texto": (t.get("text") or "")[:280], "autor": (t.get("author") or {}).get("userName", ""),
                          "fecha": xa.fecha_iso(t.get("createdAt", "")), "url": t.get("url", "")} for t in tw]


# ------------------------- internacionales con marco (Fase 18, P1-9) -------------------------
# 1303 de 1563 historias eran internacionales, muchas sin relacion con
# Ecuador ni con la region (conciertos en la CDMX, plantas de interior,
# vallenato). Dos capas: (1) farandula/espectaculos fuera, deterministico;
# (2) triaje con IA (perfil rapido, EN LOTE de 20 titulares por llamada) que
# decide si importa (global / region / ecuador / no) y escribe UNA linea de
# "por que importa". El hilo rapido solo LEE el cache. Tope INTL_MAX.
TRIAJE_INTL_PATH = os.path.join(HERE, "triaje_intl_cache.json")
INTL_MAX = int(os.environ.get("MONITOR_INTL_MAX", "150"))
TRIAJE_MAX_NEW = int(os.environ.get("MONITOR_TRIAJE_MAX", "60"))
TRIAJE_LOTE = 20
_RELEVANCIAS = ("global", "region", "ecuador", "no")
_FARANDULA_RE = re.compile(
    r"\b(concierto|conciertos|boletos|boleteria|preventa|gira mundial|festival|reality|farandula|"
    r"telenovela|cantante|reguetonero|influencer|streamer|paquetes vip|en vivo desde|horoscopo|"
    r"alfombra roja|premios grammy|premios oscar|serie de netflix|estreno de la pelicula)\b")


def es_farandula(titulo):
    return bool(_FARANDULA_RE.search(norm(titulo or "")))


def _cargar_triaje():
    try:
        with open(TRIAJE_INTL_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_PROMPT_TRIAJE = (
    "Eres editor de un medio de Guayaquil, Ecuador. Para cada titular internacional "
    "numerado decide su relevancia para un lector ecuatoriano:\n"
    "- \"global\": afecta al mundo (guerra, economia mundial, diplomacia grande).\n"
    "- \"region\": importa para America Latina.\n"
    "- \"ecuador\": tiene efecto directo en Ecuador.\n"
    "- \"no\": noticia local de otro pais, farandula, deportes, curiosidades, consumo.\n"
    "Para las que NO son \"no\", escribe \"marco\": UNA linea (max. 25 palabras) que diga POR QUE "
    "IMPORTA o QUE CONSECUENCIA puede tener -- NO repitas el titular con otras palabras. No inventes "
    "datos que el titular no dice; si no hay como explicar la consecuencia, usa relevancia \"no\".\n"
    "Mal (repite): \"Trump pregunto a Xi si quiere comprar armas estadounidenses.\"\n"
    "Bien: \"Una venta de armas a China cambiaria la tension comercial EE.UU.-China, que mueve "
    "precios de materias primas que exporta la region.\"\n"
    "Responde SOLO JSON: {\"items\": [{\"i\": 0, \"relevancia\": \"...\", \"marco\": \"...\"}]}\n\n%s")


def get_triaje_intl(stories):
    """Hilo TRABAJADOR (o corrida unica): clasifica las internacionales que
    faltan, en lotes. Devuelve texto de estado '+N nuevas'."""
    if ia is None or os.environ.get("MONITOR_NO_IA") == "1" or not ia.backend_listo():
        return "desactivado"
    cache = _cargar_triaje()
    pend = [s for s in stories if s.get("ambito") == "internacional" and not es_farandula(s.get("titular"))
            and story_key(s) not in cache]
    pend.sort(key=lambda s: s.get("interes") or 0, reverse=True)
    pend = pend[:TRIAJE_MAX_NEW]
    nuevas = 0
    for i in range(0, len(pend), TRIAJE_LOTE):
        lote = pend[i:i + TRIAJE_LOTE]
        lista = "\n".join("%d. %s" % (j, (s.get("titular") or "")[:160]) for j, s in enumerate(lote))
        r = ia._generar_json(_PROMPT_TRIAJE % lista, max_tokens=1600)
        if not r:
            break  # fallo transitorio / sin presupuesto: se reintenta en otra pasada
        for it in r.get("items") or []:
            try:
                j = int(it.get("i"))
            except (TypeError, ValueError):
                continue
            rel = it.get("relevancia")
            if not (0 <= j < len(lote)) or rel not in _RELEVANCIAS:
                continue
            marco = (it.get("marco") or "").strip()[:220]
            if rel != "no" and not marco:
                continue  # candado en codigo: relevante sin marco no se acepta
            # candado: un "marco" que solo repite el titular no aporta nada
            tt, tm = tokens(lote[j].get("titular", "")), tokens(marco)
            if tm and len(tt & tm) / len(tm) >= 0.6:
                marco = ""
            cache[story_key(lote[j])] = {"relevancia": rel, "marco": marco if rel != "no" else "",
                                         "titular": lote[j].get("titular", ""), "ts": now_utc().isoformat()}
            nuevas += 1
    if nuevas:
        if len(cache) > 4000:
            cache = dict(sorted(cache.items(), key=lambda kv: kv[1].get("ts", ""))[-3000:])
        tmp = TRIAJE_INTL_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, TRIAJE_INTL_PATH)
    return "+%d nuevas (triaje internacional, pendientes: %d)" % (nuevas, max(0, len(pend) - nuevas))


def aplicar_triaje_intl(stories, modo_lectura=True):
    """Filtra y marca las internacionales: farandula fuera, 'no' del triaje
    fuera, 'marco' pegado, y tope INTL_MAX (primero las ya clasificadas como
    relevantes, despues las pendientes, por interes). Lo local no se toca."""
    cache = _cargar_triaje()
    orden = {"ecuador": 0, "global": 1, "region": 2}
    intl = []
    for s in stories:
        if s.get("ambito") != "internacional":
            continue
        if es_farandula(s.get("titular")):
            continue
        t = cache.get(story_key(s))
        if t:
            if t.get("relevancia") == "no":
                continue
            s["relevancia_intl"] = t.get("relevancia")
            s["marco"] = t.get("marco", "")
        intl.append(s)
    intl.sort(key=lambda s: (orden.get(s.get("relevancia_intl"), 3), -(s.get("interes") or 0)))
    quedan = {id(s) for s in intl[:INTL_MAX]}
    return [s for s in stories if s.get("ambito") != "internacional" or id(s) in quedan]


# ------------------------- contraste rediseñado (Fase 18, P2-11) -------------------------
CONTRASTE_CLASE_PATH = os.path.join(HERE, "contraste_clase_cache.json")
CONTRASTE_CLASE_MAX = int(os.environ.get("MONITOR_CONTRASTE_CLASE_MAX", "40"))


def _boletines_oficiales():
    """Items de oficial_cache.json (Asamblea, Registro Oficial, INEC, BCE)
    -- solo lectura, lo que el trabajador ya bajo."""
    ruta = getattr(oficial, "OFICIAL_CACHE_PATH", os.path.join(HERE, "oficial_cache.json")) if oficial else \
        os.path.join(HERE, "oficial_cache.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            c = json.load(f)
    except Exception:
        return []
    return [dict(it, fuente=url) for url, v in c.items() if isinstance(v, dict) for it in (v.get("items") or [])]


def _cargar_clases_contraste():
    try:
        with open(CONTRASTE_CLASE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def aplicar_contraste(stories):
    """Hilo rapido: contraste de cada historia con lo ya calculado. El
    veredicto viejo (IA, medio contra medio) queda en 'veredicto_ia'; el
    nuevo pasa a 'veredicto' (estados hallazgo/documento_oficial/
    corroborado_medios/sin_hallazgo)."""
    if contraste is None:
        return
    bol = _boletines_oficiales()
    clases = _cargar_clases_contraste()
    for s in stories:
        if s.get("veredicto") and "veredicto_ia" not in s and s["veredicto"].get("estado") in (
                "coincide", "contradice", "sin_datos", "pendiente"):
            s["veredicto_ia"] = s["veredicto"]
        try:
            s["veredicto"] = contraste.evaluar(s, bol, clase_ia=(clases.get(story_key(s)) or {}).get("clase"))
        except Exception as e:
            s["veredicto"] = {"estado": "sin_hallazgo", "clase": "", "texto": "error: %s" % e, "citas": []}


_PROMPT_CLASE = (
    "Clasifica cada titular de Ecuador segun QUE AFIRMA:\n"
    "- \"acto_oficial\": una ley, decreto, contrato, cifra oficial, corte programado u obra publica.\n"
    "- \"declaracion\": algo que DIJO una persona o institucion.\n"
    "- \"hecho\": un suceso (crimen, accidente, clima, protesta).\n"
    "Responde SOLO JSON: {\"items\": [{\"i\": 0, \"clase\": \"...\"}]}\n\n%s")


def get_clase_contraste(stories):
    """Trabajador (Fase 18, P2-11): clasificacion de la afirmacion con Gemini
    (perfil rapido, lotes de 20) para las historias LOCALES; cachea por
    story_key. contraste.evaluar usa esto si existe, si no sus reglas."""
    if contraste is None or ia is None or os.environ.get("MONITOR_NO_IA") == "1" or not ia.backend_listo():
        return "desactivado"
    cache = _cargar_clases_contraste()
    pend = [s for s in sorted(stories, key=_prioridad_cupo_ia)
            if s.get("es_local") and story_key(s) not in cache][:CONTRASTE_CLASE_MAX]
    nuevas = 0
    for i in range(0, len(pend), 20):
        lote = pend[i:i + 20]
        r = ia._generar_json(_PROMPT_CLASE % "\n".join("%d. %s" % (j, (s.get("titular") or "")[:160])
                                                        for j, s in enumerate(lote)), max_tokens=600)
        if not r:
            break
        for it in r.get("items") or []:
            try:
                j = int(it.get("i"))
            except (TypeError, ValueError):
                continue
            if 0 <= j < len(lote) and it.get("clase") in contraste.CLASES:
                cache[story_key(lote[j])] = {"clase": it["clase"], "ts": now_utc().isoformat()}
                nuevas += 1
    if nuevas:
        if len(cache) > 4000:
            cache = dict(sorted(cache.items(), key=lambda kv: kv[1].get("ts", ""))[-3000:])
        tmp = CONTRASTE_CLASE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, CONTRASTE_CLASE_PATH)
    return "+%d nuevas (clase de contraste, pendientes: %d)" % (nuevas, max(0, len(pend) - nuevas))


# ------------------------- demanda (Google Trends) -------------------------

TREND_TTL = 3 * 3600  # no consultar Trends mas seguido que cada 3 horas
TREND_GEO = os.environ.get("MONITOR_TREND_GEO", "EC")
TREND_CACHE = os.path.join(HERE, "trends_cache.json")

def _trends_demand(themes):
    """Intenta Google Trends. Devuelve (vals, tend, err|None)."""
    if trends is None or os.environ.get("MONITOR_NO_TRENDS") == "1":
        return {}, {}, "desactivado"
    term_of = {t: TREND_TERMS.get(t, t) for t in themes}
    terms = list(dict.fromkeys(term_of.values()))
    data_term, err = {}, None
    for i in range(0, len(terms), 5):
        if i:
            time.sleep(2)
        r = trends.interest_over_time(terms[i:i + 5], geo=TREND_GEO)
        data_term.update(r)
        if getattr(trends, "last_error", None):
            err = trends.last_error
            break
    vals, tend = {}, {}
    for t in themes:
        d = data_term.get(term_of[t])
        if d:
            vals[t] = d.get("avg", 0)
            tend[t] = {"v": d.get("series", []), "t": d.get("times", [])}
    return vals, tend, err

def _wiki_demand(themes):
    """Vistas de Wikipedia como interes estable. Normaliza a 0-100 entre temas."""
    if wiki is None:
        return {}, {}
    art_of = {t: WIKI_TERMS.get(t) for t in themes if WIKI_TERMS.get(t)}
    raw = wiki.interest(art_of)  # {tema: {avg, series, times}}
    if not raw:
        return {}, {}
    mx = max((d["avg"] for d in raw.values()), default=0) or 1
    vals, tend = {}, {}
    for t, d in raw.items():
        vals[t] = round(100 * d["avg"] / mx)
        tend[t] = {"v": d["series"], "t": d["times"]}
    return vals, tend

def get_demand(themes, modo_lectura=False):
    """Devuelve (demanda, tendencias, estado, fuente).
    Usa Google Trends si responde; si falla o trae poco, cae a Wikipedia
    (estable, no se bloquea). Cachea el resultado por TREND_TTL.

    Estado HONESTO (Frente C): antes, 'estado' era "ok (Google Trends)" a
    secas incluso con exito PARCIAL (ej. Trends corto a mitad de camino por
    un 429 y trajo 10 de 19 temas, sin caer a Wikipedia porque 10 no es
    "menos de la mitad") -- no se notaba que faltaban 9 temas. Ahora dice
    cuantos temas de cuantos, y si Trends corto por un error, cual fue.

    modo_lectura=True (hilo rapido, Parte C, ver 'Pendiente conocido' /
    task #17): SOLO lee trends_cache.json, nunca llama a Trends/Wikipedia.
    Si el cache vencio igual se usa (mejor un dato unas horas viejo que
    bloquear el arranque del feed -- bug real: un vencimiento de cache de
    GDELT, la misma familia de llamada, llego a tardar 559s)."""
    cache = {}
    try:
        with open(TREND_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass

    # 'intentados'/'detalle' viajan DENTRO del cache (mismo patron que
    # gdelt_cache.json, ver get_gdelt): asi el hilo rapido puede mostrar el
    # mismo estado honesto ("3/5 temas, Trends corto por HTTP 429") leyendo
    # el cache, en vez de un "cache (Google Trends)" plano que no dice si la
    # ultima vez el trabajador consiguio todos los temas o solo una parte.
    #
    # BUG REAL (Problema 3, mismo patron que get_gdelt): 'vals'/'tend' se
    # pisaban ENTEROS cada corrida con lo que se consiguio ESA vez -- si
    # Trends fallaba a medias, un tema que si tenia dato bueno de la corrida
    # anterior desaparecia igual. Ahora se MERGEA por tema (last-known-good),
    # con 'vals_ts' guardando cuando se refresco cada tema.
    def _estado_cache(prefijo="cache"):
        vals_ts = cache.get("vals_ts") or {}
        n_ok = len(cache.get("vals") or {})
        n_tot = cache.get("intentados", n_ok)  # cache viejo sin el campo: mejor no inventar un total mayor
        edad = _edad_mas_vieja(vals_ts)
        s = "%s (%s, %d temas acumulados/%d intentados esta pasada)%s" % (
            prefijo, cache.get("fuente", "?"), n_ok, n_tot, cache.get("detalle", ""))
        if edad is not None:
            s += " — el mas viejo: hace %s" % _fmt_horas(edad)
        return s

    if (time.time() - cache.get("ts", 0) < TREND_TTL
            and cache.get("vals") and cache.get("tend")):  # exige curvas, no solo numeros
        return cache["vals"], cache["tend"], _estado_cache(), cache.get("fuente", "?")

    if modo_lectura:
        if cache.get("vals"):
            return (cache["vals"], cache.get("tend", {}), _estado_cache("cache vencido"),
                    cache.get("fuente", "?"))
        return {}, {}, "esperando primera pasada del trabajador", "?"

    # 1) Google Trends
    vals, tend, err = _trends_demand(themes)
    fuente = "Google Trends"
    werr = None
    # 2) si Trends trajo menos de la mitad de los temas, usa Wikipedia
    if len(vals) < max(1, len(themes) // 2):
        wv, wt = _wiki_demand(themes)
        werr = getattr(wiki, "last_error", None) if wiki else "sin modulo wiki"
        if len(wv) >= len(vals):
            vals, tend, fuente = wv, wt, "Wikipedia"

    if not vals:
        motivo = "Trends: %s | Wikipedia: %s" % (err or "sin datos", werr or "sin datos")
        return (cache.get("vals", {}), cache.get("tend", {}),
                "error (%s)" % motivo, cache.get("fuente", "?"))
    detalle = " (Trends corto por: %s)" % err if (fuente == "Google Trends" and err) else ""
    ahora = time.time()
    n_esta_pasada = len(vals)
    merged_vals = dict(cache.get("vals") or {}); merged_vals.update(vals)
    merged_tend = dict(cache.get("tend") or {}); merged_tend.update(tend)
    vals_ts = dict(cache.get("vals_ts") or {})
    for t in vals:
        vals_ts[t] = ahora
    vals, tend = merged_vals, merged_tend
    try:
        with open(TREND_CACHE, "w", encoding="utf-8") as f:
            json.dump({"ts": ahora, "geo": TREND_GEO, "vals": vals, "tend": tend, "vals_ts": vals_ts,
                       "fuente": fuente, "intentados": len(themes), "detalle": detalle},
                      f, ensure_ascii=False)
    except Exception:
        pass
    estado = "ok (%s, %d/%d temas esta pasada, %d acumulados)%s" % (
        fuente, n_esta_pasada, len(themes), len(vals), detalle)
    return vals, tend, estado, fuente


# ------------------------- agente de IA local (Ollama) -------------------------

IA_CACHE = os.path.join(HERE, "ia_cache.json")
IA_MAX_NEW = int(os.environ.get("MONITOR_IA_MAX", "80"))  # analisis nuevos por corrida (resto usa cache)
IA_MODEL = os.environ.get("MONITOR_IA_MODEL", "")
IA_TEMA_MIN = float(os.environ.get("MONITOR_IA_TEMA_MIN", "0.6"))  # umbral de confianza para temas
# Interpretacion editorial (ia.interpretar, llamada APARTE de analizar -- ver
# bug real grande arreglado 2026-09-23: esta llamada existia en ia.py desde
# el 2026-09-22 pero monitor.py nunca la invocaba, asi que "interp" nunca se
# llenaba de verdad). Acotada aparte de IA_MAX_NEW porque cada intento puede
# hacer HASTA DOS llamadas a Ollama (interpretar() reintenta si el primer
# intento sigue literal).
IA_INTERP_MAX = int(os.environ.get("MONITOR_IA_INTERP_MAX", "80"))
IA_INTERP_VERSION = 2


# Fase 9 (Problema B1) -- BUG GRAVE confirmado con 14 tarjetas locales
# revisadas a mano: en 6, la lectura de IA describia OTRA noticia (lluvias en
# Guayaquil -> lectura sobre ONGs en Ceuta; cortes de luz -> "presionar a
# manifestantes"; el C-5M en Guayaquil -> el operativo de Mocoli; marea en
# puertos -> precio del dolar; Santa Elena -> un bus accidentado). Causa
# raiz: get_ia()/get_contexto()/get_veredicto()/get_factcheck() cachean por
# fuentes[0].link -- una clave ESTABLE a proposito (para que saved.json/
# notas.json sigan apuntando a la misma historia aunque el feed la
# reprocese) -- pero calculan el resultado UNA sola vez, con el titular
# representante que la historia tenia EN ESE MOMENTO. Cuando la historia
# suma medios y el representante cambia (ver Problema A3, "deriva por
# rep_titulo"), la tarjeta muestra el titular NUEVO con la lectura/contexto/
# veredicto VIEJO -- y con la deriva de agrupamiento de A3 encima, el
# resultado puede terminar describiendo un hecho distinto por completo.
# Arreglo: la clave de cache sigue siendo fuentes[0].link (no cambia nada de
# saved.json/notas.json), pero cada entrada cacheada guarda ademas una
# HUELLA (hash barato, no cripto) del titular/resumen representante + la
# cantidad de medios en el momento de calcularla. Si la huella actual no
# coincide con la guardada (cambio el representante o se sumaron medios), el
# resultado cacheado se trata como DESACTUALIZADO: en el hilo trabajador
# compite de nuevo por el cupo de la pasada (se recalcula, no se descarta a
# ciegas); en el hilo rapido (modo_lectura) se sigue mostrando lo viejo
# (mejor eso que "analizando..." de nuevo) pero marcado explicitamente para
# que el dashboard diga "lectura desactualizada" en vez de presentarlo como
# si describiera la nota de hoy.
def _huella_contenido(s):
    rep = s.get("titular", "") + "|" + s.get("resumen", "") + "|" + str(len(s.get("fuentes") or []))
    return hashlib.sha1(rep.encode("utf-8", "ignore")).hexdigest()[:12]


# Fase 9 (Problema B2): "solo 623 de 2480 historias tienen lectura IA" -- con
# cupo fijo por pasada (IA_MAX_NEW/IA_INTERP_MAX/CONTEXTO_MAX_NEW/
# VEREDICTO_MAX_NEW), el orden de "interes" a secas dejaba competir notas
# internacionales de UN SOLO medio (ruido -- medido: 744 fuentes de Infobae,
# 271 de Semana) contra lo local por el mismo cupo. Se usa como orden de
# consumo del cupo en get_ia/get_contexto/get_veredicto (nunca cambia el
# orden real de "stories" que ve el dashboard, solo en que orden se GASTA el
# cupo de esta pasada): local primero y, dentro de cada grupo, se conserva
# el orden de interes de siempre (sort ESTABLE de Python) -- una
# internacional de 1 solo medio queda al final del cupo, aunque su interes
# calculado fuera alto.
def _prioridad_cupo_ia(s):
    # Fase 18 (P2-10): Guayaquil -> resto de Ecuador -> internacional
    # (con el ruido de 1 solo medio al final).
    if s.get("ciudad") == "Guayaquil":
        return (0, 0)
    if s.get("es_local"):
        return (1, 0)
    return (2, 1 if len(s.get("fuentes") or []) <= 1 else 0)


# Fase 18 (P2-10): cobertura. IA en 87/1563 y contexto en 34/1563 historias.
# El perfil PROFUNDO cuesta ~10x el rapido (precios de ia.py), asi que se
# reserva para las TOP_PROFUNDO locales mas importantes; el resto de lo local
# (Guayaquil primero, despues Ecuador) se cubre con el perfil RAPIDO. Lo
# internacional solo recibe lectura si sobra cupo.
TOP_PROFUNDO = int(os.environ.get("MONITOR_TOP_PROFUNDO", "10"))


def _claves_top_profundo(stories):
    locales = sorted([s for s in stories if s.get("es_local")], key=lambda s: -(s.get("interes") or 0))
    return {story_key(s) for s in locales[:TOP_PROFUNDO]}


def _perfil_para(s, top_keys):
    if ia is None:
        return None
    return (getattr(ia, "PERFIL_PROFUNDO", "profundo") if story_key(s) in top_keys
            else getattr(ia, "PERFIL_RAPIDO", "rapido"))

def get_ia(stories, modo_lectura=False):
    """Usa Ollama para revisar/corregir el etiquetado por palabras clave (temas y
    geografia) y dar interpretacion a las historias top. Cachea por nota (una vez
    por historia). Si Ollama no esta, no toca nada (se queda la clasificacion por
    palabras clave).

    modo_lectura=True (hilo rapido, Parte C): SOLO lee lo que el hilo
    trabajador ya dejo en ia_cache.json y lo pega en cada historia -- NUNCA
    llama a Ollama. El feed no debe esperar nunca al modelo; una historia sin
    cache todavia se publica igual, sin interpretacion (la tarjeta muestra
    'analizando...')."""
    if ia is None or os.environ.get("MONITOR_NO_IA") == "1":
        return "desactivado"
    cache = {}
    try:
        with open(IA_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass

    def _apply(s, r):
        # Eje tematico: catalogo fijo (feeds.KEYWORDS). La IA solo puede QUITAR
        # categorias que ya puso el etiquetado por palabras clave, nunca agregar
        # una nueva (decision del proyecto). El prompt ya se lo pide, pero ademas
        # se pone candado aqui: aunque el modelo desobedezca y devuelva una
        # categoria fuera de las pre-etiquetadas, se descarta igual. De lo que
        # queda, solo se acepta lo que pasa el umbral de confianza; si nada pasa,
        # "otros".
        temas_r = r.get("temas")
        if temas_r:
            temas_kw = set(s.get("temas") or [])
            kept = sorted({t["cat"] for t in temas_r
                           if t.get("score", 0) >= IA_TEMA_MIN and t["cat"] in temas_kw})
            # BUG REAL (Fase 2, 2026-09-23/24, caso real reproducido en vivo:
            # "Ejercito inhabilita... mineria ilegal en Putumayo", que
            # themes_for() ya clasificaba bien como Ambiente): la IA a veces
            # propone una categoria que NO se solapa NADA con lo que las
            # keywords ya habian detectado (en este caso "Policia/Militar" en
            # vez de "Ambiente", score 1.0) -- el candado de arriba la
            # descarta correctamente (no esta en temas_kw), pero como no
            # queda NINGUNA categoria en comun, 'kept' quedaba vacio y la
            # nota caia en 'otros'. El candado dice "la IA solo puede QUITAR
            # categorias", no "puede vaciar todo sin dejar nada" -- que la IA
            # no reconfirme ninguna de las categorias de keywords no es lo
            # mismo que decir que esas categorias esten mal. Si no queda
            # ninguna en comun, se preserva la clasificacion de keywords tal
            # cual en vez de perderla en 'otros'.
            s["temas"] = kept or sorted(temas_kw) or [ia.TEMA_OTROS]

        # Eje geografico (jerarquico): guayaquil implica ecuador. La IA puede
        # mandar a internacional sin condicion, pero solo puede marcar
        # ecuador/guayaquil si el texto realmente tiene esa senal (candado, igual
        # que antes): si no, se ignora y queda la clasificacion por palabras clave.
        geo = r.get("geo") or []
        # Fase 14, bug real encontrado verificando en vivo: este candado
        # usaba detect_city(texto) SIN limpiar el dateline de agencia
        # ("Guayaquil (Ecuador), 28 sep (EFE).-") ni chequear enumeracion de
        # ciudades ("aeropuertos de Quito, Guayaquil y Cuenca") -- mismos
        # dos arreglos que build_stories() ya tiene (ver _quitar_dateline/
        # _es_enumeracion_ciudades), pero como este candado corre DESPUES y
        # lee 'geo' desde el cache de la IA (que puede venir de ANTES de
        # este cambio), volvia a pisar el ciudad="" correcto que
        # build_stories() ya habia calculado en la misma pasada.
        texto = s.get("titular", "") + " " + _quitar_dateline(s.get("resumen", "") or "")
        es_enumeracion = _es_enumeracion_ciudades(texto)
        # Problema 2 (2026-09-24): veto geografico -- ni siquiera la IA
        # puede marcar local/guayaquil si el texto nombra un lugar
        # extranjero y NINGUNO de Ecuador (mismo criterio que build_stories,
        # ver extranjero_sin_ecuador). Se evalua ANTES que el resto del
        # candado para que ni "guayaquil" ni "ecuador" puedan pasar en ese
        # caso, sin importar que tan convencida este la IA.
        veto = extranjero_sin_ecuador(texto)
        if "guayaquil" in geo and not es_enumeracion and detect_city(texto) == "Guayaquil" and not veto:
            s["geo"] = ["guayaquil", "ecuador"]
            s["ciudad"] = "Guayaquil"
            s["ambito"], s["es_local"], s["internacional"] = "local", True, False
        elif "ecuador" in geo and is_ecuador(texto) and not veto:
            s["geo"] = ["ecuador"]
            s["ambito"], s["es_local"], s["internacional"] = "local", True, False
        # BUG REAL (Fase 2, pendiente ya documentado, "asimetria en el candado
        # de geografia"): el candado de arriba exige respaldo real de texto
        # (detect_city/is_ecuador) para aceptar "local"/"guayaquil", pero
        # "internacional" se aceptaba SIN ninguna condicion -- caso real ya
        # visto: "Estados Unidos intercepta embarcacion de Ecuador" quedaba
        # en Internacional aunque el texto menciona "Ecuador" explicitamente.
        # Mismo criterio ahora en los dos sentidos: si el texto SI tiene
        # señal real de Ecuador, "internacional" tampoco se acepta a ciegas.
        elif "internacional" in geo and (veto or not is_ecuador(texto)):
            s["geo"] = ["internacional"]
            s["ciudad"] = ""
            s["ambito"], s["es_local"], s["internacional"] = "internacional", False, True
        elif veto:
            # el propio texto tiene veto (extranjero sin Ecuador) pero la IA
            # ni siquiera propuso "internacional" -- se fuerza igual, es un
            # invariante de codigo, no depende de que la IA lo pida.
            s["geo"] = ["internacional"]
            s["ciudad"] = ""
            s["ambito"], s["es_local"], s["internacional"] = "internacional", False, True
        # si nada de lo anterior aplica (geo vacio, ecuador/guayaquil sin senal
        # real en el texto, o internacional pero el texto SI menciona Ecuador),
        # se deja el ambito ya calculado por palabras clave

        # BUG REAL grave (reportado por Fernando de nuevo el 2026-09-23,
        # "los contextos siguen literales" -- confirmado con datos reales:
        # 'Noticia internacional sobre reunion de primer ministro britanico
        # con Trump en la ONU'): esta linea leia r.get("interpretacion", "")
        # -- una clave que `ia.analizar()` YA NO DEVUELVE desde el arreglo
        # documentado como hecho el 2026-09-22 (la interpretacion se separo
        # a `ia.interpretar()`, una llamada aparte con filtro `es_literal`).
        # Esas dos funciones SI estaban bien escritas en ia.py, pero
        # `monitor.py` nunca llegó a llamar a `ia.interpretar()` en ningún
        # lado -- el arreglo se quedó a medio wire. En la práctica
        # `s["ia"]` salía casi siempre vacío para notas NUEVAS, y para las
        # viejas (cacheadas en ia_cache.json de ANTES del 2026-09-22)
        # arrastraba el texto LITERAL de la version vieja de analizar()
        # (que si pedia "interpretacion" en el mismo JSON de clasificar).
        # Ahora se lee de "interp" (la clave que si llena la seccion de
        # abajo, ver el loop nuevo) -- nunca la "interpretacion" vieja.
        s["ia"] = r.get("interp") or ""

    if modo_lectura:
        n, desactualizadas = 0, 0
        for s in stories:
            f0 = (s.get("fuentes") or [{}])[0]
            key = (f0.get("link") or s["titular"])[:180]
            if key in cache:
                entry = cache[key]
                _apply(s, entry); n += 1
                # Fase 9 (Problema B1): mejor mostrar lo viejo marcado como
                # tal que "analizando..." de nuevo -- pero el dashboard
                # necesita saber que puede no describir la nota de hoy.
                if entry.get("_huella") and entry["_huella"] != _huella_contenido(s):
                    s["ia_desactualizada"] = True
                    desactualizadas += 1
        extra = ", %d desactualizadas" % desactualizadas if desactualizadas else ""
        return "cache (%d/%d%s)" % (n, len(stories), extra)

    if not ia.disponible(IA_MODEL):
        return "error: %s" % (getattr(ia, "last_error", None) or "Ollama no responde")

    orden_cupo = sorted(stories, key=_prioridad_cupo_ia)  # ver comentario en _prioridad_cupo_ia (Problema B2)
    top_keys = _claves_top_profundo(stories)

    new, new_interp, err = 0, 0, None
    for s in orden_cupo:  # local primero, ruido internacional de 1 medio al final del cupo
        f0 = (s.get("fuentes") or [{}])[0]
        key = (f0.get("link") or s["titular"])[:180]
        entry = cache.get(key)
        huella = _huella_contenido(s)
        # Fase 9 (Problema B1): una entrada vieja cuya huella ya no coincide
        # con el titular/resumen/cantidad de medios actual compite de nuevo
        # por el cupo de la pasada -- no se descarta a ciegas (ya tiene un
        # analisis, aunque viejo), pero tampoco se sigue mostrando como si
        # describiera la nota de hoy sin al menos intentar refrescarla.
        desactualizada = entry is not None and entry.get("_huella") and entry["_huella"] != huella
        if entry is None or desactualizada:
            if new >= IA_MAX_NEW:
                if entry is not None:
                    _apply(s, entry)
                    s["ia_desactualizada"] = True
                continue
            r = ia.analizar(s["titular"], s.get("resumen", ""), temas_kw=s.get("temas"), forzado=IA_MODEL)
            if r:
                entry = cache[key] = r; new += 1
            elif getattr(ia, "last_error", None):
                err = ia.last_error; break
            else:
                continue
        entry["_huella"] = huella  # se acaba de (re)calcular con el contenido de HOY -- ya no esta desactualizada
        s["ia_desactualizada"] = False
        _apply(s, entry)
        # Interpretacion editorial: separada de temas/geo a proposito (ver
        # IA_INTERP_MAX arriba). "interp_v" distingue el resultado de ESTE
        # prompt/formato del que pudiera haber quedado de una version vieja
        # -- si algun dia el prompt de interpretar() cambia de nuevo, subir
        # IA_INTERP_VERSION vuelve a pedirla en vez de confiar en la vieja.
        # BUG REAL (2026-09-23, quinta pasada): antes se forzaba
        # forzado=IA_MODEL (el modelo rapido) siempre -- eso pisaba
        # cualquier intento de usar un modelo mejor para la interpretacion
        # (INTERP_MODEL/elegir_modelo_chat() en ia.py nunca podian ganar).
        # Ahora NO se fuerza nada: ia.interpretar() elige su propio modelo
        # (por defecto el pesado, monitor-critico, con fallback automatico).
        if entry.get("interp_v") != IA_INTERP_VERSION:
            if new_interp >= IA_INTERP_MAX:
                continue
            perfil = _perfil_para(s, top_keys)
            if perfil == getattr(ia, "PERFIL_PROFUNDO", "profundo"):
                texto = ia.interpretar(s["titular"], s.get("resumen", ""))
            else:
                texto = ia.interpretar(s["titular"], s.get("resumen", ""), perfil=perfil)
            if texto is not None:  # None = fallo de Ollama; "" = literal tras 2 intentos (valido, se cachea igual)
                entry["interp"] = texto
                entry["interp_v"] = IA_INTERP_VERSION
                s["ia"] = texto
                new_interp += 1
    try:
        with open(IA_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    modelo = getattr(ia, "_model", "?")
    return ("error: %s" % err) if err and not new else (
        "ok (%s, +%d nuevas, +%d interpretaciones)" % (modelo, new, new_interp))


# ------------------------- registro de entidades en el tiempo -------------------------
# Registro liviano (no es un cache recalculable, ver saved.json): que entidad
# aparecio, cuando, y en que historia. Sirve para mostrar "tambien aparecio el
# <fecha> en <titular>" aunque la entidad NUNCA tenga pagina de Wikipedia (fue
# justo el caso de Xavier Jordan -- un capturado reciente, sin pagina propia,
# pero cuyo nombre ya habia salido antes en otras notas de este monitor).
# Se llena con TODOS los candidatos que extrae la IA por historia (verificados
# o no en Wikipedia): identificar quien es "de verdad" no hace falta para esto,
# solo que el mismo nombre ya salio antes.

ENTITIES_PATH = os.path.join(HERE, "entities.json")
ENTITIES_MAX_POR_ENTIDAD = 20  # apariciones guardadas por entidad (se recorta lo mas viejo)

def _entidad_key(nombre):
    return norm(nombre or "")

def registrar_apariciones(s, nombres):
    """Anota que cada nombre de 'nombres' aparecio en la historia 's' (fecha +
    titular + link). No lanza ni bloquea la corrida si el archivo esta corrupto
    o no se puede escribir -- es un registro secundario, no una fuente de
    verdad critica."""
    nombres = [n for n in (nombres or []) if n and n.strip()]
    if not nombres:
        return
    try:
        with open(ENTITIES_PATH, encoding="utf-8") as f:
            reg = json.load(f)
    except Exception:
        reg = {}
    f0 = (s.get("fuentes") or [{}])[0]
    link = f0.get("link", "")
    fecha = s.get("newest") or now_utc().isoformat()
    titular = s.get("titular", "")
    for nombre in nombres:
        key = _entidad_key(nombre)
        if not key:
            continue
        lst = reg.setdefault(key, [])
        # evita duplicar la misma historia para la misma entidad (re-procesos,
        # o dos candidatos de la IA que normalizan al mismo nombre)
        if not any(x.get("link") == link for x in lst if link):
            lst.append({"nombre": nombre, "fecha": fecha, "titular": titular, "link": link})
        reg[key] = lst[-ENTITIES_MAX_POR_ENTIDAD:]
    try:
        with open(ENTITIES_PATH, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False)
    except Exception:
        pass

def apariciones_previas(nombre, excluir_link=""):
    """Apariciones ANTERIORES de 'nombre' en entities.json (mas recientes
    primero), sin contar la historia actual. Union con Wikipedia/GDELT: esto
    es un hecho sobre ESTE monitor (ya la vimos antes), no una pista externa
    -- pero el match es por nombre normalizado, asi que dos personas
    homonimas se mezclarian (limitacion aceptada, riesgo bajo para nombres
    propios completos)."""
    try:
        with open(ENTITIES_PATH, encoding="utf-8") as f:
            reg = json.load(f)
    except Exception:
        return []
    lst = reg.get(_entidad_key(nombre), [])
    out = [a for a in lst if not (excluir_link and a.get("link") == excluir_link)]
    out.sort(key=lambda a: a.get("fecha") or "", reverse=True)
    return out


# ------------------------- Parte B: contexto REAL por entidad -------------------------
# El codigo recupera (Wikipedia, GDELT); el modelo SOLO redacta con eso.
# Flujo por historia: 1) la IA propone candidatos de entidades CON una
# busqueda desambiguada por el contexto de la nota (Capa 1, ver
# ia.extraer_entidades). 2) cada candidato se verifica contra Wikipedia con
# esa busqueda (wiki.resumen): si no tiene pagina real, se descarta. 3) la
# pagina encontrada pasa la reja de coherencia de dominio (Capa 2, ver
# ia.coincide_dominio): si no encaja con el tema de la nota, se descarta
# igual, aunque la pagina sea real (nunca se presenta como verificado algo
# que no lo esta -- ver bug real de Carney en las dos funciones citadas).
# 4) se buscan co-menciones en GDELT para la entidad PRINCIPAL: OTROS nombres
# con los que aparecio en cobertura reciente -- esto es una PISTA, no un
# hecho, y se etiqueta como tal. La entidad principal es la primera
# VERIFICADA en Wikipedia si hay alguna, pero si ninguna candidata tiene
# pagina (bug real de Xavier Jordan, ver mas abajo) se usa igual el primer
# CANDIDATO tal como lo extrajo la IA: GDELT no necesita que la entidad tenga
# pagina propia, solo busca su nombre en prensa reciente. 5) la IA redacta el
# "por que importa" usando SOLO ese material (entidades reales + pistas),
# nunca su conocimiento general. Si no se verifico ni encontro nada, "sin
# contexto disponible" -- nunca se inventa el vinculo.
#
# BUG REAL (caso Jordan): la captura de un procesado por el caso Villavicencio
# no traia contexto NI la conexion con el caso, aunque la nota no lo nombrara.
# Causa: antes, GDELT comenciones() SOLO corria si la entidad ya estaba
# verificada en Wikipedia -- y un recien capturado casi nunca tiene pagina
# propia, asi que esa capa nunca se ejecutaba para el (ver commit anterior:
# "principal = verificadas[0]... if verificadas else None"). Wikipedia sola
# no alcanzaba porque la nota no nombraba a Villavicencio -- el vinculo solo
# aparece en OTRAS notas de prensa que GDELT si puede ver. Arreglado
# desacoplando el "principal para GDELT" de la verificacion Wikipedia.

CONTEXTO_CACHE = os.path.join(HERE, "contexto_cache.json")
CONTEXTO_MAX_NEW = int(os.environ.get("MONITOR_CONTEXTO_MAX", "100"))  # tope de calculos NUEVOS por pasada (pacing)
# Fase 11 (v2): antes se auto-calculaba contexto para hasta CONTEXTO_MAX_NEW
# historias de CUALQUIER ambito (ordenadas local-primero por
# _prioridad_cupo_ia). Ahora el pedido es explicito: automatico SOLO para las
# CONTEXTO_TOP historias LOCALES mejor rankeadas por corrida -- el resto se
# calcula bajo demanda (GET /api/contexto?id=) cuando Fernando abre la nota.
CONTEXTO_TOP = int(os.environ.get("MONITOR_CONTEXTO_TOP", "10"))

# Fase 11 (v2), bug real encontrado en el Paso 1 (diagnostico): 'principal'
# (la entidad que ancla las co-menciones de GDELT y el registro de
# apariciones) a veces terminaba siendo un MEDIO DE PRENSA ("Teleamazonas") o
# un LUGAR ("Duran", "el Aeropuerto Jose Joaquin de Olmedo") en vez de un
# actor real de la historia -- 3 de 6 casos reales revisados. Dos señales,
# ninguna necesita IA extra: (1) el nombre coincide con un outlet conocido de
# feeds.py o con la heuristica de social.es_cuenta_medio (palabras como
# "noticias"/"tv"/"radio" en el nombre del canal/cuenta); (2) el extracto YA
# VERIFICADO de Wikipedia arranca describiendolo como un lugar/medio ("Duran
# es una urbe...", "Teleamazonas es un canal de television..."). Ante la
# duda (nombre sin outlet conocido y sin extracto para revisar) NO se
# descarta -- mismo criterio de "mejor un falso negativo" del resto de
# Parte B.
_OUTLETS_CONOCIDOS = {norm(f["outlet"]) for f in FEEDS}
_PATRON_LUGAR_O_MEDIO = re.compile(
    r"\bes (un|una) (ciudad|urbe|canton|provincia|pais|nacion|republica|estado soberano|"
    r"aeropuerto|distrito|barrio|parroquia|puente|terminal|"
    r"canal de television|cadena de television|diario|periodico|"
    r"medio de comunicacion|radio|emisora|cadena)\b")


def _es_lugar_o_medio(nombre, extracto=""):
    if norm(nombre) in _OUTLETS_CONOCIDOS:
        return True
    if social is not None:
        try:
            if social.es_cuenta_medio(nombre):
                return True
        except Exception:
            pass
    if extracto and _PATRON_LUGAR_O_MEDIO.search(norm(extracto[:150])):
        return True
    return False


def _fmt_fecha_corta(v):
    """Formatea una fecha de forma defensiva -- puede llegar como datetime
    (entradas del registro, ya reconstruidas por _cargar_registro) o como
    string ISO (fuentes de una historia, todavia sin serializar en este
    punto del pipeline)."""
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d")
    return str(v or "")[:10]


def _hash_fuentes(s):
    """Huella del CONJUNTO de fuentes de una historia (Fase 11 v2, pedido
    explicito del Paso 2: 'la clave es la clave estable de la historia mas un
    hash del conjunto de fuentes... esto reemplaza el cache por
    fuentes[0].link'). A diferencia de _huella_contenido() (usada por get_ia/
    get_veredicto, que solo compara la CANTIDAD de fuentes), esto hashea los
    links reales -- una fuente que se reemplaza sin cambiar el total tambien
    dispara un recalculo."""
    links = tuple(sorted(f.get("link", "") for f in (s.get("fuentes") or [])))
    return hashlib.sha1(("|".join(links)).encode("utf-8", "ignore")).hexdigest()[:12]


def _entrada_propia_registro(s, registro):
    """La entrada del registro que corresponde a ESTA historia (busca por
    coincidencia de link en 'fuentes') -- devuelve (eid, entrada) o
    (None, None). Es la puerta de entrada para antecedentes/actores: sin
    esto, _construir_contexto no tiene forma de saber que otras entradas del
    registro son 'la misma familia' de nombres que esta historia."""
    links = {f.get("link") for f in (s.get("fuentes") or []) if f.get("link")}
    if not links:
        return None, None
    for eid, e in registro.items():
        for f_ in e.get("fuentes", []):
            if f_.get("link") in links:
                return eid, e
    return None, None


def _antecedentes_registro(propio, registro, max_items=4):
    """Historias RELACIONADAS y ANTERIORES del propio registro -- la materia
    prima real de 'antecedentes' que _construir_contexto nunca tenia antes
    (Fase 11 v2, causa #1 del diagnostico del Paso 1).

    BUG REAL encontrado verificando en vivo con una historia real ("la
    esposa de alias Fito"): la primera version comparaba contra
    propio['nombres'], el UNION de nombres de TODAS las fuentes ya
    fusionadas -- con 4 medios cubriendo el mismo hecho (uno de ellos citando
    a un funcionario, otro a Noboa opinando), ese union junta nombres
    tangenciales ajenos al hecho en si. Exigir compartir solo UNO de esos
    nombres traia basura total: una nota de Mexico sobre una ley, una marcha
    en Bogota, hasta una noticia de una pelicula de Marvel -- todas
    coincidian por un nombre suelto y generico (ej. "Noboa", mencionado en
    decenas de notas no relacionadas por dia). Arreglado en dos capas:
    (1) el set de comparacion sale del titular FUNDADOR (el primer articulo,
    inmutable -- ver Fase 9, "deriva por rep_titulo"), no del union que crece
    con cada fuente nueva; (2) se exige 2+ nombres en comun cuando el
    fundador tiene 2 o mas disponibles (mismo criterio que ya usa
    _embed_multilingue_pendientes_registro para su propia reconciliacion) --
    con menos de 2 nombres en el fundador no hay margen para pedir 2, se
    acepta 1 como ultimo recurso (mismo criterio de siempre: ante la duda,
    mejor un falso negativo que inventar un antecedente sin relacion real).
    Ademas exige ser ESTRICTAMENTE MAS VIEJA -- un antecedente paso ANTES, no
    es un fragmento concurrente del mismo hecho (eso ya lo fusiona
    agrupar_con_memoria en una sola entrada). Con embeddings en los dos lados
    se usa el coseno para ORDENAR entre los candidatos que ya pasaron el
    filtro de nombres (nunca como umbral de corte aparte: la cobertura real
    de embeddings todavia es baja, ver Paso 1, sin casos reales suficientes
    para calibrar un umbral propio de 'antecedente relacionado' -- se
    prefiere honestidad sobre el mecanismo antes que inventar un numero sin
    medir)."""
    if propio is None:
        return []
    fundador = (propio.get("fundador_titulo", "") or "") + " " + (propio.get("fundador_resumen", "") or "")
    nombres_propios = _canon_set(_nombres_propios(fundador) | _siglas(fundador))
    if not nombres_propios:
        return []
    minimo_comun = 2 if len(nombres_propios) >= 2 else 1
    ultimo_propio = propio.get("ultimo")
    candidatos = []
    for e in registro.values():
        if e is propio or not e.get("ultimo"):
            continue
        if ultimo_propio and e["ultimo"] >= ultimo_propio:
            continue  # tiene que ser estrictamente anterior
        if len(_canon_set(e.get("nombres")) & nombres_propios) < minimo_comun:
            continue
        sim = None
        if propio.get("embedding") and e.get("embedding"):
            sim = _cos_sim(propio["embedding"], e["embedding"])
        candidatos.append((sim if sim is not None else -1.0, e["ultimo"], e))
    candidatos.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [e for _, _, e in candidatos[:max_items]]


def _apariciones_actor_registro(nombre, registro, excluir_eid=None, max_items=3):
    """Otras entradas del registro donde este mismo actor (nombre canonico)
    ya aparecio -- responde 'donde mas aparecieron' con el registro RICO de
    Fase 9 (embeddings/nombres/fechas), no con entities.json (el log liviano
    que ya se usaba para 'tambien aparecio', ver apariciones_previas)."""
    canon = _EQUIV_ENTIDADES.get(nombre.replace(" ", ""), nombre)
    out = []
    for eid, e in registro.items():
        if eid == excluir_eid:
            continue
        if canon in _canon_set(e.get("nombres")):
            out.append(e)
    out.sort(key=lambda e: e.get("ultimo") or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    return out[:max_items]


def _material_contexto(s, registro, verificadas, candidatos, comenciones, titulares, otros_medios):
    """Arma el material CITABLE (con ids cortos) para contexto.construir() --
    Fase 11 v2. Junta lo que YA se calculaba (otros medios del mismo grupo,
    bios verificadas de Wikipedia, co-menciones/titulares de GDELT) MAS lo
    que el diagnostico del Paso 1 encontro que faltaba: antecedentes y
    apariciones de actores del registro propio, y contratos SERCOP ya
    colgados de la historia. Cada item tiene un id (ej. 'R1', 'A2', 'S1') que
    el modelo tiene que citar -- contexto.py descarta en codigo cualquier
    afirmacion que cite un id que no este aca."""
    material = []
    contador = [0]

    def _add(prefijo, texto, link=None):
        contador[0] += 1
        mid = "%s%d" % (prefijo, contador[0])
        material.append({"id": mid, "texto": texto, "link": link})
        return mid

    for f in otros_medios:
        _add("M", "Otro medio cubriendo el mismo hecho: \"%s\" (%s)" % (f.get("title", ""), f.get("outlet", "")),
             link=f.get("link"))

    for e in verificadas:
        tipo = "articulo del SUCESO/EVENTO" if e.get("_es_evento") else "biografia de Wikipedia"
        _add("W", "%s (%s): %s" % (e["nombre"], tipo, e.get("extracto", "")[:220]), link=e.get("url"))

    if titulares:
        for t in titulares[:4]:
            _add("G", "Cobertura reciente de prensa sobre '%s': \"%s\" (%s)"
                 % (t.get("_entidad", ""), t.get("titulo", ""), t.get("fecha") or "s/f"), link=t.get("url"))
    if comenciones:
        _add("G", "Nombres co-mencionados en prensa reciente (pista por verificar, no confirma relacion): "
             + ", ".join(comenciones))

    eid_propio, propio = _entrada_propia_registro(s, registro)
    if propio:
        for e in _antecedentes_registro(propio, registro):
            f0 = (e.get("fuentes") or [{}])[0]
            _add("R", "%s (%s)" % (e.get("rep_titulo", ""), _fmt_fecha_corta(e.get("ultimo"))),
                 link=f0.get("link"))
        # Bug real (Fase 11 v2, verificado en vivo con la API real de
        # Gemini): iterar sobre TODOS los nombres crudos del registro
        # (_canon_set(propio.get("nombres"))) traia ruido total -- "colombia"
        # (un pais, no un actor) generaba apariciones sin relacion real
        # (una marcha en Bogota, una nota de una pelicula de Marvel). Ahora
        # solo se buscan apariciones de las entidades que YA pasaron por
        # extraccion de IA + el filtro _es_lugar_o_medio (evento/candidatos,
        # los mismos que llegan a 'verificadas' cuando tienen pagina de
        # Wikipedia) -- nombres reales de actores, nunca paises/lugares/
        # palabras sueltas.
        nombres_actores = set()
        for ent in verificadas:
            nombres_actores |= _canon_set(_nombres_propios(ent["nombre"]) | _siglas(ent["nombre"]))
        for c in candidatos:
            nombres_actores |= _canon_set(_nombres_propios(c.get("nombre", "")) | _siglas(c.get("nombre", "")))
        for nombre in sorted(nombres_actores)[:5]:
            for e in _apariciones_actor_registro(nombre, registro, excluir_eid=eid_propio):
                f0 = (e.get("fuentes") or [{}])[0]
                _add("A", "%s tambien aparece en: %s (%s)"
                     % (nombre, e.get("rep_titulo", ""), _fmt_fecha_corta(e.get("ultimo"))), link=f0.get("link"))

    for c in (s.get("contratos") or [])[:5]:
        _add("S", "Contrato SERCOP: %s -- %s ($%s, %s)"
             % (c.get("entidad", ""), c.get("objeto", ""), c.get("monto", ""), c.get("fecha", "")),
             link=c.get("link"))

    return material


def _construir_contexto(s, registro=None, perfil=None):
    """Arma el contexto de 4 bloques de UNA historia (Fase 11 v2). Nunca
    inventa: si no hay NADA de material real (ni entidad verificada, ni
    co-mencion, ni antecedente del registro, ni SERCOP, ni otro medio
    cubriendo el mismo hecho), ni siquiera llama a la IA. Devuelve un dict
    con antecedentes/actores/que_es_nuevo/que_falta_saber/limitaciones (mas
    'principal'/'entidades'/'comenciones'/'previas'/'texto' por compatibilidad
    con los pocos lugares que todavia los leen -- ver get_factcheck y el
    chat de Parte E) -- o None si la llamada a la IA fallo de verdad
    (distinto de un resultado vacio, que es valido; get_contexto() decide si
    reintentar despues sin guardar nada en cache)."""
    registro = registro if registro is not None else {}
    titular, resumen = s["titular"], s.get("resumen", "")
    temas = s.get("temas") or []
    # Problema 6 ("el contexto describe a la persona, no la situacion"):
    # el material MAS barato y directo de "que mas se publico sobre esto" es
    # el propio grupo de la historia (otros medios que el clustering YA unio
    # a esta misma nota, ver cluster() en monitor.py) -- no cuesta ninguna
    # llamada de red nueva, ya esta calculado en s["fuentes"].
    otros_medios = (s.get("fuentes") or [])[1:5]
    if ia:
        candidatos, evento = ia.extraer_entidades_con_evento(titular, resumen, temas=temas,
                                                               ambito=s.get("ambito", ""), forzado=IA_MODEL)
    else:
        candidatos, evento = [], None
    # Fase 11 (v2), Paso 1: filtro determinista ANTES de gastar Wikipedia --
    # un candidato que ya es un outlet conocido no necesita verificarse para
    # saber que no sirve como actor/principal.
    candidatos = [c for c in candidatos if not _es_lugar_o_medio(c.get("nombre", ""))]
    # Registro liviano de apariciones (entities.json): TODOS los candidatos
    # que sobrevivieron el filtro de arriba -- asi se puede rastrear a
    # alguien como Xavier Jordan en el tiempo aunque nunca tenga pagina de
    # Wikipedia, sin ensuciar ese log con nombres de medios.
    registrar_apariciones(s, [c.get("nombre", "") for c in candidatos])

    def _verificar(nombre, busqueda):
        """Verifica un candidato (persona/lugar/org O evento) contra
        Wikipedia con las mismas dos capas de siempre (Parte B), mas el
        filtro de lugar/medio sobre el EXTRACTO ya verificado (Fase 11 v2:
        un nombre que no coincidia con ningun outlet conocido, como "Duran"
        o el nombre completo de un aeropuerto, igual se descarta si su
        propia bio de Wikipedia lo describe como un lugar)."""
        r = wiki.resumen(nombre, busqueda=busqueda) if wiki else None
        if r and not _nombre_se_solapa(nombre, r["nombre"]):
            return None
        if r and ia and not ia.coincide_dominio(titular, resumen, nombre, r["nombre"], r["extracto"],
                                                  forzado=IA_MODEL):
            return None
        if r and _es_lugar_o_medio(r["nombre"], r.get("extracto", "")):
            return None
        return r

    verificadas = []
    if evento:
        r = _verificar(evento["nombre"], evento["busqueda"])
        if r:
            verificadas.append(dict(r, _es_evento=True))
        time.sleep(0.3)
    for c in candidatos:
        nombre, busqueda = c.get("nombre", ""), c.get("busqueda", "")
        r = _verificar(nombre, busqueda)
        if r:
            verificadas.append(r)
        time.sleep(0.3)  # gentil con Wikipedia; los candidatos son pocos (<=5)

    # Entidad para buscar en GDELT: la primera VERIFICADA si hay alguna, si
    # no el primer CANDIDATO tal cual lo extrajo la IA (caso Jordan) -- los
    # dos ya pasaron el filtro de lugar/medio de arriba.
    principal = verificadas[0]["nombre"] if verificadas else (
        candidatos[0].get("nombre") if candidatos else None)
    comenciones, titulares = [], []
    if principal and gdelt is not None and os.environ.get("MONITOR_NO_GDELT") != "1":
        try:
            cp = gdelt.contexto_prensa(principal, geo=GDELT_GEO)
            comenciones, titulares = cp["comenciones"], cp["titulares"]
            for t in titulares:
                t["_entidad"] = principal
        except Exception:
            comenciones, titulares = [], []

    f0 = (s.get("fuentes") or [{}])[0]
    propio_link = f0.get("link", "")
    previas = apariciones_previas(principal, excluir_link=propio_link) if principal else []
    titulares = [t for t in titulares if t.get("url") != propio_link][:4]

    material = _material_contexto(s, registro, verificadas, candidatos, comenciones, titulares, otros_medios)
    if not material:
        # Sin NINGUN material real: ni siquiera se llama a la IA (se ahorra
        # la llamada y el riesgo de "rellenar" con algo no verificado).
        # 'principal' se conserva aunque no haya nada que MOSTRAR todavia:
        # get_factcheck() lo sigue usando como segunda busqueda.
        return {"texto": "sin contexto disponible", "entidades": [], "comenciones": [],
                "principal": principal, "previas": [],
                "antecedentes": [], "actores": [], "que_es_nuevo": [], "que_falta_saber": [],
                "limitaciones": "sin material verificado disponible", "descartadas": 0}

    if contexto is None:
        return {"texto": "sin contexto disponible", "entidades": verificadas, "comenciones": comenciones,
                "principal": principal, "previas": previas,
                "antecedentes": [], "actores": [], "que_es_nuevo": [], "que_falta_saber": [],
                "limitaciones": "modulo contexto.py no disponible", "descartadas": 0}

    bloques = contexto.construir(titular, resumen, material, forzado=IA_MODEL, perfil=perfil)
    if bloques is None:
        return None  # fallo real de la IA -- get_contexto() no cachea esto, reintenta despues

    # 'texto' (compatibilidad): la primera afirmacion de "que_es_nuevo" si
    # hay alguna citable, si no la primera de "antecedentes" -- para los
    # consumidores livianos que solo quieren una oracion corta (Parte E,
    # get_factcheck no usa 'texto', solo 'principal', pero el chat por-item
    # si arma su material con esto, ver _construir_contexto_chat mas abajo).
    resumen_corto = None
    if bloques["que_es_nuevo"]:
        resumen_corto = bloques["que_es_nuevo"][0]["texto"]
    elif bloques["antecedentes"]:
        resumen_corto = bloques["antecedentes"][0]["texto"]

    material_por_id = {m["id"]: {"texto": m["texto"], "link": m.get("link")} for m in material}
    return dict(bloques, texto=resumen_corto or "sin contexto disponible", entidades=verificadas,
                comenciones=comenciones, principal=principal, previas=previas, material=material_por_id)


def get_contexto(stories, modo_lectura=False):
    """Contexto real por entidad (Parte B) para las historias TOP. Cachea por
    historia (link, igual que get_ia). Puede tardar bastante por historia
    (extraccion de entidades + Wikipedia + GDELT + redaccion: varias llamadas
    en serie), asi que SOLO debe correr con red real desde el hilo trabajador.

    modo_lectura=True (hilo rapido, Parte C): SOLO lee lo que el trabajador ya
    dejo en contexto_cache.json -- nunca hace red ni llama a Ollama. Una
    historia sin cache todavia no lleva 'contexto' (la tarjeta muestra
    'analizando...')."""
    cache = {}
    try:
        with open(CONTEXTO_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass

    if modo_lectura:
        n, desactualizadas = 0, 0
        for s in stories:
            key = story_key(s)
            if key in cache:
                entry = cache[key]
                s["contexto"] = entry; n += 1
                # Fase 11 (v2): reemplaza la huella por cantidad de fuentes
                # (_huella_contenido, todavia la usan get_ia/get_veredicto)
                # por un hash del CONJUNTO de fuentes -- pedido explicito del
                # Paso 2 ("esto reemplaza el cache por fuentes[0].link").
                if entry.get("_fuentes_hash") and entry["_fuentes_hash"] != _hash_fuentes(s):
                    s["contexto_desactualizado"] = True
                    desactualizadas += 1
        extra = ", %d desactualizados" % desactualizadas if desactualizadas else ""
        return "cache (%d/%d%s)" % (n, len(stories), extra)

    if ia is None or wiki is None or os.environ.get("MONITOR_NO_CONTEXTO") == "1":
        return "desactivado"
    if not ia.disponible(IA_MODEL):
        return "error: %s" % (getattr(ia, "last_error", None) or "Ollama no responde")

    # Fase 11 (v2), pedido explicito del Paso 2: automatico SOLO para las
    # CONTEXTO_TOP historias LOCALES mejor rankeadas por corrida (antes era
    # cualquier ambito, con local solo como prioridad de orden). El resto se
    # calcula bajo demanda con GET /api/contexto?id= (ver _do_GET_contexto).
    # Fase 18 (P2-10): TODO lo local, Guayaquil primero; las CONTEXTO_TOP
    # mas importantes con el perfil profundo, el resto con el rapido.
    objetivo = sorted([s for s in stories if s.get("es_local")],
                       key=lambda s: (0 if s.get("ciudad") == "Guayaquil" else 1, -(s.get("interes") or 0)))
    top_ctx = {story_key(s) for s in sorted([s for s in stories if s.get("es_local")],
                                             key=lambda s: -(s.get("interes") or 0))[:CONTEXTO_TOP]}
    registro = _cargar_registro() if objetivo else {}
    new = 0
    for s in objetivo:
        key = story_key(s)
        huella = _hash_fuentes(s)
        entry = cache.get(key)
        # "antecedentes" not in entry: formato VIEJO (de antes de este
        # cambio, sin los 4 bloques) -- bug propio encontrado verificando en
        # vivo: sin este chequeo, una entrada vieja nunca tenia "_fuentes_hash"
        # para comparar, asi que el chequeo de abajo daba SIEMPRE falso y la
        # entrada se quedaba en formato viejo para siempre, aunque la
        # historia siguiera en el top 10 local. Ahora se prioriza para
        # recalcular con el esquema nuevo la primera vez que le toque cupo.
        desactualizado = entry is not None and (
            "antecedentes" not in entry
            or (entry.get("_fuentes_hash") and entry["_fuentes_hash"] != huella))
        if entry is not None and not desactualizado:
            s["contexto"] = entry
            continue
        if new >= CONTEXTO_MAX_NEW:
            if entry is not None:
                s["contexto"] = entry
                s["contexto_desactualizado"] = True
            continue
        perfil = _perfil_para(s, top_ctx)
        if perfil == getattr(ia, "PERFIL_PROFUNDO", "profundo"):
            nuevo = _construir_contexto(s, registro)  # el de siempre (profundo por defecto)
        else:
            nuevo = _construir_contexto(s, registro, perfil=perfil)
        new += 1  # el intento gasta cupo de esta pasada aunque la IA falle
        if nuevo is None:
            if entry is not None:
                s["contexto"] = entry
                s["contexto_desactualizado"] = True
            continue  # no se cachea un fallo real -- se reintenta en la proxima pasada
        nuevo["_fuentes_hash"] = huella
        s["contexto"] = cache[key] = nuevo
        s["contexto_desactualizado"] = False
    try:
        with open(CONTEXTO_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    return "ok (+%d nuevas, %d locales)" % (new, len(objetivo))


# ------------------------- contraste con documentacion oficial (SERCOP) -------------------------

SERCOP_CACHE = os.path.join(HERE, "sercop_cache.json")
SERCOP_TTL = 24 * 3600  # los contratos cambian lento: cache de 1 dia
# pistas de que una nota toca dinero/obra publica (solo ahi vale buscar contratos)
SPEND_HINTS = ["contrato", "contratos", "licitacion", "adjudicacion", "obra", "obras",
               "compra publica", "presupuesto", "municipio", "prefectura", "alcaldia",
               "ministerio", "hospital", "carretera", "vialidad", "puente", "sercop",
               "fondos", "recursos publicos", "concurso", "proveedor", "sobreprecio"]

def _spend_term(title):
    toks = [t for t in norm(title).split() if len(t) >= 5 and t not in STOPWORDS]
    return " ".join(toks[:2])

def get_contracts(stories, max_q=8, modo_lectura=False):
    """Cuelga en cada historia relevante (local + tema de gasto/obra) una lista
    'contratos' de SERCOP para contrastar. Bounded (max_q consultas) y con cache.

    BUG REAL (task #17, mismo problema que GDELT): la busqueda real a SERCOP
    (sercop.buscar, con sleep(2) entre cada una, hasta max_q por pasada)
    vivia en el hilo rapido -- si el cache de 24h vencia, el arranque del
    feed podia quedar esperando red en vez de publicar. Arreglado con el
    mismo patron modo_lectura de siempre: modo_lectura=True (hilo rapido)
    SOLO aplica terminos que el trabajador ya busco antes (terms cacheados),
    nunca llama a sercop.buscar ni borra el cache por vencimiento -- eso
    ultimo tambien importa: borrar el cache entero en el hilo rapido haria
    desaparecer de golpe contratos que ya se le mostraban a Fernando, sin
    haber buscado los nuevos todavia."""
    if sercop is None or os.environ.get("MONITOR_NO_SERCOP") == "1":
        return "desactivado"
    cache = {}
    try:
        with open(SERCOP_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass
    if not modo_lectura and time.time() - cache.get("ts", 0) > SERCOP_TTL:
        cache = {"ts": time.time(), "terms": {}}
    terms = cache.setdefault("terms", {})
    count, err, aplicadas = 0, None, 0
    for s in stories:
        if not s.get("es_local"):
            continue
        blob = norm(s["titular"] + " " + s.get("resumen", ""))
        if not any(h in blob for h in SPEND_HINTS):
            continue
        term = _spend_term(s["titular"])
        if not term:
            continue
        if term in terms:
            s["contratos"] = terms[term]
            aplicadas += 1
            continue
        if modo_lectura:
            continue  # el trabajador todavia no busco este termino -- no se bloquea el feed
        if count >= max_q:
            continue
        res = sercop.buscar(term)
        terms[term] = res
        s["contratos"] = res
        count += 1
        if getattr(sercop, "last_error", None):
            err = sercop.last_error
        time.sleep(2)
    if modo_lectura:
        return "cache (%d aplicados)" % aplicadas
    try:
        with open(SERCOP_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    return ("ok (+%d nuevos)" % count if not err else "parcial: %s" % err)


# ------------------------- FactCheck (Google Fact Check Tools) -------------------------

FACTCHECK_CACHE = os.path.join(HERE, "factcheck_cache.json")
FACTCHECK_MAX_NEW = int(os.environ.get("MONITOR_FACTCHECK_MAX", "8"))  # historias nuevas por pasada del trabajador

def _factcheck_relevante(s, resultados, excluir=None):
    """Filtro de relevancia para el fallback por entidad de get_factcheck (ver
    bug real ahi mismo): se queda solo con los ClaimReview que comparten al
    menos DOS palabras significativas (mismo criterio que tokens(): >=4
    letras, sin stopwords) con el titular+resumen de ESTA historia, aparte
    del nombre que ya se uso como busqueda (que siempre 'coincide' por
    definicion y no sirve como filtro).

    BUG REAL mas grave, encontrado en vivo por Fernando (2026-09-23): la
    historia "Trump Praises Burnham..." traia un ClaimReview sobre "Keir
    Starmer con la camiseta de Croacia" calificado 'Falso' -- CERO relacion
    real, ni siquiera la misma persona (Starmer vs. Burnham). Causa raiz
    doble: (1) esta funcion SOLO se aplicaba al fallback por entidad
    (`get_factcheck`, busqueda por 'principal'); la busqueda PRIMARIA por
    titular completo nunca pasaba por ningun filtro de relevancia -- Google
    Fact Check Tools (`claims:search`) no hace matching exacto de frase, asi
    que un titular en INGLES contra un corpus de verificadores
    mayormente en ESPAÑOL puede devolver "lo mas parecido que encontro",
    que a veces es basicamente ruido. (2) el umbral exigia una sola palabra
    compartida -- muy debil para frenar coincidencias sueltas. Arreglado:
    el filtro ahora se aplica a AMBAS busquedas (primaria y fallback, ver
    get_factcheck) y exige >=2 palabras significativas en comun, no 1."""
    if not resultados:
        return resultados
    base = tokens(s["titular"]) | tokens(s.get("resumen", ""))
    if excluir:
        base = base - tokens(excluir)
    if not base:
        return resultados  # nada mas para comparar -- no se puede filtrar, no se descarta por las dudas
    return [r for r in resultados if len(base & tokens(r.get("claim", ""))) >= 2]


def get_factcheck(stories, modo_lectura=False):
    """Verificaciones periodisticas relacionadas (Google Fact Check Tools) por
    historia TOP: busca por el titular y, si no encuentra nada, por la
    entidad principal ya verificada en s['contexto'] (Parte B) -- suele
    encontrar mas ClaimReview relacionados que solo el titular textual.
    Adjunta s['factcheck'] = [{claim, calificacion, verificador, url, fecha}]
    (lista vacia si no hay verificaciones relacionadas). Cachea por historia
    (link, igual que get_ia/get_contexto). SOLO debe correr con red real
    desde el hilo trabajador.

    modo_lectura=True (hilo rapido, Parte C): SOLO lee lo que el trabajador ya
    dejo en factcheck_cache.json -- nunca hace red."""
    cache = {}
    try:
        with open(FACTCHECK_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass

    # BUG REAL (Burnham/camiseta de Croacia, 2026-09-23): factcheck_cache.json
    # es un cache SIN version ni vencimiento -- una entrada mala (de antes de
    # que existiera el filtro de relevancia, o de un bug en el filtro) se
    # queda ahi para siempre, immune a que el codigo se arregle despues.
    # Re-filtrar CADA VEZ que se lee del cache (ademas de al escribirlo) es
    # defensa en profundidad barata (solo CPU, sin red): limpia sola
    # cualquier entrada vieja mala sin necesitar borrar el archivo a mano.
    if modo_lectura:
        n = 0
        for s in stories:
            f0 = (s.get("fuentes") or [{}])[0]
            key = (f0.get("link") or s["titular"])[:180]
            if key in cache:
                s["factcheck"] = _factcheck_relevante(s, cache[key]); n += 1
        return "cache (%d/%d)" % (n, len(stories))

    if factcheck is None or os.environ.get("MONITOR_NO_FACTCHECK") == "1":
        return "desactivado"
    if not factcheck.KEY:
        return "desactivado (sin MONITOR_FACTCHECK_KEY)"

    new, err = 0, None
    for s in stories:  # ya vienen ordenadas por interes: se prioriza lo top
        f0 = (s.get("fuentes") or [{}])[0]
        key = (f0.get("link") or s["titular"])[:180]
        if key in cache:
            s["factcheck"] = _factcheck_relevante(s, cache[key]); continue
        if new >= FACTCHECK_MAX_NEW:
            continue
        principal = (s.get("contexto") or {}).get("principal")
        # BUG REAL (Burnham/camiseta de Croacia, ver _factcheck_relevante):
        # la busqueda PRIMARIA por titular completo se usaba TAL CUAL, sin
        # filtro de relevancia -- solo el fallback por entidad lo tenia.
        # Ahora las dos pasan por el mismo filtro (>=2 palabras en comun).
        resultados = _factcheck_relevante(s, factcheck.buscar(s["titular"]))
        if not resultados and principal:
            # Bug real (Contraste con datos no relacionados): buscar solo por
            # la entidad principal (a veces una sola palabra, ej. "Alemania")
            # le trae a Google Fact Check Tools cualquier ClaimReview que
            # mencione esa palabra, sin relacion con ESTA historia. Se exige
            # que el resultado comparta ademas otra palabra significativa con
            # el titular/resumen -- no basta con coincidir en el nombre que
            # ya se uso como busqueda (eso siempre coincide, no filtra nada).
            resultados = _factcheck_relevante(s, factcheck.buscar(principal), excluir=principal)
        if not resultados and getattr(factcheck, "last_error", None):
            err = factcheck.last_error
            if "403" in err:
                break  # clave/config mal habilitada: no tiene sentido seguir esta pasada
        cache[key] = resultados
        s["factcheck"] = resultados
        new += 1
    try:
        with open(FACTCHECK_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    if err and "403" in err:
        return "error: %s" % err
    return "ok (+%d nuevas)" % new


# ------------------------- veredicto de contraste (Problema 4) -------------------------
# Estructura fija pedida por Fernando para Contraste: 1) afirmacion, 2)
# contexto actual, 3) fuentes oficiales (SERCOP), 4) verificadores
# (FactCheck), 5) ESTADO (coincide/contradice/sin_datos/pendiente). Las
# primeras 4 partes ya existen (s["titular"]+s["resumen"], s["contexto"],
# s["contratos"], s["factcheck"]) -- lo que faltaba era el veredicto que las
# conecta. Mismo patron de siempre (Parte B): el CODIGO junta el material ya
# verificado, la IA SOLO redacta un veredicto sobre ESE material, nunca
# busca ni inventa por su cuenta.

VEREDICTO_CACHE = os.path.join(HERE, "veredicto_cache.json")
GEO_EVIDENCIA_CACHE = os.path.join(HERE, "geo_evidencia_cache.json")
# Fase 18 (P2-11): el veredicto viejo con IA ("coincide" = medio contra
# medio) queda APAGADO por defecto -- lo reemplaza contraste.py (documento
# oficial / cifras entre medios / declaraciones previas, sin gastar IA).
# MONITOR_VEREDICTO_MAX=8 lo vuelve a encender.
VEREDICTO_MAX_NEW = int(os.environ.get("MONITOR_VEREDICTO_MAX", "0"))  # historias nuevas por pasada del trabajador

GEO_EVIDENCIA_MAX_NEW = int(os.environ.get("MONITOR_GEO_EVIDENCIA_MAX", "8"))  # historias nuevas por pasada


def _validar_frase_evidencia(frase, titular, resumen):
    """Candado en CODIGO (no solo en el prompt): la frase_evidencia tiene
    que aparecer LITERALMENTE (normalizada, sin tildes/mayusculas, ver
    norm()) en el titular+resumen real de la historia -- si no aparece, la
    IA la invento o parafraseo y su decision de ciudad no es confiable."""
    if not frase:
        return False
    blob = norm(titular + " " + (resumen or ""))
    return norm(frase) in blob


def get_geo_evidencia(stories, modo_lectura=False):
    """Fase 14, Paso 2 ("clasificacion con evidencia"): para historias
    LOCALES donde las fuentes fusionadas no se ponen de acuerdo en la ciudad
    (s["ciudad_discrepancia"]), pide al perfil rapido de Gemini una decision
    citando una frase literal del propio texto -- validada en codigo antes
    de aplicarla. Nunca reclasifica un caso resuelto por ciudad_feed (esa
    señal es mas fuerte que cualquier frase de texto, ver
    _ciudad_de_fuente) porque esos casos nunca quedan marcados con
    discrepancia real. Cachea por story_key(s), modo_lectura=True (hilo
    rapido) SOLO lee el cache, nunca llama a la IA.

    Cuando el resultado es valido, corrige la historia EN MEMORIA (para esta
    pasada del dashboard): si es_guayaquil=False, se limpia s["ciudad"]
    (deja de mostrarse como Guayaquil sin evidencia real); si
    es_guayaquil=True y s["ciudad"] estaba vacio, se completa a
    "Guayaquil"."""
    cache = {}
    try:
        with open(GEO_EVIDENCIA_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass

    def _aplicar(s, entry):
        s["geo_evidencia"] = entry
        if not entry.get("valido"):
            return
        if entry.get("es_guayaquil") is False and s.get("ciudad") == "Guayaquil":
            s["ciudad"] = ""
        elif entry.get("es_guayaquil") is True and not s.get("ciudad"):
            s["ciudad"] = "Guayaquil"

    if modo_lectura:
        n = 0
        for s in stories:
            if not s.get("ciudad_discrepancia"):
                continue
            entry = cache.get(story_key(s))
            if entry:
                _aplicar(s, entry)
                n += 1
        return "cache (%d)" % n

    if ia is None or os.environ.get("MONITOR_NO_IA") == "1":
        return "desactivado"

    candidatos = [s for s in stories if s.get("ciudad_discrepancia") and story_key(s) not in cache]
    new = 0
    for s in candidatos[:GEO_EVIDENCIA_MAX_NEW]:
        key = story_key(s)
        r = ia.clasificar_geo_evidencia(s["titular"], s.get("resumen", ""), forzado=IA_MODEL)
        new += 1
        if r is None:
            continue  # fallo transitorio: no se cachea, se reintenta la proxima pasada
        valido = _validar_frase_evidencia(r.get("frase_evidencia"), s["titular"], s.get("resumen", ""))
        entry = {
            "ciudad_del_hecho": r.get("ciudad_del_hecho") if valido else None,
            "es_guayaquil": bool(r.get("es_guayaquil")) if valido else False,
            "frase_evidencia": r.get("frase_evidencia") if valido else None,
            "valido": valido,
        }
        cache[key] = entry
        _aplicar(s, entry)
    if new:
        tmp = GEO_EVIDENCIA_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, GEO_EVIDENCIA_CACHE)
    return "+%d nuevas" % new

def _material_veredicto(s):
    """Arma el material para el veredicto: contexto ya grounded (Parte B,
    incluye 'tambien aparecio' de entities.json/history de apariciones),
    otros medios que cubren ESTA MISMA historia ahora mismo (el 'grupo' de
    la historia, via clustering), contratos SERCOP y resultados FactCheck.
    Ninguna de estas piezas se inventa aca: todas ya fueron verificadas por
    otras funciones (get_contexto/get_contracts/get_factcheck) antes de
    llegar a esta. Si no hay NADA de esto, devuelve '' -- candado de codigo
    para que get_veredicto ni llame a la IA (mejor 'sin_datos' seguro que
    forzar un veredicto sin material)."""
    bloques = []
    ctx = s.get("contexto") or {}
    if ctx.get("texto") and ctx["texto"] != "sin contexto disponible":
        bloques.append("- Contexto verificado de la situacion: %s" % ctx["texto"])
    otros_medios = [f for f in (s.get("fuentes") or [])[1:5]]
    if otros_medios:
        bloques.append("- Otros medios cubriendo el mismo hecho ahora: "
                        + "; ".join("\"%s\" (%s)" % (f.get("title", ""), f.get("outlet", ""))
                                    for f in otros_medios))
    contratos = s.get("contratos") or []
    if contratos:
        bloques.append("- Contratos oficiales SERCOP relacionados: " + "; ".join(
            "%s — %s ($%s, %s)" % (c.get("entidad", ""), c.get("objeto", "")[:90],
                                    c.get("monto", "?"), c.get("fecha", "?"))
            for c in contratos[:4]))
    fc = s.get("factcheck") or []
    if fc:
        bloques.append("- Verificaciones periodisticas (FactCheck) relacionadas: " + "; ".join(
            "\"%s\" -> %s (segun %s)" % (c.get("claim", "")[:100], c.get("calificacion", "?"),
                                          c.get("verificador", "?"))
            for c in fc[:4]))
    return "\n".join(bloques)

def get_veredicto(stories, modo_lectura=False):
    """Veredicto de Contraste por historia (Problema 4): {estado, texto,
    citas}. estado en coincide/contradice/sin_datos/pendiente. Corre DESPUES
    de contexto/SERCOP/FactCheck (necesita que ya esten calculados) -- mismo
    lugar de la secuencia que ya usaba FactCheck para la entidad principal.

    modo_lectura=True (hilo rapido): SOLO lee veredicto_cache.json."""
    cache = {}
    try:
        with open(VEREDICTO_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass

    if modo_lectura:
        n = 0
        for s in stories:
            f0 = (s.get("fuentes") or [{}])[0]
            key = (f0.get("link") or s["titular"])[:180]
            if key in cache:
                entry = cache[key]
                s["veredicto"] = entry; n += 1
                if entry.get("_huella") and entry["_huella"] != _huella_contenido(s):
                    s["veredicto_desactualizado"] = True
            else:
                s["veredicto"] = {"estado": "pendiente", "texto": "Todavia no procesado.", "citas": []}
        return "cache (%d/%d)" % (n, len(stories))

    if ia is None or os.environ.get("MONITOR_NO_IA") == "1":
        for s in stories:
            s.setdefault("veredicto", {"estado": "pendiente", "texto": "IA desactivada.", "citas": []})
        return "desactivado"

    new = 0
    for s in sorted(stories, key=_prioridad_cupo_ia):  # local primero (Problema B2)
        f0 = (s.get("fuentes") or [{}])[0]
        key = (f0.get("link") or s["titular"])[:180]
        huella = _huella_contenido(s)
        entry = cache.get(key)
        desactualizado = entry is not None and entry.get("_huella") and entry["_huella"] != huella
        if entry is not None and not desactualizado:
            s["veredicto"] = entry
            continue
        if new >= VEREDICTO_MAX_NEW:
            if entry is not None:
                s["veredicto"] = entry
                s["veredicto_desactualizado"] = True
            else:
                s.setdefault("veredicto", {"estado": "pendiente", "texto": "Todavia no procesado.", "citas": []})
            continue
        material = _material_veredicto(s)
        if not material:
            # Candado en CODIGO (no solo en el prompt de ia.py): sin ningun
            # material verificado, ni siquiera se llama al modelo.
            v = {"estado": "sin_datos", "texto": "Sin contexto, contratos ni verificaciones para contrastar.", "citas": []}
        else:
            v = ia.veredicto_contraste(s["titular"], s.get("resumen", ""), material, forzado=IA_MODEL)
            if v is None:
                if entry is not None:
                    s["veredicto"] = entry
                    s["veredicto_desactualizado"] = True
                else:
                    s.setdefault("veredicto", {"estado": "pendiente", "texto": "La IA no respondio esta vez.", "citas": []})
                continue  # no se cachea un fallo transitorio: se reintenta la proxima pasada
        v["_huella"] = huella
        cache[key] = v
        s["veredicto"] = v
        s["veredicto_desactualizado"] = False
        new += 1
    try:
        with open(VEREDICTO_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    return "ok (+%d nuevos)" % new


# ------------------------- Fase 5: contraste de declaraciones con el pasado -------------------------
# Extrae declaraciones ATRIBUIDAS de las notas (quien, cargo, que dijo) y las
# cruza contra lo que el MISMO actor dijo antes -- registro propio
# (declaraciones.py, declaraciones.json) que nunca se purga por
# MONITOR_MAX_DIAS, a diferencia de las historias del feed. Filtro barato
# (mismo actor + 2+ palabras en comun, sin IA) antes de gastar la llamada cara
# al modelo pesado -- mismo principio que _factcheck_relevante/_material_veredicto:
# el codigo decide QUE comparar, la IA SOLO compara lo que ya le seleccionaron.

DECL_CACHE_PATH = os.path.join(HERE, "declaraciones_contraste_cache.json")  # cache del VEREDICTO del modelo pesado por PAR (actor+link_nuevo+link_viejo) -- el registro en si (declaraciones.json) es aparte y nunca se purga
DECL_MAX_NEW = int(os.environ.get("MONITOR_DECL_MAX", "6"))            # historias nuevas por pasada del trabajador (extraccion, modelo rapido)
DECL_CONTRASTE_MAX = int(os.environ.get("MONITOR_DECL_CONTRASTE_MAX", "3"))  # comparaciones con el modelo PESADO por pasada (caro, ~100s c/u)

def _par_key(actor, link_nuevo, link_viejo):
    return "%s|%s|%s" % (norm(actor), link_nuevo, link_viejo)

def get_declaraciones(stories, modo_lectura=False):
    """Fase 5: extrae declaraciones atribuidas de historias nuevas
    (ia.extraer_declaracion, modelo RAPIDO), las registra en declaraciones.json
    (registro que NUNCA se purga por MONITOR_MAX_DIAS -- decl.registrar), y
    para las que tienen candidatos de contradiccion (filtro barato por
    actor+palabras en comun, decl.candidatos_contradiccion) le pide al modelo
    PESADO que compare (ia.comparar_declaraciones).

    DECL_CACHE_PATH guarda DOS cosas por separado: "_por_historia" (por link,
    lo que se le va a mostrar a Fernando en ESA historia: declaracion +
    contradicciones encontradas) y el resultado del modelo pesado por PAR
    (actor+link_nuevo+link_viejo, para no repetir la llamada cara si el mismo
    par vuelve a salir como candidato en otra pasada).

    modo_lectura=True (hilo rapido): SOLO relee "_por_historia" por link y lo
    vuelve a pegar en los objetos 's' RECIEN reconstruidos por build_stories()
    -- mismo patron que get_veredicto/get_contexto (run_fast rearma 'stories'
    desde cero en cada pasada, asi que sin este re-pegado por link el dato
    calculado por el trabajador se perderia en la siguiente pasada del hilo
    rapido)."""
    if decl is None:
        return "modulo no disponible"

    cache = {}
    try:
        with open(DECL_CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass
    por_historia = cache.get("_por_historia") or {}

    if modo_lectura:
        n = 0
        for s in stories:
            f0 = (s.get("fuentes") or [{}])[0]
            link = f0.get("link", "")
            entry = por_historia.get(link)
            if not entry:
                continue
            n += 1
            if entry.get("declaracion"):
                s["declaracion"] = entry["declaracion"]
            if entry.get("contradicciones"):
                s["contradiccion_declaracion"] = entry["contradicciones"]
        return "cache (%d/%d)" % (n, len(stories))

    if ia is None or os.environ.get("MONITOR_NO_IA") == "1":
        return "desactivado"
    # Fase 10 (migracion a la nube): sin este chequeo, con la IA caida
    # extraer_declaracion() devuelve None y la nota quedaba marcada como
    # "_procesadas" SIN declaracion -- para siempre, aunque la IA volviera.
    # El docstring de ia.extraer_declaracion ya decia que monitor.py hacia
    # este chequeo, pero nunca se habia escrito (otro caso del patron
    # "documentado pero no conectado").
    if not ia.disponible(IA_MODEL):
        return "error: %s" % (getattr(ia, "last_error", None) or "IA no disponible")

    procesadas = set(cache.get("_procesadas") or [])
    nuevas = 0
    comparaciones = 0
    for s in stories:  # ya vienen ordenadas por interes: se prioriza lo top
        if nuevas >= DECL_MAX_NEW:
            break
        f0 = (s.get("fuentes") or [{}])[0]
        link = f0.get("link", "")
        if not link or link in procesadas:
            if link in por_historia:  # ya procesada antes: reaplicar lo que ya se sabe
                entry = por_historia[link]
                if entry.get("declaracion"):
                    s["declaracion"] = entry["declaracion"]
                if entry.get("contradicciones"):
                    s["contradiccion_declaracion"] = entry["contradicciones"]
            continue
        d = ia.extraer_declaracion(s["titular"], s.get("resumen", ""), forzado=IA_MODEL)
        procesadas.add(link)
        nuevas += 1
        if not d:
            continue
        fecha = s.get("newest") or now_utc().isoformat()
        medio = f0.get("outlet", "")
        decl.registrar(d["actor"], d["cargo"], d["texto"], fecha, medio, link, historia_key=link)
        declaracion = {"actor": d["actor"], "cargo": d["cargo"], "texto": d["texto"],
                       "fecha": fecha, "medio": medio}
        s["declaracion"] = declaracion
        por_historia[link] = {"declaracion": declaracion}

        if comparaciones >= DECL_CONTRASTE_MAX:
            continue
        candidatos = decl.candidatos_contradiccion(d["actor"], d["texto"], fecha, excluir_link=link)
        resultados = []
        for c in candidatos:
            if comparaciones >= DECL_CONTRASTE_MAX:
                break
            key = _par_key(d["actor"], link, c.get("link", ""))
            if key in cache:
                resultados.append(cache[key]); continue
            r = ia.comparar_declaraciones(
                d["actor"], d["texto"], fecha, medio,
                c.get("texto", ""), c.get("fecha", ""), c.get("medio", ""))
            comparaciones += 1
            if r is None:
                continue  # fallo transitorio de Ollama: no se cachea, se reintenta otra pasada
            r = dict(r)
            r["fuente_previa"] = {"actor": c.get("actor", d["actor"]), "texto": c.get("texto", ""),
                                   "fecha": c.get("fecha", ""), "medio": c.get("medio", ""),
                                   "link": c.get("link", "")}
            cache[key] = r
            resultados.append(r)
        # candado en CODIGO: solo se muestran las que el modelo marco como
        # posible contradiccion -- 'consistente'/'sin_relacion' no se le
        # muestran a Fernando como si fueran un hallazgo (ruido innecesario)
        posibles = [r for r in resultados if r.get("estado") == "posible_contradiccion"]
        if posibles:
            s["contradiccion_declaracion"] = posibles
            por_historia[link]["contradicciones"] = posibles

    cache["_procesadas"] = list(procesadas)[-800:]
    cache["_por_historia"] = por_historia
    try:
        with open(DECL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    return "ok (+%d nuevas, %d comparaciones)" % (nuevas, comparaciones)


# ------------------------- cobertura + tono (GDELT) -------------------------

GDELT_CACHE = os.path.join(HERE, "gdelt_cache.json")
GDELT_GEO = os.environ.get("MONITOR_GDELT_PAIS", "")  # "" = toda la prensa en espanol; "ecuador" = solo EC

def get_gdelt(themes, modo_lectura=False):
    """Devuelve ({tema:{vol,tone,tone_series}}, estado). Cobertura mediatica y tono
    por tema, via GDELT (gratis, sin clave). Cache TREND_TTL. No rompe si falla.

    Estado HONESTO (Frente C): antes, un exito PARCIAL (ej. GDELT respondio
    solo 1 de 19 temas, el resto 429) se reportaba igual que "ok" a secas --
    no habia forma de notar, mirando el dashboard, que casi todo habia
    fallado. Ahora dice cuantos temas de cuantos se consiguieron, y si algo
    fallo, el motivo exacto (gdelt.last_error, ver bug real arreglado en
    gdelt.py: antes solo se guardaba el error si TODO fallaba).

    BUG REAL (task #17): esta llamada real vivia SOLO en el hilo rapido
    (run_fast); un dia con GDELT rate-limited, el vencimiento del cache
    trabo el arranque del servidor mas de 9 minutos (medido: hasta 559s en
    un solo vencimiento) -- justo lo que el 'Pendiente conocido' de este
    archivo ya avisaba que podia pasar. Arreglado moviendo la llamada real
    al hilo trabajador (enrich_pass), igual que IA/contexto/social:
    modo_lectura=True (hilo rapido, Parte C): SOLO lee gdelt_cache.json,
    nunca llama a la red. Si el cache vencio se sigue usando igual (mejor
    un dato de hace unas horas que frenar el arranque del feed)."""
    if gdelt is None or os.environ.get("MONITOR_NO_GDELT") == "1":
        return {}, "desactivado"
    cache = {}
    try:
        with open(GDELT_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass
    # 'intentados'/'err' viajan DENTRO del cache (no solo 'g', los temas que
    # salieron bien): asi el hilo rapido puede reconstruir el mismo estado
    # honesto ("1/19 temas; resto: HTTP 429") leyendo el cache, en vez de
    # mostrar un "cache" plano que esconde que la mayoria de los temas
    # fallaron la ultima vez que el trabajador lo intento (bug real
    # relacionado: el mismo reclamo de "no lo tapes" que motivo el resto de
    # este estado honesto, ver docstring arriba).
    #
    # BUG REAL (Problema 3, diagnosticado con datos reales: gdelt_cache.json
    # en produccion solo tenia 1 tema -- "Ejecutivo" -- de los 20 posibles,
    # DESPUES DE DIAS corriendo): esta funcion escribia "g": data pisando el
    # diccionario ENTERO cada vez que el trabajador conseguia aunque sea un
    # exito parcial. Con GDELT devolviendo casi siempre 1/20 temas (429 en el
    # resto), cada pasada BORRABA los temas buenos de la pasada anterior en
    # vez de sumarse -- la "cobertura" del dashboard nunca podia acumular mas
    # de 1 tema. Arreglado: 'g' ahora se MERGEA (ultimo dato bueno por tema
    # persiste hasta que ese mismo tema se refresque con exito), con
    # 'g_ts' guardando CUANDO se consiguio cada tema por separado -- el
    # dashboard puede mostrar "dato de hace X horas" por tema en vez de
    # perderlo. Mismo patron que ya usaba get_contracts (SERCOP) para esto.
    def _estado_cache(prefijo="", n_pasada=None, n_tot_pasada=None):
        g_ts = cache.get("g_ts") or {}
        n_ok, err_ = len(cache.get("g") or {}), cache.get("err")
        edad = _edad_mas_vieja(g_ts)
        detalle = "%s (%d temas acumulados" % (prefijo or "cache", n_ok)
        if n_pasada is not None:
            detalle += ", %d/%d esta pasada" % (n_pasada, n_tot_pasada)
        if err_:
            detalle += "; resto: %s" % err_
        detalle += ")"
        if edad is not None:
            detalle += " — el mas viejo: hace %s" % _fmt_horas(edad)
        return detalle

    if time.time() - cache.get("ts", 0) < TREND_TTL and cache.get("g"):
        return cache["g"], _estado_cache()
    if modo_lectura:
        if cache.get("g"):
            return cache["g"], _estado_cache("cache vencido")
        if cache.get("ts_intento"):
            # BUG REAL: un corte largo de GDELT (429 sostenido, ej. hoy) hacia
            # que este mensaje se quedara en "esperando primera pasada del
            # trabajador" para SIEMPRE -- indistinguible de "el trabajador
            # todavia ni arranco". El trabajador SI lo intenta cada pasada
            # (ver mas abajo), esto deja el rastro de ese intento fallido.
            return {}, "sin datos aun (intentado, sigue fallando: %s)" % (cache.get("err") or "motivo desconocido")
        return {}, "esperando primera pasada del trabajador"
    term_of = {t: TREND_TERMS.get(t, t) for t in themes}
    data = gdelt.interest(term_of, geo=GDELT_GEO)
    err = getattr(gdelt, "last_error", None)
    if not data:
        # Se guarda el intento fallido (sin pisar 'g'/'g_ts'/'intentados'
        # viejos si habia datos buenos de una corrida anterior) para que
        # modo_lectura pueda reportarlo en vez de decir "esperando" para
        # siempre.
        try:
            registro = dict(cache)
            registro.update({"ts_intento": time.time(), "err": err or "sin datos"})
            with open(GDELT_CACHE, "w", encoding="utf-8") as f:
                json.dump(registro, f, ensure_ascii=False)
        except Exception:
            pass
        return cache.get("g", {}), "error: %s" % (err or "sin datos")
    ahora = time.time()
    merged_g = dict(cache.get("g") or {})
    merged_g.update(data)  # ultimo dato bueno por tema: nunca se pisa el resto
    g_ts = dict(cache.get("g_ts") or {})
    for t in data:
        g_ts[t] = ahora
    try:
        with open(GDELT_CACHE, "w", encoding="utf-8") as f:
            json.dump({"ts": ahora, "geo": GDELT_GEO, "g": merged_g, "g_ts": g_ts,
                       "intentados": len(term_of), "err": err}, f, ensure_ascii=False)
    except Exception:
        pass
    if err:
        return merged_g, ("ok (%d/%d temas esta pasada, %d acumulados; resto: %s)"
                           % (len(data), len(term_of), len(merged_g), err))
    return merged_g, "ok (%d/%d temas, %d acumulados)" % (len(data), len(term_of), len(merged_g))


# ------------------------- escucha social (Bluesky/Reddit) + OSINT -------------------------

def tema_ambito_map(stories):
    """Para cada tema presente, en que ambito geografico vive mayormente
    (jerarquico, igual que el resto del dashboard: guayaquil > ecuador >
    internacional). Un 'tema' de escucha social no es una historia -- es una
    categoria que puede tener notas locales E internacionales a la vez -- asi
    que se usa la senal MAS LOCAL entre todas las historias que lo llevan:
    si UNA sola historia de 'Crimen/Violencia' es de Guayaquil, el panel
    social agrupa ese tema en Guayaquil. Sirve para separar el panel "Pulso
    social" por Guayaquil/Ecuador/Internacional en vez de mezclar todo."""
    orden = {"guayaquil": 0, "ecuador": 1, "internacional": 2}
    out = {}
    for s in stories:
        amb = "guayaquil" if s.get("ciudad") == "Guayaquil" else ("ecuador" if s.get("es_local") else "internacional")
        for t in s.get("temas", []):
            if t not in out or orden[amb] < orden[out[t]]:
                out[t] = amb
    return out

SOCIAL_CACHE = os.path.join(HERE, "social_cache.json")
# Fase 12 (pedido de Fernando: "Pulso social desfasado, no recoge los temas en
# el momento"): bajado de 6h a 10 minutos. El trabajador (enrich_pass) ya
# reintenta cada ~20s (MONITOR_WORKER_PAUSA) -- 6h de TTL descartaba casi
# TODOS esos intentos, dejando el panel congelado horas enteras. Esta funcion
# NO llama a ningun LLM (_social_model() devuelve None en esta version, ver
# mas abajo), solo a redes publicas gratuitas/best-effort (Bluesky/Reddit/
# Mastodon/YouTube) -- bajar el TTL no agrega costo de API, solo mas trafico
# de red hacia esas fuentes, ya toleradas en el resto del proyecto.
SOCIAL_TTL = float(os.environ.get("MONITOR_SOCIAL_TTL", str(10 * 60)))
# Bug real (2026-09-23, cuarta pasada): un intento donde el OSINT fallo (ej.
# Ollama todavia no habia arrancado cuando partio el servidor) escribia el
# MISMO 'ts' global que un intento exitoso, asi que el panel quedaba sin
# lectura OSINT hasta 6h despues aunque Ollama ya estuviera disponible hace
# rato. Si el cache tiene algun tema con 'osint_error' y sin 'resumen', el
# TTL efectivo baja a este valor (20 min) en vez de las 6h completas, para
# que el trabajador lo reintente pronto -- no cambia el TTL normal cuando
# todo viene bien.
SOCIAL_OSINT_RETRY_TTL = float(os.environ.get("MONITOR_SOCIAL_OSINT_RETRY_MIN", "20")) * 60
SOCIAL_MAX = int(os.environ.get("MONITOR_SOCIAL_MAX", "5"))              # cuantos temas top consultar por corrida
SOCIAL_SUBREDDIT = os.environ.get("MONITOR_SOCIAL_SUB", "ecuador")
# YouTube (search.list) cuesta 100 de las 10.000 unidades/dia de cuota: se
# limita a MONITOR_YT_MAX_BUSQ busquedas por PASADA del trabajador (no una por
# tema como Bluesky/Reddit, que son gratis), aunque SOCIAL_MAX permita mas
# temas. Los temas que se quedan sin cupo igual se consultan en Bluesky/Reddit.
YT_MAX_BUSQ = int(os.environ.get("MONITOR_YT_MAX_BUSQ", "5"))

def _social_query(term, ambito):
    """Ajusta el termino de busqueda social segun el ambito del TEMA (no de una
    historia puntual). BUG REAL detectado en vivo: el tema 'Ambiente' quedaba
    con ambito 'guayaquil' (por notas locales genuinas, ej. mineria en
    Quimsacocha) pero la busqueda social usaba el termino generico del tema
    ('medio ambiente' sale de TREND_TERMS) -- en Bluesky/YouTube eso lo domina
    la conversacion de otros paises con mucho mas volumen (se vio trayendo
    politica MEXICANA -- PRI, Morena, Tren Maya -- bajo un tema marcado como
    Guayaquil). Para temas locales, se agrega 'Ecuador' al termino: Bluesky lo
    usa en la busqueda de texto completo, y YouTube ya combina con
    regionCode=EC (ver social.py) asi que el termino ayuda a reforzar, no a
    reemplazar esa señal. Reddit ya esta acotado al subreddit (SOCIAL_SUBREDDIT,
    'ecuador' por defecto) asi que no necesita el agregado."""
    if ambito in ("ecuador", "guayaquil"):
        return term + " Ecuador"
    return term

def _post_es_foraneo(p):
    """Filtro de RESPALDO (ademas de _social_query) para temas locales: un post
    que menciona claramente OTRO pais y ninguna señal de Ecuador se descarta.
    No es perfecto -- un comentario puede hablar de politica extranjera sin
    nombrar el pais (ej. solo 'PRI'/'Morena', partidos mexicanos, sin decir
    'Mexico') y a eso no llega este filtro de texto; por eso la query scopeada
    arriba es la defensa principal, esto es la segunda capa."""
    texto = p.texto or ""
    return is_foreign(texto) and not is_ecuador(texto)

# Fase 18 (P1-7): en el Pulso LOCAL un post cuenta solo con senal POSITIVA
# de aqui (menciona Ecuador, una ciudad, un barrio de Guayaquil o una entidad
# de la historia). Antes alcanzaba con "no nombra otro pais"
# (_post_es_foraneo) -- y medido el 2026-09-30, los 20 temas mostraban posts
# de Espana, Chile, Venezuela y Eslovaquia etiquetados como "guayaquil".
SOCIAL_LOCAL_H = float(os.environ.get("MONITOR_SOCIAL_LOCAL_H", "48"))


def _post_senal_local(p, entidades=()):
    texto = p.texto or ""
    if is_ecuador(texto) or ciudades_en(texto):
        return True
    blob = norm(texto)
    if alertas is not None and any(geo_hit(t, blob) for ts in alertas.BARRIOS_GYE.values() for t in ts):
        return True
    return any(len(n) >= 3 and geo_hit(n, blob) for n in entidades)


def _filtrar_pulso_local(posts, entidades=()):
    """Posts que sirven para un Pulso local: con senal de aqui y de las
    ultimas SOCIAL_LOCAL_H horas (con hora real, ver social._iso_completo)."""
    return [p for p in posts if _post_senal_local(p, entidades)
            and social._es_reciente(p.fecha, horas=SOCIAL_LOCAL_H)]


def _dias_desde(fecha):
    """Antiguedad de 'fecha' (YYYY-MM-DD) en dias. Sin fecha valida se trata
    como MUY vieja (9999): no se puede confirmar que sea reciente, asi que no
    debe ganarle a nada por 'antiguedad desconocida' en _social_score."""
    if not fecha:
        return 9999
    try:
        f = dt.datetime.strptime(fecha[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return 9999
    return max(0, (now_utc() - f).days)

def _social_score(p):
    """Puntaje para elegir la 'mejor' publicacion de una fuente: RECENCIA +
    engagement, no solo engagement (Frente A). Bug real: Bluesky con
    sort=top rankeaba por likes de TODA la historia del termino sin ventana
    de tiempo -- la 'mejor' publicacion de un tema podia ser de anios atras.
    Ya se filtra por SOCIAL_DIAS antes de llegar aca (social.recolectar), asi
    que esto es el segundo paso: DENTRO de esa ventana, una publicacion mas
    vieja pesa menos. Decaimiento lineal simple, no una formula elaborada:
    peso 1.0 el dia de hoy, peso 0.5 en el borde de la ventana (SOCIAL_DIAS)."""
    ventana = max(social.SOCIAL_DIAS, 1)
    peso = 1.0 - 0.5 * min(_dias_desde(p.fecha), ventana) / ventana
    return (p.likes + p.reposts) * peso

def _social_model():
    """Modelo para el analisis OSINT de redes (social.analizar_osint).

    Fase 10 (migracion a la nube): Ollama se retiro, y social.analizar_osint
    sigue apuntando a localhost:11434 (social.py queda intacto a proposito:
    su recoleccion es de las piezas protegidas). Devolver None hace que
    get_social() NO llame al OSINT -- asi ningun Ollama que siga instalado
    en la PC vuelve a cargar un modelo en la GPU por esta via. La lectura
    OSINT vuelve en la Fase 3, pasando por ia.py."""
    return None

def _temas_por_relevancia(themes, tema_ambito, max_temas):
    """Elige que temas consultar esta pasada del pulso social (Problema 1,
    BUG REAL grave encontrado en vivo 2026-09-23: 'themes[:SOCIAL_MAX]' tomaba
    SIEMPRE los primeros N en orden alfabetico -- confirmado con
    social_cache.json real: 'Ambiente', 'Asamblea/Leyes', 'Carceles',
    'Comercio/Inversion', 'Crimen/Violencia' (los primeros 5 alfabeticos de
    'themes_present', que YA llega ordenado con sorted()) aparecian SIEMPRE,
    y los otros 15 temas JAMAS se consultaban, pasada tras pasada, sin
    importar cuanto tiempo pasara. Esto explica de raiz la queja "el pulso
    social no diferencia bien Ecuador/Guayaquil/Internacional": si por pura
    casualidad alfabetica ningun tema de un ambito caia en ese prefijo fijo,
    ese ambito JAMAS tenia una sola publicacion, para siempre -- no un
    problema intermitente, sino una exclusion total y permanente.

    Documentado antes como resuelto con una funcion '_temas_por_relevancia()'
    que en realidad nunca se habia escrito (mismo patron que el bug de
    ia.interpretar() nunca conectado, ver Problema 1 de la ronda anterior).
    Esta es la implementacion real: garantiza AL MENOS un tema de CADA
    ambito presente (Guayaquil/Ecuador/Internacional), elegido al azar
    dentro de ese ambito (no el primero alfabetico); el resto de los cupos
    se llena tambien al azar entre lo que sobra -- asi, en el tiempo, todos
    los temas de todos los ambitos tienen chance real de aparecer."""
    por_ambito = {}
    for t in themes:
        amb = (tema_ambito or {}).get(t, "internacional")
        por_ambito.setdefault(amb, []).append(t)
    elegidos = []
    ambitos = list(por_ambito.keys())
    random.shuffle(ambitos)
    for amb in ambitos:
        if len(elegidos) >= max_temas:
            break
        candidatos = por_ambito[amb]
        random.shuffle(candidatos)
        elegidos.append(candidatos[0])
    resto = [t for t in themes if t not in elegidos]
    random.shuffle(resto)
    elegidos += resto[:max(0, max_temas - len(elegidos))]
    return elegidos

def get_social(themes, modo_lectura=False, tema_ambito=None):
    """Escucha social por tema (Bluesky publico + Reddit + YouTube) con lectura
    OSINT via Ollama. Devuelve ({tema: {sentimiento, polarizacion,
    temas_recurrentes, resumen, n_posts, por_fuente:{fuente:n}, ambito,
    top:[{fuente,autor,texto,url,likes,reposts}]}}, estado). Acotado a
    SOCIAL_MAX temas y cacheado por SOCIAL_TTL: es la parte mas lenta (red +
    LLM). No rompe si falla.

    'top' NUNCA rankea por engagement crudo mezclando plataformas (los likes
    de YouTube y los reposts de Bluesky no son comparables: una sola
    plataforma se comeria el top) -- muestra la MEJOR publicacion de CADA
    fuente presente, garantizando representacion de todas.

    'tema_ambito' (de tema_ambito_map) le pone a cada tema su ambito
    geografico, para que el panel "Pulso social" pueda separarlo por
    Guayaquil/Ecuador/Internacional en vez de mezclar todo en una lista.

    modo_lectura=True (hilo rapido, Parte C): devuelve lo que haya en cache
    (aunque este vencido) SIN disparar ninguna consulta de red -- el refresco
    real lo hace el hilo trabajador."""
    if social is None or os.environ.get("MONITOR_NO_SOCIAL") == "1":
        return {}, "desactivado"
    cache = {}
    try:
        with open(SOCIAL_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass
    if modo_lectura:
        if not cache.get("s"):
            return {}, "sin datos aun"
        edad = _edad_mas_vieja(cache.get("s_ts") or {})
        detalle = " (%d temas" % len(cache["s"])
        if edad is not None:
            detalle += ", el mas viejo: hace %s" % _fmt_horas(edad)
        detalle += ")"
        return cache["s"], "cache" + detalle
    ttl_efectivo = SOCIAL_TTL
    if any(e.get("osint_error") and not e.get("resumen") for e in (cache.get("s") or {}).values()):
        ttl_efectivo = min(SOCIAL_TTL, SOCIAL_OSINT_RETRY_TTL)
    if time.time() - cache.get("ts", 0) < ttl_efectivo and cache.get("s"):
        return cache["s"], "cache"

    tema_ambito = tema_ambito or {}
    modelo = _social_model()  # una sola deteccion por corrida, no una por tema
    elegidos = _temas_por_relevancia(themes, tema_ambito, SOCIAL_MAX)
    term_of = {t: TREND_TERMS.get(t, t) for t in elegidos}
    out, errs, yt_usadas = {}, [], 0
    for i, (tema, term) in enumerate(term_of.items()):
        ambito = tema_ambito.get(tema, "internacional")
        query = _social_query(term, ambito)
        try:
            if i:
                time.sleep(1)  # gentil con los endpoints
            usar_yt = yt_usadas < YT_MAX_BUSQ
            # 'ambito' (Problema 1): social.recolectar usa esto para elegir
            # subreddit(s) y regionCode/relevanceLanguage de YouTube por
            # alcance (Internacional/Ecuador/Guayaquil) en vez de siempre
            # Ecuador -- ver social.REDDIT_SUB_POR_AMBITO/YT_REGION_POR_AMBITO.
            # 'term_base' (bug real 2026-09-23): Mastodon busca por hashtag,
            # necesita el termino SIN el sufijo "Ecuador" que 'query' ya
            # lleva para Bluesky/YouTube (ver social.recolectar).
            posts, perr = social.recolectar(query, subreddit=SOCIAL_SUBREDDIT, limite=15,
                                             youtube=usar_yt, ambito=ambito, term_base=term)
            if usar_yt:
                yt_usadas += 1
            if perr:
                errs.extend(perr)
            if ambito in ("ecuador", "guayaquil"):
                posts = _filtrar_pulso_local(posts)
            if not posts:
                # igual se registra el tema (con 0 posts): asi el panel puede
                # mostrar "sin conversacion captada" en vez de no decir nada,
                # distinguiendo "lo intentamos y no habia nada" de "todavia no
                # se intento" (temas fuera de SOCIAL_MAX).
                out[tema] = {"n_posts": 0, "n_personas": 0, "n_medios": 0, "top": [], "por_fuente": {}, "ambito": ambito}
                continue
            # BUG REAL encontrado en vivo (Problema 1): el dashboard ya tenia
            # el bloque "vozTxt" listo para mostrar personas vs. cuentas de
            # medios (d.n_personas/d.n_medios), pero monitor.py nunca
            # calculaba esos dos numeros -- el bloque quedaba SIEMPRE oculto
            # (`d.n_personas!=null` nunca era verdad). Confirmado con datos
            # reales: ningun tema de social_cache.json/data.json tenia esas
            # claves. Ahora se calculan, y el OSINT ("que dice la gente")
            # corre SOLO sobre personas si hay >=3 -- si no, se avisa en el
            # propio texto en vez de mezclar en silencio la voz de los medios
            # con la de la gente.
            personas = [p for p in posts if p.tipo == "persona"]
            n_personas, n_medios = len(personas), len(posts) - len(personas)
            posts_osint = personas if len(personas) >= 3 else posts
            osint = social.analizar_osint(posts_osint, modelo=modelo) if modelo else None
            osint_error = None
            if osint is None and modelo:
                # un solo reintento: Ollama a veces devuelve JSON mal formado
                # de forma transitoria (hipo puntual, no falta de modelo) y con
                # esto se recupera casi siempre sin gastar mucho mas tiempo.
                osint = social.analizar_osint(posts_osint, modelo=modelo)
            if osint is None and modelo:
                # BUG REAL (reportado por Fernando: tema "Ambiente" con 119
                # posts salio con sentimiento=None, sin ninguna pista de por
                # que): antes, si los DOS intentos fallaban, el motivo real
                # (social.last_error: timeout, HTTP, JSON mal formado
                # persistente) se perdia -- el dashboard solo podia mostrar un
                # generico "puede faltar Ollama o haber fallado la lectura
                # puntual". Ahora se guarda el error real de este intento
                # puntual en el propio 'entry' del tema, para mostrarlo tal
                # cual en vez de adivinar.
                osint_error = getattr(social, "last_error", None) or "motivo desconocido"

            por_fuente = {}
            for p in posts:
                por_fuente[p.fuente] = por_fuente.get(p.fuente, 0) + 1
            # mejor post de CADA fuente (por su propio puntaje, no cruzado):
            # recencia + engagement (_social_score), no solo engagement --
            # ver Frente A. Nunca compara entre fuentes (likes de YouTube y
            # reposts de Bluesky no son comparables). Ademas de "la mejor de
            # cada fuente" (como antes), se separa la mejor de PERSONA y la
            # mejor de MEDIO por fuente cuando hay las dos -- asi "Lo que
            # dice la gente" (Problema 1) siempre puede mostrar una voz
            # ciudadana real, no solo lo que ya ganaba por engagement (los
            # medios suelen tener mas likes/reposts que una persona suelta).
            mejor = {}
            for p in posts:
                clave = (p.fuente, p.tipo)
                cur = mejor.get(clave)
                if cur is None or _social_score(p) > _social_score(cur):
                    mejor[clave] = p
            orden_fuente = {"bluesky": 0, "reddit": 1, "youtube": 2, "mastodon": 3, "telegram": 4}
            top = [{"fuente": p.fuente, "autor": p.autor, "texto": p.texto[:200],
                    "url": p.url, "likes": p.likes, "reposts": p.reposts, "fecha": p.fecha,
                    "tipo": p.tipo, "canal": p.canal, "canal_tipo": p.canal_tipo, "canal_subs": p.canal_subs}
                   for p in sorted(mejor.values(),
                                    key=lambda p: (orden_fuente.get(p.fuente, 9), p.tipo != "persona"))]

            entry = {"n_posts": len(posts), "n_personas": n_personas, "n_medios": n_medios,
                      "top": top, "por_fuente": por_fuente, "ambito": ambito}
            if osint:
                entry.update({
                    "sentimiento": osint.get("sentimiento_general", ""),
                    "polarizacion": osint.get("polarizacion", ""),
                    "temas_recurrentes": osint.get("temas_recurrentes", []),
                    "resumen": osint.get("resumen_discusion", ""),
                })
            elif osint_error:
                entry["osint_error"] = osint_error
            out[tema] = entry
        except Exception as e:
            errs.append(type(e).__name__)

    if not out:
        motivo = errs[0] if errs else "sin datos"
        return cache.get("s", {}), "error: %s" % motivo
    # BUG REAL (Problema 3, mismo patron que get_gdelt/get_demand): esta
    # funcion solo procesa SOCIAL_MAX (def. 5) temas por pasada, pero
    # escribia "s": out pisando el diccionario ENTERO -- los otros ~15 temas
    # que habian quedado bien en una pasada anterior desaparecian del panel
    # "Pulso social" en la pasada siguiente, aunque su dato todavia fuera
    # valido. Medido en vivo: social_cache.json solo tenia 5 temas de los 20
    # posibles. Ahora se MERGEA por tema (last-known-good), con 's_ts'
    # guardando cuando se refresco cada uno.
    ahora = time.time()
    merged_s = dict(cache.get("s") or {}); merged_s.update(out)
    s_ts = dict(cache.get("s_ts") or {})
    for t in out:
        s_ts[t] = ahora
    try:
        with open(SOCIAL_CACHE, "w", encoding="utf-8") as f:
            json.dump({"ts": ahora, "s": merged_s, "s_ts": s_ts}, f, ensure_ascii=False)
    except Exception:
        pass
    con_osint = sum(1 for e in out.values() if e.get("resumen"))
    if con_osint:
        return merged_s, "ok (%d/%d temas esta pasada, OSINT en %d, %d acumulados)" % (
            len(out), len(term_of), con_osint, len(merged_s))
    return merged_s, "ok (%d/%d temas esta pasada, %d acumulados, sin OSINT: Ollama sin modelo)" % (
        len(out), len(term_of), len(merged_s))


# ------------------------- Fase 9, Problema C: Pulso social anclado a historias -------------------------
# Diagnostico real (ver CLAUDE.md "Fase 9"): el panel de arriba (get_social)
# consulta por TEMA ABSTRACTO ("Ambiente", "Asamblea/Leyes") -- Bluesky/
# Mastodon devuelven de vuelta la conversacion GLOBAL de esa palabra (Armenia,
# Venezuela, Delcy Rodriguez bajo "Asamblea/Leyes"; manchas de petroleo del
# mundo bajo "Ambiente"), sin ningun hilo real, solo publicaciones sueltas.
# Rediseño: anclar la escucha a las HISTORIAS locales mas importantes de HOY
# (no a la categoria), buscando por sus ENTIDADES puntuales (nombres, siglas,
# lugar especifico -- las mismas señales que ya usa el agrupamiento de la
# Parte A), con un filtro de PERTENENCIA explicito (un post que no menciona
# ninguna entidad de la historia ni tiene señal de Ecuador se descarta y
# queda CONTADO, no oculto en silencio) y mostrando POSTURAS con citas reales
# en vez de un resumen unico. get_social()/SOCIAL_CACHE (arriba) NO se tocan
# -- Oportunidades (renderGap) sigue usando esa data por tema para el calculo
# de brecha, documentado en "Decisiones ya tomadas"; esto es una pieza NUEVA
# para el panel Pulso social, no un reemplazo del dato que ya usa otro panel.

SOCIAL_HIST_CACHE = os.path.join(HERE, "social_historias_cache.json")
SOCIAL_HIST_MAX = int(os.environ.get("MONITOR_SOCIAL_HIST_MAX", "6"))   # historias por pasada del trabajador
# Fase 12 (mismo pedido que SOCIAL_TTL arriba): bajado de 6h a 20 minutos --
# menos agresivo que SOCIAL_TTL porque esta funcion SI llama a Gemini
# (ia.clasificar_posturas) por cada historia top con posts reales, y el
# proyecto ya trackea gasto real de la API (ver ia_gasto.json/estado_ia_nube)
# con topes diarios/mensuales -- 20 min sigue siendo mucho mas "tiempo real"
# que 6h, sin multiplicar el gasto de golpe.
SOCIAL_HIST_TTL = float(os.environ.get("MONITOR_SOCIAL_HIST_TTL", str(20 * 60)))

def _entidades_historia(s):
    """Nombres propios/siglas del titular (ver Problema A2) + ciudad
    especifica -- la busqueda social de esta historia se arma con ESTO, nunca
    con el nombre de la categoria (esa era la causa real del ruido)."""
    nombres = sorted(_nombres_propios(s.get("titular", "")) - EVENTO_GENERICO - LUGARES_COMUNES)
    ciudad = s.get("ciudad") or detect_city(s.get("titular", "") + " " + s.get("resumen", ""))
    return nombres, ciudad

def _social_query_historia(s):
    nombres, ciudad = _entidades_historia(s)
    partes = list(nombres[:3])
    if not partes:
        # sin nombre propio identificable: mejor buscar por las palabras de
        # contenido mas especificas del titular que no buscar nada.
        partes = sorted(tokens(s.get("titular", "")), key=len, reverse=True)[:3]
    lugar = ciudad or ("Ecuador" if s.get("es_local") else "")
    if lugar and lugar.lower() not in (p.lower() for p in partes):
        partes.append(lugar)
    return " ".join(partes), nombres, ciudad

def _post_pertenece_historia(p, nombres, ciudad):
    """Filtro de pertenencia (Problema C2): un post solo cuenta si menciona
    una entidad de ESTA historia, la ciudad de la historia, o tiene una señal
    clara de Ecuador -- nunca "porque salio en la busqueda", que es lo que
    traia ruido global (politica de otro pais bajo un tema marcado Ecuador)."""
    blob = norm(p.texto or "")
    if any(geo_hit(n, blob) for n in nombres if len(n) >= 3):
        return True
    if ciudad and geo_hit(ciudad, blob):
        return True
    return is_ecuador(p.texto or "")

def _historias_top_social(stories, max_hist):
    """Guayaquil primero, despues Ecuador -- mismo orden pedido para el
    Pulso social. Dentro de cada grupo, se respeta el orden de 'interes' que
    ya trae 'stories' (build_stories ya las ordena asi)."""
    gye = [s for s in stories if s.get("ciudad") == "Guayaquil"]
    ecu = [s for s in stories if s.get("es_local") and s.get("ciudad") != "Guayaquil"]
    return (gye + ecu)[:max_hist]

# Fase 9, parte D3 -- hallazgo real: la simulacion de xapi/redes eligiendo
# top-Guayaquil-primero dio 3 de 6 historias que eran boletines de plantilla
# (2 pronosticos del clima + "Fenomeno de El Niño") -- gastar presupuesto de
# X/TikTok ahi es desperdiciarlo en ruido de baja prioridad periodistica.
def _es_boletin_plantilla(s):
    """Fase 18 (P1-5.5): solo pronosticos del clima y portadas son
    "plantilla". Antes tambien sacaba de X toda historia con un servicio
    mencionado (cortes de agua/luz) y todo lo de El Nino -- justo lo
    comunitario: inundaciones, cortes y afectaciones SON la noticia local."""
    texto = s.get("titular", "") + " " + s.get("resumen", "")
    blob = norm(texto)
    if _es_pronostico_clima(blob) or re.search(r"\b(pronostico|tendra lluvias|clima hoy)\b", blob):
        return True
    if _es_portada_o_noticiero(norm(s.get("titular", ""))):
        return True
    return False


# Fase 18 (P1-5.1): palabras REALES (con tilde) para buscar alertas en X --
# nunca la clave interna ("corte_luz"), que es lo que se mandaba antes.
TERMINOS_X_POR_TIPO = {
    "inundacion": ["inundación", "inundado", "anegado", "anegada", "calles inundadas"],
    "lluvias": ["inundación", "anegado", "anegada", "lluvia", "aguacero", "acumulación de agua"],
    "corte_luz": ["corte de luz", "sin luz", "apagón"],
    "corte_agua": ["corte de agua", "sin agua"],
    "cortes": ["corte de agua", "sin agua", "corte de luz", "sin luz", "apagón"],
    "incendio": ["incendio"],
    "balacera": ["balacera", "disparos", "tiroteo"],
    "violencia": ["balacera", "disparos", "ataque armado", "sicariato"],
    "accidente": ["choque", "accidente de tránsito", "volcamiento"],
    "protesta": ["protesta", "plantón", "bloqueo de vía"],
    "protestas": ["protesta", "plantón", "bloqueo de vía"],
    "sismo": ["sismo", "temblor"],
}
_TIPOS_ALERTA_X = ["inundacion", "corte_luz", "corte_agua", "incendio", "balacera", "accidente", "protesta", "sismo"]


def terminos_alerta_x():
    vistos, out = set(), []
    for tipo in _TIPOS_ALERTA_X:
        for t in TERMINOS_X_POR_TIPO[tipo]:
            if t not in vistos:
                vistos.add(t)
                out.append(t)
    return out


def terminos_evento_x(tipo):
    return list(TERMINOS_X_POR_TIPO.get(tipo) or terminos_alerta_x())


def consulta_x_historia(s):
    """Fase 18 (P1-5.4): consulta de X para UNA historia solo con entidades
    reales -- nombres propios, siglas o barrios. Antes tomaba como "nombre
    propio" la primera palabra del titular (siempre va con mayuscula en
    espanol): salian consultas como "hasta Guayaquil", "ataque Guayaquil" o
    "fuerte Guayaquil". Sin una entidad buena devuelve None (no se gasta)."""
    titular = s.get("titular", "") or ""
    resumen = s.get("resumen", "") or ""
    nombres = set(_nombres_propios(titular)) - EVENTO_GENERICO - LUGARES_COMUNES
    palabras = titular.split()
    if palabras:
        primera = norm(palabras[0])
        resto = " ".join(palabras[1:]) + " " + resumen
        # la primera palabra cuenta solo si tambien aparece con mayuscula en
        # otro lado (o es una sigla/lugar conocido)
        if primera in nombres and not re.search(r"\b" + re.escape(palabras[0].strip(":,.")) + r"\b", resto) \
                and primera not in {norm(x) for x in _siglas(titular)} and not ciudades_en(palabras[0]):
            nombres.discard(primera)
    partes = sorted(nombres, key=len, reverse=True)[:3]
    if alertas is not None:
        sector = alertas.detectar_lugar(titular + " " + resumen)
        if sector and not sector.startswith("Guayaquil") and norm(sector) not in partes:
            partes.append(sector)
    if not partes:
        return None
    lugar = s.get("ciudad") or ("Ecuador" if s.get("es_local") else "")
    if lugar and norm(lugar) not in {norm(p) for p in partes}:
        partes.append(lugar)
    return " ".join(partes)

def _historias_top_redes(stories, max_hist):
    """Mismo orden que _historias_top_social (Guayaquil primero), pero
    descarta boletines de plantilla ANTES de recortar al tope -- para no
    gastar presupuesto real de X/TikTok en ellos."""
    candidatas = _historias_top_social(stories, max_hist * 4)
    filtradas = [s for s in candidatas if not _es_boletin_plantilla(s)]
    return filtradas[:max_hist]

def get_social_historias(stories, modo_lectura=False):
    """Pulso social anclado a historias (Problema C). Devuelve
    ({historia_key: {titular, n_posts, n_descartados, por_fuente, posturas,
    hilo_principal, top}}, estado). Cachea por historia_key (fuentes[0].link,
    mismo criterio que ia_cache/contexto_cache) -- sobrevive a que la
    historia deje de estar en el top de esta pasada."""
    if social is None or os.environ.get("MONITOR_NO_SOCIAL") == "1":
        return {}, "desactivado"
    cache = {}
    try:
        with open(SOCIAL_HIST_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        pass

    if modo_lectura:
        if not cache.get("h"):
            return {}, "sin datos aun"
        return cache["h"], "cache (%d historias)" % len(cache["h"])

    top = _historias_top_social(stories, SOCIAL_HIST_MAX)
    modelo = _social_model()
    out = dict(cache.get("h") or {})
    ts_por_key = dict(cache.get("h_ts") or {})
    ahora = time.time()
    procesadas, errs = 0, []
    for s in top:
        f0 = (s.get("fuentes") or [{}])[0]
        key = (f0.get("link") or s["titular"])[:180]
        if ahora - ts_por_key.get(key, 0) < SOCIAL_HIST_TTL:
            continue  # todavia fresco, no gastar red de nuevo
        query, nombres, ciudad = _social_query_historia(s)
        ambito = "guayaquil" if s.get("ciudad") == "Guayaquil" else "ecuador"
        try:
            posts, perr = social.recolectar(query, subreddit=SOCIAL_SUBREDDIT, limite=20,
                                             youtube=True, ambito=ambito, term_base=query)
            if perr:
                errs.extend(perr)
        except Exception as e:
            errs.append(type(e).__name__)
            continue
        n_total = len(posts)
        pertenecen = [p for p in posts if _post_pertenece_historia(p, nombres, ciudad)
                      and social._es_reciente(p.fecha, horas=SOCIAL_LOCAL_H)]
        n_descartados = n_total - len(pertenecen)
        if not pertenecen:
            out[key] = {"titular": s.get("titular", ""), "n_posts": 0, "n_descartados": n_descartados,
                        "por_fuente": {}, "posturas": [], "hilo_principal": None, "top": [],
                        "ambito": ambito}
            ts_por_key[key] = ahora
            procesadas += 1
            continue
        por_fuente = {}
        for p in pertenecen:
            por_fuente[p.fuente] = por_fuente.get(p.fuente, 0) + 1
        # Postura (Problema C3): tarea CHICA para el modelo -- clasificar,
        # nunca resumir. Cada post recibe un id corto y estable (indice) para
        # que la IA pueda citarlo; cualquier postura sin ids REALES se
        # descarta (candado en ia.py, reforzado aca).
        posts_con_id = [{"id": str(i), "texto": p.texto, "_post": p} for i, p in enumerate(pertenecen)]
        posturas_r = ia.clasificar_posturas(s.get("titular", ""), s.get("resumen", ""),
                                             [{"id": pc["id"], "texto": pc["texto"]} for pc in posts_con_id],
                                             forzado=IA_MODEL) if ia else None
        by_id = {pc["id"]: pc["_post"] for pc in posts_con_id}
        posturas = []
        if posturas_r:
            for grp in posturas_r:
                ids_validos = [i for i in grp["ids"] if i in by_id]
                if not ids_validos:
                    continue  # segundo candado: el id tiene que existir de VERDAD en esta pasada
                citas = [{"autor": by_id[i].autor, "texto": by_id[i].texto[:200], "url": by_id[i].url,
                          "fuente": by_id[i].fuente} for i in ids_validos[:3]]
                posturas.append({"postura": grp["postura"], "n": len(ids_validos), "citas": citas})
        # Hilo principal: el post con mas respuestas/comentarios propios (lo
        # que social.py YA trae, comentarios_n/comentarios) -- no se inventa
        # un mecanismo de hilos nuevo, se usa el dato que ya existia.
        con_comentarios = [p for p in pertenecen if p.comentarios_n or p.comentarios]
        hilo = None
        if con_comentarios:
            principal = max(con_comentarios, key=lambda p: p.comentarios_n or len(p.comentarios or []))
            hilo = {"autor": principal.autor, "texto": principal.texto[:280], "url": principal.url,
                    "fuente": principal.fuente, "respuestas": (principal.comentarios or [])[:5]}
        orden_fuente = {"bluesky": 0, "reddit": 1, "youtube": 2, "mastodon": 3, "telegram": 4}
        mejor = {}
        for p in pertenecen:
            clave = (p.fuente, p.tipo)
            cur = mejor.get(clave)
            if cur is None or _social_score(p) > _social_score(cur):
                mejor[clave] = p
        top_posts = [{"fuente": p.fuente, "autor": p.autor, "texto": p.texto[:200], "url": p.url,
                      "likes": p.likes, "reposts": p.reposts, "fecha": p.fecha, "tipo": p.tipo}
                     for p in sorted(mejor.values(), key=lambda p: (orden_fuente.get(p.fuente, 9), p.tipo != "persona"))]
        out[key] = {"titular": s.get("titular", ""), "n_posts": len(pertenecen), "n_descartados": n_descartados,
                    "por_fuente": por_fuente, "posturas": posturas, "hilo_principal": hilo, "top": top_posts,
                    "ambito": ambito}
        ts_por_key[key] = ahora
        procesadas += 1

    try:
        with open(SOCIAL_HIST_CACHE, "w", encoding="utf-8") as f:
            json.dump({"h": out, "h_ts": ts_por_key}, f, ensure_ascii=False)
    except Exception:
        pass
    detalle = " -- errores: %s" % "; ".join(errs[:3]) if errs else ""
    return out, "ok (%d/%d historias esta pasada, %d acumuladas)%s" % (
        procesadas, len(top), len(out), detalle)


# ------------------------- Parte C: Guardadas / para reportaje -------------------------
# A diferencia de los caches (ia_cache.json, contexto_cache.json, etc.), este
# archivo es CONTENIDO DEL USUARIO, no algo recalculable: guarda la historia
# COMPLETA (titular, resumen, ia, contexto, fuentes...) tal como estaba al
# momento de guardarla, para que sobreviva aunque la noticia caduque del feed
# (MAX_AGE_DAYS) o el dashboard se regenere. Se escribe con archivo temporal +
# os.replace (en vez del json.dump directo que usan los caches) porque perder
# esto es peor: son notas que Fernando eligio a mano para un reportaje.

SAVED_PATH = os.path.join(HERE, "saved.json")

def load_saved():
    try:
        with open(SAVED_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_saved(items):
    tmp = SAVED_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SAVED_PATH)

# BUG REAL (2026-09-23, cuarta pasada, Problema 6, el mas grave del
# diagnostico): el frontend (dashboard_template.html) ya mandaba las notas a
# POST /api/nota y esperaba leer notas.json -- pero esa ruta NUNCA se
# implemento en el servidor (_do_POST solo conocia /api/guardar y /api/chat).
# Cada nota que Fernando escribia recibia un 404 y se perdia al instante; no
# era el problema de clave inestable que sospechaba (aunque ESE tambien era
# real por separado, ver el reordenamiento de 'fuentes' en build_stories: la
# clave ahora usa la fuente mas VIEJA del grupo, mas estable entre corridas).
# Mismo patron que saved.json: contenido del usuario, no un cache
# recalculable, se escribe con archivo temporal + os.replace. Estructura:
# {clave_de_historia_o_"tema:<nombre>": {"texto":..., "titular":..., "ts":...}}.
NOTAS_PATH = os.path.join(HERE, "notas.json")

def load_notas():
    try:
        with open(NOTAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_notas(notas):
    tmp = NOTAS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notas, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NOTAS_PATH)

def story_key(h):
    """Misma idea que las claves de cache (get_ia/get_contexto/...): el link de
    la primera fuente, o el titular si no hay link. Es la MISMA formula del
    lado del cliente (dashboard_template.html) para que ambos calculen la
    misma clave sin coordinarse por otra via."""
    f0 = (h.get("fuentes") or [{}])[0]
    return (f0.get("link") or h.get("titular") or "")[:180]


# ---------------- Fase 7, Paso D: puente Dashboard -> Asistente de casos ----------------
# Determinista, SIN IA (pedido explicito): si una historia (o un contrato
# SERCOP ya colgado de ella por get_contracts, mas arriba en el pipeline)
# nombra una entidad/alias de un caso ABIERTO, se crea un aviso con enlace a
# la fuente. Corre al final de run_fast, cuando cada 's' ya tiene todo lo
# que el trabajador dejo listo (contexto/contratos/etc.) -- asi una sola
# pasada cubre "feed, SERCOP, GDELT, social" sin repetir logica de busqueda
# por cada fuente por separado.

def revisar_casos_avisos(stories):
    if casos is None:
        return
    ids = [c["id"] for c in casos.listar_casos()]
    if not ids:
        return
    reglas = []  # (caso_id, alias, nombre_canonico)
    for caso_id in ids:
        for alias, nombre in casos.entidades_y_alias(caso_id):
            # mismo umbral que geo_hit()/EC_TERMS: un alias de 1-2 letras
            # colisionaria con cualquier texto, no sirve para identificar nada.
            if len(alias.strip()) >= 3:
                reglas.append((caso_id, alias, nombre))
    if not reglas:
        return
    conf_movil = movil.cargar_config() if movil else None
    push_casos = bool(conf_movil and conf_movil.get("avisos_activos") and conf_movil.get("avisos_casos_activos"))
    for s in stories:
        blob = norm(s.get("titular", "") + " " + s.get("resumen", ""))
        f0 = (s.get("fuentes") or [{}])[0]
        link, medio = f0.get("link", ""), f0.get("medio", f0.get("outlet", ""))
        for caso_id, alias, nombre in reglas:
            if not geo_hit(alias, blob):
                continue
            if casos.ya_avisado(caso_id, nombre, link):
                continue
            aviso = casos.agregar_aviso(caso_id, {
                "tipo": "historia", "entidad": nombre, "origen_key": link,
                "texto": "\"%s\" menciona a %s." % (s.get("titular", "")[:160], nombre),
                "fuente": {"tipo": "historia", "titulo": s.get("titular", ""), "link": link, "medio": medio},
            })
            if push_casos:
                caso_titulo = next((c.get("titulo", "") for c in casos.listar_casos() if c["id"] == caso_id), "")
                movil.enviar(conf_movil, "Caso: %s" % caso_titulo, aviso["texto"],
                              prioridad=3, etiquetas=["mag"], click=link or "")
        for contrato in (s.get("contratos") or []):
            try:
                blob_c = norm(json.dumps(contrato, ensure_ascii=False))
            except Exception:
                continue
            clave_contrato = "sercop:%s" % (contrato.get("ocid") or contrato.get("id") or contrato.get("link") or link)
            for caso_id, alias, nombre in reglas:
                if not geo_hit(alias, blob_c):
                    continue
                if casos.ya_avisado(caso_id, nombre, clave_contrato):
                    continue
                aviso = casos.agregar_aviso(caso_id, {
                    "tipo": "contrato_sercop", "entidad": nombre, "origen_key": clave_contrato,
                    "texto": "Un contrato SERCOP relacionado con \"%s\" menciona a %s."
                             % (s.get("titular", "")[:120], nombre),
                    "fuente": {"tipo": "contrato_sercop",
                               "titulo": contrato.get("objeto") or contrato.get("ocid") or "contrato SERCOP",
                               "link": contrato.get("link", ""), "medio": "SERCOP"},
                })
                if push_casos:
                    caso_titulo = next((c.get("titulo", "") for c in casos.listar_casos() if c["id"] == caso_id), "")
                    movil.enviar(conf_movil, "Caso: %s" % caso_titulo, aviso["texto"],
                                  prioridad=3, etiquetas=["moneybag"], click=contrato.get("link", "") or "")


# ---------------- Fase 8: alertas tempranas (Problema 3) ----------------
# Va en run_fast/write_outputs (nunca en el hilo trabajador): vincular_con_prensa
# es determinista y barato (compara texto contra 'stories' que YA esta en
# memoria, sin red) -- la parte con red real (Bluesky/Telegram/RSS oficial)
# vive en alertas.recolectar_senales(), llamada aparte desde enrich_pass.

def procesar_alertas(stories):
    """Enlaza alertas activas con la prensa (estado 'Ya en medios' + metrica
    de minutos de adelanto) y manda ntfy SOLO para las que llegan a
    Corroborado o mas (pedido explicito -- nunca por 'Sin confirmar', y
    nunca dos veces por el mismo escalon). Devuelve (lista de alertas
    activas para data.json, texto de estado)."""
    if alertas is None:
        return [], "no disponible (falta alertas.py)"
    if os.environ.get("MONITOR_SAMPLE") == "1":
        return [], "apagado en modo muestra"
    try:
        enlazadas = alertas.vincular_con_prensa(stories)
    except Exception as e:
        enlazadas = 0
        print("Error vinculando alertas con prensa: %s" % e)
    conf_movil = movil.cargar_config() if movil else None
    if conf_movil and conf_movil.get("avisos_activos"):
        for a in alertas.pendientes_de_aviso("corroborado"):
            ultimo_texto = a["senales"][-1]["texto"] if a.get("senales") else ""
            titulo = "Alerta: %s en %s" % (
                (a.get("tipo") or "evento").replace("_", " ").title(), a.get("lugar") or "Guayaquil")
            texto = "%s (%s, %d fuente[s])." % (
                ultimo_texto, alertas.ESTADO_LABEL.get(a.get("estado"), a.get("estado")), len(a.get("senales") or []))
            ok, _ = movil.enviar(conf_movil, titulo, texto, prioridad=4, etiquetas=["warning"],
                                  click=a.get("historia_link", "") or "")
            if ok:
                alertas.marcar_avisada(a["id"])
    activas = alertas.listar_activas()
    return activas, "activas: %d (enlazadas a prensa esta pasada: %d)" % (len(activas), enlazadas)


# ---------------- Fase 7, Paso E: pausar el trabajador mientras se chatea ----------------
# Pedido explicito de Fernando (PC nueva sin GPU, un solo modelo cargado a
# la vez): mientras el chat de un caso esta generando, el hilo trabajador
# (enrich_pass, Parte C) no debe competir por Ollama. Contador (no booleano)
# porque en teoria puede haber mas de una pestaña de chat abierta a la vez.
_pausa_trabajador_lock = threading.Lock()
_pausa_trabajador_n = 0

def _pausar_trabajador():
    global _pausa_trabajador_n
    with _pausa_trabajador_lock:
        _pausa_trabajador_n += 1

def _reanudar_trabajador():
    global _pausa_trabajador_n
    with _pausa_trabajador_lock:
        _pausa_trabajador_n = max(0, _pausa_trabajador_n - 1)

def _trabajador_pausado():
    with _pausa_trabajador_lock:
        return _pausa_trabajador_n > 0


# ------------------------- historial (interes editorial en el tiempo) -------------------------

HIST_PATH = os.path.join(HERE, "history.json")
HIST_MAX = 2000  # snapshots guardados (se recorta lo mas viejo)
# Fase 0 (velocidad): antes de bajar el tick de run_fast (MONITOR_FEED_MIN,
# de 2 a 1 min por defecto), un snapshot de history.json se guardaba en CADA
# pasada del feed -- con el tick mas rapido, eso hubiera duplicado la
# velocidad de crecimiento del archivo y, con HIST_MAX fijo, RECORTADO A LA
# MITAD cuanto tiempo hacia atras llega el historial (justo lo que necesita
# Fase 2 para "evolucion en el tiempo" y el Asistente para comparar_periodo).
# Se desacopla: el feed puede chequear cada 1 min, pero un snapshot NUEVO de
# history.json solo se guarda si paso HIST_MIN_MIN desde el ultimo -- mismo
# espaciado de antes (2 min) sin importar que tan seguido corra el feed.
HIST_MIN_MIN = float(os.environ.get("MONITOR_HIST_MIN", "2"))

def load_history():
    try:
        with open(HIST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _ultimo_snapshot_hace(hist):
    if not hist:
        return None
    try:
        ts = dt.datetime.fromisoformat(hist[-1]["ts"])
    except Exception:
        return None
    return (now_utc() - ts).total_seconds() / 60

def append_history(stories, demand=None):
    """Guarda un snapshot con el conteo de historias por tema, seccion y ambito,
    y la demanda (Google Trends) por tema. Materia prima de las graficas en el
    tiempo. Se salta el guardado (devuelve el historial tal cual) si todavia
    no paso HIST_MIN_MIN desde el ultimo snapshot -- ver nota de HIST_MIN_MIN
    arriba."""
    hist = load_history()
    hace = _ultimo_snapshot_hace(hist)
    if hace is not None and hace < HIST_MIN_MIN:
        return hist
    temas = {}
    for s in stories:
        for t in s.get("temas", []):
            temas[t] = temas.get(t, 0) + 1
    # Fase 2 (2026-09-23/24): "secciones_ambito" -- el mismo conteo por
    # categoria de siempre, pero desglosado por Mundo/Ecuador/Guayaquil, para
    # poder graficar la evolucion de cada ambito por separado en el tiempo
    # (antes solo existia el agregado total, sin forma de saber si un pico de
    # "seguridad" era de Guayaquil o del resto del mundo). "cobertura" (suma
    # de n_articles, no de historias) es la señal de "Mercado de cobertura"
    # con DATOS PROPIOS -- ver Fase 2, reemplaza la dependencia de GDELT
    # (bloqueado la mayor parte del tiempo) como fuente principal.
    guayaquil = [s for s in stories if s.get("ciudad") == "Guayaquil"]
    local_no_gye = [s for s in stories if s.get("es_local") and s.get("ciudad") != "Guayaquil"]
    internacional = [s for s in stories if s.get("internacional")]
    snap = {
        "ts": now_utc().isoformat(),
        "total": len(stories),
        # antes solo contaba politica/economia (bug real, parte del reclamo de
        # Fernando: la cobertura por categoria se perdia) -- ahora las 5.
        "secciones": contar_por_categoria(stories),
        "secciones_ambito": {
            "guayaquil": contar_por_categoria(guayaquil),
            "local": contar_por_categoria(local_no_gye),
            "internacional": contar_por_categoria(internacional),
        },
        "cobertura": {c: sum(s.get("n_articles", 0) for s in stories
                              if normalizar_categoria(s.get("seccion")) == c)
                      for c in CATEGORIAS_VALIDAS},
        "ambito": {
            "local": sum(1 for s in stories if s.get("es_local")),
            "internacional": sum(1 for s in stories if s.get("internacional")),
        },
        "temas": temas,
        "temas_demanda": demand or {},
    }
    hist.append(snap)
    hist = hist[-HIST_MAX:]
    with open(HIST_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)
    return hist


# ------------------------- salida (JSON + HTML) -------------------------

def _fuente_ok(detalle):
    """De un texto de estado (ej. 'ok (Google Trends, 3/5 temas)', 'error: ...',
    'desactivado', 'esperando primera pasada del trabajador') decide si esa
    fuente aporto algo utilizable esta corrida. 'cache'/'cache vencido' cuentan
    como OK (hay un ultimo dato bueno, aunque viejo) -- 'desactivado' no es un
    fallo (Fernando lo apago a proposito), se marca aparte."""
    d = (detalle or "").strip().lower()
    if d.startswith("desactivado"):
        return None  # ni ok ni error: apagado a proposito
    return d.startswith("ok") or d.startswith("cache")

def construir_salud_fuentes(report, estado, gestado, sstatus, iastatus,
                             social_status, cstatus, fcstatus):
    """Registro de salud de datos por corrida (Problema 3): para cada fuente,
    si respondio, cuanto establecio, y el detalle/error tal cual lo reporto
    esa fuente. Un solo lugar que arma esto, para que el dashboard muestre un
    indicador honesto de que tan completos estan los datos de ESTA corrida
    (en vez de que Fernando tenga que adivinarlo mirando si una seccion
    parece vacia)."""
    ok_feeds = sum(1 for (_o, _s, _n, st) in report if st == "ok")
    items_feeds = sum(n for (_o, _s, n, _st) in report)
    feeds_detalle = "%d/%d feeds respondieron, %d notas leidas" % (ok_feeds, len(report), items_feeds)
    fuentes = [
        {"fuente": "Feeds RSS", "ok": (ok_feeds == len(report) if report else None), "detalle": feeds_detalle},
        {"fuente": "Busqueda (Trends/Wikipedia)", "ok": _fuente_ok(estado), "detalle": estado},
        {"fuente": "GDELT (cobertura/tono)", "ok": _fuente_ok(gestado), "detalle": gestado},
        {"fuente": "SERCOP (contratos)", "ok": _fuente_ok(sstatus), "detalle": sstatus},
        {"fuente": "IA (Ollama)", "ok": _fuente_ok(iastatus), "detalle": iastatus},
        {"fuente": "Contexto (Wikipedia+GDELT)", "ok": _fuente_ok(cstatus), "detalle": cstatus},
        {"fuente": "FactCheck", "ok": _fuente_ok(fcstatus), "detalle": fcstatus},
        {"fuente": "Escucha social", "ok": _fuente_ok(social_status), "detalle": social_status},
        # Fase 9 (Problema A1): visible aca mismo, junto al resto de "estado_X"
        # -- antes no habia forma de notar que la capa semantica del
        # agrupamiento (embeddings) llevaba dias apagada sin ir a mirar el
        # JSON del registro a mano.
        {"fuente": "Embeddings (agrupamiento)", "ok": (ia.embed_disponible() if ia else False),
         "detalle": estado_embeddings_dashboard()},
    ]
    return fuentes

def _embeddings_cobertura():
    """Cuenta liviana (sin reconstruir datetimes) de cuantas entradas del
    registro ya tienen embedding -- Fase 9 (Problema A1): antes de este
    cambio no habia forma de VER que la capa semantica llevaba dias apagada
    (2481 entradas, 0 con embedding) sin ir a mirar el JSON a mano."""
    try:
        with open(REGISTRO_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return "0/0"
    total = len(raw)
    con_emb = sum(1 for e in raw.values() if e.get("embedding"))
    return "%d/%d" % (con_emb, total)

def estado_embeddings_dashboard():
    """Texto honesto para data.json, mismo criterio que estado_gdelt/
    estado_interes -- nunca "cache" a secas si la capa semantica esta
    apagada o vacia."""
    if ia is None:
        return "ia.py no disponible"
    base = ia.estado_embeddings()
    return "%s -- %s historias con embedding" % (base, _embeddings_cobertura())

def write_outputs(stories, report, demand=None, tend=None, fuente="?", estado="",
                  gdelt_data=None, gestado="", sstatus="", iastatus="",
                  social_data=None, social_status="", cstatus="", fcstatus="", vstatus="", dstatus="",
                  social_hist_data=None, social_hist_status=""):
    hist = append_history(stories, demand)
    estado_movil = avisar_movil(stories, demand)
    alertas_activas, alertas_estado = procesar_alertas(stories)
    salud_fuentes = construir_salud_fuentes(report, estado, gestado, sstatus, iastatus,
                                             social_status, cstatus, fcstatus)
    payload = {
        "generado": now_utc().isoformat(),
        "total_historias": len(stories),
        "reporte_feeds": [{"outlet": o, "seccion": s, "items": n, "estado": st}
                          for (o, s, n, st) in report],
        "historias": stories,
        "historial": hist,
        "tendencias": tend or {},
        "fuente_interes": fuente,
        "estado_interes": estado,
        "gdelt": gdelt_data or {},
        "estado_gdelt": gestado,
        "estado_sercop": sstatus,
        "estado_ia": iastatus,
        "estado_contexto": cstatus,
        "estado_factcheck": fcstatus,
        "estado_veredicto": vstatus,
        "estado_declaraciones": dstatus,
        "estado_embeddings": estado_embeddings_dashboard(),
        "estado_ia_nube": ({
            "activo": ia.backend_listo(),
            "estado": ia.estado(),
            **ia.estado_gasto(),
        } if ia else {"activo": False, "estado": "ia.py no disponible",
                       "gasto_hoy": 0.0, "gasto_mes": 0.0, "tope_dia": 0.0, "tope_mes": 0.0,
                       "restante_hoy": 0.0, "restante_mes": 0.0}),
        "social": social_data or {},
        "estado_social": social_status,
        # Fase 9 (Problema C): Pulso social anclado a historias (nuevo,
        # separado del panel por tema de arriba -- ese sigue alimentando
        # Oportunidades, ver comentario en get_social_historias).
        "social_historias": social_hist_data or {},
        "estado_social_historias": social_hist_status,
        # Fase 9 (Problema D): X via Apify -- gasto real (nunca el token),
        # honesto sobre si esta activo o no (mismo criterio que estado_gdelt).
        "estado_redes": (redes.estado_dashboard() if redes else {"activo": False, "estado": "redes.py no disponible"}),
        "feed_fresh_h": FEED_FRESH_H,
        "max_age_dias": MAX_AGE_DAYS,
        "estado_movil": estado_movil,
        "salud_fuentes": salud_fuentes,
        # Fase 0 (velocidad): demora real medida por medio (primera_vez_vista -
        # publicado_segun_el_feed) -- ver calcular_latencia_por_feed(). Vacio
        # hasta que se acumulen datos reales (no antes de la primera vez que
        # esto corre en modo serve por un rato).
        "latencia_feeds": calcular_latencia_por_feed(),
        # Fase 3: que hay disponible ahora mismo en la base de contraste
        # oficial (Constitucion + boletines institucionales) -- honesto, sin
        # inventar: si algo todavia no se construyo/consulto, sale en 0.
        "oficial": oficial.estado() if oficial else {"constitucion": {"disponible": False}, "boletines": {}},
        # Fase 5: tamaño del registro de declaraciones atribuidas -- honesto,
        # arranca en 0 hasta que el trabajador procese las primeras notas.
        "declaraciones_estado": decl.estado() if decl else {"actores": 0, "declaraciones": 0},
        # Fase 8 (Problema 3): alertas tempranas -- nunca declara "verdadero",
        # solo mide corroboracion (ver alertas.py). Vacio y honesto hasta que
        # el trabajador recolecte la primera señal real.
        "alertas": alertas_activas,
        "alertas_estado": alertas_estado,
        "alertas_metricas": alertas.metricas_adelanto() if alertas else {"n": 0, "promedio_min": None, "casos": []},
        # Fase 18 (P0-4): senales de la Fase 15, que nunca se habian conectado.
        # El hilo rapido solo LEE senales_estado.json (lo escribe senales_loop).
        **senales_para_dashboard(),
    }
    # BUG REAL encontrado en el Fase 0 (2026-09-23): el CLAUDE.md documentaba
    # "data.json se escribe atomico (_escribir_atomico)" como ya hecho, pero
    # esa funcion NUNCA se escribio -- write_outputs() seguia escribiendo
    # data.json/dashboard.html DIRECTO. Riesgo real: el dashboard (poll() cada
    # 45s) puede pedir data.json justo mientras esta a mitad de escribir y
    # recibir JSON incompleto/invalido (poll() ya lo tolera -- se queda con lo
    # que tenia y reintenta en 45s -- pero mejor que no pase). Mismo patron
    # de "documentado pero nunca conectado" que ya aparecio 5 veces en el
    # proyecto. Arreglado con archivo temporal + os.replace, igual que
    # saved.json/notas.json/fetch_cache.json.
    def _escribir_atomico(ruta, contenido, binario=False):
        tmp = ruta + ".tmp"
        modo = "wb" if binario else "w"
        kwargs = {} if binario else {"encoding": "utf-8"}
        with open(tmp, modo, **kwargs) as f:
            f.write(contenido)
        os.replace(tmp, ruta)

    _escribir_atomico(os.path.join(HERE, "data.json"),
                       json.dumps(payload, ensure_ascii=False, indent=2))

    tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read()
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html_out = tpl.replace("/*__DATA__*/null", blob)
    _escribir_atomico(os.path.join(HERE, "dashboard.html"), html_out)


def avisar_movil(stories, demand):
    """Despues de cada pasada: si hubo un GRAN CAMBIO, avisa al iPhone (ver movil.py).
    Nunca rompe la corrida: cualquier error queda como texto de estado."""
    if movil is None:
        return "no disponible (falta movil.py)"
    if os.environ.get("MONITOR_SAMPLE") == "1":
        return "apagado en modo muestra"
    try:
        est = movil.procesar(stories, demand, MOVIL_PUERTO)
    except Exception as e:
        est = "error: %s" % str(e)[:80]
    if est not in ("sin cambios grandes", "apagado"):
        print("Avisos al celular: %s" % est)
    return est


# ------------------------- muestra sin internet -------------------------

def sample_articles():
    base = now_utc()
    def d(h): return base - dt.timedelta(hours=h)
    raw = [
        ("El Universo", "politica", "Asamblea Nacional aprueba en primer debate la reforma tributaria en Ecuador", 2),
        ("El Comercio", "politica", "La Asamblea de Ecuador debate la reforma tributaria del Gobierno", 3),
        ("El Universo", "economia", "El precio del diesel sube en Ecuador tras la focalizacion del subsidio", 1),
        ("Cronica", "seguridad", "Sicariato deja tres muertos en Guayaquil en medio de ola de violencia", 1),
        ("El Comercio", "sociedad", "Hospitales de Quito reportan falta de medicinas y personal", 4),
        ("El Universo", "seguridad", "Nuevo motin en carcel de Ecuador deja varios heridos", 6),
        ("Confirmado", "general", "Lider del Congreso de Estados Unidos rechaza freno a la IA", 5),
        # Internacionales (medios de afuera, tema mundial):
        ("El Mundo", "politica", "La Union Europea debate nuevas sanciones contra Rusia por Ucrania", 3),
        ("NYT", "economia", "Wall Street cae en Estados Unidos por temor a la inflacion global", 5),
        ("La Nacion (AR)", "general", "Milei enfrenta protestas en Argentina por el ajuste economico", 7),
    ]
    return [{"outlet": o, "seccion": s, "title": t,
             "link": "https://example.com/n%d" % i, "date": d(h),
             "summary": "Resumen de ejemplo: contexto breve de la nota para "
                        "mostrar como se ve el detalle en la tarjeta."}
            for i, (o, s, t, h) in enumerate(raw)]


# ------------------------- corrida y servidor -------------------------

def run_once(verbose=True):
    """Una recoleccion completa: feeds -> dedup -> agrupar -> dashboard.

    Cronometra cada fase (Paso 0 de la Parte C: medir antes de optimizar a
    ciegas) y lo imprime al final en modo verbose. Es solo diagnostico, no
    afecta el resultado."""
    tiempos = {}
    def _fase(nombre, t_inicio):
        tiempos[nombre] = round(time.time() - t_inicio, 2)
        return time.time()

    t0 = time.time()
    if os.environ.get("MONITOR_SAMPLE") == "1":
        if verbose: print("Modo muestra (sin internet).")
        articles = sample_articles()
        report = [("MUESTRA", "-", len(articles), "ok")]
    else:
        if verbose: print("Leyendo feeds...")
        # respetar_frecuencia=False: una corrida unica no debe "esperar el
        # turno" de ningun feed (eso es para el modo serve, que vuelve a
        # pasar cada rato) -- aca siempre se trae todo fresco.
        articles, report = collect(respetar_frecuencia=False)
    t0 = _fase("collect", t0)

    if verbose:
        print("\nReporte de feeds:")
        for o, s, n, st in report:
            print("  [%-4s] %-14s %-9s %3d items" % (st, o, s, n))

    articles = dedup(articles)
    # Problema 1 (2026-09-24): agrupar_con_memoria() compara cada nota contra
    # las historias YA EXISTENTES de historias_registro.json (ultimas 72h),
    # no solo contra las de esta corrida -- reemplaza a cluster()+
    # build_stories() en el pipeline real (cluster() sigue intacta para sus
    # propias pruebas, ver el modulo de arriba).
    if os.environ.get("MONITOR_SAMPLE") == "1":
        clusters = cluster(articles)
        stories = build_stories(clusters)
    else:
        migrar_registro_si_hace_falta(verbose=verbose)
        stories = agrupar_con_memoria(articles)
        # Fase 18 (P0-2.4): eventos en curso (ej. lluvias en Guayaquil) ->
        # una historia madre en vez de ~10 tarjetas sueltas.
        stories = agrupar_eventos_en_curso(stories)
        _adjuntar_tweets_eventos(stories)
        try:
            print("Triaje internacional: %s" % get_triaje_intl(stories)) if verbose else get_triaje_intl(stories)
        except Exception as e:
            print("Error en triaje internacional: %s" % e)
        # Fase 18 (P1-9): internacionales con marco (farandula fuera, triaje, tope)
        stories = aplicar_triaje_intl(stories)
    t0 = _fase("cluster", t0)

    # DEMANDA (Google Trends) por tema, y se cuelga en cada historia.
    themes_present = sorted({t for s in stories for t in s.get("temas", [])})
    if os.environ.get("MONITOR_SAMPLE") == "1":
        # demanda y curvas ficticias para ver la funcion sin internet
        import random, math; random.seed(7)
        demand, tend = {}, {}
        for t in themes_present:
            base = random.randint(20, 70)
            serie = [max(0, min(100, int(base + 25*math.sin(k/4) + random.randint(-8, 8))))
                     for k in range(48)]
            demand[t] = round(sum(serie[-8:]) / 8)
            tend[t] = {"v": serie, "t": ["h-%d" % (48 - k) for k in range(48)]}
        dstatus, fuente = "muestra", "muestra"
    else:
        demand, tend, dstatus, fuente = get_demand(themes_present)
    t0 = _fase("get_demand", t0)

    if os.environ.get("MONITOR_SAMPLE") == "1":
        import random, math
        gdelt_data = {}
        for t in themes_present:
            vol = [max(0, int(30 + 20*math.sin(k/3) + random.randint(-6, 6))) for k in range(21)]
            gdelt_data[t] = {"vol": vol, "tone": round(random.uniform(-4, 3), 2),
                             "tone_series": [round(random.uniform(-5, 4), 1) for _ in range(21)]}
        gstatus = "muestra"
    else:
        gdelt_data, gstatus = get_gdelt(themes_present)
    t0 = _fase("get_gdelt", t0)

    for s in stories:
        ds = [demand[t] for t in s.get("temas", []) if t in demand]
        s["demanda"] = max(ds) if ds else None
        # BRECHA: mucha demanda + poca cobertura = interes desatendido
        s["brecha"] = bool(s["demanda"] is not None and s["demanda"] >= 50 and s["n_outlets"] <= 1)
        # INTERES: lo que mas se habla (medios) + lo que mas se busca (demanda) + recencia.
        # Asi la portada ordena por interes de la NOTICIA, no por tema.
        # _peso_outlets (Problema 4): en ambito local, medios internacionales
        # pesan menos que medios ecuatorianos -- no alcanzan solos para
        # encabezar Ecuador sin cobertura local.
        bono_impacto = _bono_impacto(s)
        s["alto_impacto"] = bono_impacto > 0
        s["interes"] = round(_peso_outlets(s) + s["n_articles"] * 6
                             + (s["demanda"] or 0) * 0.6 + s.get("recency", 0) * 20
                             + bono_impacto, 1)
    stories.sort(key=lambda s: s["interes"], reverse=True)
    t0 = _fase("interes", t0)

    # IA LOCAL (Ollama): reclasifica por significado y da interpretacion a lo top
    if os.environ.get("MONITOR_SAMPLE") == "1":
        for s in stories[:6]:
            s["ia"] = "Analisis IA de ejemplo: por que este tema importa y su contexto."
        iastatus = "muestra"
    else:
        iastatus = get_ia(stories)
    t0 = _fase("get_ia", t0)

    # CONTEXTO REAL por entidad (Parte B): Wikipedia + co-menciones GDELT
    if os.environ.get("MONITOR_SAMPLE") == "1":
        for s in stories[:3]:
            s["contexto"] = {
                "texto": "Ejemplo: esta historia es una continuacion de un hecho anterior en el registro.",
                "entidades": [{"nombre": "Entidad de ejemplo", "extracto": "Extracto de ejemplo desde Wikipedia.",
                               "url": "https://es.wikipedia.org/wiki/Ejemplo"}],
                "comenciones": ["Nombre de Ejemplo"], "principal": "Entidad de ejemplo", "previas": [],
                "antecedentes": [{"texto": "Hace una semana ocurrio un hecho relacionado (ejemplo).", "fuentes": ["R1"]}],
                "actores": [{"nombre": "Entidad de ejemplo", "rol": "involucrado", "apariciones": ["A1"]}],
                "que_es_nuevo": [{"texto": "Esta nota agrega un dato nuevo de ejemplo.", "fuentes": ["M1"]}],
                "que_falta_saber": [{"pregunta": "¿Que falta confirmar? (ejemplo)",
                                      "por_que_importa": "Ejemplo de por que esto le importaria a un reportero.",
                                      "fuentes": []}],
                "limitaciones": "Ejemplo de limitacion del material disponible.", "descartadas": 0,
                "material": {"R1": {"texto": "Antecedente de ejemplo", "link": None},
                             "A1": {"texto": "Aparicion de ejemplo", "link": None},
                             "M1": {"texto": "Otro medio de ejemplo", "link": None}},
            }
        for s in stories[3:6]:
            s["contexto"] = {"texto": "sin contexto disponible", "entidades": [], "comenciones": [], "principal": None,
                              "previas": [], "antecedentes": [], "actores": [], "que_es_nuevo": [],
                              "que_falta_saber": [], "limitaciones": "sin material verificado disponible",
                              "descartadas": 0}
        cstatus = "muestra"
    else:
        cstatus = get_contexto(stories)
    t0 = _fase("get_contexto", t0)

    # CONTRASTE con documentacion oficial (SERCOP) en las historias top de gasto/obra
    if os.environ.get("MONITOR_SAMPLE") == "1":
        for s in stories:
            if any(h in norm(s["titular"]) for h in SPEND_HINTS):
                s["contratos"] = [{"ocid": "ocds-ejemplo-1",
                    "objeto": "ADQUISICION DE EJEMPLO PARA MOSTRAR EL CONTRASTE",
                    "entidad": "GAD Municipal (ejemplo)", "monto": "125000",
                    "fecha": "2026-09-01", "link": "https://datosabiertos.compraspublicas.gob.ec"}]
        sstatus = "muestra"
    else:
        sstatus = get_contracts(stories)
    t0 = _fase("get_contracts", t0)

    # FACTCHECK (Google Fact Check Tools) en las historias top: verificaciones
    # periodisticas relacionadas, para el sector Contraste junto a SERCOP.
    if os.environ.get("MONITOR_SAMPLE") == "1":
        if stories:
            stories[0]["factcheck"] = [{"claim": "Ejemplo: afirmacion de muestra sobre esta noticia",
                "calificacion": "Enganoso", "verificador": "Verificador de Ejemplo",
                "url": "https://example.org/factcheck", "fecha": "2026-09-01"}]
        for s in stories[1:4]:
            s["factcheck"] = []
        fcstatus = "muestra"
    else:
        fcstatus = get_factcheck(stories)
    t0 = _fase("get_factcheck", t0)

    # VEREDICTO DE CONTRASTE (Problema 4): estado coincide/contradice/sin_datos
    if os.environ.get("MONITOR_SAMPLE") == "1":
        if stories:
            stories[0]["veredicto"] = {"estado": "contradice",
                "texto": "Ejemplo: el contrato SERCOP no coincide con el monto que menciona la nota.",
                "citas": ["SERCOP"]}
        for s in stories[1:4]:
            s["veredicto"] = {"estado": "sin_datos", "texto": "Sin material para contrastar.", "citas": []}
        vstatus = "muestra"
    else:
        vstatus = get_veredicto(stories)
    t0 = _fase("get_veredicto", t0)

    # DECLARACIONES (Fase 5): actor+cargo+que dijo, cruzado contra lo que el
    # mismo actor dijo antes (registro propio, nunca purgado por MONITOR_MAX_DIAS)
    if os.environ.get("MONITOR_SAMPLE") == "1":
        if stories:
            stories[0]["declaracion"] = {"actor": "Autoridad de ejemplo", "cargo": "Cargo de ejemplo",
                "texto": "Declaracion de ejemplo para mostrar el panel.", "fecha": stories[0].get("newest", ""),
                "medio": "Medio de ejemplo"}
        declstatus = "muestra"
    else:
        declstatus = get_declaraciones(stories)
    t0 = _fase("get_declaraciones", t0)

    # ESCUCHA SOCIAL (Bluesky/Reddit/YouTube) + lectura OSINT con Ollama, por tema top
    if os.environ.get("MONITOR_SAMPLE") == "1":
        _amb_muestra = tema_ambito_map(stories)
        social_data = {}
        for t in themes_present[:5]:
            social_data[t] = {
                "n_posts": 12,
                "por_fuente": {"bluesky": 7, "reddit": 3, "youtube": 2},
                "ambito": _amb_muestra.get(t, "internacional"),
                "sentimiento": ["mixto", "negativo", "positivo"][hash(t) % 3],
                "polarizacion": ["alta", "media", "baja"][hash(t) % 3],
                "temas_recurrentes": ["reclamo ciudadano", "criticas al gobierno", "propuestas"],
                "resumen": "Ejemplo: la conversacion en redes sobre este tema mezcla criticas y reclamos.",
                "top": [
                    {"fuente": "bluesky", "autor": "usuario.bsky.social",
                     "texto": "Comentario de ejemplo sobre %s en Bluesky." % t,
                     "url": "https://bsky.app", "likes": 34, "reposts": 7,
                     "fecha": now_utc().strftime("%Y-%m-%d")},
                    {"fuente": "reddit", "autor": "u/ejemplo",
                     "texto": "Comentario de ejemplo sobre %s en Reddit." % t,
                     "url": "https://reddit.com", "likes": 20, "reposts": 20,
                     "fecha": now_utc().strftime("%Y-%m-%d")},
                    {"fuente": "youtube", "autor": "@ejemplo",
                     "texto": "Comentario de ejemplo sobre %s en YouTube." % t,
                     "url": "https://youtube.com", "likes": 15, "reposts": 0,
                     "fecha": now_utc().strftime("%Y-%m-%d")},
                ],
            }
        social_status = "muestra"
        social_hist_data = {}
        if stories:
            f0 = (stories[0].get("fuentes") or [{}])[0]
            key = (f0.get("link") or stories[0]["titular"])[:180]
            social_hist_data[key] = {
                "titular": stories[0]["titular"], "n_posts": 8, "n_descartados": 2,
                "por_fuente": {"bluesky": 5, "youtube": 3},
                "posturas": [{"postura": "en_contra", "n": 3, "citas": [
                    {"autor": "usuario.bsky.social", "texto": "Ejemplo de postura en contra.",
                     "url": "https://bsky.app", "fuente": "bluesky"}]}],
                "hilo_principal": None, "top": [],
            }
        social_hist_status = "muestra"
    else:
        social_data, social_status = get_social(themes_present, tema_ambito=tema_ambito_map(stories))
        social_hist_data, social_hist_status = get_social_historias(stories)
    t0 = _fase("get_social", t0)
    if os.environ.get("MONITOR_SAMPLE") != "1":
        # Fase 18 (P0-4): la corrida unica tambien deja senales_estado.json
        # listo (en modo serve lo hace senales_loop cada 15 min).
        try:
            if verbose:
                print("Senales: %s" % correr_senales(stories, demand if "Trends" in (fuente or "") else {}))
            else:
                correr_senales(stories, demand if "Trends" in (fuente or "") else {})
        except Exception as e:
            print("Error en senales: %s" % e)
        t0 = _fase("senales", t0)

    aplicar_contraste(stories)  # Fase 18 (P2-11): sin red ni IA, lee lo ya calculado
    write_outputs(stories, report, demand, tend, fuente, dstatus, gdelt_data, gstatus,
                  sstatus, iastatus, social_data, social_status, cstatus, fcstatus, vstatus,
                  dstatus=declstatus, social_hist_data=social_hist_data, social_hist_status=social_hist_status)
    t0 = _fase("write_outputs", t0)

    if verbose:
        print("\nInteres/busquedas: %s" % dstatus)
        print("Cobertura/tono (GDELT): %s" % gstatus)
        print("Contraste oficial (SERCOP): %s" % sstatus)
        print("Verificaciones (FactCheck): %s" % fcstatus)
        print("Declaraciones (Fase 5): %s" % declstatus)
        print("Veredicto de contraste: %s" % vstatus)
        print("Agente IA (Ollama): %s" % iastatus)
        print("Contexto por entidad (Wikipedia+GDELT): %s" % cstatus)
        print("Escucha social (Bluesky/Reddit/YouTube): %s" % social_status)
        tam_reg = _tam_registro_mb()
        if tam_reg is not None:
            print("Registro de historias (historias_registro.json): %.2f MB" % tam_reg)
        locales = [s for s in stories if s.get("es_local")]
        intl = [s for s in stories if s.get("internacional")]
        print("%d notas -> %d historias (%d Ecuador, %d internacionales)."
              % (len(articles), len(stories), len(locales), len(intl)))
        imprimir_categorias(stories)
        if locales:
            print("Top Ecuador por prominencia:")
            for s in locales[:3]:
                print("  * (%d medios) %s" % (s["n_outlets"], s["titular"]))
        print("\nTiempos por fase:")
        for k, v in tiempos.items():
            print("  %-14s %6.2fs" % (k, v))
        print("  %-14s %6.2fs" % ("TOTAL", sum(tiempos.values())))
    return stories


def run_fast(verbose=False):
    """Pasada RAPIDA del hilo feed (Parte C, hilo rapido): feeds -> dedup ->
    cluster -> clasificacion por palabras clave -> prominencia -> demanda/
    GDELT/contratos (cada uno con su propio cache de horas) -> SOLO LEE los
    caches de enriquecimiento (ia_cache.json, contexto_cache.json,
    social_cache.json) y pega en cada historia lo que el hilo trabajador ya
    dejo listo. NUNCA llama a Ollama para calcular algo nuevo -- eso es
    trabajo exclusivo de enrich_pass() en el hilo trabajador. Es el UNICO
    lugar que escribe data.json/dashboard.html."""
    tiempos = {}
    def _fase(nombre, t_inicio):
        tiempos[nombre] = round(time.time() - t_inicio, 2)
        return time.time()

    t0 = time.time()
    if os.environ.get("MONITOR_SAMPLE") == "1":
        articles = sample_articles()
        report = [("MUESTRA", "-", len(articles), "ok")]
    else:
        articles, report = collect()
    t0 = _fase("collect", t0)

    articles = dedup(articles)
    # Problema 1: mismo cambio que run_once (ver comentario ahi) -- el modo
    # muestra sigue con cluster() intra-pasada para no ensuciar el registro
    # persistente real con datos ficticios.
    if os.environ.get("MONITOR_SAMPLE") == "1":
        clusters = cluster(articles)
        stories = build_stories(clusters)
    else:
        # Fase 17 (pedido de revision de Codex, Frente B): marca explicita de
        # inicio/fin de esta etapa puntual -- antes, si esto se colgaba, el
        # unico indicio en arranque.log era la AUSENCIA de la siguiente
        # linea ("cluster: ...", que solo se escribe al terminar), nunca un
        # aviso directo de "estoy en agrupar_con_memoria ahora mismo".
        _log_arranque("cluster: agrupando %d articulos contra el registro persistente..." % len(articles))
        stories = agrupar_con_memoria(articles)
        # Fase 18 (P0-2.4): eventos en curso (ej. lluvias en Guayaquil) ->
        # una historia madre en vez de ~10 tarjetas sueltas.
        stories = agrupar_eventos_en_curso(stories)
        _adjuntar_tweets_eventos(stories)
        # Fase 18 (P1-9): internacionales con marco (farandula fuera, triaje, tope)
        stories = aplicar_triaje_intl(stories)
    t0 = _fase("cluster", t0)

    themes_present = sorted({t for s in stories for t in s.get("temas", [])})
    # Demanda/GDELT: modo_lectura=True, SOLO leen su cache (nunca red) -- ver
    # task #17. La llamada real ahora vive en enrich_pass (hilo trabajador).
    # Bug real que esto arregla: un vencimiento de cache de GDELT trabo el
    # arranque del servidor mas de 9 minutos (medido: hasta 559s).
    demand, tend, dstatus, fuente = get_demand(themes_present, modo_lectura=True)
    t0 = _fase("get_demand", t0)
    gdelt_data, gstatus = get_gdelt(themes_present, modo_lectura=True)
    t0 = _fase("get_gdelt", t0)

    for s in stories:
        ds = [demand[t] for t in s.get("temas", []) if t in demand]
        s["demanda"] = max(ds) if ds else None
        s["brecha"] = bool(s["demanda"] is not None and s["demanda"] >= 50 and s["n_outlets"] <= 1)
        bono_impacto = _bono_impacto(s)
        s["alto_impacto"] = bono_impacto > 0
        s["interes"] = round(_peso_outlets(s) + s["n_articles"] * 6
                             + (s["demanda"] or 0) * 0.6 + s.get("recency", 0) * 20
                             + bono_impacto, 1)
    stories.sort(key=lambda s: s["interes"], reverse=True)
    t0 = _fase("interes", t0)

    iastatus = get_ia(stories, modo_lectura=True)
    t0 = _fase("get_ia", t0)
    # Fase 14, Paso 2: aplica (si hay algo en cache) la correccion de ciudad
    # por evidencia ANTES de que el resto de run_fast use s["ciudad"] (temas/
    # geo ya se calcularon en build_stories, pero el filtro Ecuador/
    # Guayaquil/Mundo del dashboard lee s["ciudad"] directo de 'stories').
    gestatus = get_geo_evidencia(stories, modo_lectura=True)
    t0 = _fase("get_geo_evidencia", t0)
    cstatus = get_contexto(stories, modo_lectura=True)
    t0 = _fase("get_contexto", t0)
    sstatus = get_contracts(stories, modo_lectura=True)  # ver task #17: real solo en enrich_pass
    t0 = _fase("get_contracts", t0)
    fcstatus = get_factcheck(stories, modo_lectura=True)
    t0 = _fase("get_factcheck", t0)
    vstatus = get_veredicto(stories, modo_lectura=True)
    t0 = _fase("get_veredicto", t0)
    declstatus = get_declaraciones(stories, modo_lectura=True)
    t0 = _fase("get_declaraciones", t0)
    social_data, social_status = get_social(themes_present, modo_lectura=True)
    t0 = _fase("get_social", t0)
    social_hist_data, social_hist_status = get_social_historias(stories, modo_lectura=True)
    t0 = _fase("get_social_historias", t0)

    # Fase 7, Paso D: puente Dashboard -> Asistente de casos (determinista,
    # sin IA). Va aca porque recien aca cada 's' ya tiene contratos/contexto
    # ya pegados por las llamadas de arriba (todas en modo_lectura=True).
    try:
        revisar_casos_avisos(stories)
    except Exception as e:
        print("Error revisando avisos de casos: %s" % e)
    t0 = _fase("revisar_casos_avisos", t0)

    aplicar_contraste(stories)  # Fase 18 (P2-11): sin red ni IA, lee lo ya calculado
    write_outputs(stories, report, demand, tend, fuente, dstatus, gdelt_data, gstatus,
                  sstatus, iastatus, social_data, social_status, cstatus, fcstatus, vstatus,
                  dstatus=declstatus, social_hist_data=social_hist_data, social_hist_status=social_hist_status)
    t0 = _fase("write_outputs", t0)

    if verbose:
        locales = [s for s in stories if s.get("es_local")]
        intl = [s for s in stories if s.get("internacional")]
        print("Feed: %d notas -> %d historias (%d Ecuador, %d internacionales). "
              "IA: %s | Contexto: %s | Social: %s"
              % (len(articles), len(stories), len(locales), len(intl),
                 iastatus, cstatus, social_status))
        imprimir_categorias(stories)
        tam_reg = _tam_registro_mb()
        if tam_reg is not None:
            print("Registro de historias (historias_registro.json): %.2f MB" % tam_reg)
        print("Tiempos: " + " ".join("%s=%.2fs" % (k, v) for k, v in tiempos.items())
              + " | TOTAL=%.2fs" % sum(tiempos.values()))
    # Fase 17 (log de arranque): esta linea es la MAS importante del diagnostico
    # de arranque lento -- siempre se escribe a arranque.log (nunca depende de
    # 'verbose', a diferencia de los prints de arriba, que son solo para
    # cuando SI hay consola), asi que un run_fast() disparado desde
    # _arrancar_backend() (Fase 16, .exe sin consola) deja registro igual.
    _log_arranque(
        "run_fast: %d articulos -> %d historias | " % (len(articles), len(stories))
        + " ".join("%s=%.2fs" % (k, v) for k, v in tiempos.items())
        + " | TOTAL=%.2fs" % sum(tiempos.values()))
    return stories


# ------------------------- senales (Fase 15, conectadas en Fase 18 P0-4) -------------------------
SENALES_MIN = float(os.environ.get("MONITOR_SENALES_MIN", "15"))
SENALES_IA_MAX = int(os.environ.get("MONITOR_SENALES_IA_MAX", "5"))


def senales_para_dashboard():
    """Lo que va a data.json: senales activas + estado honesto."""
    if senales is None:
        return {"senales": [], "estado_senales": "senales.py no disponible"}
    act = senales.activas()
    ult = senales.ultima_vuelta()
    return {"senales": act,
            "estado_senales": ("%d activas (ultima vuelta %s)" % (len(act), ult)) if ult
                              else "esperando la primera vuelta del motor de senales"}


def _ia_desenlace(material):
    """Para senales.detectar_sin_resolver: ¿el material muestra un desenlace?
    Pide una cita LITERAL (senales la valida en codigo)."""
    prompt = ("Estas son notas de prensa sobre UNA historia de Ecuador:\n%s\n\n"
              "¿Alguna de ellas muestra que el hecho ya se resolvio (sentencia, captura, "
              "reapertura, acuerdo, desmentido, cierre)? Responde SOLO JSON: "
              '{"hubo_desenlace": true|false, "cita": "frase copiada LITERAL del material o null"}'
              % material[:2500])
    return ia._generar_json(prompt, max_tokens=200) if ia else None


def _ia_texto_rapido(prompt):
    return ia._generar(prompt, max_tokens=160) if ia else None


def correr_senales(stories=None, demand=None):
    """Una vuelta del motor de senales con TODO lo que ya esta calculado.
    Nunca llama a feeds/redes; la IA (perfil rapido) queda acotada a
    SENALES_IA_MAX llamadas por vuelta. Devuelve el texto de estado."""
    if senales is None:
        return "senales.py no disponible"
    if stories is None:
        stories = _cargar_ultimas_historias() or []
    if demand is None:
        themes = sorted({t for s in stories for t in s.get("temas", [])})
        try:
            vals, _t, _e, fuente = get_demand(themes, modo_lectura=True)
            # Fase 18 (P2-12): Wikipedia mide hispanohablantes del mundo, no
            # Guayaquil/Ecuador -- no sirve como "la gente lo busca" para una
            # historia local. Solo cuenta Google Trends (geo EC).
            demand = vals if "Trends" in (fuente or "") else {}
        except Exception:
            demand = {}
    reg = _cargar_registro()
    entries, by_link = [], {}
    for eid, e in reg.items():
        d_ = {"eid": eid, "ciudad": e.get("ciudad", ""), "rep_titulo": e.get("fundador_titulo") or e.get("rep_titulo", ""),
              "ultimo": e["ultimo"].isoformat() if e.get("ultimo") else None,
              "fuentes": [dict(f_, date=f_["date"].isoformat() if f_.get("date") else None) for f_ in e.get("fuentes", [])]}
        entries.append(d_)
        for f_ in d_["fuentes"]:
            if f_.get("link"):
                by_link[f_["link"]] = d_
    try:
        with open(ENTITIES_PATH, encoding="utf-8") as f:
            entities = json.load(f)
    except Exception:
        entities = {}
    usar_ia = bool(ia and os.environ.get("MONITOR_NO_IA") != "1" and ia.backend_listo())
    r = senales.ciclo_senales(stories, demand=demand, registro_entries=entries, entities=entities,
                              saved=load_saved(), registro_by_link=by_link,
                              ia_desenlace=_ia_desenlace if usar_ia else None,
                              ia_texto=_ia_texto_rapido if usar_ia else None,
                              max_ia=SENALES_IA_MAX if usar_ia else 0)
    return r["estado"]


def _cargar_ultimas_historias():
    """Lee las historias que el hilo rapido ya publico (data.json): es el
    punto de entrega entre hilos (nunca se comparten objetos de Python). None
    si todavia no hay nada publicado (arranque en frio del hilo trabajador
    antes de la primera pasada del feed)."""
    try:
        with open(os.path.join(HERE, "data.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("historias") or []
    except Exception:
        return None


_RE_NUEVAS = re.compile(r"\+(\d+) nuevas")

def enrich_pass():
    """UNA pasada del hilo TRABAJADOR (Parte C): toma las historias que el
    hilo rapido ya publico y enriquece las que todavia no tienen cache --
    interpretacion IA, contexto por entidad, y analisis social -- de a UNA (el
    modelo local se serializa solo: no tiene sentido paralelizar llamadas a la
    misma GPU). Escribe SOLO en los caches en disco; NUNCA toca data.json ni
    dashboard.html (eso es trabajo exclusivo del hilo rapido, run_fast).

    Devuelve True si proceso algo nuevo (IA o contexto), False si no habia
    nada pendiente -- asi serve() sabe si debe seguir de largo (puede quedar
    mas backlog) o esperar MONITOR_WORKER_PAUSA antes de volver a mirar."""
    _t_enrich0 = time.time()
    stories = _cargar_ultimas_historias()
    if not stories:
        return False  # el hilo rapido todavia no publico nada que enriquecer
    _log_arranque("enrich_pass: arranca con %d historias publicadas" % len(stories))
    themes_present = sorted({t for s in stories for t in (s.get("temas") or [])})
    # Demanda/GDELT/SERCOP (task #17): cada una tiene su propio cache de
    # horas y se auto-limita (si el cache sigue fresco, no hace red) -- se
    # llaman ACA, en el hilo trabajador, para que un vencimiento (con GDELT
    # llego a tardar 559s medido en vivo) nunca frene el hilo rapido/el
    # arranque del servidor. Van primero porque son independientes del
    # modelo de IA (no compiten por la GPU) y son las mas lentas si vencio
    # el cache.
    # Problema 1 (2026-09-24): embeddings de historias_registro.json +
    # reconciliacion de duplicados por parafraseo -- opera sobre el registro
    # en disco, no sobre 'stories' (que run_fast ya reconstruyo desde ahi),
    # por eso va primero y no depende de nada de lo de abajo. Nunca corre en
    # run_fast (nunca llama a Ollama ahi, mismo criterio que el resto de
    # Parte C).
    # Fase 17: cada substep se mide por separado (arranque.log) -- enrich_pass
    # corre en bucle continuo en el hilo trabajador, y con el registro grande
    # (63MB+) cualquiera de estos puede ser el que explique "no termina".
    with _medir_etapa("embed_pendientes_registro"):
        try:
            embedstatus = _embed_pendientes_registro()
        except Exception as e:
            embedstatus = "error: %s" % e
    # Fase 9, parte D3 (Problema 3): reconciliacion cruzada de idioma
    # (ES<->EN) con el modelo multilingue -- mismo criterio que la de
    # arriba (nunca en run_fast), acotada a EMBED_MULTI_MAX_NEW por pasada.
    with _medir_etapa("embed_multilingue_pendientes_registro"):
        try:
            embedmultistatus = _embed_multilingue_pendientes_registro()
        except Exception as e:
            embedmultistatus = "error: %s" % e
    # Fase 14 (Paso 2, "evitar mezclas"): verificacion de coherencia sobre el
    # registro en disco -- mismo criterio que las dos de arriba (nunca en
    # run_fast, opera sobre historias_registro.json, no sobre 'stories').
    with _medir_etapa("coherencia_pendientes_registro"):
        try:
            coherenciastatus = _coherencia_pendientes_registro()
        except Exception as e:
            coherenciastatus = "error: %s" % e
    # Fase 8 (Problema 3): recoleccion de señales para alertas tempranas --
    # llamadas de red reales (Bluesky/Telegram/RSS oficiales), por eso va
    # aca (trabajador) y nunca en run_fast. vincular_con_prensa (barato, sin
    # red) sigue viviendo en write_outputs/procesar_alertas, con 'stories'
    # ya en memoria.
    with _medir_etapa("alertas_recolectar_senales"):
        if alertas is not None:
            try:
                alertstatus = alertas.recolectar_senales()
            except Exception as e:
                alertstatus = "error: %s" % e
        else:
            alertstatus = "no disponible"
    # Fase 9, parte D3: X + TikTok via Apify, orquestados por redes.py --
    # apagado por completo sin MONITOR_APIFY_TOKEN/x_config.json
    # (redes.activo() ya lo chequea). Reusa las mismas entidades por
    # historia que arma Pulso social (Problema C), pero excluyendo
    # boletines de plantilla (ver _historias_top_redes).
    with _medir_etapa("redes_pasada"):
        if redes is not None:
            try:
                top_redes = _historias_top_redes(stories, 12)
                historias_redes = []
                for s in top_redes:
                    query = consulta_x_historia(s)
                    if not query:
                        continue  # Fase 18 (P1-5.4): sin entidad buena no se gasta
                    f0 = (s.get("fuentes") or [{}])[0]
                    historias_redes.append({"titular": s.get("titular", ""), "query": query,
                                             "link": (f0.get("link") or s.get("titular", ""))[:180]})
                historias_redes = historias_redes[:6]
                # Fase 18 (P1-5.3): eventos en curso de Gran Guayaquil de las
                # ultimas 6 h -> busqueda reactiva, primero que todo.
                eventos_redes = []
                for s in stories:
                    ev = s.get("evento_en_curso")
                    if not ev or ev.get("lugar") != "Guayaquil" or (s.get("hours") or 99) > 6:
                        continue
                    f0 = (s.get("fuentes") or [{}])[0]
                    eventos_redes.append({"titular": s.get("titular", ""), "evento": ev,
                                          "terminos": terminos_evento_x(ev.get("tipo")),
                                          "link": (f0.get("link") or s.get("titular", ""))[:180]})
                barrios_redes = list(alertas.BARRIOS_GYE.keys()) if alertas else []
                redesstatus = redes.pasada(historias_redes, terminos_alerta_x(), barrios_redes,
                                           eventos=eventos_redes[:3])
            except Exception as e:
                redesstatus = "error: %s" % e
        else:
            redesstatus = "no disponible"
    with _medir_etapa("demanda_gdelt_sercop"):
        get_demand(themes_present)
        get_gdelt(themes_present)
        get_contracts(stories)
    with _medir_etapa("oficial_actualizar"):
        if oficial:
            try:
                oficial.actualizar()  # Fase 3: se auto-limita por frecuencia_seg propia de cada fuente
            except Exception:
                pass
    with _medir_etapa("get_ia"):
        iastatus = get_ia(stories)             # bounded por IA_MAX_NEW, cachea por link
    with _medir_etapa("get_triaje_intl"):
        try:
            triajestatus = get_triaje_intl(stories)  # Fase 18 (P1-9): lotes de 20, TRIAJE_MAX_NEW por pasada
        except Exception as e:
            triajestatus = "error: %s" % e
    # Fase 14, Paso 2: clasificacion con evidencia para notas ambiguas --
    # solo llama a la IA para historias con s["ciudad_discrepancia"]=True,
    # acotado a GEO_EVIDENCIA_MAX_NEW por pasada, cachea por story_key.
    with _medir_etapa("get_geo_evidencia"):
        gestatus = get_geo_evidencia(stories)  # bounded por GEO_EVIDENCIA_MAX_NEW, cachea por story_key
    with _medir_etapa("get_contexto"):
        cstatus = get_contexto(stories)        # bounded por CONTEXTO_MAX_NEW, cachea por link
    # get_factcheck despues de get_contexto: usa la entidad principal ya
    # verificada (s["contexto"]["principal"]) como segunda busqueda si el
    # titular solo no encuentra nada.
    with _medir_etapa("get_factcheck"):
        fcstatus = get_factcheck(stories)      # bounded por FACTCHECK_MAX_NEW, cachea por link
    # get_veredicto despues de contexto+SERCOP+FactCheck: los necesita a los
    # tres ya calculados como material para el veredicto (Problema 4).
    with _medir_etapa("get_veredicto"):
        vstatus = get_veredicto(stories)       # bounded por VEREDICTO_MAX_NEW, cachea por link
    with _medir_etapa("get_clase_contraste"):
        try:
            clasestatus = get_clase_contraste(stories)  # Fase 18 (P2-11)
        except Exception as e:
            clasestatus = "error: %s" % e
    # get_declaraciones despues de veredicto: no depende de el, pero sigue el
    # mismo orden de "lo barato primero" (extraccion con el modelo rapido) y
    # deja la llamada cara (comparar_declaraciones, modelo pesado) al final de
    # la secuencia de IA de esta pasada.
    with _medir_etapa("get_declaraciones"):
        dstatus = get_declaraciones(stories)   # bounded por DECL_MAX_NEW/DECL_CONTRASTE_MAX, cachea por par
    with _medir_etapa("get_social"):
        get_social(themes_present, tema_ambito=tema_ambito_map(stories))  # bounded/TTL propio, cachea por tema
    # Fase 9 (Problema C): Pulso social anclado a historias, TTL propio
    # (SOCIAL_HIST_TTL), acotado a SOCIAL_HIST_MAX historias por pasada.
    with _medir_etapa("get_social_historias"):
        try:
            get_social_historias(stories)
        except Exception as e:
            print("Error en get_social_historias: %s" % e)
    for st in (iastatus, gestatus, cstatus, fcstatus, vstatus, dstatus, triajestatus, clasestatus):
        m = _RE_NUEVAS.search(st or "")
        if m and int(m.group(1)) > 0:
            return True
    # embedstatus (Problema 1) no sigue el patron "+N nuevas" con un solo
    # numero -- trae DOS contadores (embeddings calculados, fusiones), y
    # cualquiera de los dos en positivo significa que hubo trabajo real esta
    # pasada (no hace falta esperar MONITOR_WORKER_PAUSA completo).
    if re.search(r"\+([1-9]\d*) nuevas|\+([1-9]\d*) fusiones", embedstatus or ""):
        return True
    if re.search(r"\+([1-9]\d*) nuevas|\+([1-9]\d*) fusiones", embedmultistatus or ""):
        return True
    # coherenciastatus (Fase 14): mismo criterio -- "+N nuevas"/"+N divisiones"
    # en positivo significa que hubo trabajo real esta pasada.
    if re.search(r"\+([1-9]\d*) nuevas|\+([1-9]\d*) divisiones", coherenciastatus or ""):
        return True
    # alertstatus (Problema 3): "oficiales: +N, sociales: +N" -- mismo
    # criterio, cualquiera de los dos contadores en positivo es trabajo real.
    if re.search(r"\+[1-9]\d*", alertstatus or ""):
        return True
    return False


# ------------------------- Parte E: aterrizaje del chat (grounding) -------------------------
# BUG REAL: le preguntaron al chat "quien es Alias Fito" (dentro del
# contexto ecuatoriano) y respondio "Carlos Ospina" -- un nombre inventado
# con total confianza. El chat, a diferencia del resto del pipeline, SI
# tiene permiso de opinar con su propio criterio (es su funcion: discutir
# interpretaciones, no solo repetir datos verificados) -- pero eso abre la
# puerta a que un modelo local alucine una identidad completa sin que se
# note. Arreglado con el MISMO patron que Parte B: antes de responder, se
# intenta reconocer si la pregunta pide identificar una entidad puntual
# (extraer_entidades_chat, modelo rapido) y se verifica contra Wikipedia
# (wiki.resumen, misma Capa 1 de busqueda desambiguada del bug de Carney).
# El resultado -- verificado o explicitamente "SIN VERIFICAR" -- se agrega
# al contexto de ESTA pregunta puntual antes de mandarselo al chat, y el
# system prompt (_PROMPT_CHAT_SISTEMA en ia.py) tiene la regla dura de nunca
# completar con un nombre que "suene familiar" cuando no hay nada verificado.

def _aterrizar_chat(item_contexto, mensaje):
    """Agrega material verificado (o la falta de el) sobre las entidades que
    el MENSAJE del chat pregunta, antes de dejarlo responder. No modifica
    item_contexto de forma persistente -- solo para esta pregunta puntual."""
    if ia is None or wiki is None:
        return item_contexto
    candidatos = ia.extraer_entidades_chat(mensaje, item_contexto)
    if not candidatos:
        return item_contexto
    bloques = []
    for c in candidatos:
        nombre, busqueda = c.get("nombre", ""), c.get("busqueda", "")
        r = wiki.resumen(nombre, busqueda=busqueda) if nombre else None
        if not r and nombre and busqueda and busqueda.strip().lower() != nombre.strip().lower():
            # Respaldo: si la busqueda con el nombre completo que adivino el
            # modelo no encontro nada (bug real: el propio modelo se
            # equivoco en el apellido -- "Villamaran" en vez de "Villamar"),
            # reintentar buscando por el alias TAL CUAL lo escribio el
            # periodista. Probado en vivo: "Alias Fito" solo resuelve bien a
            # "Fito (criminal)"; un nombre legal completo mal adivinado, no.
            r = wiki.resumen(nombre, busqueda=nombre)
        if r and not _nombre_se_solapa(nombre, r["nombre"]):
            # Mismo backstop deterministico de Parte B (ver _nombre_se_solapa):
            # este camino del chat nunca tuvo ningun chequeo de coherencia
            # (ni siquiera coincide_dominio) -- se agrega el barato aca, sin
            # llamar a la IA de vuelta, para no atrasar el chat.
            r = None
        if r:
            bloques.append("- %s (verificado en Wikipedia): %s" % (r["nombre"], r["extracto"]))
        else:
            bloques.append(
                "- \"%s\": SIN VERIFICAR -- no se encontro una pagina real de "
                "Wikipedia. No completes quien/que es con conocimiento propio; "
                "decile al periodista que no esta verificado." % nombre)
        time.sleep(0.3)  # gentil con Wikipedia, igual que Parte B
    return item_contexto + "\n\nMATERIAL VERIFICADO PARA ESTA PREGUNTA (Wikipedia):\n" + "\n".join(bloques)


# ------------------------- Fase 4: buscador por tema EN VIVO -------------------------
# A diferencia de TODO lo demas del monitor (que siempre lee cache/lo ya
# recolectado -- ver herramientas.py, "el codigo recupera, la IA solo
# redacta") y a diferencia del Asistente (Bloque 2, que tambien SOLO lee
# cache a proposito, ver herramientas.py), esta seccion pedida en la Fase 4
# SI dispara llamadas nuevas en vivo cuando Fernando escribe un tema --
# es la unica parte del proyecto donde una accion del usuario en el
# dashboard llega a golpear una API externa en el momento. Bounded a
# proposito (una sola llamada por fuente por ambito, nunca un loop) para no
# provocar 429 -- mismo espiritu que el resto del proyecto.
BUSQUEDAS_PATH = os.path.join(HERE, "busquedas.json")
BUSQUEDAS_MAX = 50  # busquedas guardadas (se recorta la mas vieja)
_AMBITOS_BUSQUEDA = ("guayaquil", "ecuador", "mundo")


def _cargar_busquedas():
    try:
        with open(BUSQUEDAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _guardar_busqueda(item):
    items = _cargar_busquedas()
    items.append(item)
    items = items[-BUSQUEDAS_MAX:]
    tmp = BUSQUEDAS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, BUSQUEDAS_PATH)


def _buscar_noticias_vivo(query, ambito):
    """Google News RSS geo-scopeado EN VIVO (mismo mecanismo que las 3
    fuentes 'Busqueda: <lugar>' agregadas a feeds.py en la Fase 1, pero para
    un termino arbitrario que escribe Fernando, no uno fijo). Para Mundo se
    manda el termino solo; Ecuador/Guayaquil le suman el lugar, mismo
    criterio que _social_query."""
    if ambito == "guayaquil":
        termino = query + " Guayaquil"
    elif ambito == "ecuador":
        termino = query + " Ecuador"
    else:
        termino = query
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(termino) + "&hl=es-419&gl=EC&ceid=EC:es-419"
    try:
        data, _etag, _lm, _status = fetch(url)
        items = parse_feed(data, "Google News (búsqueda)", "auto", google_news=True)
    except Exception as e:
        return [], "%s: %s" % (type(e).__name__, e)
    out = [{"titulo": a["title"], "link": a["link"],
            "fecha": a["date"].isoformat() if a["date"] else None,
            "resumen": a["summary"]} for a in items[:12]]
    return out, None


def _buscar_gente_vivo(query, ambito):
    if social is None:
        return [], "social.py no disponible"
    amb_social = "internacional" if ambito == "mundo" else ambito
    q = _social_query(query, amb_social)
    try:
        posts, errs = social.recolectar(q, subreddit=SOCIAL_SUBREDDIT, limite=15,
                                         youtube=True, ambito=amb_social, term_base=query)
    except Exception as e:
        return [], "%s: %s" % (type(e).__name__, e)
    if amb_social in ("ecuador", "guayaquil"):
        posts = [p for p in posts if not _post_es_foraneo(p)]
    out = [{"fuente": p.fuente, "tipo": p.tipo, "autor": p.autor, "texto": p.texto[:300],
            "url": p.url, "likes": p.likes, "reposts": p.reposts, "fecha": p.fecha}
           for p in sorted(posts, key=_social_score, reverse=True)[:10]]
    return out, ("; ".join(errs) if errs else None)


def _buscar_interes_vivo(query):
    """Demanda de busqueda EN VIVO para el termino exacto (no un tema del
    catalogo fijo) -- Trends primero, Wikipedia como respaldo (mismo orden
    de siempre en el proyecto, ver get_demand). BUG REAL encontrado probando
    esta funcion en vivo: `trends.interest_over_time()` devuelve UN dict
    ({termino: {"avg","series","times"}}), no una tupla de 3 -- y
    `wiki.interest()` pide un DICT {tema: termino}, no un string suelto.
    Las firmas reales (no las que se habian asumido al escribir esto)."""
    if trends:
        try:
            vals = trends.interest_over_time([query])
            v = (vals or {}).get(query)
            if v and v.get("avg") is not None:
                return {"fuente": "Google Trends", "valor": v["avg"], "serie": v.get("series")}
        except Exception:
            pass
    if wiki:
        try:
            vals = wiki.interest({query: query})
            v = (vals or {}).get(query)
            if v and v.get("avg") is not None:
                return {"fuente": "Wikipedia (vistas)", "valor": v["avg"], "serie": v.get("series")}
        except Exception:
            pass
    return None


def _buscar_contraste_vivo(query):
    out = {"constitucion": [], "boletines": [], "sercop": []}
    if oficial:
        out["constitucion"] = oficial.buscar_constitucion(query)
        out["boletines"] = oficial.buscar_oficial(query)
    if sercop:
        try:
            out["sercop"] = sercop.buscar(query, limit=5)
        except Exception:
            out["sercop"] = []
    return out


def buscar_en_vivo(query):
    """Punto de entrada de la Fase 4: para el termino 'query', arma un
    resultado por cada ambito (Guayaquil/Ecuador/Mundo, NUNCA mezclados) con
    noticias en vivo + voz de la gente + interes + contraste oficial. Se
    guarda en busquedas.json para poder volver a verla despues. La lectura
    del Asistente NO va aca (va aparte, streameada, ver
    _responder_busqueda_stream) para no frenar el resto con la espera del
    modelo pesado."""
    resultado = {"query": query, "ts": now_utc().isoformat(), "ambitos": {}}
    for amb in _AMBITOS_BUSQUEDA:
        noticias, err_n = _buscar_noticias_vivo(query, amb)
        gente, err_g = _buscar_gente_vivo(query, amb)
        resultado["ambitos"][amb] = {
            "noticias": noticias, "error_noticias": err_n,
            "gente": gente, "error_gente": err_g,
            "interes": _buscar_interes_vivo(query) if amb == "ecuador" else None,
            "contraste": _buscar_contraste_vivo(query) if amb != "mundo" else {"constitucion": [], "boletines": [], "sercop": []},
            "vacio": not noticias and not gente,
        }
    _guardar_busqueda(resultado)
    return resultado


# ============================ Fase 7 (Pasos B-E): Asistente de casos ============================
# Helpers de servidor para /api/casos... -- casos.py hace el trabajo de
# datos (solo lectura/escritura de disco); esto arma lo que necesita el
# dashboard (detalle completo de un caso) y el puente con Ollama (chat del
# caso, ingesta de documentos en segundo plano).

def _detalle_caso(caso_id):
    """Todo lo que el dashboard necesita para pintar un caso: el caso.json
    de siempre mas avisos/notas/evidencia/tablero/documentos, mas nuevo
    primero donde aplica -- un solo GET en vez de 5."""
    caso = casos.cargar_caso(caso_id) or {}
    out = dict(caso)
    out["avisos"] = list(reversed(casos.cargar_avisos(caso_id)))[:100]
    out["notas"] = list(reversed(casos.cargar_notas_caso(caso_id)))
    out["evidencia"] = list(reversed(casos.cargar_evidencia(caso_id)))
    out["tablero"] = casos.cargar_tablero(caso_id)
    out["documentos"] = casos.listar_documentos(caso_id)
    out["docs_estado"] = casos.cargar_estado_docs(caso_id)
    return out


def _material_caso(caso_id, mensaje):
    """Material del chat de un caso (Paso E): resumen del caso, los 3-4
    fragmentos de documentos mas relevantes a la PREGUNTA puntual (via
    embeddings), y avisos/evidencia recientes -- mismo criterio que
    agente._fmt_material_busqueda, texto legible con lo que hay REALMENTE,
    nunca inventa lo que falta."""
    caso = casos.cargar_caso(caso_id) or {}
    partes = ["=== CASO: %s ===" % caso.get("titulo", "")]
    if caso.get("descripcion"):
        partes.append("Descripcion del caso: %s" % caso["descripcion"])
    entidades = caso.get("entidades") or []
    if entidades:
        partes.append("Entidades que el periodista sigue en este caso: " + ", ".join(
            "%s (%s)" % (e.get("nombre", ""), e.get("tipo", "")) for e in entidades))

    frag_txt = []
    tiene_docs = bool(casos.listar_documentos(caso_id))
    if ia is not None and tiene_docs:
        emb = None
        try:
            emb = ia.embed(mensaje)
        except Exception:
            emb = None
        if emb:
            for f in casos.buscar_fragmentos(caso_id, emb, top_k=4):
                frag_txt.append("- [documento \"%s\", fragmento %s]: %s"
                                 % (f["doc_nombre"], f["posicion"], f["texto"][:800]))
    if frag_txt:
        partes.append("Fragmentos de los documentos del caso mas relacionados con la pregunta:\n"
                       + "\n".join(frag_txt))
    elif tiene_docs:
        partes.append("(el caso tiene documentos indexados, pero no se encontro ningun fragmento "
                       "claramente relacionado con esta pregunta puntual, o el modelo de embeddings "
                       "no esta disponible ahora mismo -- no inventes contenido de los documentos)")
    else:
        partes.append("(este caso todavia no tiene documentos subidos)")

    avisos = list(reversed(casos.cargar_avisos(caso_id)))[:5]
    if avisos:
        partes.append("Avisos recientes (el Dashboard detecto que algo nuevo menciona una entidad "
                       "de este caso):\n" + "\n".join(
            "- %s (entidad: %s): %s" % (a.get("ts", "")[:10], a.get("entidad", ""), a.get("texto", ""))
            for a in avisos))
    evidencia = list(reversed(casos.cargar_evidencia(caso_id)))[:5]
    if evidencia:
        def _etq(e):
            d = e.get("datos") or {}
            return d.get("titular") or d.get("objeto") or d.get("ocid") or e.get("id", "")
        partes.append("Evidencia que el periodista guardo en el caso:\n" + "\n".join(
            "- [%s] %s" % (e.get("tipo", ""), _etq(e)) for e in evidencia))
    return "\n\n".join(partes)


def _procesar_sugerencias_caso(caso_id, mensaje, respuesta):
    """Despues de que el chat de un caso responde: un paso APARTE y barato
    (modelo rapido del pipeline, nunca el de casos) para ver si el
    intercambio sugiere una entidad o conexion nueva. Quedan 'sugerida' de
    una -- Fernando decide despues si las confirma (pedido explicito: 'Solo
    yo las marco como verificada'), asi el chat no se detiene a preguntar."""
    if ia is None:
        return {"entidades": [], "conexiones": []}
    caso = casos.cargar_caso(caso_id) or {}
    propuestas = ia.extraer_sugerencias_caso(
        mensaje, respuesta, caso.get("titulo", ""),
        [e.get("nombre", "") for e in caso.get("entidades") or []])
    entidades_ok, conexiones_ok = [], []
    for e in propuestas.get("entidades", [])[:3]:
        try:
            casos.agregar_entidad(caso_id, e.get("nombre", ""), e.get("tipo", "otro"), [])
            entidades_ok.append(e)
        except Exception:
            pass
    for c in propuestas.get("conexiones", [])[:2]:
        try:
            con = casos.agregar_conexion_sugerida(
                caso_id, c.get("origen", ""), c.get("destino", ""), c.get("tipo", "relacion"),
                {"tipo": "chat", "pregunta": mensaje[:200], "ts": now_utc().isoformat()})
            conexiones_ok.append(con)
        except Exception:
            pass
    return {"entidades": entidades_ok, "conexiones": conexiones_ok}


def _procesar_ingesta_bg(caso_id, doc_id, nombre):
    """Corre en un hilo aparte (Paso C): el POST de subida ya respondio con
    el doc_id apenas se copio el archivo, esto hace el trabajo lento
    (extraer/fragmentar/pedir embeddings) sin bloquear esa respuesta HTTP."""
    try:
        casos.procesar_ingesta(caso_id, doc_id, nombre)
    except Exception as e:
        try:
            casos.actualizar_estado_doc(caso_id, doc_id, estado="error",
                                         error="%s: %s" % (type(e).__name__, e))
        except Exception:
            pass


def _escapar_html(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# Fase 16 (pedido de Fernando: "no quiero pantalla negra cmd... integrale un
# esqueleto si tarda en cargar"): pagina de carga que se muestra en la
# ventana nativa DESDE EL PRIMER INSTANTE (via webview.create_window(html=...),
# sin necesitar que el servidor ya este arriba) mientras corre la primera
# pasada del feed real en segundo plano. Mismos colores/variables que
# dashboard_template.html (claro/oscuro) para que el cambio a la app real,
# cuando este lista, no se sienta como una pantalla distinta.
_ESQUELETO_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spike</title>
<style>
  :root{ --bg:#f6f7f9; --card:#ffffff; --ink:#16181d; --muted:#5b6472; --line:#e5e8ee; --accent:#1f6feb; }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#141824; --card:#1c2130; --ink:#eef2f8; --muted:#9aa6bd; --line:#2b3242; --accent:#5b9bff; }
  }
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px -apple-system,Segoe UI,Roboto,Arial,sans-serif;
       height:100vh;display:flex;align-items:center;justify-content:center;}
  .wrap{width:min(420px,90vw);text-align:center;}
  .logo{font-size:30px;font-weight:800;letter-spacing:.5px;margin-bottom:6px;}
  .logo b{color:var(--accent);}
  .msg{color:var(--muted);margin:0 0 26px;}
  .spinner{width:34px;height:34px;margin:0 auto 22px;border-radius:50%;
           border:3px solid var(--line);border-top-color:var(--accent);
           animation:girar 0.8s linear infinite;}
  @keyframes girar{to{transform:rotate(360deg);}}
  .sk{background:var(--card);border:1px solid var(--line);border-radius:10px;
      padding:12px 14px;margin:10px 0;text-align:left;overflow:hidden;position:relative;}
  .sk .l{height:10px;border-radius:5px;background:var(--line);margin:6px 0;
         position:relative;overflow:hidden;}
  .sk .l.w60{width:60%;} .sk .l.w90{width:90%;} .sk .l.w40{width:40%;}
  .sk .l::after{content:"";position:absolute;inset:0;
      background:linear-gradient(90deg,transparent,rgba(255,255,255,.35),transparent);
      transform:translateX(-100%);animation:brillo 1.4s ease-in-out infinite;}
  @keyframes brillo{100%{transform:translateX(100%);}}
</style></head>
<body>
  <div class="wrap">
    <div class="spinner"></div>
    <div class="logo"><b>Spike</b></div>
    <p class="msg">Preparando las noticias de hoy&hellip;</p>
    <div class="sk"><div class="l w90"></div><div class="l w60"></div></div>
    <div class="sk"><div class="l w60"></div><div class="l w40"></div></div>
    <div class="sk"><div class="l w90"></div><div class="l w40"></div></div>
  </div>
</body></html>"""

# Se usa solo si la primera pasada del feed falla de verdad (ej. sin internet
# la primerísima vez) -- MENSAJE se reemplaza con .replace(), nunca con "%"
# ni .format(), porque el HTML/CSS de arriba ya tiene llaves y signos "%"
# propios que esos dos mecanismos interpretarían mal.
_ERROR_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spike</title>
<style>
  :root{ --bg:#f6f7f9; --card:#ffffff; --ink:#16181d; --muted:#5b6472; --line:#e5e8ee; --accent:#d64545; }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#141824; --card:#1c2130; --ink:#eef2f8; --muted:#9aa6bd; --line:#2b3242; --accent:#ff6b6b; }
  }
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px -apple-system,Segoe UI,Roboto,Arial,sans-serif;
       height:100vh;display:flex;align-items:center;justify-content:center;}
  .wrap{width:min(460px,90vw);text-align:center;}
  .logo{font-size:26px;font-weight:800;margin-bottom:14px;}
  .box{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);
       border-radius:10px;padding:14px 16px;text-align:left;color:var(--muted);
       font-size:13px;white-space:pre-wrap;word-break:break-word;}
</style></head>
<body><div class="wrap">
  <div class="logo">Spike no pudo arrancar</div>
  <div class="box">%%MENSAJE%%</div>
</div></body></html>"""


def serve(port=8000, minutes=None):
    """Modo TIEMPO REAL, dos velocidades (Parte C):
      - hilo RAPIDO (cada MONITOR_FEED_MIN minutos, por defecto 1 -- Fase 0,
        bajado de 2 a 1: el pipeline completo mide ~10s, hay margen de sobra;
        acepta fracciones, ej. MONITOR_FEED_MIN=0.5 para cada 30s): publica
        ya, sin esperar a la IA (run_fast). Cada feed ademas respeta su
        PROPIA frecuencia si la tiene (`frecuencia_seg` en feeds.py) y
        peticion condicional (ETag/Last-Modified) para no gastar de mas
        chequeando seguido un feed que no publico nada nuevo -- ver
        collect()/_fetch_feed().
      - hilo TRABAJADOR (de fondo, continuo): calcula IA/contexto/social de a
        uno y escribe SOLO en los caches (enrich_pass); el hilo rapido recoge
        el resultado en su proxima pasada (a lo sumo MONITOR_FEED_MIN despues).
    Sirve el dashboard en http://localhost:PORT (se refresca solo, consulta
    data.json cada minuto)."""
    feed_min = minutes if minutes else float(os.environ.get("MONITOR_FEED_MIN", "1"))
    worker_pausa = int(os.environ.get("MONITOR_WORKER_PAUSA", "20"))

    # Fase 16: la primera pasada del feed (la mas lenta, ~53 feeds RSS) ya NO
    # bloquea aca -- se movio a _arrancar_backend(), mas abajo, para poder
    # mostrar la ventana nativa YA (con un esqueleto de carga) en vez de
    # dejar al usuario mirando nada mientras esto corre.
    stop = threading.Event()

    def fast_loop():
        while not stop.wait(feed_min * 60):
            try:
                print("\n[%s] Feed rapido..." % now_utc().strftime("%H:%M:%S"))
                run_fast(verbose=True)
            except Exception as e:
                print("Error en feed rapido: %s" % e)

    def senales_loop():
        # Fase 18 (P0-4): hilo propio del motor de senales (Fase 15), cada
        # MONITOR_SENALES_MIN minutos. Espera 1 min al arrancar para que el
        # hilo rapido ya haya publicado data.json.
        espera = 60
        while not stop.wait(espera):
            espera = SENALES_MIN * 60
            try:
                with _medir_etapa("senales"):
                    print("[%s] Senales: %s" % (now_utc().strftime("%H:%M:%S"), correr_senales()))
            except Exception as e:
                print("Error en senales: %s" % e)

    def worker_loop():
        if oficial:
            try:
                # Fase 3: se construye UNA vez (o se reusa si ya existe y no
                # esta vencida, ver CONSTITUCION_MAX_DIAS) -- tarda unos
                # segundos (9 paginas de Wikisource), por eso va en el hilo
                # trabajador y no en el arranque del hilo rapido.
                oficial.construir_constitucion_si_hace_falta()
            except Exception:
                pass
        while not stop.is_set():
            # Fase 7, Paso E: mientras el chat de un caso esta generando, el
            # trabajador no compite por Ollama (pedido explicito, PC sin GPU
            # -- un solo modelo cargado a la vez). Chequeo corto (2s) en vez
            # de esperar worker_pausa entero, para retomar apenas el chat libera.
            if _trabajador_pausado():
                stop.wait(2)
                continue
            try:
                hizo_algo = enrich_pass()
            except Exception as e:
                print("Error en trabajador: %s" % e)
                hizo_algo = False
            # si hizo algo puede quedar mas backlog (ej. arranque en frio con
            # muchas historias sin cache): sigue de largo sin esperar. Solo
            # espera cuando ya no hay nada pendiente, para no golpear el disco
            # en un loop vacio.
            if not hizo_algo:
                stop.wait(worker_pausa)

    os.chdir(HERE)
    # Acceso desde el celular: si movil.json tiene acceso_red=true, el servidor
    # escucha en la red (no solo en esta PC). Cualquier aparato que NO sea esta
    # PC necesita la clave de movil.json (una vez; queda en una cookie) y solo
    # puede ver el dashboard y sus datos -- nunca los demas archivos de la carpeta.
    conf_movil = movil.cargar_config() if movil else {}
    acceso_red = bool(conf_movil.get("acceso_red"))
    clave = conf_movil.get("clave_acceso") or ""
    RUTAS_MOVIL = {"/dashboard.html", "/data.json", "/logo.png", "/saved.json", "/notas.json", "/busquedas.json"}
    handler = http.server.SimpleHTTPRequestHandler
    _primera_respuesta = {"hecho": False}  # Fase 17: diagnostico, ver do_GET
    class Quiet(handler):  # sin log por cada request
        def log_message(self, *a): pass

        def end_headers(self):
            # Fase 18 (bug real reportado por Fernando: "reorganice el
            # pulso social pero al abrir Spike.exe no se ven los cambios"):
            # WebView2 (el motor Chromium que usa pywebview en Windows)
            # aplica el cacheo heuristico normal de HTTP a
            # dashboard.html/data.json/etc. -- SimpleHTTPRequestHandler
            # nunca mandaba ningun Cache-Control, solo Last-Modified, asi
            # que el navegador quedaba libre de decidir por su cuenta
            # cuanto tiempo confiar en una copia vieja SIN preguntarle al
            # servidor. Confirmado: un archivo nuevo en disco (con nuevo
            # contenido/JS) podia seguir sirviendose desde el cache del
            # perfil de WebView2 de una corrida anterior del .exe.
            # "no-cache" (que NO es lo mismo que "no-store"): el navegador
            # puede seguir guardando la respuesta, pero queda OBLIGADO a
            # revalidar con el servidor antes de reusarla -- un chequeo
            # barato (compara fecha/ETag), no una descarga completa de
            # nuevo, asi que no hace mas lento el uso normal.
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def _marcar_primera_respuesta(self):
            # Fase 17: cuanto tardo el servidor en responder su PRIMER
            # request real (desde que arranco el proceso) -- si esto nunca
            # aparece en arranque.log, el servidor no llego ni a bindear/
            # responder nada, aunque la ventana este abierta con el esqueleto.
            if not _primera_respuesta["hecho"]:
                _primera_respuesta["hecho"] = True
                _log_arranque("servidor: primera respuesta HTTP (%s %s)" % (self.command, self.path))

        def _es_esta_pc(self):
            return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

        def _tiene_clave(self):
            if not clave:
                return False
            try:
                ck = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
                return "mk" in ck and hmac.compare_digest(ck["mk"].value, clave)
            except Exception:
                return False

        def _pedir_clave(self, error=False):
            aviso = "<p style='color:#c33'>Clave incorrecta.</p>" if error else ""
            page = ("<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
                    "<title>Monitor</title><body style='font:17px -apple-system,sans-serif;"
                    "max-width:420px;margin:15vh auto;padding:0 20px'>"
                    "<h2>Monitor de noticias</h2><p>Escribe la clave de acceso "
                    "(esta en <b>movil.json</b>, campo <i>clave_acceso</i>).</p>%s"
                    "<form><input name=k autocomplete=off style='font:inherit;width:100%%;"
                    "padding:10px;box-sizing:border-box'><button style='font:inherit;"
                    "margin-top:10px;padding:10px 18px'>Entrar</button></form>" % aviso)
            data = page.encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._marcar_primera_respuesta()
            ruta_api, _, query_api = self.path.partition("?")
            if ruta_api.startswith("/api/"):
                # Fase 7: lecturas del Asistente de casos (listar casos, detalle
                # de uno, "hoy en mis casos") -- mismo criterio de auth que
                # do_POST (esta PC siempre puede, otro aparato necesita la
                # clave de movil.json).
                if not (self._es_esta_pc() or self._tiene_clave()):
                    self.send_error(401)
                    return
                return self._do_GET_api(ruta_api, query_api)
            if self._es_esta_pc():
                return super().do_GET()  # esta PC: todo igual que siempre
            ruta, _, query = self.path.partition("?")
            k = (urllib.parse.parse_qs(query).get("k") or [""])[0]
            if k:
                if clave and hmac.compare_digest(k, clave):
                    # clave correcta: se guarda en cookie (1 ano) y se limpia la URL
                    self.send_response(302)
                    self.send_header("Set-Cookie", "mk=%s; Max-Age=31536000; Path=/; "
                                     "HttpOnly; SameSite=Lax" % clave)
                    self.send_header("Location", "/dashboard.html")
                    self.end_headers()
                    return
                return self._pedir_clave(error=True)
            if not self._tiene_clave():
                return self._pedir_clave()
            if ruta in ("/", ""):
                self.send_response(302)
                self.send_header("Location", "/dashboard.html")
                self.end_headers()
                return
            if ruta not in RUTAS_MOVIL:
                self.send_error(404, "Ruta no encontrada")
                return
            return super().do_GET()

        def do_HEAD(self):
            if self._es_esta_pc() or self._tiene_clave():
                return super().do_HEAD()
            self.send_error(401)

        def _leer_json(self):
            largo = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(largo).decode("utf-8"))

        def _responder_json(self, payload, status=200):
            resp = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        def _do_GET_contexto(self, query):
            """Fase 11 (v2): GET /api/contexto?id=<clave> -- contexto de 4
            bloques bajo demanda para UNA historia (clave = story_key(h), la
            misma formula que storyKey() del lado del cliente). Si ya hay un
            contexto fresco en cache (mismo hash de fuentes), lo devuelve sin
            gastar una llamada nueva a Gemini; si no, lo calcula ahora mismo
            y lo deja en contexto_cache.json para que la proxima pasada del
            hilo rapido tambien lo sirva desde data.json."""
            clave = (urllib.parse.parse_qs(query).get("id") or [""])[0]
            if not clave:
                self._responder_json({"ok": False, "error": "falta el parametro id"}, status=400)
                return
            if ia is None or wiki is None or os.environ.get("MONITOR_NO_CONTEXTO") == "1":
                self._responder_json({"ok": False, "error": "contexto desactivado (MONITOR_NO_CONTEXTO)"})
                return
            if not ia.disponible(IA_MODEL):
                self._responder_json({"ok": False, "error": getattr(ia, "last_error", None)
                                       or "IA no disponible (revisa GEMINI_API_KEY en .env)"})
                return
            historias = _cargar_ultimas_historias()
            s = next((h for h in (historias or []) if story_key(h) == clave), None)
            if s is None:
                self.send_error(404, "historia no encontrada en la ultima pasada publicada")
                return
            cache = {}
            try:
                with open(CONTEXTO_CACHE, encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception:
                pass
            huella = _hash_fuentes(s)
            entry = cache.get(clave)
            if entry is not None and entry.get("_fuentes_hash") == huella:
                self._responder_json({"ok": True, "contexto": entry, "recalculado": False})
                return
            registro = _cargar_registro()
            nuevo = _construir_contexto(s, registro)
            if nuevo is None:
                self._responder_json({"ok": False, "error": getattr(ia, "last_error", None)
                                       or "la IA no respondio"})
                return
            nuevo["_fuentes_hash"] = huella
            cache[clave] = nuevo
            try:
                with open(CONTEXTO_CACHE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
            except Exception:
                pass
            self._responder_json({"ok": True, "contexto": nuevo, "recalculado": True})

        def _do_GET_api(self, ruta, query=""):
            """Fase 7: lecturas del Asistente de casos.
              - GET /api/casos -> listar_casos()
              - GET /api/casos/<id> -> detalle completo (avisos/notas/
                evidencia/tablero/documentos/docs_estado)
              - GET /api/hoy -> avisos de TODOS los casos, mas nuevo primero
                ('Hoy en mis casos', pedido explicito).
            Fase 11 (v2): GET /api/contexto?id=<clave> -> contexto de 4
            bloques BAJO DEMANDA para una historia puntual (la clave es la
            misma que arma story_key()/storyKey() del lado del cliente) --
            para cuando Fernando abre una historia que no entro en el top 10
            local automatico de esta pasada."""
            if ruta == "/api/contexto":
                return self._do_GET_contexto(query)
            if casos is None:
                self.send_error(404, "Asistente de casos no disponible (falta casos.py)")
                return
            if ruta == "/api/hoy":
                self._responder_json({"ok": True, "avisos": casos.hoy_en_casos()})
                return
            partes = ruta.strip("/").split("/")
            if partes[:2] != ["api", "casos"]:
                self.send_error(404, "Ruta no encontrada")
                return
            if len(partes) == 2:
                self._responder_json({"ok": True, "casos": casos.listar_casos()})
                return
            caso_id = partes[2]
            if not casos.existe_caso(caso_id):
                self.send_error(404, "caso no encontrado")
                return
            self._responder_json({"ok": True, "caso": _detalle_caso(caso_id)})

        def _responder_stream(self, item_contexto, historial, mensaje, modo):
            """Streaming real del chat (Frente B): manda los headers YA (sin
            Content-Length -- mas simple que armar chunked encoding a mano;
            se cierra la conexion al terminar y eso le marca el EOF al
            navegador) y una linea NDJSON {"delta": "..."} apenas Ollama va
            generando cada pedazo, en vez de esperar el bloque completo. La
            linea final {"done": true, "ok": ...} le avisa al navegador que
            ya termino (con el motivo si fallo)."""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.close_connection = True
            self.end_headers()

            def on_delta(delta):
                linea = (json.dumps({"delta": delta}, ensure_ascii=False) + "\n").encode("utf-8")
                self.wfile.write(linea)
                self.wfile.flush()

            try:
                respuesta = ia.chat_stream(item_contexto, historial, mensaje, on_delta, modo=modo)
            except Exception:
                respuesta = None
            final = {"done": True, "ok": respuesta is not None}
            if respuesta is None:
                final["error"] = getattr(ia, "last_error", None) or "sin respuesta del modelo"
            try:
                self.wfile.write((json.dumps(final, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass  # el navegador ya se fue: no pasa nada, no hay a quien avisarle

        def _responder_asistente_stream(self, mensaje, historial):
            """Streaming del Asistente (Bloque 2, Parte F): mismo protocolo
            NDJSON que _responder_stream, mas un tipo de linea nuevo
            {"progreso": "..."} mientras el ciclo de herramientas consulta
            datos (agente.ciclo_herramientas puede tardar varias rondas
            antes de la respuesta final) -- asi el dashboard puede mostrar
            "consultando buscar_historias..." en vez de una espera muda de
            varios segundos sin ninguna señal."""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.close_connection = True
            self.end_headers()

            def on_progreso(texto):
                linea = (json.dumps({"progreso": texto}, ensure_ascii=False) + "\n").encode("utf-8")
                self.wfile.write(linea)
                self.wfile.flush()

            def on_delta(delta):
                linea = (json.dumps({"delta": delta}, ensure_ascii=False) + "\n").encode("utf-8")
                self.wfile.write(linea)
                self.wfile.flush()

            try:
                respuesta = agente.responder_stream(mensaje, historial, on_delta, on_progreso=on_progreso)
            except Exception:
                respuesta = None
            final = {"done": True, "ok": respuesta is not None}
            if respuesta is None:
                final["error"] = getattr(ia, "last_error", None) or "sin respuesta del modelo"
            try:
                self.wfile.write((json.dumps(final, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        def _responder_buscar_leer_stream(self, query, ambitos):
            """Fase 4: lectura del Asistente sobre un resultado de
            /api/buscar YA TRAIDO (el navegador se lo manda de vuelta, no se
            vuelve a buscar nada) -- mismo protocolo NDJSON que
            _responder_asistente_stream, sin progreso (no hay ciclo de
            herramientas aca, el material ya esta armado)."""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.close_connection = True
            self.end_headers()

            def on_delta(delta):
                linea = (json.dumps({"delta": delta}, ensure_ascii=False) + "\n").encode("utf-8")
                self.wfile.write(linea)
                self.wfile.flush()

            try:
                respuesta = agente.leer_busqueda_stream(query, ambitos, on_delta)
            except Exception:
                respuesta = None
            final = {"done": True, "ok": respuesta is not None}
            if respuesta is None:
                final["error"] = getattr(ia, "last_error", None) or "sin respuesta del modelo"
            try:
                self.wfile.write((json.dumps(final, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        def _responder_caso_chat_stream(self, caso_id, mensaje, historial):
            """Fase 7, Paso E: chat de UN caso. Mismo protocolo NDJSON de
            siempre, mas una linea final con 'sugerencias' (entidades/
            conexiones que la IA propuso durante este intercambio, ya
            guardadas como 'sugerida' -- ver _procesar_sugerencias_caso).
            Pausa el hilo trabajador mientras dura (pedido explicito, PC sin
            GPU): _pausar_trabajador()/_reanudar_trabajador() con try/finally
            para que una excepcion a mitad de camino no la deje pausada para
            siempre."""
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.close_connection = True
            self.end_headers()

            def on_delta(delta):
                linea = (json.dumps({"delta": delta}, ensure_ascii=False) + "\n").encode("utf-8")
                self.wfile.write(linea)
                self.wfile.flush()

            respuesta = None
            sugerencias = {"entidades": [], "conexiones": []}
            _pausar_trabajador()
            try:
                material = _material_caso(caso_id, mensaje)
                respuesta = agente._responder_final_stream(
                    mensaje, material, historial, on_delta, timeout=220,
                    modelo_fn=ia.elegir_modelo_caso, num_predict=1600, num_ctx=8192)
                if respuesta:
                    sugerencias = _procesar_sugerencias_caso(caso_id, mensaje, respuesta)
            except Exception:
                respuesta = None
            finally:
                _reanudar_trabajador()
            final = {"done": True, "ok": respuesta is not None, "sugerencias": sugerencias}
            if respuesta is None:
                final["error"] = getattr(ia, "last_error", None) or "sin respuesta del modelo"
            try:
                self.wfile.write((json.dumps(final, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        def _do_post_caso_doc(self, caso_id):
            """Fase 7, Paso C: subida de un documento. Sin multipart (el
            modulo 'cgi' que lo parseaba se saco de la libreria estandar en
            Python 3.13+, y esta PC corre 3.14) -- el navegador manda el
            archivo como base64 dentro de un JSON normal, igual que el resto
            de las rutas de este servidor. Responde apenas se copia el
            archivo (rapido) y arranca el trabajo lento (extraer/fragmentar/
            embeddings) en un hilo de fondo -- 'se muestra el progreso'
            (pedido explicito) via GET /api/casos/<id> mientras corre."""
            try:
                body = self._leer_json()
            except Exception:
                self.send_response(400); self.end_headers(); return
            nombre = str(body.get("nombre") or "").strip()[:200]
            b64 = body.get("contenido_b64") or ""
            if not nombre or not b64:
                self.send_response(400); self.end_headers(); return
            ext = os.path.splitext(nombre)[1].lower()
            if ext not in casos.EXT_SOPORTADAS:
                self._responder_json({"ok": False,
                    "error": "formato no soportado: %s (uso .txt/.md/.docx/.pdf)" % ext})
                return
            try:
                crudo = base64.b64decode(b64, validate=False)
            except Exception:
                self._responder_json({"ok": False, "error": "el archivo no se pudo decodificar"})
                return
            if len(crudo) > 20 * 1024 * 1024:
                self._responder_json({"ok": False, "error": "el archivo supera el limite de 20MB"})
                return
            tmp_dir = os.path.join(HERE, "casos", ".subidas_tmp")
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_path = os.path.join(tmp_dir, "%s_%s" % (uuid.uuid4().hex[:8], nombre))
            try:
                with open(tmp_path, "wb") as f:
                    f.write(crudo)
                doc_id, motivo = casos.iniciar_ingesta(caso_id, nombre, tmp_path)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            if doc_id is None:
                self._responder_json({"ok": False, "error": motivo})
                return
            self._responder_json({"ok": True, "doc_id": doc_id})
            threading.Thread(target=_procesar_ingesta_bg, args=(caso_id, doc_id, nombre), daemon=True).start()

        def _do_post_casos(self):
            """Fase 7 (Pasos B-E): todo lo que muta un caso.
              POST /api/casos                         -> crear caso {titulo, descripcion}
              POST /api/casos/<id>/entidades           -> {accion:"agregar"|"quitar", nombre, tipo, alias}
              POST /api/casos/<id>/notas               -> {accion:"agregar"|"borrar", texto|id}
              POST /api/casos/<id>/avisos              -> marca todos los avisos como vistos
              POST /api/casos/<id>/evidencia           -> {accion:"agregar"|"quitar", tipo, datos, origen|id}
              POST /api/casos/<id>/tablero             -> {accion:"marcar"|"quitar", conexion_id, estado}
              POST /api/casos/<id>/docs                -> subir documento (base64), ver _do_post_caso_doc
              POST /api/casos/<id>/chat                -> chat del caso (streaming), ver _responder_caso_chat_stream
            """
            if casos is None:
                self.send_error(404, "Asistente de casos no disponible (falta casos.py)")
                return
            partes = self.path.strip("/").split("/")  # ["api","casos", ...]
            if len(partes) == 2:
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                titulo = str(body.get("titulo") or "").strip()
                if not titulo:
                    self.send_response(400); self.end_headers(); return
                try:
                    caso = casos.crear_caso(titulo, body.get("descripcion") or "")
                except Exception as e:
                    self._responder_json({"ok": False, "error": str(e)})
                    return
                self._responder_json({"ok": True, "caso": caso})
                return

            caso_id = partes[2] if len(partes) > 2 else ""
            if not casos.existe_caso(caso_id):
                self.send_error(404, "caso no encontrado")
                return
            sub = partes[3] if len(partes) > 3 else ""

            if sub == "entidades":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                try:
                    if body.get("accion") == "quitar":
                        caso = casos.quitar_entidad(caso_id, body.get("nombre", ""))
                    else:
                        caso = casos.agregar_entidad(caso_id, body.get("nombre", ""),
                                                      body.get("tipo", "otro"), body.get("alias") or [])
                except Exception as e:
                    self._responder_json({"ok": False, "error": str(e)}); return
                self._responder_json({"ok": True, "caso": caso})

            elif sub == "notas":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                if body.get("accion") == "borrar":
                    notas = casos.borrar_nota_caso(caso_id, body.get("id", ""))
                else:
                    try:
                        casos.agregar_nota_caso(caso_id, body.get("texto", ""))
                    except Exception as e:
                        self._responder_json({"ok": False, "error": str(e)}); return
                    notas = casos.cargar_notas_caso(caso_id)
                self._responder_json({"ok": True, "notas": list(reversed(notas))})

            elif sub == "avisos":
                self._responder_json({"ok": True, "avisos": casos.marcar_avisos_vistos(caso_id)})

            elif sub == "evidencia":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                if body.get("accion") == "quitar":
                    ev = casos.quitar_evidencia(caso_id, body.get("id", ""))
                else:
                    casos.agregar_evidencia(caso_id, body.get("tipo", "historia"),
                                             body.get("datos") or {}, body.get("origen", ""))
                    ev = casos.cargar_evidencia(caso_id)
                self._responder_json({"ok": True, "evidencia": list(reversed(ev))})

            elif sub == "tablero":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                try:
                    if body.get("accion") == "quitar":
                        t = casos.quitar_conexion(caso_id, body.get("conexion_id", ""))
                    else:
                        t = casos.marcar_conexion(caso_id, body.get("conexion_id", ""), body.get("estado", ""))
                except Exception as e:
                    self._responder_json({"ok": False, "error": str(e)}); return
                self._responder_json({"ok": True, "tablero": t})

            elif sub == "docs":
                self._do_post_caso_doc(caso_id)

            elif sub == "chat":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                mensaje = str(body.get("mensaje") or "").strip()
                historial = body.get("historial") or []
                if not mensaje or ia is None or agente is None:
                    self.send_response(400); self.end_headers(); return
                if not ia.disponible(IA_MODEL):
                    self._responder_json({"ok": False,
                        "error": getattr(ia, "last_error", None) or "Ollama no responde"})
                    return
                self._responder_caso_chat_stream(caso_id, mensaje, historial)

            else:
                self.send_error(404, "Ruta no encontrada")

        def do_POST(self):
            self._marcar_primera_respuesta()
            if not (self._es_esta_pc() or self._tiene_clave()):
                self.send_error(401)
                return
            self._do_POST()

        def _do_POST(self):
            """Endpoints propios del servidor. Todo lo demas (dashboard.html,
            data.json, saved.json/notas.json de lectura) lo sirve GET normal,
            heredado de SimpleHTTPRequestHandler -- no hace falta duplicarlo.
              - /api/guardar (Parte C): guardar/quitar una historia completa en
                saved.json.
              - /api/nota (2026-09-23, cuarta pasada): guardar/borrar una nota
                personal por historia o tema en notas.json -- ver load_notas/
                save_notas (bug real: esta ruta nunca se habia conectado, el
                frontend la llamaba desde hace dias y siempre daba 404).
              - /api/chat (Parte E): puente a Ollama para el chat por item --
                el navegador NUNCA habla directo con Ollama. On-demand, lo
                dispara el usuario desde el detalle de una tarjeta; puede
                tardar unos segundos (es una llamada a un LLM local), por eso
                el servidor corre con hilos (ThreadingMixIn, ver mas abajo):
                sin eso, una consulta de chat en curso congelaria el resto del
                dashboard (poll de data.json, cambiar de seccion, etc.)."""
            if self.path == "/api/guardar":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                accion = body.get("accion")
                items = load_saved()
                if accion == "guardar":
                    historia = body.get("historia") or {}
                    key = story_key(historia)
                    if not key:
                        self.send_response(400); self.end_headers(); return
                    items = [it for it in items if story_key(it) != key]
                    historia = dict(historia)
                    historia["_guardado_ts"] = now_utc().isoformat()
                    items.append(historia)
                    save_saved(items)
                elif accion == "quitar":
                    key = body.get("id") or ""
                    items = [it for it in items if story_key(it) != key]
                    save_saved(items)
                else:
                    self.send_response(400); self.end_headers(); return
                self._responder_json({"ok": True, "guardadas": items})
            elif self.path == "/api/nota":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                key = str(body.get("id") or "")[:180]
                if not key:
                    self.send_response(400); self.end_headers(); return
                texto = str(body.get("texto") or "").strip()
                notas = load_notas()
                if texto:
                    notas[key] = {"texto": texto, "titular": body.get("titular") or "",
                                  "ts": now_utc().isoformat()}
                else:
                    notas.pop(key, None)
                save_notas(notas)
                self._responder_json({"ok": True, "notas": notas})
            elif self.path == "/api/chat":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                mensaje = str(body.get("mensaje") or "").strip()
                item_contexto = str(body.get("item") or "")
                historial = body.get("historial") or []
                # "rapido" (def.) usa el modelo rapido del pipeline; "profundo"
                # usa el modelo critico dedicado -- ver MODOS_CHAT en ia.py.
                modo = body.get("modo") or "rapido"
                if modo not in ("rapido", "profundo"):
                    modo = "rapido"
                if not mensaje or ia is None:
                    self.send_response(400); self.end_headers(); return
                if not ia.disponible(IA_MODEL):
                    self._responder_json({"ok": False,
                        "error": getattr(ia, "last_error", None) or "Ollama no responde"})
                    return
                # Capa de aterrizaje (grounding) ANTES de dejar que el chat
                # responda -- ver bug real de "Alias Fito" en Decisiones ya
                # tomadas. NO cambia item_contexto de forma persistente, solo
                # para esta pregunta puntual.
                item_contexto = _aterrizar_chat(item_contexto, mensaje)
                # Streaming real (Frente B): la respuesta se manda de a
                # pedazos apenas Ollama los genera, no en un solo bloque al
                # final -- ver _responder_stream.
                self._responder_stream(item_contexto, historial, mensaje, modo)
            elif self.path == "/api/asistente":
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                mensaje = str(body.get("mensaje") or "").strip()
                historial = body.get("historial") or []
                if not mensaje or agente is None:
                    self.send_response(400); self.end_headers(); return
                if not ia or not ia.disponible(IA_MODEL):
                    self._responder_json({"ok": False,
                        "error": getattr(ia, "last_error", None) or "Ollama no responde"})
                    return
                self._responder_asistente_stream(mensaje, historial)
            elif self.path == "/api/buscar":
                # Fase 4: buscador EN VIVO -- a diferencia de todo lo demas,
                # esto SI dispara llamadas de red nuevas en el momento
                # (Google News/social/Trends-Wikipedia/SERCOP por cada
                # ambito). Tarda ~15-25s medido en vivo -- el servidor con
                # hilos (ServidorHilos) ya garantiza que esto no congele el
                # resto del dashboard mientras corre (mismo mecanismo que
                # /api/chat).
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                query = str(body.get("query") or "").strip()[:120]
                if not query:
                    self.send_response(400); self.end_headers(); return
                try:
                    resultado = buscar_en_vivo(query)
                    self._responder_json({"ok": True, "resultado": resultado})
                except Exception as e:
                    self._responder_json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
            elif self.path == "/api/buscar_leer":
                # Fase 4: lectura del Asistente sobre resultados YA TRAIDOS
                # (el navegador manda de vuelta lo que /api/buscar le dio) --
                # streameada, aparte de /api/buscar, para que la espera del
                # modelo pesado no frene mostrar noticias/gente/interes.
                try:
                    body = self._leer_json()
                except Exception:
                    self.send_response(400); self.end_headers(); return
                query = str(body.get("query") or "").strip()
                ambitos = body.get("ambitos") or {}
                if not query or not ambitos or agente is None:
                    self.send_response(400); self.end_headers(); return
                if not ia or not ia.disponible(IA_MODEL):
                    self._responder_json({"ok": False,
                        "error": getattr(ia, "last_error", None) or "Ollama no responde"})
                    return
                self._responder_buscar_leer_stream(query, ambitos)
            elif self.path == "/api/casos" or self.path.startswith("/api/casos/"):
                # Fase 7 (Pasos B-E): crear/mutar un caso, subir un documento,
                # o chatear con el -- ver _do_post_casos para el detalle de
                # cada sub-ruta.
                self._do_post_casos()
            else:
                self.send_error(404, "Ruta no encontrada")

    # El enlazado de puerto ya NO se hace en linea recta aca (Fase 16): se
    # movio adentro de _arrancar_backend(), mas abajo, para poder mostrar la
    # ventana nativa (con el esqueleto) ANTES de que exista un servidor real
    # -- ver la nota grande al principio de la funcion.
    class ServidorHilos(socketserver.ThreadingMixIn, socketserver.TCPServer):
        # Parte E: /api/chat puede tardar unos segundos (llamada a Ollama) --
        # sin hilos, esa espera congelaria TODO el servidor (hasta el poll de
        # data.json que hace el dashboard cada minuto). daemon_threads=True:
        # que un hilo de request colgado no impida cerrar el programa.
        daemon_threads = True

    resultado = {"error": None}
    listo = threading.Event()

    # Fase 17 (Paso 2, "carga progresiva" -- pedido explicito de Fernando):
    # bindear el puerto y arrancar el servidor HTTP ACA, ANTES de la primera
    # pasada del feed -- es practicamente instantaneo (nunca depende de
    # red/IA), a diferencia de run_fast() que ahora sabemos que puede tardar.
    # Con el servidor ya arriba, si YA existe un dashboard.html/data.json de
    # una corrida anterior (el caso normal, salvo la primerisima vez que se
    # usa el programa), la ventana puede mostrar ESE dato real de inmediato
    # -- ni siquiera el esqueleto -- en vez de esperar a que termine una
    # pasada nueva. No hace falta tocar el frontend para esto:
    # dashboard_template.html YA sabe refrescarse solo cuando data.json
    # cambia (poll periodico + "Actualizado hace...", ver Decisiones ya
    # tomadas) -- escribir data.json nuevo cuando este listo alcanza.
    puerto_pedido, srv, intento = port, None, port
    while srv is None:
        try:
            srv = ServidorHilos(("0.0.0.0" if acceso_red else "127.0.0.1", intento), Quiet)
        except OSError as e:
            if intento - puerto_pedido >= 50:  # limite de sensatez: no buscar para siempre
                print("No encontre un puerto libre entre %d y %d (%s)." % (puerto_pedido, intento, e))
                return
            print("Puerto %d ocupado (%s) -- seguramente otra instancia viva. Probando %d..."
                  % (intento, e, intento + 1))
            intento += 1
    port = intento
    url = "http://localhost:%d/dashboard.html" % port
    global MOVIL_PUERTO
    MOVIL_PUERTO = port
    _log_arranque("serve: puerto %d bindeado" % port)
    # Si dashboard.html no existe todavia (primerisima corrida en esta
    # carpeta, o alguien lo borro a mano), no hay nada real que mostrar --
    # ahi si hace falta el esqueleto mientras se genera el primero.
    hay_dashboard_previo = os.path.exists(os.path.join(HERE, "dashboard.html"))

    def _arrancar_backend():
        # La primera pasada del feed + arrancar los hilos de fondo corren
        # ACA, en un hilo aparte cuando hay ventana nativa, para no bloquear
        # su aparicion (el puerto/servidor YA estan arriba, ver mas arriba).
        try:
            # Fase 18 (P0-2/P0-3): una sola vez por instalacion, rehace el
            # registro con las reglas nuevas (mezclas viejas separadas).
            try:
                migrar_registro_si_hace_falta(verbose=True)
            except Exception as ex:
                _log_arranque("registro: migracion fase18 fallo (%s) -- se sigue con el registro tal cual" % ex)
            _log_arranque("_arrancar_backend: primera pasada del feed (rapida, no espera a la IA)...")
            _t_backend0 = time.time()
            run_fast(verbose=True)
            _log_arranque("_arrancar_backend: primera pasada terminada (%.2fs) -- dashboard %s"
                          % (time.time() - _t_backend0,
                             "actualizado" if hay_dashboard_previo else "listo para mostrarse"))

            threading.Thread(target=fast_loop, daemon=True).start()
            threading.Thread(target=worker_loop, daemon=True).start()
            threading.Thread(target=senales_loop, daemon=True).start()

            print("\n" + "=" * 56)
            if port != puerto_pedido:
                print("  (puerto %d ocupado -> quedo en %d)" % (puerto_pedido, port))
            print("  Monitor en vivo:  %s" % url)
            print("  Feed rapido cada %d min (nunca espera a la IA)." % feed_min)
            print("  Trabajador de fondo enriqueciendo (IA/contexto/social) cada ~%ds." % worker_pausa)
            print("  Deja esta ventana abierta. Para detener: Ctrl+C")
            if acceso_red and movil:
                print("  Desde el celular:")
                for et, u in movil.enlaces_dashboard(conf_movil, port):
                    print("    %s: %s" % (et, u))
            if movil and conf_movil.get("avisos_activos"):
                print("  Avisos al iPhone: activos (tema ntfy en movil.json). Probar: python monitor.py movil")
            print("=" * 56 + "\n")
        except Exception as e:
            resultado["error"] = e
            _log_arranque("_arrancar_backend: ERROR en la primera pasada (%s)" % e)
        finally:
            listo.set()

    def _fallback_navegador():
        # Mismo respaldo de siempre (abrir el navegador, servidor bloqueante
        # en el hilo principal) -- se usa tanto si no hay pywebview instalado
        # como si la ventana nativa no se pudo crear o crasheo.
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nDetenido.")
            stop.set()
            srv.shutdown()

    def al_cerrar_ventana():
        # El cierre de la ventana debe detener los bucles y el servidor para que no quede un proceso oculto.
        stop.set()
        srv.shutdown()

    window = None
    if webview is not None:
        try:
            # text_select=True (Fase 12, bug real reportado por Fernando: "es
            # imposible seleccionar o sombrear el texto con el mouse") --
            # pywebview deshabilita la seleccion de texto por defecto en
            # TODA la ventana nativa, no solo el chat, y ningun CSS del
            # dashboard puede arreglarlo por su cuenta.
            if hay_dashboard_previo:
                # Fase 17: mostrar el dashboard REAL de entrada (el servidor
                # ya esta arriba) en vez del esqueleto -- la pasada nueva
                # sigue corriendo de fondo y el dashboard se refresca solo
                # cuando termine, sin que el usuario tenga que esperar nada.
                window = webview.create_window("Spike", url, text_select=True)
                _log_arranque("serve: ventana nativa creada, mostrando el dashboard existente mientras se actualiza")
            else:
                # Fase 16 (pedido de Fernando: "no quiero pantalla negra
                # cmd... integrale un esqueleto si tarda en cargar"):
                # primera corrida en esta carpeta, todavia no hay nada real
                # que mostrar -- esqueleto de carga inline mientras
                # _arrancar_backend() corre la primera pasada.
                window = webview.create_window("Spike", html=_ESQUELETO_HTML, text_select=True)
                _log_arranque("serve: ventana nativa creada, esqueleto visible (sin datos previos todavia)")
            window.events.closed += al_cerrar_ventana
        except Exception as e:
            print("No se pudo abrir la ventana de escritorio (%s). Se abrira el dashboard en el navegador." % e)
            window = None

    if window is None:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _arrancar_backend()
        _fallback_navegador()
        return

    # El backend nativo puede exigir el hilo principal; el servidor queda
    # atendiendo en segundo plano desde YA (no espera a la primera pasada).
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    if not hay_dashboard_previo:
        def _cuando_este_listo():
            listo.wait()
            if resultado["error"] is not None:
                try:
                    window.load_html(_ERROR_HTML.replace("%%MENSAJE%%", _escapar_html(resultado["error"])))
                except Exception:
                    pass
                return
            _log_arranque("serve: navegando del esqueleto al dashboard real (%s)" % url)
            window.load_url(url)  # del esqueleto al dashboard real, misma ventana
        threading.Thread(target=_cuando_este_listo, daemon=True).start()

    threading.Thread(target=_arrancar_backend, daemon=True).start()
    try:
        webview.start()
    except Exception as e:
        print("La ventana de escritorio fallo (%s). Se abrira el dashboard en el navegador." % e)
        _fallback_navegador()
        return
    # Respaldo por si el backend retorna sin emitir el evento de cierre.
    if not stop.is_set():
        stop.set()
        try:
            srv.shutdown()
        except Exception:
            pass


def _chequear_entorno_ia():
    """Fase 11: avisa al arrancar si falta la clave para las funciones de IA.

    Las corridas de ejemplo y las que desactivan IA explícitamente no requieren
    esta clave; el chequeo solo confirma que está configurada, no que funcione.
    """
    if os.environ.get("MONITOR_SAMPLE") == "1" or os.environ.get("MONITOR_NO_IA") == "1":
        return
    if ia is None or not ia.configurada():
        print()
        print("Falta configurar GEMINI_API_KEY.")
        print("Crea (o completa) el archivo .env en esta misma carpeta con una linea como:")
        print("  GEMINI_API_KEY=tu_clave_aqui")
        print("El programa NO puede seguir sin esto (las funciones de IA son el corazon")
        print("de esta version). Si queres correrlo a proposito sin IA, usa MONITOR_NO_IA=1.")
        sys.exit(1)


def main():
    # Fase 17: primera linea de arranque.log de todo el proceso -- confirma
    # con HERE cual carpeta esta usando de verdad (la hipotesis mas comun de
    # ".exe lento" es que arranque en una carpeta distinta a la del .py, ver
    # CLAUDE.md/COORDINACION.md), y si es el .exe compilado o el .py interpretado.
    _log_arranque("=== arranque (%s) ===  HERE=%s  argv=%s" %
                  ("exe compilado" if getattr(sys, "frozen", False) or "__compiled__" in globals()
                   else "python interpretado", HERE, sys.argv[1:]))
    args = [a for a in sys.argv[1:] if a != "--sample"]  # --sample viejo se ignora
    if args and args[0] == "movil":
        # configura/prueba los avisos al iPhone y muestra los enlaces para el celular
        if movil is None:
            print("Falta movil.py en esta carpeta.")
        else:
            movil.probar(int(args[1]) if len(args) > 1 else 8000)
        return
    _chequear_entorno_ia()
    if not args or args[0] == "serve":
        # Fase 12: sin argumentos (ej. doble clic sobre el ejecutable
        # compilado) ahora arranca serve() por defecto -- antes caia en la
        # corrida unica (run_once), asi que un doble clic nunca abria ninguna
        # ventana. "python monitor.py serve [puerto] [minutos]" sigue
        # aceptando los mismos parametros de siempre.
        port = int(args[1]) if len(args) > 1 else 8000
        minutes = float(args[2]) if len(args) > 2 else None  # None: usa MONITOR_FEED_MIN (def. 1)
        serve(port, minutes)
    elif args[0] == "probar_sitemaps":
        probar_sitemaps()
    elif args[0] == "reconstruir_registro":
        reconstruir_registro(verbose=True)
    elif args[0] == "once":
        # La corrida unica bloqueante (el default de antes de esta fase)
        # queda accesible a mano con "once" -- la siguen necesitando
        # scripts/pruebas que generan datos sin abrir servidor ni ventana
        # (ej. MONITOR_SAMPLE=1 python monitor.py once).
        run_once(verbose=True)
        print("Listo: abre dashboard.html en tu navegador.")
    else:
        print("Argumento no reconocido: %r" % args[0])
        print("Uso: python monitor.py            (abre la app de escritorio)")
        print("     python monitor.py serve [puerto] [minutos]")
        print("     python monitor.py once         (corrida unica sin servidor)")
        print("     python monitor.py movil [puerto]")
        print("Para que se actualice solo en vivo:  python3 monitor.py serve")


if __name__ == "__main__":
    main()
