# -*- coding: utf-8 -*-
"""
Capa de IA del monitor -- EN LA NUBE via Gemini (Fase 10, 2026-09-26).

Hasta la Fase 9 esto hablaba con Ollama local (localhost:11434: qwen2.5:3b,
monitor-critico, nomic-embed-text/bge-m3). Esos modelos colapsaban el hardware
de esta PC (VRAM chica: el servidor se caia y las pasadas del hilo trabajador,
enrich_pass, quedaban corruptas a mitad de camino). Decision de Fernando: sacar
Ollama POR COMPLETO y pasar a Gemini en la nube via su API REST (SIN el SDK
google-generativeai, que quedo sin soporte el 30-11-2025 -- todo con urllib,
libreria estandar, misma regla de oro del proyecto).

ESTADO ACTUAL (Fase 10, Fases 3 y 4 -- transporte conectado): las tres
funciones de transporte (_generar, _generar_stream, embed) hablan de verdad
con la API REST de Gemini (generativelanguage.googleapis.com/v1beta). Los
prompts, los candados en codigo y el parseo de cada funcion publica NO
cambiaron, y ninguna firma publica cambio (monitor.py/agente.py/casos.py/
declaraciones.py siguen llamando lo mismo que llamaban con Ollama).

Perfiles (reemplazan a los "modelos" de Ollama, mapeados a modelos concretos
de Gemini por variable de entorno -- ver MODELO_RAPIDO/MODELO_PROFUNDO):
  - PERFIL_RAPIDO: triaje y extraccion por lotes en el hilo trabajador
    (analizar, entidades, contexto, veredicto, posturas, declaraciones,
    traduccion, coincide_dominio, sugerencias de casos, chat "rapido").
    Default: gemini-3.8-flash.
  - PERFIL_PROFUNDO: lectura editorial y redaccion con criterio
    (interpretar, comparar_declaraciones, chat "profundo", respuesta final
    del Asistente y del chat de casos). Default: gemini-3.1-pro-preview (esta
    en PREVIEW -- si el modelo deja de existir o da 404 sostenido, este
    perfil cae solo al modelo rapido, ver _resolver_modelo()).

El parametro 'forzado' que siguen aceptando varias funciones es solo por
compatibilidad con los llamadores existentes: ya no elige un modelo de
Ollama y se ignora (Gemini se elige por PERFIL, no por nombre suelto).

Clave: GEMINI_API_KEY en el archivo .env de la raiz del proyecto (se lee con
libreria estandar, sin python-dotenv). Va SIEMPRE en el header
'x-goog-api-key' (nunca en la URL) y NUNCA se imprime, ni en last_error, ni
en data.json, ni en ningun mensaje de error (_error_http limpia cualquier URL
antes de usarla en un mensaje).

Presupuesto duro (mismo patron que xapi.py/redes.py, pero para Gemini):
MONITOR_IA_TOPE_DIA_USD/MONITOR_IA_TOPE_MES_USD, registrado en ia_gasto.json
a partir del 'usageMetadata' REAL de cada respuesta (nunca estimado a
ciegas). Precios verificados en vivo el 2026-09-26 en
https://ai.google.dev/gemini-api/docs/pricing (ver PRECIO_* mas abajo).

El catalogo de categorias tematicas sigue siendo FIJO (viene de
feeds.KEYWORDS): la IA nunca inventa categorias nuevas ni las elimina del
catalogo, solo decide para CADA NOTA cuales de esas categorias ya existentes
le aplican.
"""

import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from feeds import KEYWORDS

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")


def _cargar_env(ruta=ENV_PATH):
    """Lee .env (formato CLAVE=valor, una por linea, '#' para comentarios)
    y lo carga en os.environ SIN pisar variables que ya esten definidas en el
    sistema. Solo libreria estandar: no hace falta python-dotenv para esto."""
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                clave = clave.strip()
                valor = valor.strip().strip('"').strip("'")
                if clave and clave not in os.environ:
                    os.environ[clave] = valor
    except FileNotFoundError:
        pass
    except Exception:
        pass  # un .env mal formado nunca debe tumbar el monitor


_cargar_env()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
UA = "Monitor-Noticias/1.0 (uso personal, via API REST de Gemini)"

PERFIL_RAPIDO = "rapido"
PERFIL_PROFUNDO = "profundo"

MODELO_RAPIDO = os.environ.get("MONITOR_GEMINI_RAPIDO", "gemini-3.8-flash")
MODELO_PROFUNDO = os.environ.get("MONITOR_GEMINI_PROFUNDO", "gemini-3.1-pro-preview")
GEMINI_EMBED_MODEL = os.environ.get("MONITOR_GEMINI_EMBED", "gemini-embedding-001")

# Precios verificados EN VIVO el 2026-09-26 en
# https://ai.google.dev/gemini-api/docs/pricing (nunca supuestos):
#   gemini-3.8-flash:        input $0.75/1M tok, output $3.75/1M tok (tier pago, vigente hasta 2026-12-31)
#   gemini-3.1-pro-preview:  input $2.00/1M tok, output $12.00/1M tok (prompts <=200k tokens)
#   gemini-embedding-001: NO figura en la pagina de precios actual (la
#   reemplazo alli "Gemini Embedding 2", $0.20/1M tok de input) -- se usa ese
#   valor como estimacion CONSERVADORA (embeddings solo tienen costo de
#   input, sin output) mientras no se mida el costo real de este modelo en
#   particular via usageMetadata.
PRECIO_RAPIDO_INPUT = 0.75 / 1_000_000
PRECIO_RAPIDO_OUTPUT = 3.75 / 1_000_000
PRECIO_PROFUNDO_INPUT = 2.00 / 1_000_000
PRECIO_PROFUNDO_OUTPUT = 12.00 / 1_000_000
PRECIO_EMBED_INPUT = 0.20 / 1_000_000

TOPE_DIA_USD = float(os.environ.get("MONITOR_IA_TOPE_DIA_USD", "1.00"))
TOPE_MES_USD = float(os.environ.get("MONITOR_IA_TOPE_MES_USD", "20.00"))

GASTO_PATH = os.path.join(HERE, "ia_gasto.json")
ESTADO_PATH = os.path.join(HERE, "ia_nube_estado.json")  # cache: modelos confirmados + pausas por 429

_PENDIENTE = "falta GEMINI_API_KEY en .env"

last_error = None
_model = None  # compatibilidad: monitor.get_ia() lo imprime en su estado ("ok (%s, ...)")

# Catalogo FIJO de categorias tematicas: todas las hojas de feeds.KEYWORDS
# (Elecciones, Salud, Cultura/Comunidad, ...) mas "otros" para cuando ninguna
# aplica. Una sola fuente de verdad (feeds.py) para que IA y palabras clave
# nunca se desalineen.
TEMA_CATALOG = sorted({tema for bank in KEYWORDS.values() for tema in bank})
TEMA_OTROS = "otros"
# Match tolerante a mayusculas/espacios: el modelo a veces no reproduce el
# nombre EXACTO de la categoria (p.ej. "cultura/comunidad" en vez de
# "Cultura/Comunidad"), pero igual debe mapear a la categoria fija real.
_TEMA_LOOKUP = {t.strip().lower(): t for t in TEMA_CATALOG}
_TEMA_LOOKUP[TEMA_OTROS] = TEMA_OTROS

# Eje geografico jerarquico que decide la IA: guayaquil implica ecuador.
GEO_CATALOG = ["guayaquil", "ecuador", "internacional"]

# ------------------------- gasto (dia + mes, mismo patron que redes.py) -------------------------

def _hoy():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _mes():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def _cargar_gasto():
    try:
        with open(GASTO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"dias": {}, "meses": {}, "historial": []}


def _guardar_gasto(g):
    tmp = GASTO_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False)
    os.replace(tmp, GASTO_PATH)


def gasto_hoy():
    return _cargar_gasto().get("dias", {}).get(_hoy(), 0.0)


def gasto_mes():
    return _cargar_gasto().get("meses", {}).get(_mes(), 0.0)


def _registrar_gasto(monto, motivo=""):
    if monto <= 0:
        return
    g = _cargar_gasto()
    hoy, mes = _hoy(), _mes()
    g.setdefault("dias", {})[hoy] = round(g.get("dias", {}).get(hoy, 0.0) + monto, 6)
    g.setdefault("meses", {})[mes] = round(g.get("meses", {}).get(mes, 0.0) + monto, 6)
    hist = g.setdefault("historial", [])
    hist.append({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "monto": round(monto, 6), "motivo": motivo})
    g["historial"] = hist[-300:]
    _guardar_gasto(g)


def _cabe_en_presupuesto(costo_max):
    if gasto_hoy() + costo_max > TOPE_DIA_USD:
        return False, "tope diario de IA (%.4f + %.4f > %.2f USD)" % (gasto_hoy(), costo_max, TOPE_DIA_USD)
    if gasto_mes() + costo_max > TOPE_MES_USD:
        return False, "tope mensual de IA (%.4f + %.4f > %.2f USD)" % (gasto_mes(), costo_max, TOPE_MES_USD)
    return True, ""


def _costo_generacion(perfil, tokens_in, tokens_out):
    if perfil == PERFIL_PROFUNDO:
        return tokens_in * PRECIO_PROFUNDO_INPUT + tokens_out * PRECIO_PROFUNDO_OUTPUT
    return tokens_in * PRECIO_RAPIDO_INPUT + tokens_out * PRECIO_RAPIDO_OUTPUT


def estado_gasto():
    """Para data.json['estado_ia_nube'] y el panel 'Salud de los datos'."""
    return {"gasto_hoy": round(gasto_hoy(), 5), "gasto_mes": round(gasto_mes(), 5),
            "tope_dia": TOPE_DIA_USD, "tope_mes": TOPE_MES_USD,
            "restante_hoy": round(max(0.0, TOPE_DIA_USD - gasto_hoy()), 5),
            "restante_mes": round(max(0.0, TOPE_MES_USD - gasto_mes()), 5)}


# ------------------------- estado: modelos confirmados + pausa por 429 -------------------------

_ESTADO_TTL = 3600.0  # confirmar el catalogo de modelos cada hora, no en cada llamada

def _cargar_estado():
    try:
        with open(ESTADO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_estado(e):
    tmp = ESTADO_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(tmp, ESTADO_PATH)


def _listar_modelos_reales():
    """GET /v1beta/models, cacheado (_ESTADO_TTL) -- nunca en cada llamada.
    Devuelve un set de nombres base (sin 'models/' adelante) o None si la
    consulta fallo (se sigue confiando en el ultimo catalogo bueno que haya
    en cache, si lo hay)."""
    e = _cargar_estado()
    if e.get("modelos") and (time.time() - e.get("modelos_ts", 0)) < _ESTADO_TTL:
        return set(e["modelos"])
    try:
        req = urllib.request.Request(GEMINI_BASE + "/models",
                                      headers={"x-goog-api-key": GEMINI_API_KEY, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        nombres = {m.get("name", "").split("/")[-1] for m in data.get("models", [])}
        e["modelos"] = sorted(nombres)
        e["modelos_ts"] = time.time()
        _guardar_estado(e)
        return nombres
    except Exception:
        return set(e.get("modelos") or []) or None


def _modelo_existe(nombre):
    modelos = _listar_modelos_reales()
    if modelos is None:
        return True  # no se pudo confirmar (red caida): no bloquear por eso, ya lo va a decir el 404 real si no existe
    return nombre in modelos


def _resolver_modelo(perfil):
    """MODELO_PROFUNDO esta en PREVIEW -- si no aparece en el catalogo real
    (o quedo pausado por 404 sostenido, ver _pausado), el perfil profundo
    CAE al rapido, y se anota en el estado (nunca en silencio)."""
    if perfil == PERFIL_PROFUNDO:
        if _modelo_existe(MODELO_PROFUNDO) and not _pausado(PERFIL_PROFUNDO):
            return MODELO_PROFUNDO, False
        return MODELO_RAPIDO, True  # cayo al rapido
    return MODELO_RAPIDO, False


def _pausado(clave):
    e = _cargar_estado()
    hasta = e.get("pausas", {}).get(clave)
    if not hasta:
        return False
    try:
        return dt.datetime.now(dt.timezone.utc) < dt.datetime.fromisoformat(hasta)
    except Exception:
        return False


def _pausar(clave, minutos, motivo=""):
    e = _cargar_estado()
    hasta = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutos)
    e.setdefault("pausas", {})[clave] = hasta.isoformat()
    e.setdefault("pausas_motivo", {})[clave] = motivo
    _guardar_estado(e)


def _motivo_pausa(clave):
    return _cargar_estado().get("pausas_motivo", {}).get(clave, "")


# ------------------------- estado publico -------------------------

def configurada():
    """True si hay GEMINI_API_KEY en .env o en el entorno."""
    return bool(GEMINI_API_KEY)


def backend_listo():
    """True cuando hay clave Y el modelo rapido (el minimo indispensable)
    existe de verdad en el catalogo de Gemini Y no esta pausado por 429."""
    if not configurada():
        return False
    if _pausado(PERFIL_RAPIDO):
        return False
    return _modelo_existe(MODELO_RAPIDO)


def disponible(forzado=""):
    """monitor.py lo usa antes de cada lote del hilo trabajador y en las
    rutas /api/chat, /api/asistente, /api/buscar_leer y el chat de casos."""
    global last_error
    if not configurada():
        last_error = _PENDIENTE
        return False
    if _pausado(PERFIL_RAPIDO):
        last_error = "perfil rapido pausado por limite de peticiones: %s" % _motivo_pausa(PERFIL_RAPIDO)
        return False
    if not _modelo_existe(MODELO_RAPIDO):
        last_error = "el modelo '%s' (MONITOR_GEMINI_RAPIDO) no existe en el catalogo real de Gemini" % MODELO_RAPIDO
        return False
    return True


def elegir_modelo(forzado=""):
    """Compatibilidad (monitor._social_model): devuelve el perfil rapido si
    hay backend, o None."""
    return PERFIL_RAPIDO if disponible() else None


def elegir_modelo_chat():
    """Compatibilidad (agente.py): perfil profundo si hay backend, o None."""
    return PERFIL_PROFUNDO if disponible() else None


def elegir_modelo_caso():
    """Compatibilidad (chat de casos, monitor.py -> agente): perfil profundo."""
    return PERFIL_PROFUNDO if disponible() else None


def estado():
    """Texto honesto para el dashboard/terminal."""
    if not configurada():
        return "pausada: %s" % _PENDIENTE
    if not backend_listo():
        return "pausada: %s" % (last_error or "backend no listo")
    modelo_prof, cayo = _resolver_modelo(PERFIL_PROFUNDO)
    extra = " (perfil profundo cayo a %s: %s no disponible)" % (MODELO_RAPIDO, MODELO_PROFUNDO) if cayo else ""
    return "ok (nube: %s / %s)%s -- gasto hoy $%.4f" % (MODELO_RAPIDO, MODELO_PROFUNDO, extra, gasto_hoy())


# ------------------------- transporte REST (punto UNICO que habla con Gemini) -------------------------

def _error_http(e, contexto=""):
    """Nunca repite una URL (podria llevar parametros sensibles) -- solo el
    codigo HTTP y el motivo tipico de cada uno."""
    try:
        cuerpo = e.read().decode("utf-8", "ignore")[:300]
    except Exception:
        cuerpo = ""
    if e.code == 400:
        return "HTTP 400 (pedido invalido%s)" % (": %s" % cuerpo if cuerpo else "")
    if e.code == 401 or e.code == 403:
        return "HTTP %s (clave de Gemini invalida o sin permiso)" % e.code
    if e.code == 404:
        return "HTTP 404 (modelo no encontrado)"
    if e.code == 429:
        return "HTTP 429 (limite de peticiones)"
    return "HTTP %s%s" % (e.code, (" -- %s" % contexto) if contexto else "")


def _retry_after(e):
    try:
        v = e.headers.get("Retry-After")
        return float(v) if v else None
    except Exception:
        return None


def _cuota_cero(e):
    """BUG REAL medido en vivo (Fase 10, prueba minima): gemini-3.1-pro-preview
    devuelve 429 con 'limit: 0' en el cuerpo -- NO es un limite de trafico
    transitorio, es que la cuenta no tiene facturacion habilitada para ese
    modelo en el nivel gratis. Reintentar cada 5 min es inutil (va a fallar
    SIEMPRE hasta que Fernando habilite facturacion o se cambie de modelo) --
    se detecta este caso especifico para pausar mucho mas tiempo (6h) en vez
    de reintentar sin sentido."""
    try:
        cuerpo = e.read().decode("utf-8", "ignore")
    except Exception:
        return False
    return "limit: 0" in cuerpo or '"limit":0' in cuerpo.replace(" ", "")


def _post_gemini(path, payload, timeout, perfil_pausa=None, max_reintentos=2):
    """POST generico contra la API REST de Gemini, con reintento con espera
    creciente ante 429 (maximo max_reintentos veces, respetando Retry-After
    si viene) y pausa del perfil despues de agotar los reintentos -- nunca
    deja que una rafaga de 429 frene toda la pasada del trabajador (el
    llamador recibe None y sigue con la siguiente nota)."""
    global last_error
    url = GEMINI_BASE + "/" + path
    body = json.dumps(payload).encode("utf-8")
    espera = 2.0
    for intento in range(max_reintentos + 1):
        req = urllib.request.Request(url, data=body, method="POST",
                                      headers={"Content-Type": "application/json",
                                               "x-goog-api-key": GEMINI_API_KEY, "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if _cuota_cero(e):
                    if perfil_pausa:
                        _pausar(perfil_pausa, 360, "sin cuota gratis para este modelo (requiere facturacion habilitada)")
                    last_error = "HTTP 429 (sin cuota gratis para este modelo -- requiere facturacion habilitada)"
                    return None
                if intento < max_reintentos:
                    time.sleep(_retry_after(e) or espera)
                    espera *= 2
                    continue
                if perfil_pausa:
                    _pausar(perfil_pausa, 5, "HTTP 429 sostenido tras %d reintentos" % max_reintentos)
                last_error = _error_http(e)
                return None
            if e.code in (500, 503) and intento < max_reintentos:
                # BUG REAL medido en vivo: 503 "modelo con alta demanda" es
                # transitorio (confirmado -- el MISMO request repetido segundos
                # despues funciono bien) pero antes NO se reintentaba, solo se
                # reintentaba 429. Mismo backoff creciente que 429.
                time.sleep(espera)
                espera *= 2
                continue
            last_error = _error_http(e)
            return None
        except Exception as ex:
            last_error = type(ex).__name__
            return None
    return None


def _contents_de(prompt, mensajes):
    if mensajes:
        return [{"role": ("model" if m.get("role") == "assistant" else "user"),
                  "parts": [{"text": str(m.get("content", ""))}]} for m in mensajes]
    return [{"role": "user", "parts": [{"text": prompt or ""}]}]


def _generation_config(modelo, temperatura, max_tokens, json_mode=False):
    """BUG REAL encontrado en vivo (Fase 10, prueba minima): gemini-3.8-flash
    gasta ~90-100 tokens de 'pensamiento' INVISIBLE (thoughtsTokenCount) por
    default, incluso en un prompt trivial de una palabra -- con poco
    max_tokens, se queda sin presupuesto para el texto visible y devuelve
    ('', finishReason=MAX_TOKENS), mismo patron de bug que ya paso con
    modelos de razonamiento locales (monitor-critico/deepseek-r1) documentado
    en fases anteriores. 'thinkingConfig: {thinkingLevel: low}' (probado en
    vivo, medido: 0 thoughtsTokenCount) SI elimina ese costo -- se aplica
    segun el MODELO REAL que se va a usar (no el perfil pedido): si el
    perfil profundo cayo al modelo rapido por estar pausado/no disponible
    (ver _resolver_modelo), tambien hay que apagar el thinking, sino se
    repite el mismo bug de respuesta vacia con el modelo de respaldo."""
    # Medido en vivo con el modelo profundo real (gemini-3.1-pro-preview,
    # billing habilitado): 'thinkingLevel: high' gasta ~1150 tokens de
    # pensamiento antes de escribir una frase corta; 'low' gasta ~580 (la
    # mitad) con calidad comparable en el caso probado (misma idea central,
    # una frase completa). Con el rapido (gemini-3.8-flash), 'low' elimina
    # el pensamiento por completo (medido: thoughtsTokenCount=None). Se usa
    # 'low' para los DOS perfiles -- el ahorro de costo es real y medido, la
    # calidad no bajo en el caso de prueba.
    cfg = {"temperature": temperatura, "maxOutputTokens": max_tokens,
           "thinkingConfig": {"thinkingLevel": "low"}}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    return cfg


def _generar(prompt="", sistema=None, mensajes=None, json_mode=False, perfil=PERFIL_RAPIDO,
             temperatura=0.2, max_tokens=300, timeout=60):
    """PUNTO UNICO de generacion de texto (sin streaming), via
    generateContent. Devuelve el texto de la respuesta, o None si fallo (con
    el motivo en last_error, SIN la clave)."""
    global last_error
    last_error = None
    if not configurada():
        last_error = _PENDIENTE
        return None
    # _resolver_modelo PRIMERO (no antes de chequear la pausa): si el perfil
    # profundo esta pausado/no disponible, cae al rapido -- BUG REAL
    # encontrado en vivo, chequear "_pausado(perfil)" antes de resolver el
    # modelo bloqueaba la llamada ENTERA aunque el modelo de respaldo (rapido)
    # estuviera perfectamente disponible.
    modelo, cayo = _resolver_modelo(perfil)
    perfil_efectivo = PERFIL_RAPIDO if cayo else perfil
    if _pausado(perfil_efectivo):
        last_error = "perfil '%s' pausado por limite de peticiones: %s" % (perfil_efectivo, _motivo_pausa(perfil_efectivo))
        return None
    # presupuesto: costo MAXIMO posible (max_tokens de salida completos, mas
    # una estimacion generosa de entrada por caracteres/4) antes de llamar.
    entrada_aprox = (len(prompt or "") + sum(len(str(m.get("content", ""))) for m in (mensajes or []))
                     + len(sistema or "")) / 4
    costo_max = _costo_generacion(perfil_efectivo, entrada_aprox, max_tokens)
    ok, razon = _cabe_en_presupuesto(costo_max)
    if not ok:
        last_error = "presupuesto agotado: %s" % razon
        return None
    payload = {
        "contents": _contents_de(prompt, mensajes),
        "generationConfig": _generation_config(modelo, temperatura, max_tokens, json_mode=json_mode),
    }
    if sistema:
        payload["systemInstruction"] = {"parts": [{"text": sistema}]}
    data = _post_gemini("models/%s:generateContent" % modelo, payload, timeout, perfil_pausa=perfil_efectivo)
    if data is None:
        return None
    candidatos = data.get("candidates") or []
    if not candidatos:
        pf = (data.get("promptFeedback") or {}).get("blockReason")
        last_error = "sin candidatos en la respuesta%s" % (" (bloqueado: %s)" % pf if pf else "")
        return None
    cand = candidatos[0]
    finish = cand.get("finishReason", "")
    if finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
        last_error = "respuesta bloqueada por Gemini (finishReason=%s)" % finish
        return None
    partes = (cand.get("content") or {}).get("parts") or []
    texto = "".join(p.get("text", "") for p in partes)
    uso = data.get("usageMetadata") or {}
    costo_real = _costo_generacion(perfil_efectivo, uso.get("promptTokenCount", 0) or 0,
                                    uso.get("candidatesTokenCount", 0) or 0)
    _registrar_gasto(costo_real, "generar (%s, %s)" % (perfil_efectivo, modelo))
    if not texto:
        last_error = "respuesta vacia (finishReason=%s)" % finish
        return None
    return texto


def _generar_stream(prompt, on_delta, sistema=None, perfil=PERFIL_PROFUNDO,
                    temperatura=0.3, max_tokens=1600, timeout=220):
    """Como _generar, pero via streamGenerateContent?alt=sse: llama a
    on_delta(texto_parcial) por cada pedazo (linea 'data:') que llega, y
    devuelve el texto completo acumulado (o None). Un on_delta que falla (el
    navegador se fue) nunca corta la generacion -- se ignora y se sigue
    leyendo el stream."""
    global last_error
    last_error = None
    if not configurada():
        last_error = _PENDIENTE
        return None
    modelo, cayo = _resolver_modelo(perfil)
    perfil_efectivo = PERFIL_RAPIDO if cayo else perfil
    if _pausado(perfil_efectivo):
        last_error = "perfil '%s' pausado por limite de peticiones: %s" % (perfil_efectivo, _motivo_pausa(perfil_efectivo))
        return None
    entrada_aprox = (len(prompt or "") + len(sistema or "")) / 4
    costo_max = _costo_generacion(perfil_efectivo, entrada_aprox, max_tokens)
    ok, razon = _cabe_en_presupuesto(costo_max)
    if not ok:
        last_error = "presupuesto agotado: %s" % razon
        return None
    payload = {
        "contents": _contents_de(prompt, None),
        "generationConfig": _generation_config(modelo, temperatura, max_tokens),
    }
    if sistema:
        payload["systemInstruction"] = {"parts": [{"text": sistema}]}
    url = "%s/models/%s:streamGenerateContent?alt=sse" % (GEMINI_BASE, modelo)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Content-Type": "application/json",
                                           "x-goog-api-key": GEMINI_API_KEY, "User-Agent": UA})
    acumulado = []
    uso_final = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for linea_b in r:
                linea = linea_b.decode("utf-8", "ignore").strip()
                if not linea.startswith("data:"):
                    continue
                trozo = linea[len("data:"):].strip()
                if not trozo or trozo == "[DONE]":
                    continue
                try:
                    chunk = json.loads(trozo)
                except ValueError:
                    continue
                candidatos = chunk.get("candidates") or []
                if candidatos:
                    finish = candidatos[0].get("finishReason", "")
                    if finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
                        last_error = "respuesta bloqueada por Gemini (finishReason=%s)" % finish
                        break
                    partes = (candidatos[0].get("content") or {}).get("parts") or []
                    delta = "".join(p.get("text", "") for p in partes)
                    if delta:
                        acumulado.append(delta)
                        try:
                            on_delta(delta)
                        except Exception:
                            pass  # que el navegador se haya ido no debe tumbar la generacion
                if chunk.get("usageMetadata"):
                    uso_final = chunk["usageMetadata"]
    except urllib.error.HTTPError as e:
        if e.code == 429:
            if _cuota_cero(e):
                _pausar(perfil_efectivo, 360, "sin cuota gratis para este modelo (requiere facturacion habilitada)")
            else:
                _pausar(perfil_efectivo, 5, "HTTP 429 durante streaming")
        last_error = _error_http(e)
        if not acumulado:
            return None
    except Exception as ex:
        last_error = type(ex).__name__
        if not acumulado:
            return None
    costo_real = _costo_generacion(perfil_efectivo, uso_final.get("promptTokenCount", 0) or 0,
                                    uso_final.get("candidatesTokenCount", 0) or 0)
    _registrar_gasto(costo_real, "generar_stream (%s, %s)" % (perfil_efectivo, modelo))
    return "".join(acumulado) or None


def _json(texto):
    """Parsea la respuesta de un prompt que pide JSON. Tolera que el modelo
    envuelva el JSON en un bloque ```json ... ``` o agregue texto alrededor.
    Devuelve dict, o None si no hay JSON valido."""
    if not texto:
        return None
    t = texto.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    try:
        r = json.loads(t)
        return r if isinstance(r, dict) else None
    except ValueError:
        pass
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        try:
            r = json.loads(t[i:j + 1])
            return r if isinstance(r, dict) else None
        except ValueError:
            return None
    return None


def _generar_json(prompt, perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=300, timeout=60):
    """_generar + _json en un paso. None si fallo la llamada o el JSON."""
    global last_error
    texto = _generar(prompt, json_mode=True, perfil=perfil, temperatura=temperatura,
                     max_tokens=max_tokens, timeout=timeout)
    if texto is None:
        return None
    r = _json(texto)
    if r is None:
        last_error = "respuesta sin JSON valido"
    return r


_PROMPT = (
    "Clasifica esta noticia y responde SOLO un JSON valido con estas claves:\n"
    '{"temas": [{"cat": "<categoria del catalogo>", "score": 0.0-1.0}, ...],\n'
    ' "geo": ["guayaquil"|"ecuador"|"internacional", ...]}.\n\n'
    # La interpretacion ya NO se pide aca (bug real 2026-09-22): pedirle al
    # mismo modelo chico clasificar + ubicar + interpretar en un solo JSON hacia
    # que el campo 'interpretacion' se llenara con la JUSTIFICACION de la
    # etiqueta ("Noticia internacional sobre X, sin impacto en Ecuador") -- de
    # ahi la queja de que "la IA interpreta todo literal" pese a las
    # correcciones del prompt. Ahora es una llamada aparte: interpretar().
    "CATALOGO FIJO de categorias tematicas (no existen otras, no inventes ninguna "
    "fuera de esta lista):\n%s\n\n"
    "Para 'temas': las palabras clave ya pre-etiquetaron esta nota con: %s. Tu "
    "unica tarea aqui es DEPURAR esa lista, nunca ampliarla: revisa cada categoria "
    "y, si NO corresponde al contenido real, no la incluyas en tu respuesta (ej.: "
    "una nota sobre la muerte de un poeta que quedo etiquetada 'Comercio/Inversion' "
    "por una palabra clave suelta no debe llevar esa categoria). No agregues "
    "ninguna categoria del catalogo que no este en esa lista pre-etiquetada, "
    "aunque creas que aplica. Da un score de 0 a 1 de tu confianza en cada "
    "categoria de la lista que SI incluyas. Si ninguna de esas categorias aplica "
    "de verdad, responde "
    '"temas": [{"cat": "otros", "score": 1}]. Nunca inventes categorias fuera del '
    "catalogo.\n\n"
    "Para 'geo' (jerarquico): \"guayaquil\" si el hecho ocurre en o trata "
    "especificamente de Guayaquil (en ese caso incluye tambien \"ecuador\", nunca "
    "\"guayaquil\" solo); \"ecuador\" si es noticia nacional de Ecuador (incluidas "
    "Quito y otras ciudades: una nota de Quito es \"ecuador\", nunca \"guayaquil\"); "
    "\"internacional\" si el foco esta fuera de Ecuador, aunque mencione bloques como "
    "la Union Europea.\n"
    "Ejemplo: \"Canada siendo invitado a la Union Europea\" = [\"internacional\"] "
    "(no menciona a Ecuador).\n\n"
    "Titular: %s\nResumen: %s"
)

_CATALOGO_TXT = ", ".join(TEMA_CATALOG)


def analizar(titular, resumen="", temas_kw=None, forzado="", timeout=120):
    """Devuelve {"temas": [{"cat","score"}, ...], "geo": [...]} o None si
    falla. 'temas_kw' son las categorias que ya asignaron las palabras clave
    (feeds.py), para que la IA las revise y corrija en vez de partir de cero.
    La interpretacion NO sale de aca (ver interpretar())."""
    global last_error
    last_error = None
    kw_txt = ", ".join(temas_kw) if temas_kw else "(ninguna)"
    r = _generar_json(_PROMPT % (_CATALOGO_TXT, kw_txt, titular or "", (resumen or "")[:300]),
                      perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=220, timeout=timeout)
    if r is None:
        return None
    temas = []
    for t in (r.get("temas") or []):
        if not isinstance(t, dict):
            continue
        cat = _TEMA_LOOKUP.get(str(t.get("cat", "")).strip().lower())
        if not cat:
            continue  # nunca se inventa una categoria fuera del catalogo fijo
        try:
            score = float(t.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        temas.append({"cat": cat, "score": max(0.0, min(1.0, score))})
    geo_raw = r.get("geo") or []
    geo = [g for g in (str(x).lower().strip() for x in geo_raw) if g in GEO_CATALOG]
    return {"temas": temas, "geo": geo}


# ------------------------- interpretacion (lectura editorial) -------------------------
# Llamada PROPIA, en texto libre (sin JSON) y con ejemplos resueltos. Un
# filtro (es_literal) descarta lo que siga siendo parafrasis o descripcion
# de la nota: mejor no mostrar nada que mostrar relleno. Perfil PROFUNDO
# (lectura editorial, no triaje).

_INTERP_SISTEMA = (
    "Eres editor de una redaccion en Ecuador. Un reportero te pasa un titular y "
    "tu le respondes en UNA o DOS frases (maximo 40 palabras) que hay DETRAS del "
    "hecho: que esta en juego, a quien beneficia o perjudica, que tension revela "
    "o que pregunta concreta deberia perseguir el reportero. Nunca describas la "
    "noticia ni digas de que trata, nunca menciones si es nacional o "
    "internacional, nunca empieces con 'La noticia' o 'La nota'. No inventes "
    "cifras, nombres ni fechas que no esten en el texto; si el texto es muy "
    "escueto, di que dato falta para dimensionarlo."
)

_INTERP_EJEMPLOS = [
    ("Titular: Gobierno sube el precio del diesel en 10 centavos desde el viernes\n"
     "Resumen: El Ministerio de Energia anuncio el nuevo precio por galon.",
     "El golpe cae primero en transportistas y agricultores, que suelen trasladarlo "
     "a pasajes y alimentos: la pregunta es si hay compensacion para ellos y cuanto "
     "ahorra realmente el fisco."),
    ("Titular: Asamblea archiva el juicio politico contra la ministra de Salud\n"
     "Resumen: La mocion no alcanzo los votos necesarios.",
     "Lo relevante es quien cambio su voto y a cambio de que: un archivo por pocos "
     "votos suele revelar acuerdos entre bancadas que no se dicen en el pleno."),
    ("Titular: Trump amenaza con aranceles a paises que compren petroleo venezolano\n"
     "Resumen: El anuncio se hizo en la Casa Blanca.",
     "Para Ecuador, exportador de petroleo y con EE.UU. como primer socio, conviene "
     "mirar si esto le abre mercado o lo expone a presion por sus propios socios "
     "comerciales."),
]

_LITERAL_INICIOS = ("la noticia", "noticia", "la nota", "esta noticia", "esta nota",
                    "el articulo", "se trata", "trata sobre", "interpreta", "el titular",
                    "la informacion", "informa", "se informa", "reporta", "nota ",
                    "interaccion", "reunion entre", "alerta de", "anuncio de")
_LITERAL_FRASES = ("sin impacto directo", "no relacionada con", "no menciona", "sin mencionar",
                   "relacionada con ecuador", "noticia internacional", "noticia nacional",
                   "contexto internacional", "escala internacional", "foco internacional",
                   "no implica a ecuador", "ni guayaquil", "o guayaquil", "relacionada con",
                   "relacionado con", "tema internacional", "no directamente", "en contexto de")

def _sin_tildes(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()

def es_literal(texto, titular=""):
    """True si el texto es parafrasis/descripcion de la nota y no una lectura
    editorial. Heuristica, no perfecta -- pero atrapa los casos reales vistos
    en ia_cache.json ("Noticia internacional sobre...", "La nota trata
    sobre...", "...sin impacto directo en Ecuador")."""
    t = _sin_tildes(texto).strip(" .\"'")
    if len(t) < 25:
        return True
    if t.startswith(_LITERAL_INICIOS) or any(f in t for f in _LITERAL_FRASES):
        return True
    # demasiado parecido al titular = parafrasis
    pal = lambda x: {w for w in re.findall(r"[a-z0-9]{4,}", _sin_tildes(x))}
    pt, pi = pal(titular), pal(texto)
    if pt and pi and len(pt & pi) / max(1, len(pi)) > 0.6:
        return True
    return False

def interpretar(titular, resumen="", forzado="", timeout=90, perfil=None):
    """Lectura editorial de UNA nota (texto libre). Devuelve el texto, "" si
    el modelo solo produjo parafrasis (dos intentos), o None si la IA fallo."""
    global last_error
    last_error = None
    msgs = []
    for u, a in _INTERP_EJEMPLOS:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": "Titular: %s\nResumen: %s" % (
        titular or "", (resumen or "")[:400])})
    for temp in (0.5, 0.8):
        # Fase 18 (P2-10): 'perfil' permite usar el rapido para la cobertura
        # masiva de lo local (el profundo queda para las mas importantes).
        texto = _generar(sistema=_INTERP_SISTEMA, mensajes=msgs, perfil=perfil or PERFIL_PROFUNDO,
                         temperatura=temp, max_tokens=900, timeout=timeout)
        if texto is None:
            return None
        texto = texto.strip().strip('"')
        if texto and not es_literal(texto, titular):
            return texto[:300]
    return ""


# ------------------------- Parte B: contexto real por entidad -------------------------
# El codigo (monitor.py) RECUPERA los datos (Wikipedia, GDELT); estas
# funciones son las UNICAS que le piden algo al modelo para esto, y todas le
# dan el material ya recuperado -- el modelo NUNCA consulta una API por su
# cuenta, solo extrae nombres del texto o redacta con lo que le pasan.

_PROMPT_ENTIDADES = (
    "Lee esta noticia y extrae las ENTIDADES con NOMBRE PROPIO que menciona: "
    "personas, lugares (ciudades, instituciones con sede) u organizaciones. NO "
    "temas genericos, NO fechas, NO paises ya obvios por el contexto (Ecuador, "
    "Guayaquil, Quito).\n\n"
    "Para CADA entidad da dos cosas: el \"nombre\" tal como aparece en el texto, "
    "SIN cargos ni titulos (ej. \"Daniel Noboa\", no \"el presidente Daniel "
    "Noboa\"); y una \"busqueda\" -- el termino que usarias para encontrar la "
    "pagina de Wikipedia CORRECTA de esa entidad, usando el contexto de esta "
    "nota (tema, ambito geografico, otras entidades) para desambiguarla. Esto "
    "es CRITICO cuando el texto usa solo un apellido o un nombre corto que "
    "podria confundirse con otra cosa: ejemplo, si el texto dice solo "
    "\"Carney\" en una nota de politica internacional sobre aranceles con "
    "Trump, la busqueda debe ser \"Mark Carney primer ministro de Canada\", "
    "NO solo \"Carney\" (que en Wikipedia tambien es una villa en Michigan, "
    "Estados Unidos, y confundirias la pagina). Si el nombre YA es inequivoco "
    "tal cual aparece (ej. \"Daniel Noboa\"), la busqueda puede ser igual al "
    "nombre.\n\n"
    "ADEMAS, por separado: si la nota describe un SUCESO/EVENTO con nombre "
    "propio o casi-propio que podria tener su PROPIA pagina de Wikipedia "
    "aparte de cualquier persona (una ley, un paro/protesta, un conflicto, un "
    "desastre, un proceso electoral, un escandalo -- ej. \"Paro nacional de "
    "Ecuador de 2022\", \"Muerte de Fernando Villavicencio\"), da tambien "
    "\"evento\": {\"nombre\": \"...\", \"busqueda\": \"...\"} con el mismo "
    "criterio de desambiguacion. Si la nota es solo un hecho cotidiano sin "
    "identidad propia como para tener un articulo dedicado, \"evento\" debe "
    "ser null -- no inventes un nombre de evento que no calza.\n\n"
    "Contexto de esta nota -- tema(s): %s | ambito: %s.\n\n"
    "Responde SOLO un JSON valido: "
    '{"entidades": [{"nombre": "...", "busqueda": "..."}, ...], '
    '"evento": {"nombre": "...", "busqueda": "..."} | null}. Maximo 5 entidades, en '
    "orden de importancia para la nota (la mas relevante primero). Si no hay "
    'ninguna entidad clara, "entidades" es [].\n\n'
    "Titular: %s\nResumen: %s"
)

def extraer_entidades(titular, resumen="", temas=None, ambito="", forzado="", timeout=60):
    """Lista de candidatos [{"nombre","busqueda"}, ...] que la nota menciona,
    en orden de relevancia. Son CANDIDATOS: quien llama debe verificarlos
    contra una fuente real (wiki.resumen) antes de usarlos. Wrapper de
    compatibilidad de extraer_entidades_con_evento()."""
    return extraer_entidades_con_evento(titular, resumen, temas, ambito, forzado, timeout)[0]


def extraer_entidades_con_evento(titular, resumen="", temas=None, ambito="", forzado="", timeout=60):
    """Como extraer_entidades(), pero devuelve (entidades, evento) -- 'evento'
    es un candidato {"nombre","busqueda"} para un SUCESO con posible pagina
    propia de Wikipedia (una ley, un paro, un conflicto...), o None."""
    global last_error
    last_error = None
    r = _generar_json(_PROMPT_ENTIDADES % (", ".join(temas or []) or "(sin tema)",
                                            ambito or "(sin dato)",
                                            titular or "", (resumen or "")[:300]),
                      perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=260, timeout=timeout)
    if r is None:
        return [], None
    vistos, out_list = set(), []
    for e in (r.get("entidades") or []):
        if isinstance(e, dict):
            nombre = str(e.get("nombre", "")).strip()
            busqueda = str(e.get("busqueda", "")).strip()
        else:  # tolerancia: formato viejo (lista de strings sueltos)
            nombre = str(e).strip()
            busqueda = nombre
        if nombre and nombre.lower() not in vistos:
            vistos.add(nombre.lower())
            out_list.append({"nombre": nombre, "busqueda": busqueda or nombre})
    evento = r.get("evento")
    if isinstance(evento, dict) and str(evento.get("nombre", "")).strip():
        evento = {"nombre": str(evento.get("nombre", "")).strip(),
                  "busqueda": str(evento.get("busqueda", "")).strip() or str(evento.get("nombre", "")).strip()}
    else:
        evento = None
    return out_list[:5], evento


_PROMPT_CONTEXTO = (
    "Tienes el TITULAR y RESUMEN de una noticia (asi son los HECHOS: quien hizo "
    "que, segun la nota -- no los cambies ni los reinterpretes), y un MATERIAL YA "
    "VERIFICADO: puede incluir extractos reales de Wikipedia sobre las entidades "
    "que menciona, titulares REALES y recientes de otras notas de prensa sobre lo "
    "mismo (con fecha), y nombres con los que la entidad principal aparecio junto "
    "en cobertura reciente segun GDELT.\n\n"
    "Tu tarea es explicar LA SITUACION, no solo quien es alguien: por que pasa "
    "esto ahora, que antecedente inmediato tiene (si los titulares recientes "
    "muestran una seguidilla de hechos, un conflicto en curso, una escalada, "
    "etc.), o que rol juega la entidad en ese marco mas amplio -- SOLO si el "
    "material te da con que armar eso. Si el material SOLO trae una bio de "
    "Wikipedia sin nada que conecte con la situacion (ej. no hay titulares "
    "recientes ni co-menciones utiles), ahi si limitate a decir brevemente quien "
    "es la entidad; no inventes una conexion que el material no respalda.\n\n"
    "Redacta en 1-2 frases (maximo 45 palabras). NO repitas ni reformules los "
    "hechos del resumen, y sobre todo NO les cambies los roles (si el resumen "
    "dice que A publico algo sobre B, tu texto no puede decir que A hizo lo que "
    "hizo B). Usa SOLO el material verificado, nunca conocimiento previo tuyo: "
    "si el material no menciona una fecha, un lugar o un dato puntual, vos "
    "tampoco lo inventes. Si el material incluye nombres de GDELT (co-menciones, "
    "no titulares), mencionalos EXPLICITAMENTE como \"pista por verificar\" (que "
    "dos nombres compartan cobertura de prensa no prueba una relacion entre "
    "ellos). Los TITULARES si son hechos reales publicados, podes citarlos como "
    "evidencia de la situacion (ej. \"esto se da luego de que...\", citando el "
    "titular y su fecha). Si el material no alcanza para agregar nada util, "
    "responde exactamente 'sin contexto disponible'. Responde SOLO un JSON "
    'valido: {"contexto": "..."}.\n\n'
    "Titular: %s\nResumen: %s\n\nMATERIAL VERIFICADO:\n%s"
)

def contextualizar(titular, resumen, material_txt, forzado="", timeout=90):
    """Redacta el 'por que importa' grounded SOLO con 'material_txt' (lo arma
    monitor.py con Wikipedia + prensa reciente ya verificados). Sin material
    ni siquiera llama al modelo. Devuelve el texto, o None si la IA fallo
    (distinto de 'sin contexto disponible', que es una respuesta valida)."""
    global last_error
    last_error = None
    if not (material_txt or "").strip():
        return "sin contexto disponible"
    r = _generar_json(_PROMPT_CONTEXTO % (titular or "", (resumen or "")[:300], material_txt[:2500]),
                      perfil=PERFIL_RAPIDO, temperatura=0.2, max_tokens=220, timeout=timeout)
    if r is None:
        return None
    texto = str(r.get("contexto", "")).strip()[:420]
    return texto or "sin contexto disponible"


_PROMPT_VEREDICTO = (
    "Tienes una AFIRMACION (titular+resumen de una noticia) y MATERIAL YA "
    "VERIFICADO para contrastarla: puede incluir contexto reciente sobre el "
    "tema (otras notas, co-menciones, antecedentes), contratos publicos "
    "oficiales (SERCOP) relacionados, y verificaciones periodisticas "
    "(ClaimReview) relacionadas.\n\n"
    "Tu tarea es un VEREDICTO de contraste, usando SOLO el material dado (nunca "
    "tu conocimiento previo): decide si ese material COINCIDE con la "
    "afirmacion, la CONTRADICE, o no hay suficiente material para decidir "
    "(sin_datos). En 'texto' escribi el HECHO CONCRETO que encontraste en el "
    "material (un numero, una fecha, una calificacion, un dato puntual) -- "
    "NUNCA una frase generica tipo 'segun el contexto verificado' o 'la "
    "cobertura reciente muestra que' sin completarla con el dato real: esas "
    "frases sueltas, sin el hecho concreto detras, no sirven de nada. Si el "
    "material no menciona nada que confirme o contradiga la afirmacion "
    "puntual, el estado es 'sin_datos' -- NUNCA inventes un dato que el "
    "material no tiene.\n\n"
    "Ejemplo 1 (contradice, con el dato concreto):\n"
    "AFIRMACION: El municipio adjudico sin licitacion un contrato de recoleccion de basura.\n"
    "MATERIAL: Contratos oficiales SERCOP relacionados: GAD Municipal -- "
    "Recoleccion de residuos solidos (Licitacion Publica, $450000, 2026-08-10)\n"
    '{"estado": "contradice", "texto": "El contrato SERCOP (ocds, $450000) muestra que el '
    'proceso fue Licitacion Publica, no una adjudicacion directa como dice la nota.", '
    '"citas": ["SERCOP"]}\n\n'
    "Ejemplo 2 (sin_datos, el material no habla del reclamo puntual):\n"
    "AFIRMACION: La ministra asegura que el programa redujo la desnutricion infantil a la mitad.\n"
    "MATERIAL: Contexto verificado de la situacion: la ministra fue nombrada en "
    "enero de 2026 tras la salida de su antecesor.\n"
    '{"estado": "sin_datos", "texto": "El material solo confirma cuando asumio la '
    'ministra, no trae ninguna cifra sobre desnutricion infantil para confirmar o '
    'desmentir el dato que da la nota.", "citas": []}\n\n'
    "Responde SOLO un JSON valido con esta forma exacta: "
    '{"estado": "coincide"|"contradice"|"sin_datos", "texto": "...", "citas": ["..."]} '
    "-- 'texto' maximo 35 palabras, 'citas' una lista corta de que partes del material "
    'usaste (ej. ["SERCOP", "FactCheck: Ecuador Chequea"]).\n\n'
    "AFIRMACION (titular): %s\nResumen: %s\n\nMATERIAL:\n%s"
)

def veredicto_contraste(titular, resumen, material_txt, forzado="", timeout=90):
    """Veredicto de contraste -- 'coincide'/'contradice'/'sin_datos', citando
    que parte del material uso. Sin material, 'sin_datos' sin llamar al
    modelo. None si la IA fallo (monitor.py muestra 'pendiente', no inventa)."""
    global last_error
    last_error = None
    if not (material_txt or "").strip():
        return {"estado": "sin_datos", "texto": "Sin material verificado para contrastar esta nota.", "citas": []}
    r = _generar_json(_PROMPT_VEREDICTO % (titular or "", (resumen or "")[:300], material_txt[:2500]),
                      perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=220, timeout=timeout)
    if r is None:
        return None
    estado = str(r.get("estado", "")).strip().lower()
    if estado not in ("coincide", "contradice", "sin_datos"):
        estado = "sin_datos"  # candado en codigo: ante respuesta rara del modelo, nunca inventar un estado
    texto = str(r.get("texto", "")).strip()[:300]
    citas = r.get("citas") or []
    if not isinstance(citas, list):
        citas = []
    return {"estado": estado, "texto": texto or "Sin detalle.", "citas": [str(c)[:80] for c in citas][:6]}


# ------------------------- Fase 9, Problema C: posturas del Pulso social -------------------------
# Tarea CHICA y verificable: la IA NO redacta un resumen del debate, solo
# clasifica cada post ya recolectado. Toda postura tiene que citar los IDs de
# los posts que la sostienen -- lo que no tenga cita se descarta en CODIGO.
_PROMPT_POSTURAS = (
    "Tenes una HISTORIA (titular+resumen) y una lista de POSTS reales de redes "
    "sociales sobre ese tema, cada uno con un ID. Tu tarea es agrupar los "
    "posts por la POSTURA que toman respecto a la historia, en una de estas "
    "4 categorias: 'a_favor' (apoya/celebra lo que cuenta la noticia), "
    "'en_contra' (critica/rechaza), 'duda' (pregunta, pide mas informacion, "
    "no toma partido), 'denuncia' (testimonio/denuncia de un hecho relacionado, "
    "no necesariamente sobre la noticia en si).\n\n"
    "Cada grupo tiene que listar los IDs EXACTOS (tal cual aparecen abajo) de "
    "los posts que sostienen esa postura -- NUNCA inventes un ID que no este "
    "en la lista, y NUNCA pongas un post en una postura si no tenes un post "
    "real que la sostenga. Un post puede no encajar en ninguna postura clara "
    "-- en ese caso simplemente no lo incluyas en ningun grupo (no fuerces).\n\n"
    "Responde SOLO un JSON valido: "
    '{"posturas": [{"postura": "a_favor"|"en_contra"|"duda"|"denuncia", "ids": ["id1","id2"]}]} '
    "-- sin texto fuera del JSON.\n\n"
    "HISTORIA: %s\nResumen: %s\n\nPOSTS:\n%s"
)


def clasificar_posturas(titular, resumen, posts, forzado="", timeout=90):
    """posts: lista de dicts {"id": str, "texto": str}. Devuelve una lista de
    {"postura", "ids"} -- SOLO con ids que de verdad estan en 'posts' (el
    candado real vive en monitor.py; aca se filtra tambien). None si la IA
    no respondio."""
    global last_error
    last_error = None
    if not posts:
        return []
    ids_validos = {str(p.get("id", "")) for p in posts}
    listado = "\n".join("[%s] %s" % (p.get("id", ""), (p.get("texto", "") or "")[:220]) for p in posts[:40])
    r = _generar_json(_PROMPT_POSTURAS % (titular or "", (resumen or "")[:300], listado),
                      perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=400, timeout=timeout)
    if r is None:
        return None
    out_posturas = []
    for p in (r.get("posturas") or []):
        if not isinstance(p, dict):
            continue
        postura = str(p.get("postura", "")).strip().lower()
        if postura not in ("a_favor", "en_contra", "duda", "denuncia"):
            continue  # candado en codigo: vocabulario fijo, nunca lo que el modelo invente
        ids = [str(i) for i in (p.get("ids") or []) if str(i) in ids_validos]
        if not ids:
            continue  # sin citas reales, se descarta -- una postura no puede quedar sin evidencia
        out_posturas.append({"postura": postura, "ids": ids})
    return out_posturas


# ------------------------- Fase 14, Paso 2: coherencia de historias agrupadas -------------------------
# Tarea CHICA y verificable, mismo criterio que clasificar_posturas: la IA NO
# redacta nada, solo agrupa fuentes ya recolectadas por HECHO real. El candado
# de que cada fuente aparezca en EXACTAMENTE un grupo se aplica en monitor.py
# (aca solo se descarta lo obviamente invalido, ej. menos de 2 grupos).
_PROMPT_COHERENCIA = (
    "Estas son varias notas de prensa que un sistema automatico agrupo como si "
    "fueran LA MISMA noticia (mismo hecho concreto). Revisa si de verdad "
    "describen UN SOLO hecho, o si en realidad mezclan DOS O MAS hechos "
    "distintos.\n\n"
    "IMPORTANTE: compartir el mismo LUGAR, la misma ORGANIZACION/PERSONA, o "
    "vocabulario parecido (ej. \"operativo\", \"lluvias\", \"casos\") NO alcanza "
    "para ser el mismo hecho -- tienen que describir el MISMO suceso puntual "
    "(mismo momento, mismo episodio). Ejemplo: \"Renuncia la presidenta de la "
    "Camara X tras un discurso\" y \"La Camara X alza la voz por la democracia\" "
    "NO son el mismo hecho aunque sea la misma organizacion -- son dos "
    "episodios distintos.\n\n"
    "NOTAS:\n%s\n\n"
    "Si TODAS describen el mismo hecho, responde: "
    '{"un_solo_hecho": true, "grupos": []}\n\n'
    "Si mezclan hechos distintos, responde: "
    '{"un_solo_hecho": false, "grupos": [["0","2"], ["1","3","4"]]} '
    "(cada lista interna son los ids, como texto, de las notas que SI son el "
    "mismo hecho entre si). Cada id tiene que aparecer en EXACTAMENTE un "
    "grupo -- ninguno se puede quedar afuera ni repetirse en dos grupos.\n\n"
    "Responde SOLO el JSON, sin texto extra."
)


def verificar_coherencia(fuentes, forzado="", timeout=90):
    """fuentes: lista de dicts {\"id\": str, \"titulo\": str, \"resumen\": str}
    (orden estable, el id es el indice como string). Devuelve
    {\"un_solo_hecho\": bool, \"grupos\": [[id,...],...]} o None si la IA no
    respondio o el JSON no sirve para nada. El candado de que cada id
    aparezca en EXACTAMENTE un grupo (y que todos existan) se aplica en
    monitor.py -- aca solo se descarta lo obviamente invalido (menos de 2
    grupos, o un formato que no es lista de listas)."""
    global last_error
    last_error = None
    if len(fuentes) < 2:
        return {"un_solo_hecho": True, "grupos": []}
    listado = "\n".join(
        "[%s] %s -- %s" % (f.get("id", ""), (f.get("titulo", "") or "")[:160],
                            (f.get("resumen", "") or "")[:200])
        for f in fuentes[:40]
    )
    r = _generar_json(_PROMPT_COHERENCIA % listado, perfil=PERFIL_RAPIDO,
                      temperatura=0.1, max_tokens=500, timeout=timeout)
    if r is None:
        return None
    un_solo = bool(r.get("un_solo_hecho", True))
    grupos_raw = r.get("grupos") or []
    if un_solo or not isinstance(grupos_raw, list):
        return {"un_solo_hecho": True, "grupos": []}
    grupos = [[str(x) for x in g] for g in grupos_raw if isinstance(g, list) and g]
    if len(grupos) < 2:
        return {"un_solo_hecho": True, "grupos": []}
    return {"un_solo_hecho": False, "grupos": grupos}


_PROMPT_TRADUCIR_TITULAR = (
    "Traduci este titular de noticia del ingles al español, en una frase neutral "
    "y periodistica (no literal palabra por palabra, pero fiel al hecho, sin "
    "agregar nada que el titular original no diga). Responde SOLO la "
    "traduccion, sin comillas ni texto extra.\n\nTitular: %s"
)


def traducir_titular(titulo_en, forzado="", timeout=30):
    """Fase 9, D3 (marco global ES+EN): solo se llama cuando una historia
    global NO tiene ningun titular real en espanol entre sus fuentes. None
    si la IA no responde."""
    global last_error
    texto = _generar(_PROMPT_TRADUCIR_TITULAR % (titulo_en or "")[:200],
                     perfil=PERFIL_RAPIDO, temperatura=0.2, max_tokens=80, timeout=timeout)
    if texto is None:
        return None
    texto = texto.strip().strip('"').strip()
    return texto[:200] or None


# ------------------------- Fase 14, Paso 2: clasificacion geografica con evidencia -------------------------
# Tarea CHICA y verificable: para historias donde las fuentes fusionadas NO
# se ponen de acuerdo en la ciudad del hecho, la IA decide UNA vez, citando
# una frase LITERAL del propio texto -- el candado real (que esa frase
# exista de verdad en el titular/resumen) se aplica en monitor.py, nunca se
# confia a ciegas en el string que devuelve el modelo.
_PROMPT_GEO_EVIDENCIA = (
    "Lee este titular y resumen de una noticia de Ecuador. Las fuentes que "
    "la cubren no se ponen de acuerdo en la ciudad del HECHO (no de donde "
    "se publico o redacto la nota, sino donde ocurrio lo que cuenta). Tu "
    "tarea es decidir, SOLO con lo que el texto dice explicitamente (nunca "
    "inventes ni asumas), en que ciudad ocurrio el hecho.\n\n"
    "Si el texto NO menciona ninguna ciudad especifica del hecho (ej. es "
    "una noticia nacional, una ley, una declaracion sin lugar puntual), "
    "responde ciudad_del_hecho: null y es_guayaquil: false -- NO fuerces "
    "una ciudad que el texto no da.\n\n"
    "frase_evidencia tiene que ser una frase LITERAL, copiada tal cual del "
    "titular o resumen de abajo (sin traducir, sin resumir, sin cambiar ni "
    "una palabra) -- la frase exacta que te hizo decidir la ciudad. Si no "
    "hay ninguna frase que lo respalde, frase_evidencia: null y "
    "ciudad_del_hecho: null.\n\n"
    "Responde SOLO un JSON valido: "
    '{"ciudad_del_hecho": "..." | null, "es_guayaquil": true|false, '
    '"frase_evidencia": "..." | null}\n\n'
    "TITULAR: %s\nRESUMEN: %s"
)


def clasificar_geo_evidencia(titular, resumen, forzado="", timeout=60):
    """Devuelve {"ciudad_del_hecho", "es_guayaquil", "frase_evidencia"} o
    None si la IA no respondio o el JSON no sirve. NO valida que
    frase_evidencia exista de verdad en el texto -- eso lo hace monitor.py
    (necesita comparar contra el texto real, que aca no se repite)."""
    global last_error
    last_error = None
    r = _generar_json(_PROMPT_GEO_EVIDENCIA % ((titular or "")[:250], (resumen or "")[:400]),
                      perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=200, timeout=timeout)
    if r is None:
        return None
    ciudad = r.get("ciudad_del_hecho")
    ciudad = str(ciudad).strip() if ciudad else None
    frase = r.get("frase_evidencia")
    frase = str(frase).strip() if frase else None
    return {
        "ciudad_del_hecho": ciudad,
        "es_guayaquil": bool(r.get("es_guayaquil", False)),
        "frase_evidencia": frase,
    }


_PROMPT_DECLARACION = (
    "Lee esta noticia. ¿Le ATRIBUYE explicitamente una declaracion, anuncio, "
    "promesa o afirmacion puntual a UNA persona con nombre propio (ej. \"dijo "
    "que...\", \"aseguro que...\", \"anuncio que...\", \"afirmo que...\", una "
    "cita textual entre comillas)? Si NO hay ninguna atribucion clara a una "
    "persona nombrada (ej. la nota solo describe un hecho, o dice \"el "
    "gobierno anuncio\" sin nombrar a nadie), responde declaracion: null -- NO "
    "inventes un actor ni fuerces una declaracion que el texto no tiene.\n\n"
    "Si SI hay una declaracion clara, da: \"actor\" (nombre de la persona, sin "
    "cargo ni titulo), \"cargo\" (su cargo/rol si el texto lo menciona, si no "
    "\"\"), y \"texto\" (resumen LITERAL de lo que la nota dice que la persona "
    "dijo/anuncio/afirmo -- maximo 200 caracteres, sin agregar ni interpretar "
    "nada que el texto no diga).\n\n"
    "Responde SOLO un JSON valido: "
    '{"declaracion": {"actor": "...", "cargo": "...", "texto": "..."} | null}\n\n'
    "Titular: %s\nResumen: %s"
)

def extraer_declaracion(titular, resumen="", forzado="", timeout=60):
    """Extrae UNA declaracion atribuida a un actor con nombre (Fase 5) --
    nunca fuerza una si el texto no atribuye nada a nadie. Devuelve
    {"actor","cargo","texto"} o None. OJO: None tambien si la IA fallo --
    quien llama debe chequear disponible() ANTES, para no confundir 'IA
    caida' con 'esta nota no tiene declaracion'."""
    global last_error
    last_error = None
    r = _generar_json(_PROMPT_DECLARACION % (titular or "", (resumen or "")[:400]),
                      perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=180, timeout=timeout)
    if r is None:
        return None
    d = r.get("declaracion")
    if not isinstance(d, dict):
        return None
    actor = str(d.get("actor", "")).strip()
    texto = str(d.get("texto", "")).strip()
    if not actor or not texto:
        return None
    cargo = str(d.get("cargo", "")).strip()
    return {"actor": actor[:80], "cargo": cargo[:80], "texto": texto[:220]}


_PROMPT_COMPARAR_DECL = (
    "Compara estas DOS declaraciones del MISMO actor (%s), en fechas "
    "distintas, usando SOLO lo que dice cada una -- nunca tu conocimiento "
    "previo sobre el tema.\n\n"
    "DECLARACION NUEVA (%s, segun %s): \"%s\"\n"
    "DECLARACION ANTERIOR (%s, segun %s): \"%s\"\n\n"
    "Tu tarea NO es decidir si algo es verdadero o falso -- es notar si las "
    "DOS declaraciones son dificiles de sostener juntas (se contradicen en un "
    "hecho, una cifra, una fecha, una promesa vs. lo que paso despues), o si "
    "son consistentes (agregan informacion sin chocar), o si en realidad "
    "hablan de cosas distintas sin relacion real (sin_relacion) aunque "
    "compartan palabras.\n\n"
    "Ejemplo 1 (posible_contradiccion, con el hecho concreto):\n"
    "NUEVA (2026-09-20): \"El ministro aseguro que el subsidio al diesel se mantiene sin cambios este año.\"\n"
    "ANTERIOR (2026-06-10): \"El ministro anuncio que el subsidio al diesel se elimina gradualmente desde julio.\"\n"
    '{"estado": "posible_contradiccion", "texto": "En junio el ministro anuncio '
    'eliminacion gradual del subsidio desde julio; en septiembre dice que se '
    'mantiene sin cambios.", "confianza": 0.7}\n\n'
    "Ejemplo 2 (sin_relacion):\n"
    "NUEVA: \"La alcaldesa inauguro un nuevo parque en el norte de la ciudad.\"\n"
    "ANTERIOR: \"La alcaldesa critico el aumento de tarifas de agua potable.\"\n"
    '{"estado": "sin_relacion", "texto": "Son dos temas distintos (un parque y '
    'tarifas de agua), no hay nada puntual que comparar.", "confianza": 0.9}\n\n'
    "Responde SOLO un JSON valido con esta forma exacta: "
    '{"estado": "posible_contradiccion"|"consistente"|"sin_relacion", "texto": "...", "confianza": 0.0-1.0} '
    "-- 'texto' maximo 40 palabras, con el hecho concreto que compara (nunca una "
    "frase generica sin completar)."
)

def comparar_declaraciones(actor, texto_nueva, fecha_nueva, medio_nueva,
                            texto_vieja, fecha_vieja, medio_vieja,
                            forzado="", timeout=90):
    """Compara una declaracion NUEVA de un actor contra una ANTERIOR del
    MISMO actor (ya emparejadas por un filtro barato sin IA en
    declaraciones.candidatos_contradiccion). Perfil PROFUNDO: pocas llamadas
    por pasada, necesita criterio.

    Candado en CODIGO: el estado NUNCA sale del vocabulario fijo -- si el
    modelo responde otra cosa, se recorta a 'sin_relacion' (ninguna
    acusacion). La calificacion final es de Fernando, nunca 'falso'."""
    global last_error
    last_error = None
    r = _generar_json(_PROMPT_COMPARAR_DECL % (
        actor or "", fecha_nueva or "?", medio_nueva or "?", (texto_nueva or "")[:280],
        fecha_vieja or "?", medio_vieja or "?", (texto_vieja or "")[:280]),
        perfil=PERFIL_PROFUNDO, temperatura=0.1, max_tokens=900, timeout=timeout)
    if r is None:
        return None
    estado = str(r.get("estado", "")).strip().lower()
    if estado not in ("posible_contradiccion", "consistente", "sin_relacion"):
        estado = "sin_relacion"  # candado: ante respuesta rara del modelo, nunca inventar una contradiccion
    texto = str(r.get("texto", "")).strip()[:300]
    try:
        confianza = float(r.get("confianza", 0))
    except Exception:
        confianza = 0.0
    confianza = max(0.0, min(1.0, confianza))
    return {"estado": estado, "texto": texto or "Sin detalle.", "confianza": confianza}


_PROMPT_DOMINIO = (
    "NOTICIA: %s. %s\n\n"
    "PAGINA DE WIKIPEDIA (titulo: \"%s\"): %s\n\n"
    "Pregunta: la noticia menciona a \"%s\". Esa pagina de Wikipedia, ¿es sobre "
    "esa misma persona/lugar/organizacion (aunque el titulo este mas completo)? "
    "Piensa brevemente y termina tu respuesta con exactamente SI o NO en "
    "mayusculas."
)
_RE_SI_NO = re.compile(r"\bS[IÍ]\b|\bNO\b", re.IGNORECASE)

def coincide_dominio(titular, resumen, nombre_mencionado, titulo_wiki, extracto_wiki, forzado="", timeout=60):
    """Capa 2 del bug de Carney: verifica que la pagina de Wikipedia
    encontrada sea la MISMA entidad que la nota menciona. Texto libre
    terminando en SI/NO (forzar JSON sesgaba el juicio en esta tarea puntual);
    se toma la ULTIMA mencion de SI/NO.

    Regla dura en CODIGO: ante la duda -- o si no se puede consultar la IA,
    o no hay SI/NO en la respuesta -- devuelve False. Mejor 'sin contexto
    disponible' que un contexto equivocado con sello de verificado."""
    global last_error
    last_error = None
    texto = _generar(_PROMPT_DOMINIO % (titular or "", (resumen or "")[:300],
                                        titulo_wiki, (extracto_wiki or "")[:500],
                                        nombre_mencionado),
                     perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=200, timeout=timeout)
    if texto is None:
        return False
    matches = _RE_SI_NO.findall(texto)
    if not matches:
        last_error = "sin veredicto SI/NO"
        return False
    return matches[-1].strip().upper() in ("SI", "SÍ")


# ------------------------- Parte E: chat por item (on-demand) -------------------------
# Lo dispara el USUARIO desde el dashboard -- nunca el feed. monitor.py arma
# 'item_contexto' con los datos YA CALCULADOS de esa tarjeta; esta funcion
# NUNCA consulta Wikipedia/GDELT por su cuenta.

_PROMPT_CHAT_SISTEMA = (
    "Sos un asistente que ayuda a un estudiante de periodismo a revisar y "
    "discutir UN item de su monitor de noticias (una noticia puntual, un tema "
    "candidato a reportaje, o el pulso social de un tema). Estos son los datos "
    "YA CALCULADOS por el programa sobre ese item, incluyendo material "
    "verificado contra Wikipedia cuando la pregunta lo necesito:\n\n"
    "%s\n\n"
    "REGLA DURA sobre HECHOS CONCRETOS (quien es alguien, que cargo tiene, "
    "cifras, fechas, nombres): SOLO afirmes lo que este en el material de "
    "arriba. Si ese material dice 'SIN VERIFICAR' sobre algo, o si te "
    "preguntan por una persona/entidad que NO aparece ahi, respondé "
    "EXPLICITAMENTE que no tenes ese dato verificado en este momento -- "
    "NUNCA completes con un nombre o dato que te 'suene familiar', eso es "
    "inventar (ya paso una vez: le dijiste a un periodista que 'Alias Fito' "
    "era 'Carlos Ospina', un dato FALSO). Mejor decir 'no lo tengo "
    "verificado, convendria confirmarlo' que arriesgar un dato incorrecto.\n\n"
    "Fuera de eso, para la INTERPRETACION (que angulo le falta a la nota, a "
    "quien conviene esa version, si es una oportunidad de reportaje) si "
    "podes opinar libremente con tu criterio -- ahi el periodista es el "
    "juez final y puede corregirte.\n\n"
    "Responde en espanol, breve (maximo 5-6 lineas), en tono conversacional "
    "-- sin JSON ni formato especial."
)


_PROMPT_ENTIDADES_CHAT = (
    "Un periodista te esta preguntando algo en un chat, dentro del contexto de "
    "este item de su monitor de noticias:\n%s\n\n"
    "Su mensaje: %s\n\n"
    "Si el mensaje pregunta por una entidad con NOMBRE PROPIO (persona, alias, "
    "lugar, organizacion) sobre la que haria falta verificar quien/que es "
    "realmente, extraela. Para cada una da el \"nombre\" tal como aparece en "
    "el mensaje, y una \"busqueda\" que la desambigue para encontrar su pagina "
    "REAL de Wikipedia (nombre completo + el dato que la identifica, usando "
    "el contexto del item y tu propio conocimiento si lo tenes -- ej. si "
    "preguntan por \"Alias Fito\" en contexto ecuatoriano, la busqueda debe "
    "ser algo como \"Jose Adolfo Macias Villamar lider Los Choneros\", NO "
    "solo \"Fito\"). Si el mensaje NO pregunta por ninguna entidad puntual "
    "(es una pregunta general, de opinion, o sobre datos que ya estan en el "
    "contexto del item), responde una lista vacia.\n\n"
    "Responde SOLO un JSON valido: "
    '{"entidades": [{"nombre": "...", "busqueda": "..."}, ...]}, maximo 3.'
)

def extraer_entidades_chat(mensaje, item_contexto="", forzado="", timeout=30):
    """Capa de aterrizaje (grounding) para el chat: reconoce si el mensaje
    pregunta por una entidad puntual, para verificarla contra Wikipedia
    (monitor._aterrizar_chat hace la verificacion real). Perfil RAPIDO: es un
    paso previo, no la respuesta final. Bug real que la motivo: 'Alias Fito'
    respondido como 'Carlos Ospina', un nombre inventado."""
    global last_error
    last_error = None
    r = _generar_json(_PROMPT_ENTIDADES_CHAT % ((item_contexto or "")[:800], (mensaje or "")[:500]),
                      perfil=PERFIL_RAPIDO, temperatura=0.1, max_tokens=150, timeout=timeout)
    if r is None:
        return []
    vistos, out_list = set(), []
    for e in (r.get("entidades") or []):
        if not isinstance(e, dict):
            continue
        nombre = str(e.get("nombre", "")).strip()
        busqueda = str(e.get("busqueda", "")).strip()
        if nombre and nombre.lower() not in vistos:
            vistos.add(nombre.lower())
            out_list.append({"nombre": nombre, "busqueda": busqueda or nombre})
    return out_list[:3]


# Dos modos de chat: "rapido" (perfil rapido, contexto magro) y "profundo"
# (perfil profundo, contexto completo). Los numeros de Ollama (num_ctx) ya
# no aplican; queda solo el tope de salida.
MODOS_CHAT = {
    "rapido":   {"perfil": PERFIL_RAPIDO,   "max_tokens": 400},
    "profundo": {"perfil": PERFIL_PROFUNDO, "max_tokens": 1400},
}


def chat_stream(item_contexto, historial, mensaje, on_delta, modo="rapido", forzado="", timeout=220):
    """Chat conversacional sobre UN item del dashboard, CON STREAMING
    (on_delta(texto_parcial) por cada pedazo). 'historial': lista de
    {"rol": "usuario"|"ia", "texto": ...} (se mandan los ultimos 8).
    Devuelve el texto completo, o None si no se genero nada."""
    global last_error
    last_error = None
    cfg = MODOS_CHAT.get(modo, MODOS_CHAT["rapido"])
    turnos = []
    for h in (historial or [])[-8:]:
        rol = "Periodista" if h.get("rol") == "usuario" else "Vos"
        turnos.append("%s: %s" % (rol, str(h.get("texto", ""))[:500]))
    turnos.append("Periodista: %s" % (mensaje or "")[:1000])
    prompt = (_PROMPT_CHAT_SISTEMA % (item_contexto or "")[:3000]) + "\n\n" + "\n".join(turnos) + "\n\nVos:"
    texto = _generar_stream(prompt, on_delta, perfil=cfg["perfil"], temperatura=0.4,
                            max_tokens=cfg["max_tokens"], timeout=timeout)
    return (texto or "").strip()[:1200] or None


# ======================= Embeddings (agrupamiento + casos) =======================
# Los embeddings LOCALES (nomic-embed-text / bge-m3 via Ollama) se retiraron.
# gemini-embedding-001 es MULTILINGUE de por si (medido en vivo, ver
# CLAUDE.md Fase 10 parte B): reemplaza a la vez a nomic-embed-text (Parte A)
# Y a bge-m3 (Parte D3, marco global ES/EN) -- por eso EMBED_MODEL y
# EMBED_MODEL_MULTILINGUE apuntan al MISMO modelo de Gemini por defecto.
#
# CANDADO DE ESPACIO VECTORIAL (Fase 10, Parte B1): los vectores de un
# modelo NO son comparables con los de otro (distinta dimension/distinto
# espacio) -- monitor.py guarda 'embedding_modelo' junto a cada vector en
# historias_registro.json y SOLO compara coseno entre vectores del MISMO
# modelo (ver monitor._cos_sim_seguro). Este modulo no impone eso (no sabe
# que hace el llamador con el vector), pero SI expone GEMINI_EMBED_MODEL
# para que el llamador pueda taggear correctamente.

EMBED_MODEL = os.environ.get("MONITOR_EMBED_MODEL", "") or GEMINI_EMBED_MODEL
EMBED_MODEL_MULTILINGUE = os.environ.get("MONITOR_EMBED_MULTI_MODEL", "") or GEMINI_EMBED_MODEL


def embed_disponible(modelo=None):
    """True si hay clave Y el modelo de embeddings existe en el catalogo
    real de Gemini Y no esta pausado por 429 -- sin red en cada llamada
    (_listar_modelos_reales ya cachea con TTL)."""
    modelo = modelo or EMBED_MODEL
    if not configurada():
        return False
    if _pausado("embed"):
        return False
    return _modelo_existe(modelo)


def estado_embeddings():
    """Texto honesto para data.json/'Salud de los datos'."""
    if not configurada():
        return "apagados: %s" % _PENDIENTE
    if _pausado("embed"):
        return "pausados por limite de peticiones: %s" % _motivo_pausa("embed")
    if not _modelo_existe(EMBED_MODEL):
        return "el modelo de embeddings '%s' no existe en el catalogo real de Gemini" % EMBED_MODEL
    return "ok (%s) -- gasto hoy $%.4f" % (EMBED_MODEL, gasto_hoy())


def embed(texto, timeout=30, modelo=None):
    """Vector de UN fragmento de texto via embedContent, o None si fallo
    (motivo en last_error). casos.py lo llama fragmento por fragmento
    (~500 palabras cada uno) -- nunca un documento entero."""
    global last_error
    last_error = None
    modelo = modelo or EMBED_MODEL
    if not embed_disponible(modelo):
        last_error = last_error or ("modelo de embeddings '%s' no disponible" % modelo)
        return None
    costo_max = (len(texto or "") / 4) * PRECIO_EMBED_INPUT
    ok, razon = _cabe_en_presupuesto(costo_max)
    if not ok:
        last_error = "presupuesto agotado: %s" % razon
        return None
    payload = {"content": {"parts": [{"text": (texto or "")[:20000]}]}}
    data = _post_gemini("models/%s:embedContent" % modelo, payload, timeout, perfil_pausa="embed")
    if data is None:
        return None
    valores = (data.get("embedding") or {}).get("values")
    if not isinstance(valores, list) or not valores:
        last_error = "respuesta sin vector de embedding"
        return None
    # embedContent no siempre devuelve usageMetadata -- costo estimado por
    # caracteres de entrada (barato, sin output) si no viene el real.
    uso = data.get("usageMetadata") or {}
    tokens_in = uso.get("promptTokenCount") or (len(texto or "") / 4)
    _registrar_gasto(tokens_in * PRECIO_EMBED_INPUT, "embed (%s)" % modelo)
    return valores


def embed_lote(textos, timeout=60, modelo=None):
    """Varios fragmentos en UNA sola llamada via batchEmbedContents -- mas
    barato en overhead de red que llamar a embed() uno por uno. Devuelve una
    lista de vectores (o None en la posicion de los que fallaron), del mismo
    largo que 'textos'. None entero si la llamada completa fallo."""
    global last_error
    last_error = None
    modelo = modelo or EMBED_MODEL
    if not embed_disponible(modelo):
        last_error = last_error or ("modelo de embeddings '%s' no disponible" % modelo)
        return None
    if not textos:
        return []
    costo_max = sum((len(t or "") / 4) * PRECIO_EMBED_INPUT for t in textos)
    ok, razon = _cabe_en_presupuesto(costo_max)
    if not ok:
        last_error = "presupuesto agotado: %s" % razon
        return None
    payload = {"requests": [{"model": "models/%s" % modelo, "content": {"parts": [{"text": (t or "")[:20000]}]}}
                             for t in textos]}
    data = _post_gemini("models/%s:batchEmbedContents" % modelo, payload, timeout, perfil_pausa="embed")
    if data is None:
        return None
    respuestas = data.get("embeddings") or []
    out = [(r.get("values") if isinstance(r, dict) else None) for r in respuestas]
    _registrar_gasto(costo_max, "embed_lote (%s, %d textos)" % (modelo, len(textos)))
    return out


# ======================= Fase 7: Asistente de casos =======================

_PROMPT_SUGERENCIAS_CASO = (
    "Estas ayudando a un periodista a investigar un caso titulado \"%s\". Entidades que ya sigue "
    "en este caso: %s.\n\n"
    "Pregunta del periodista: %s\n\nTu respuesta: %s\n\n"
    "Si de este intercambio surge una entidad NUEVA (persona, institucion, empresa o lugar, que no "
    "este ya en la lista de arriba) que valdria la pena agregar al caso, o una CONEXION entre dos "
    "entidades ya mencionadas (ej. \"X trabajo para Y\", \"X firmo un contrato con Y\"), propone la. "
    "Nunca inventes una entidad o conexion que no este respaldada por el texto de arriba -- si no hay "
    "nada que proponer, respondes con listas vacias, eso es lo normal la mayoria de las veces.\n\n"
    "Responde SOLO un JSON con esta forma exacta:\n"
    '{"entidades": [{"nombre": "...", "tipo": "persona"|"institucion"|"empresa"|"lugar"|"otro"}, ...], '
    '"conexiones": [{"origen": "...", "destino": "...", "tipo": "breve descripcion de la relacion"}, ...]}'
)


def extraer_sugerencias_caso(pregunta, respuesta, titulo_caso, entidades_existentes, forzado="", timeout=30):
    """Despues de que el chat del caso responde, un paso APARTE y liviano
    (perfil rapido) propone entidades/conexiones nuevas. Quedan 'sugerida':
    solo Fernando las marca como verificadas."""
    global last_error
    last_error = None
    r = _generar_json(_PROMPT_SUGERENCIAS_CASO % (
        titulo_caso, ", ".join(entidades_existentes) or "(ninguna todavia)",
        (pregunta or "")[:500], (respuesta or "")[:1500]),
        perfil=PERFIL_RAPIDO, temperatura=0.2, max_tokens=300, timeout=timeout)
    if r is None:
        return {"entidades": [], "conexiones": []}
    entidades = [e for e in (r.get("entidades") or [])
                 if isinstance(e, dict) and str(e.get("nombre", "")).strip()][:3]
    conexiones = [c for c in (r.get("conexiones") or [])
                  if isinstance(c, dict) and str(c.get("origen", "")).strip()
                  and str(c.get("destino", "")).strip()][:2]
    return {"entidades": entidades, "conexiones": conexiones}
