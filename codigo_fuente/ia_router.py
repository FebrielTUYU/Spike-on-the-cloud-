# -*- coding: utf-8 -*-
"""
ia_router.py -- Fase 24 (Parte A2): el trabajo de fondo de la IA pasa por
servicios GRATUITOS, repartido por tarea, y nunca cae en la clave pagada.

Pedido de Fernando: "que el trabajo de fondo no gaste nada" y "no quiero que
un solo proveedor cargue con todo". Cada tarea tiene un proveedor TITULAR y un
RESPALDO distintos; si los dos estan agotados (o sin clave), la tarea ESPERA
(devuelve None y el trabajador sigue con otra cosa). Lo que Fernando pide en
persona (chat, Asistente, contexto bajo demanda) y todo lo privado (casos,
documentos, notas) sigue por la clave pagada de ia.py: eso no pasa por aca.

Proveedores (claves en .env, ver LEEME.md):
  - gemini_free: proyecto de AI Studio SIN facturacion (GEMINI_FREE_KEY).
    Mismo endpoint generateContent que la pagada; Gemma se sirve por aca.
  - groq: API compatible con OpenAI (GROQ_API_KEY).
  - cerebras: API compatible con OpenAI (CEREBRAS_API_KEY).

Cupos: medidos, no supuestos. Cada respuesta de Groq y Cerebras trae
cabeceras x-ratelimit-* (limite y restante por minuto/dia) y se guardan tal
cual; Gemini gratis no las trae, asi que se cuentan los pedidos del dia y un
HTTP 429 lo marca agotado hasta que vence la espera que indique (o hasta el
dia siguiente si es cuota diaria). Todo queda en ia_router_estado.json y en el
panel de IA del dashboard.

Privacidad (condicion de Fernando): los planes gratuitos pueden usar lo que
reciben para entrenar. Por aca SOLO pasan noticias publicas. ia.py nunca
enruta aca los modulos privados (casos, chat).

Solo libreria estandar. Standalone (no importa monitor.py ni ia.py).
"""
import collections
import datetime as dt
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ESTADO_PATH = os.path.join(HERE, "ia_router_estado.json")
UA = "Spike/1.0 (monitor de noticias personal)"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

PROVEEDORES = {
    "gemini_free": {"tipo": "gemini", "clave": "GEMINI_FREE_KEY", "nombre": "Gemini gratis"},
    "groq": {"tipo": "openai", "clave": "GROQ_API_KEY", "nombre": "Groq", "base": "https://api.groq.com/openai/v1"},
    "cerebras": {"tipo": "openai", "clave": "CEREBRAS_API_KEY", "nombre": "Cerebras", "base": "https://api.cerebras.ai/v1"},
}

# Limites conocidos por (proveedor, modelo), medidos en vivo el 2026-09-30 con
# las claves de Fernando (cabeceras de respuesta). Se pisan solos con lo que
# informe cada respuesta. Gemini gratis no informa: valores prudentes que se
# ajustan con los 429.
LIMITES = {
    ("groq", "*"): {"rpm": 30, "rpd": 1000, "tpm": 8000},
    ("cerebras", "*"): {"rpm": 5, "rpd": 2400, "tpm": 30000, "tpd": 1000000},
    ("gemini_free", "*"): {"rpm": 10, "rpd": 500},
    ("gemini_free", "gemini-embedding-001"): {"rpm": 60, "rpd": 1000},
}

# Tarea -> [(proveedor, modelo) titular, respaldo]. Reparto inicial del pedido,
# ajustado a lo que respondio en vivo: Gemma 4 31b devolvio HTTP 500 y la 26b
# tardo 22 s y devolvio su razonamiento en vez de la respuesta, asi que la
# clasificacion arranca en Cerebras con Gemma de respaldo (se re-evalua con el
# CSV de la Parte 0). Se puede cambiar sin tocar codigo:
# MONITOR_IA_RUTA_<TAREA>="groq:openai/gpt-oss-120b,cerebras:gpt-oss-120b".
RUTAS = {
    "triaje": [("gemini_free", "gemini-3.5-flash-lite"), ("groq", "openai/gpt-oss-20b")],
    "clasificacion": [("cerebras", "gpt-oss-120b"), ("gemini_free", "gemma-4-26b-a4b-it")],
    "contexto": [("groq", "openai/gpt-oss-120b"), ("gemini_free", "gemini-3.5-flash")],
    "verificacion": [("cerebras", "gpt-oss-120b"), ("groq", "openai/gpt-oss-120b")],
    "general": [("gemini_free", "gemini-3.5-flash-lite"), ("groq", "openai/gpt-oss-20b")],
    "embeddings": [("gemini_free", "gemini-embedding-001")],
}
# Modulo de ia.py (Parte 0) -> tarea del enrutador.
TAREA_DE_MODULO = {
    "triaje": "triaje", "geo": "triaje", "traduccion": "triaje",
    "clasificacion": "clasificacion",
    "contexto": "contexto", "comunidad": "contexto", "interpretacion": "contexto",
    "veredicto": "verificacion", "declaraciones": "verificacion", "agrupamiento": "verificacion",
    "embeddings": "embeddings",
}
# Nunca por aca (privado o pedido en persona): los resuelve ia.py con la clave pagada.
PRIVADOS = {"casos", "chat"}

_LOCK = threading.RLock()
_VENTANA = collections.defaultdict(collections.deque)  # (prov, modelo) -> [(ts, tokens)] ultimo minuto
# Revision de Codex: pedidos en vuelo que todavia no se anotaron. Cuentan para
# el cupo diario, asi dos hilos no pasan juntos el ultimo pedido del dia.
_EN_VUELO = collections.Counter()
last_error = None


# ------------------------------------------------------------------ claves
def _env():
    """Lee .env junto al programa (las variables del sistema tienen prioridad)."""
    out = {}
    try:
        with open(os.path.join(HERE, ".env"), encoding="utf-8-sig") as f:
            for l in f:
                if "=" in l and not l.lstrip().startswith("#"):
                    k, v = l.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def clave(prov):
    nombre = PROVEEDORES[prov]["clave"]
    v = os.environ.get(nombre) or _env().get(nombre) or ""
    return "" if "pega-aqui" in v else v.strip()


def configurado(prov):
    return bool(clave(prov))


# ------------------------------------------------------------------ estado
def _hoy():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _cargar():
    try:
        with open(ESTADO_PATH, encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                return d
    except Exception:
        pass
    return {}


def _guardar(d):
    tmp = ESTADO_PATH + ".tmp.%d" % threading.get_ident()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, ESTADO_PATH)


def _limites(prov, modelo, estado=None):
    lim = dict(LIMITES.get((prov, "*"), {}))
    lim.update(LIMITES.get((prov, modelo), {}))
    medido = ((estado or _cargar()).get("limites") or {}).get("%s|%s" % (prov, modelo)) or {}
    lim.update({k: v for k, v in medido.items() if isinstance(v, (int, float)) and k in ("rpm", "rpd", "tpm", "tpd")})
    return lim


def _uso_dia(estado, prov, modelo):
    return ((estado.get("dias") or {}).get(_hoy()) or {}).get("%s|%s" % (prov, modelo)) or {}


def _agotado(estado, prov, modelo):
    hasta = ((estado.get("agotado") or {}).get("%s|%s" % (prov, modelo)) or {}).get("hasta")
    if not hasta:
        return None
    try:
        if dt.datetime.fromisoformat(hasta) > dt.datetime.now(dt.timezone.utc):
            return hasta
    except Exception:
        return None
    return None


def _marcar_agotado(prov, modelo, segundos, motivo):
    with _LOCK:
        d = _cargar()
        hasta = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=segundos)
        d.setdefault("agotado", {})["%s|%s" % (prov, modelo)] = {"hasta": hasta.isoformat(), "motivo": motivo}
        _guardar(d)


def _anotar(prov, modelo, tarea, ok, tokens_in=0, tokens_out=0, segundos=0.0, error="", cabeceras=None):
    with _LOCK:
        d = _cargar()
        clave_pm = "%s|%s" % (prov, modelo)
        dia = d.setdefault("dias", {}).setdefault(_hoy(), {})
        u = dia.setdefault(clave_pm, {"pedidos": 0, "ok": 0, "errores": 0, "tokens_in": 0, "tokens_out": 0,
                                      "por_tarea": {}})
        u["pedidos"] += 1
        u["ok" if ok else "errores"] += 1
        u["tokens_in"] += int(tokens_in or 0)
        u["tokens_out"] += int(tokens_out or 0)
        u["por_tarea"][tarea] = u["por_tarea"].get(tarea, 0) + 1
        for k in sorted(d["dias"])[:-14]:
            del d["dias"][k]
        lim = _lim_de_cabeceras(cabeceras or {})
        if lim:
            d.setdefault("limites", {})[clave_pm] = dict(d.get("limites", {}).get(clave_pm) or {}, **lim)
            rest = _restante_de_cabeceras(cabeceras)
            if rest:
                d.setdefault("restante", {})[clave_pm] = dict(rest, ts=dt.datetime.now(dt.timezone.utc).isoformat())
        reg = d.setdefault("registro", [])
        reg.append({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "tarea": tarea, "proveedor": prov,
                    "modelo": modelo, "ok": ok, "tokens_in": int(tokens_in or 0), "tokens_out": int(tokens_out or 0),
                    "segundos": round(segundos, 2), "error": (error or "")[:160]})
        d["registro"] = reg[-200:]
        _guardar(d)


def _num(v):
    try:
        return int(float(str(v).strip()))
    except Exception:
        return None


def _lim_de_cabeceras(h):
    h = {k.lower(): v for k, v in (h or {}).items()}
    out = {}
    pares = {"rpm": ("x-ratelimit-limit-requests-minute",), "rpd": ("x-ratelimit-limit-requests-day", "x-ratelimit-limit-requests"),
             "tpm": ("x-ratelimit-limit-tokens-minute", "x-ratelimit-limit-tokens"), "tpd": ("x-ratelimit-limit-tokens-day",)}
    for k, nombres in pares.items():
        for n in nombres:
            if _num(h.get(n)) is not None:
                out[k] = _num(h.get(n))
                break
    return out


def _restante_de_cabeceras(h):
    h = {k.lower(): v for k, v in (h or {}).items()}
    out = {}
    for k in ("x-ratelimit-remaining-requests-day", "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens-day",
              "x-ratelimit-remaining-tokens", "x-ratelimit-remaining-tokens-minute", "x-ratelimit-remaining-requests-minute"):
        if _num(h.get(k)) is not None:
            out[k.replace("x-ratelimit-remaining-", "")] = _num(h.get(k))
    return out


# ------------------------------------------------------------------ eleccion
def ruta(tarea):
    env = os.environ.get("MONITOR_IA_RUTA_%s" % tarea.upper(), "")
    if env:
        r = []
        for par in env.split(","):
            if ":" in par:
                p, m = par.split(":", 1)
                if p.strip() in PROVEEDORES:
                    r.append((p.strip(), m.strip()))
        if r:
            return r
    return RUTAS.get(tarea) or RUTAS["general"]


def _cabe(prov, modelo, tokens_est, estado):
    """(True, "") o (False, motivo). Motivo 'minuto' = esperar unos segundos."""
    if not configurado(prov):
        return False, "sin clave (%s)" % PROVEEDORES[prov]["clave"]
    if _agotado(estado, prov, modelo):
        return False, "agotado hasta %s" % _agotado(estado, prov, modelo)
    lim = _limites(prov, modelo, estado)
    u = _uso_dia(estado, prov, modelo)
    if lim.get("rpd") and u.get("pedidos", 0) + _EN_VUELO[(prov, modelo)] >= lim["rpd"]:
        return False, "cupo diario de pedidos usado (%d)" % lim["rpd"]
    if lim.get("tpd") and u.get("tokens_in", 0) + u.get("tokens_out", 0) + tokens_est > lim["tpd"]:
        return False, "cupo diario de tokens usado"
    ahora = time.time()
    v = _VENTANA[(prov, modelo)]
    while v and ahora - v[0][0] > 60:
        v.popleft()
    if lim.get("rpm") and len(v) >= lim["rpm"]:
        return False, "minuto"
    if lim.get("tpm") and sum(t for _, t in v) + tokens_est > lim["tpm"]:
        return False, "minuto"
    return True, ""


# ------------------------------------------------------------------ transporte
def _post(url, headers, cuerpo, timeout):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
                                 headers=dict(headers, **{"Content-Type": "application/json", "User-Agent": UA}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8")), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            cuerpo_err = e.read()[:600].decode("utf-8", "replace")
        except Exception:
            cuerpo_err = ""
        return e.code, cuerpo_err, dict(e.headers or {})


def _retry_after(h, cuerpo_err):
    h = {k.lower(): v for k, v in (h or {}).items()}
    s = _num(h.get("retry-after"))
    if s:
        return s
    m = re.search(r'"retryDelay":\s*"(\d+)', cuerpo_err or "")
    return int(m.group(1)) if m else None


def _llamar_gemini(prov, modelo, prompt, sistema, json_mode, temperatura, max_tokens, timeout):
    cfg = {"temperature": temperatura, "maxOutputTokens": max_tokens}
    if modelo.startswith("gemini-"):
        cfg["thinkingConfig"] = {"thinkingBudget": 0} if "2.5" in modelo else {"thinkingLevel": "low"}
        if json_mode:
            cfg["responseMimeType"] = "application/json"
    cuerpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": cfg}
    if sistema:
        if modelo.startswith("gemma"):
            cuerpo["contents"][0]["parts"][0]["text"] = sistema + "\n\n" + prompt  # Gemma no acepta systemInstruction
        else:
            cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}
    c, d, h = _post("%s/models/%s:generateContent" % (GEMINI_BASE, modelo), {"x-goog-api-key": clave(prov)}, cuerpo, timeout)
    if c != 200:
        return None, 0, 0, c, d, h
    cand = (d.get("candidates") or [{}])[0]
    partes = [p for p in ((cand.get("content") or {}).get("parts") or []) if not p.get("thought")]
    texto = "".join(p.get("text", "") for p in partes).strip()
    uso = d.get("usageMetadata") or {}
    return texto, uso.get("promptTokenCount", 0), uso.get("candidatesTokenCount", 0), c, "", h


def _llamar_openai(prov, modelo, prompt, sistema, json_mode, temperatura, max_tokens, timeout):
    msgs = ([{"role": "system", "content": sistema}] if sistema else []) + [{"role": "user", "content": prompt}]
    # gpt-oss razona antes de responder y ese razonamiento cuenta en el tope:
    # razonamiento bajo y margen extra, si no devuelve el texto vacio (visto en vivo).
    cuerpo = {"model": modelo, "messages": msgs, "temperature": temperatura,
              "max_completion_tokens": max_tokens + (1500 if "gpt-oss" in modelo else 0)}
    if "gpt-oss" in modelo:
        cuerpo["reasoning_effort"] = "low"
    if json_mode:
        cuerpo["response_format"] = {"type": "json_object"}
    c, d, h = _post(PROVEEDORES[prov]["base"] + "/chat/completions", {"Authorization": "Bearer " + clave(prov)},
                    cuerpo, timeout)
    if c != 200:
        return None, 0, 0, c, d, h
    msg = ((d.get("choices") or [{}])[0].get("message") or {})
    uso = d.get("usage") or {}
    return (msg.get("content") or "").strip(), uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0), c, "", h


def generar(tarea, prompt, sistema=None, json_mode=False, temperatura=0.2, max_tokens=400, timeout=90,
            espera_max=8):
    """Texto de la respuesta, o None si ningun proveedor gratuito pudo (la
    tarea espera). Nunca usa la clave pagada."""
    global last_error
    last_error = None
    tokens_est = int((len(prompt or "") + len(sistema or "")) / 3.5) + max_tokens
    limite_espera = time.time() + espera_max
    motivos = []
    while True:
        esperar = False
        motivos = []
        estado = _cargar()
        for prov, modelo in ruta(tarea):
            with _LOCK:
                ok, motivo = _cabe(prov, modelo, tokens_est, estado)
                if ok:
                    _VENTANA[(prov, modelo)].append((time.time(), tokens_est))
                    _EN_VUELO[(prov, modelo)] += 1
            if not ok:
                motivos.append("%s %s: %s" % (PROVEEDORES[prov]["nombre"], modelo, motivo))
                esperar = esperar or motivo == "minuto"
                continue
            t0 = time.time()
            fn = _llamar_gemini if PROVEEDORES[prov]["tipo"] == "gemini" else _llamar_openai
            try:
                texto, tin, tout, codigo, err, cab = fn(prov, modelo, prompt, sistema, json_mode, temperatura,
                                                        max_tokens, timeout)
            except Exception as e:
                texto, tin, tout, codigo, err, cab = None, 0, 0, None, type(e).__name__, {}
            finally:
                with _LOCK:
                    _EN_VUELO[(prov, modelo)] -= 1
            seg = time.time() - t0
            if texto:
                _anotar(prov, modelo, tarea, True, tin, tout, seg, cabeceras=cab)
                return texto
            error = "HTTP %s %s" % (codigo, (err or "")[:120]) if codigo else (err or "sin respuesta")
            if codigo == 200:
                error = "respuesta vacia"
            _anotar(prov, modelo, tarea, False, tin, tout, seg, error, cabeceras=cab)
            if codigo == 429:
                ra = _retry_after(cab, err)
                diario = "day" in (err or "").lower() or "PerDay" in (err or "")
                _marcar_agotado(prov, modelo, 3600 * 6 if diario else (ra or 60), "HTTP 429%s" % (" (cuota diaria)" if diario else ""))
            elif codigo in (401, 403):
                _marcar_agotado(prov, modelo, 3600, "HTTP %s (clave rechazada)" % codigo)
            elif codigo in (400, 404):
                _marcar_agotado(prov, modelo, 3600 * 6, "HTTP %s (modelo o pedido no aceptado)" % codigo)
            elif codigo is None or codigo >= 500:
                _marcar_agotado(prov, modelo, 60, "error transitorio (%s): pausa corta" % (codigo or err))
            motivos.append("%s %s: %s" % (PROVEEDORES[prov]["nombre"], modelo, error))
        if esperar and time.time() < limite_espera:
            time.sleep(3)
            continue
        last_error = "ningun proveedor gratuito disponible para '%s' (%s); la tarea espera" % (tarea, "; ".join(motivos))
        return None


def json_de(texto):
    if not texto:
        return None
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.I).strip()
    for cand in (t, t[t.find("{"):t.rfind("}") + 1] if "{" in t else "", t[t.find("["):t.rfind("]") + 1] if "[" in t else ""):
        if not cand:
            continue
        try:
            return json.loads(cand)
        except ValueError:
            continue
    return None


def embed(texto, modelo="gemini-embedding-001", timeout=30):
    """Vector de embedding por la clave GRATIS (mismo modelo que la pagada: los
    vectores viejos siguen siendo comparables). None si no se pudo."""
    global last_error
    prov = "gemini_free"
    estado = _cargar()
    with _LOCK:
        ok, motivo = _cabe(prov, modelo, int(len(texto or "") / 3.5), estado)
        if ok:
            _VENTANA[(prov, modelo)].append((time.time(), 0))
    if not ok:
        last_error = "embeddings gratis: %s" % motivo
        return None
    t0 = time.time()
    try:
        c, d, h = _post("%s/models/%s:embedContent" % (GEMINI_BASE, modelo), {"x-goog-api-key": clave(prov)},
                        {"content": {"parts": [{"text": texto or ""}]}}, timeout)
    except Exception as e:
        c, d, h = None, type(e).__name__, {}
    if c == 200 and (d.get("embedding") or {}).get("values"):
        _anotar(prov, modelo, "embeddings", True, int(len(texto or "") / 4), 0, time.time() - t0, cabeceras=h)
        return d["embedding"]["values"]
    _anotar(prov, modelo, "embeddings", False, 0, 0, time.time() - t0, "HTTP %s" % c, cabeceras=h)
    if c == 429:
        _marcar_agotado(prov, modelo, 3600 * 6 if "day" in str(d).lower() else (_retry_after(h, str(d)) or 60), "HTTP 429")
    elif c in (401, 403):
        _marcar_agotado(prov, modelo, 3600, "HTTP %s (clave rechazada)" % c)
    elif c in (400, 404):
        _marcar_agotado(prov, modelo, 3600 * 6, "HTTP %s (modelo o pedido no aceptado)" % c)
    elif c is None or c >= 500:
        _marcar_agotado(prov, modelo, 60, "error transitorio: pausa corta")
    last_error = "embeddings gratis: HTTP %s" % c
    return None


# ------------------------------------------------------------------ panel
def estado_dashboard():
    """Cupo usado y restante por proveedor/modelo, quien respondio ultimo y
    si estan todos agotados (en ese caso el fondo espera: NO usa la pagada)."""
    d = _cargar()
    hoy = (d.get("dias") or {}).get(_hoy()) or {}
    filas = []
    vistos = set()
    for tarea, r in RUTAS.items():
        for i, (prov, modelo) in enumerate(ruta(tarea)):
            k = "%s|%s" % (prov, modelo)
            if k in vistos:
                continue
            vistos.add(k)
            lim = _limites(prov, modelo, d)
            u = hoy.get(k) or {}
            filas.append({"proveedor": prov, "nombre": PROVEEDORES[prov]["nombre"], "modelo": modelo,
                          "clave": configurado(prov), "pedidos_hoy": u.get("pedidos", 0), "ok_hoy": u.get("ok", 0),
                          "errores_hoy": u.get("errores", 0), "tokens_hoy": u.get("tokens_in", 0) + u.get("tokens_out", 0),
                          "limite_dia": lim.get("rpd"), "restante_informado": (d.get("restante") or {}).get(k),
                          "agotado_hasta": _agotado(d, prov, modelo),
                          "motivo_agotado": ((d.get("agotado") or {}).get(k) or {}).get("motivo") if _agotado(d, prov, modelo) else None,
                          "tareas": sorted(t for t, rr in RUTAS.items() if (prov, modelo) in ruta(t))})
    usables = [f for f in filas if f["clave"] and not f["agotado_hasta"]
               and not (f["limite_dia"] and f["pedidos_hoy"] >= f["limite_dia"])]
    reg = d.get("registro") or []
    ultimo = next((r for r in reversed(reg) if r.get("ok")), None)
    return {"filas": filas, "todos_agotados": not usables, "ultimo": ultimo,
            "rutas": {t: ["%s:%s" % pm for pm in ruta(t)] for t in RUTAS},
            "registro": reg[-15:], "hoy": _hoy()}
