# -*- coding: utf-8 -*-
"""
Fase 9, parte D3 -- orquestador COMPARTIDO de X (xapi.py) y TikTok
(tiktok.py), ambas via Apify con la MISMA cuenta/token. Instagram queda
FUERA (decision de Fernando, ver CLAUDE.md). Standalone (solo importa
xapi/tiktok/alertas, nunca monitor.py -- mismo criterio que el resto del
proyecto para evitar import circular, ya que monitor.py es quien llama a
redes.pasada()).

Objetivo real (pedido explicito): gastar CERCA de los $5 gratis de Apify por
mes SIN pasarse nunca, en vez de dejar credito sin usar -- ritmo diario
DINAMICO (presupuesto_hoy = restante_del_mes / dias_que_quedan), no
frecuencias fijas por red. Lo que no se gasta un dia pasa al siguiente; si
un dia se gasta de mas, los siguientes se ajustan solos.
"""
import calendar
import datetime as dt
import json
import threading
import os
import re

import xapi
import tiktok

try:
    import alertas
except Exception:
    alertas = None

HERE = os.path.dirname(os.path.abspath(__file__))
GASTO_PATH = os.path.join(HERE, "redes_gasto.json")
CACHE_PATH = os.path.join(HERE, "redes_cache.json")

last_error = None
# Fase 20b: comunidad_loop (hilo propio) y el trabajador escriben los mismos
# archivos (gasto y frecuencias); sin candado podian pisarse.
_LOCK = threading.RLock()

TOPE_MES_USD = float(os.environ.get("MONITOR_REDES_TOPE_MES_USD", "4.70"))
REPARTO_INICIAL = {"x": 0.65, "tiktok": 0.35}
MALOS_DIAS_PARA_CEDER = 2

FREQ_ALERTAS_X_H = 1
FREQ_CUENTAS_X_H = 1       # Fase 18 (P1-5.2): cuentas hiperlocales
FREQ_EVENTO_X_MIN = 45     # Fase 18 (P1-5.3): busqueda reactiva por evento en curso
FREQ_HISTORIAS_X_H = 12
# Fase 20b: quejas de la gente de Guayaquil -- hilo propio (comunidad_loop en
# monitor.py), NO dentro de pasada(): el trabajador puede tardar mas de 10 min
# en dar una vuelta. Pedido explicito de Fernando: "minimo cada 10 minutos".
FREQ_COMUNIDAD_X_MIN = float(os.environ.get("MONITOR_COMUNIDAD_X_MIN", "10"))
COMUNIDAD_X_MAX_ITEMS = int(os.environ.get("MONITOR_COMUNIDAD_X_ITEMS", "20"))
# Parte del presupuesto DIARIO de X que Comunidad puede usar como maximo, para
# que las alertas/cuentas/eventos (mas urgentes) nunca se queden sin nada.
COMUNIDAD_PARTE_X = float(os.environ.get("MONITOR_COMUNIDAD_X_PARTE", "0.6"))
FREQ_DEBATE_X_H = 24
FREQ_TIKTOK_H = 24


def activo():
    return xapi.activo()  # misma cuenta/token para las dos redes


# ------------------------- tiempo -------------------------

def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _hoy():
    return _ahora().strftime("%Y-%m-%d")


def _mes():
    return _ahora().strftime("%Y-%m")


def _dias_en_mes():
    ahora = _ahora()
    return calendar.monthrange(ahora.year, ahora.month)[1]


def _dias_restantes_mes():
    """Incluye HOY -- si es el ultimo dia del mes, todavia queda 1 dia de
    presupuesto por gastar (no 0, que dividiria por cero)."""
    ahora = _ahora()
    return max(1, _dias_en_mes() - ahora.day + 1)


# ------------------------- gasto (unificado X + TikTok) -------------------------

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


def gasto_hoy(red=None):
    dia = _cargar_gasto().get("dias", {}).get(_hoy(), {})
    if red:
        return dia.get(red, 0.0)
    return sum(dia.values())


def gasto_mes(red=None):
    mes = _cargar_gasto().get("meses", {}).get(_mes(), {})
    if red:
        return mes.get(red, 0.0)
    return sum(mes.values())


def registrar_gasto(red, monto, motivo=""):
    """Unico punto donde se anota un cobro real -- redes.json (unificado,
    reemplaza a x_gasto.json de la version anterior de xapi.py: el pedido
    explicito era 'renombralo redes_gasto.json si lo unificas')."""
    if monto <= 0:
        return
    with _LOCK:
        _registrar_gasto_sin_lock(red, monto, motivo)


def _registrar_gasto_sin_lock(red, monto, motivo):
    g = _cargar_gasto()
    hoy, mes = _hoy(), _mes()
    g.setdefault("dias", {}).setdefault(hoy, {})
    g["dias"][hoy][red] = round(g["dias"][hoy].get(red, 0.0) + monto, 6)
    g.setdefault("meses", {}).setdefault(mes, {})
    g["meses"][mes][red] = round(g["meses"][mes].get(red, 0.0) + monto, 6)
    hist = g.setdefault("historial", [])
    hist.append({"ts": _ahora().isoformat(), "red": red, "monto": round(monto, 6), "motivo": motivo})
    g["historial"] = hist[-300:]
    _guardar_gasto(g)


def presupuesto_restante_mes():
    # Fase 20b: Facebook tiene tope propio (facebook.py); no descuenta del de X/TikTok.
    return max(0.0, TOPE_MES_USD - gasto_mes("x") - gasto_mes("tiktok"))


def presupuesto_hoy_total():
    """Ritmo dinamico (pedido explicito, no frecuencias fijas): lo que
    todavia no se gasto este mes, repartido entre los dias que quedan
    (incluido hoy). Si ayer se gasto de menos, hoy hay mas margen; si ayer
    se gasto de mas, hoy hay menos -- se ajusta solo, sin acumular estado
    aparte."""
    return presupuesto_restante_mes() / _dias_restantes_mes()


# ------------------------- reparto X/TikTok (con cesion por mal desempeño) -------------------------

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


def marcar_resultado_red(red, util):
    """'util' = True si la red trajo algo real esta pasada (o no se llego a
    intentar por presupuesto -- eso no cuenta como mal desempeño), False si
    hubo un ERROR real o 0 resultados utiles. Dos dias seguidos malos ceden
    la parte de esa red a la otra (ver reparto_hoy)."""
    with _LOCK:
        cache = _cargar_cache()
        malos = cache.setdefault("malos_dias", {})
        if util:
            malos[red] = 0
        else:
            malos[red] = malos.get(red, 0) + 1
        _guardar_cache(cache)


def reparto_hoy():
    cache = _cargar_cache()
    malos = cache.get("malos_dias", {})
    if malos.get("x", 0) >= MALOS_DIAS_PARA_CEDER:
        return {"x": 0.0, "tiktok": 1.0}
    if malos.get("tiktok", 0) >= MALOS_DIAS_PARA_CEDER:
        return {"x": 1.0, "tiktok": 0.0}
    return dict(REPARTO_INICIAL)


def presupuesto_hoy(red):
    return presupuesto_hoy_total() * reparto_hoy().get(red, 0.0)


def cabe(red, costo_max):
    """Antes de CUALQUIER llamada real: entra en el presupuesto de HOY para
    esa red (segun el reparto) Y en lo que queda del mes (red de seguridad
    global, por si el ritmo diario se calculo mal)."""
    restante_mes = presupuesto_restante_mes()
    if costo_max > restante_mes:
        return False, "tope mensual (quedan $%.4f, hace falta $%.4f)" % (restante_mes, costo_max)
    disponible_hoy = presupuesto_hoy(red) - gasto_hoy(red)
    if costo_max > disponible_hoy:
        return False, "presupuesto de hoy para %s agotado (quedan $%.4f, hace falta $%.4f)" % (
            red, disponible_hoy, costo_max)
    return True, ""


# ------------------------- frecuencia por capa -------------------------

def _ultima_vez(clave):
    return _cargar_cache().get("frecuencia", {}).get(clave)


def _marcar_corrida(clave):
    with _LOCK:
        cache = _cargar_cache()
        cache.setdefault("frecuencia", {})[clave] = _ahora().isoformat()
        _guardar_cache(cache)


def _paso_frecuencia(clave, horas):
    ts = _ultima_vez(clave)
    if not ts:
        return True
    try:
        anterior = dt.datetime.fromisoformat(ts)
    except Exception:
        return True
    return (_ahora() - anterior).total_seconds() / 3600 >= horas


# ------------------------- modo simulacion -------------------------

def simular(historias_top, terminos_alerta, barrios):
    """Arma TODAS las consultas reales que se harian HOY (X: alertas +
    historias + debate; TikTok: videos + comentarios) y proyecta el costo
    por dia y por mes -- CERO llamadas de red, sin necesitar token."""
    plan = []
    costo_dia = 0.0

    terms = ["%s Guayaquil" % t for t in terminos_alerta[:8]]
    c_alertas = xapi.costo_estimado(10) * 24  # 1 vez por hora
    plan.append({"capa": "alertas_x", "red": "x", "query": " | ".join(terms), "costo_dia": c_alertas})
    costo_dia += c_alertas

    for h in historias_top[:6]:
        q = h.get("query") or h.get("titular", "")
        c = xapi.costo_estimado(25) * 2  # 2 veces al dia
        plan.append({"capa": "historias_x", "red": "x", "query": q, "costo_dia": c})
        costo_dia += c

    for h in historias_top[:3]:
        q = h.get("query") or h.get("titular", "")
        c = xapi.costo_estimado(30)  # 1 vez al dia
        plan.append({"capa": "debate_x", "red": "x",
                      "query": "conversation_id del tweet mas respondido de: %s" % q, "costo_dia": c})
        costo_dia += c

    for h in historias_top[:2]:
        q = h.get("query") or h.get("titular", "")
        c_videos = tiktok.costo_estimado_videos(3)
        c_comentarios = tiktok.costo_estimado_comentarios(20)
        plan.append({"capa": "tiktok_videos", "red": "tiktok", "query": q, "costo_dia": c_videos})
        plan.append({"capa": "tiktok_comentarios", "red": "tiktok", "query": q, "costo_dia": c_comentarios})
        costo_dia += c_videos + c_comentarios

    dias_mes = _dias_en_mes()
    costo_mes = costo_dia * dias_mes
    costo_x = sum(p["costo_dia"] for p in plan if p["red"] == "x")
    costo_tiktok = sum(p["costo_dia"] for p in plan if p["red"] == "tiktok")
    return {
        "plan": plan,
        "costo_proyectado_dia": round(costo_dia, 4),
        "costo_proyectado_mes": round(costo_mes, 4),
        "reparto_proyectado": {
            "x": round(costo_x / costo_dia, 3) if costo_dia else 0,
            "tiktok": round(costo_tiktok / costo_dia, 3) if costo_dia else 0,
        },
        "tope_mes": TOPE_MES_USD,
        "dentro_del_tope_mes": costo_mes <= TOPE_MES_USD,
    }


# ------------------------- orquestacion por pasada (prioridad D3-2.3) -------------------------

def _registrar_alertas_x(tweets, oficiales=()):
    """Cada tweet nuevo entra a alertas.py con la MISMA funcion que usan
    Bluesky/Telegram, como fuente 'x' -- registrar_senal() ya exige que el
    texto mencione un tipo+lugar reconocido, mas especifico que mirar
    author.location. Dedup por (fuente, autor) via _recomputar_estado, sin
    cambios ahi."""
    if alertas is None:
        return 0
    nuevas = 0
    for t in tweets:
        author = t.get("author") or {}
        usuario = author.get("userName", "?")
        fecha = xapi.fecha_iso(t.get("createdAt", ""))
        if not fecha:
            continue  # Fase 18 (P1-6): sin fecha real no se puede saber si es de hoy
        r = alertas.registrar_senal("x", usuario, t.get("text", ""), t.get("url", ""), fecha,
                                      oficial=usuario.lower() in {o.lower() for o in oficiales})
        if r:
            nuevas += 1
    return nuevas


def _a_comunidad(tweets):
    """Fase 20: todo tweet que ya se pago para otra capa se aprovecha tambien
    como voz de la gente en Comunidad Guayaquil (comunidad.py filtra: solo
    personas, solo Guayaquil, solo si nombra un problema). Sin costo extra."""
    if not tweets:
        return 0
    try:
        import comunidad
        return comunidad.registrar_tweets(tweets)
    except Exception:
        return 0


def tiktok_en_pausa():
    """Fase 18 (P1-5.6): TikTok con MALOS_DIAS_PARA_CEDER dias malos seguidos
    queda en pausa automatica (no se gasta presupuesto en el)."""
    return _cargar_cache().get("malos_dias", {}).get("tiktok", 0) >= MALOS_DIAS_PARA_CEDER


def _pasada_eventos(eventos, terminos_alerta, simular_red, r):
    """Capa 0 (Fase 18, P1-5.3): busqueda REACTIVA por evento en curso -- la
    detecta el agrupamiento (historia madre, ej. lluvias en Guayaquil) y
    dispara una consulta X al instante (sin esperar las 12 h de la capa de
    historias) con los sectores de las notas + palabras del tipo de hecho."""
    hubo = False
    for ev in eventos or []:
        link = ev.get("link") or ev.get("titular", "")
        clave = "_evento_x:%s" % link
        if not _paso_frecuencia(clave, FREQ_EVENTO_X_MIN / 60.0):
            continue
        q = xapi.consulta_evento(ev.get("evento") or {}, ev.get("terminos") or terminos_alerta, horas=2)
        costo_max = xapi.costo_estimado(20)
        ok, razon = (True, "") if simular_red else cabe("x", costo_max)
        if not ok:
            r["saltadas_por_presupuesto"].append("evento_x: %s" % razon)
            continue
        tweets, costo = xapi.buscar_consulta(q, "evento:%s" % link, horas=3, max_items=20, simular=simular_red)
        if tweets is None and xapi.last_error:
            r["errores"].append("evento_x: %s" % xapi.last_error)
            continue
        if not simular_red and isinstance(tweets, list):
            if tweets:
                previos = {str(t.get("id")) for t in xapi.tweets_de_historia(link)}
                xapi.guardar_tweets_historia(link, xapi.tweets_de_historia(link) +
                                             [t for t in tweets if str(t.get("id")) not in previos])
                _registrar_alertas_x(tweets)
                hubo = True
            if costo > 0:
                registrar_gasto("x", costo, "evento_x: %s" % ev.get("titular", ""))
            _marcar_corrida(clave)
        r["evento_x"] += len(tweets) if isinstance(tweets, list) else 0
    return hubo


# ------------------------- Fase 21: EmergenciasEc y su red -------------------------
# Pedido de Fernando (2026-09-30): "haz especial enfasis en la cuenta
# emergencias.ec y sus usuarios con los que interactua, porque es una cuenta con
# medio millon de seguidores que publica las cosas que pasan al momento... y de
# esa forma es leyendo a la gente". Tres cosas, en este orden de prioridad:
#   1) lo que publica @EmergenciasEc, la gente que le RESPONDE y la que la
#      ETIQUETA (una sola consulta: from:/to:/@), cada FREQ_EMERG_MIN (10 min);
#   2) se aprende SU RED: quien le responde, a quien menciona, a quien
#      responde ella (conteo en redes_cache.json, ultimos 14 dias);
#   3) las cuentas mas activas de esa red se leen aparte, cada FREQ_EMERG_RED_MIN.
# Todo entra a Alertas (mismo registrar_senal de siempre) y a Comunidad (que
# filtra solo personas), y queda en un panel propio "Al momento".
# NO verificado en vivo: que el actor de Apify respete from:/to: (operadores
# estandar de la busqueda avanzada de X). Si no, los tweets igual pasan por el
# filtro de fecha e ids vistos.
EMERG_CUENTA = os.environ.get("MONITOR_EMERG_CUENTA", "EmergenciasEc").lstrip("@")
FREQ_EMERG_MIN = float(os.environ.get("MONITOR_EMERG_MIN", "10"))
FREQ_EMERG_RED_MIN = float(os.environ.get("MONITOR_EMERG_RED_MIN", "30"))
EMERG_MAX_ITEMS = int(os.environ.get("MONITOR_EMERG_ITEMS", "40"))
EMERG_RED_TOP = int(os.environ.get("MONITOR_EMERG_RED_TOP", "8"))
# Parte del presupuesto diario de X que esta capa puede usar (va primero: es la
# fuente mas rapida de lo que pasa en la calle). El resto queda para las demas.
EMERG_PARTE_X = float(os.environ.get("MONITOR_EMERG_PARTE", "0.7"))
EMERG_RED_DIAS = 14
_MENCION = re.compile(r"@(\w{2,15})")


def _autor(t):
    return ((t.get("author") or {}).get("userName") or "").lstrip("@")


def _tipo_emerg(t, capa):
    u = _autor(t).lower()
    if u == EMERG_CUENTA.lower():
        return "cuenta"
    if capa == "red":
        return "red"
    return "respuesta"


def _aprender_red(tweets):
    """Cuenta quien interactua con la cuenta: autores que le responden o la
    etiquetan, y cuentas que ella menciona o a las que responde."""
    if not tweets:
        return
    yo = EMERG_CUENTA.lower()
    ahora = _ahora().isoformat()
    with _LOCK:
        cache = _cargar_cache()
        red = cache.setdefault("red_emergencias", {})
        for t in tweets:
            u = _autor(t)
            if u.lower() == yo:
                otros = set(_MENCION.findall(t.get("text") or ""))
                if t.get("inReplyToUsername"):
                    otros.add(t["inReplyToUsername"])
            else:
                otros = {u} if u else set()
            for o in otros:
                if not o or o.lower() == yo:
                    continue
                e = red.setdefault(o, {"n": 0})
                e["n"] += 1
                e["ult"] = ahora
        corte = (_ahora() - dt.timedelta(days=EMERG_RED_DIAS)).isoformat()
        for k in [k for k, v in red.items() if (v.get("ult") or "") < corte]:
            del red[k]
        _guardar_cache(cache)


def red_emergencias(top=EMERG_RED_TOP):
    """[(usuario, n)] de las cuentas que mas interactuan con EmergenciasEc."""
    red = _cargar_cache().get("red_emergencias") or {}
    return sorted(((u, v.get("n", 0)) for u, v in red.items()), key=lambda x: -x[1])[:top]


def _guardar_feed_emerg(tweets, capa):
    """Lo ultimo de la cuenta y su red, para el panel 'Al momento'. Solo lo de
    las ultimas VENTANA_H horas; dedup por id."""
    if not tweets:
        return
    with _LOCK:
        cache = _cargar_cache()
        feed = {x["id"]: x for x in (cache.get("emergencias_feed") or []) if x.get("id")}
        for t in tweets:
            tid = str(t.get("id") or "")
            fecha = xapi.fecha_iso(t.get("createdAt", ""))
            if not tid or not fecha:
                continue
            feed[tid] = {"id": tid, "autor": "@" + _autor(t), "texto": (t.get("text") or "")[:500],
                         "url": t.get("url") or "", "fecha": fecha, "tipo": _tipo_emerg(t, capa),
                         "respuestas": t.get("replyCount") or 0}
        corte = (_ahora() - dt.timedelta(hours=xapi.VENTANA_H)).isoformat()
        vivos = [x for x in feed.values() if _iso_utc(x["fecha"]) >= corte]
        vivos.sort(key=lambda x: _iso_utc(x["fecha"]), reverse=True)
        cache["emergencias_feed"] = vivos[:200]
        _guardar_cache(cache)


def _iso_utc(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return ""


def gasto_emerg_hoy():
    return float((_cargar_cache().get("emerg_gasto") or {}).get(_hoy(), 0.0))


def _sumar_gasto_emerg(monto):
    with _LOCK:
        cache = _cargar_cache()
        g = cache.setdefault("emerg_gasto", {})
        g[_hoy()] = round(g.get(_hoy(), 0.0) + monto, 6)
        for d in sorted(g)[:-7]:
            del g[d]
        _guardar_cache(cache)


def _correr_emerg(clave, consulta, horas, capa):
    """Una consulta de la capa EmergenciasEc con sus topes. Devuelve texto."""
    costo_max = xapi.costo_estimado(EMERG_MAX_ITEMS)
    tope = presupuesto_hoy("x") * EMERG_PARTE_X
    if gasto_emerg_hoy() + costo_max > tope:
        _marcar_corrida(clave)
        return "saltada: parte de EmergenciasEc del presupuesto de X de hoy agotada ($%.4f de $%.4f)" % (
            gasto_emerg_hoy(), tope)
    ok, razon = cabe("x", costo_max)
    if not ok:
        _marcar_corrida(clave)
        return "saltada: %s" % razon
    tweets, costo = xapi.buscar_consulta(consulta, "emergencias", horas=horas, max_items=EMERG_MAX_ITEMS)
    _marcar_corrida(clave)
    if tweets is None:
        return "error: %s" % (xapi.last_error or "sin respuesta")
    if costo > 0:
        registrar_gasto("x", costo, "emergencias_%s" % capa)
        _sumar_gasto_emerg(costo)
    _guardar_feed_emerg(tweets, capa)
    if capa == "cuenta":
        _aprender_red(tweets)
    alertas_n = _registrar_alertas_x(tweets)
    personas = _a_comunidad(tweets) or 0
    return "%d tweets nuevos (%d a alertas, %d de personas a Comunidad, $%.4f)" % (
        len(tweets), alertas_n, personas, costo or 0)


def pasada_emergencias():
    """Hilo de Comunidad (monitor.comunidad_ciclo), cada minuto decide si toca."""
    if not activo():
        return "desactivado (falta token de Apify)"
    hechos = []
    if _paso_frecuencia("_emerg", FREQ_EMERG_MIN / 60.0):
        horas = max(0.5, 2 * FREQ_EMERG_MIN / 60.0)
        c = EMERG_CUENTA
        q = "(from:%s OR to:%s OR @%s) %s" % (c, c, c, xapi._since(horas))
        hechos.append("@%s: %s" % (c, _correr_emerg("_emerg", q, horas, "cuenta")))
    red = red_emergencias()
    if red and _paso_frecuencia("_emerg_red", FREQ_EMERG_RED_MIN / 60.0):
        horas = max(1.0, 2 * FREQ_EMERG_RED_MIN / 60.0)
        q = xapi.consulta_cuentas([{"usuario": u} for u, _ in red], horas=horas)
        hechos.append("su red (%d cuentas): %s" % (len(red), _correr_emerg("_emerg_red", q, horas, "red")))
    return "; ".join(hechos) or "todavia no toca"


def emergencias_dashboard():
    """Lectura sin red para data.json['emergencias']."""
    cache = _cargar_cache()
    corte = (_ahora() - dt.timedelta(hours=xapi.VENTANA_H)).isoformat()
    feed = [x for x in (cache.get("emergencias_feed") or []) if _iso_utc(x.get("fecha")) >= corte]
    return {"cuenta": EMERG_CUENTA, "activo": activo(), "tweets": feed[:120],
            "red": [{"usuario": u, "n": n} for u, n in red_emergencias(15)],
            "frecuencia_min": FREQ_EMERG_MIN, "frecuencia_red_min": FREQ_EMERG_RED_MIN,
            "ventana_h": xapi.VENTANA_H,
            "ultima": (cache.get("frecuencia") or {}).get("_emerg"),
            "gasto_hoy": round(gasto_emerg_hoy(), 5)}


# ------------------------- Fase 23: cuentas comunitarias -------------------------
# Paginas y personas de barrio que Fernando aprobo desde el panel de Comunidad
# (x_cuentas_locales.json, tipo "comunitaria"). Van en UNA consulta "from:A OR
# from:B ..." por tanda (xapi.tandas_cuentas): agregar cuentas sube el costo por
# tweets DEVUELTOS, no por cuenta. Prioridad mas baja de todas las capas de X:
# si el mes se acerca al tope, estas bajan de frecuencia (y despues se pausan)
# ANTES que EmergenciasEc y las Alertas. Nunca cuentan como fuente oficial.
FREQ_COMUNITARIAS_MIN = float(os.environ.get("MONITOR_COMUNITARIAS_MIN", "30"))
COMUNITARIAS_MAX_ITEMS = int(os.environ.get("MONITOR_COMUNITARIAS_ITEMS", "20"))
COMUNITARIAS_PARTE_X = float(os.environ.get("MONITOR_COMUNITARIAS_PARTE", "0.25"))
# Umbrales sobre lo que QUEDA del tope mensual: por debajo de REDUCIR, la
# frecuencia se multiplica por 4; por debajo de PAUSAR, no se consultan.
COMUNITARIAS_REDUCIR = float(os.environ.get("MONITOR_COMUNITARIAS_REDUCIR", "0.25"))
COMUNITARIAS_PAUSAR = float(os.environ.get("MONITOR_COMUNITARIAS_PAUSAR", "0.10"))


def _tipo(c):
    try:
        import cuentas
        return cuentas.tipo_cuenta(c)
    except Exception:
        return "oficial" if c.get("oficial") else "local"


def ritmo_comunitarias():
    """(minutos entre consultas, o None si en pausa; motivo). Decide SOLO con
    el gasto real del mes y de hoy: las demas capas no cambian."""
    frac = presupuesto_restante_mes() / TOPE_MES_USD if TOPE_MES_USD else 0.0
    if frac < COMUNITARIAS_PAUSAR:
        return None, "pausada: queda %.0f%% del tope del mes (se reserva para EmergenciasEc y Alertas)" % (100 * frac)
    if frac < COMUNITARIAS_REDUCIR:
        return FREQ_COMUNITARIAS_MIN * 4, "reducida: queda %.0f%% del tope del mes" % (100 * frac)
    hoy = presupuesto_hoy("x")
    if hoy and gasto_hoy("x") >= 0.7 * hoy:
        return FREQ_COMUNITARIAS_MIN * 2, "reducida: X ya uso %.0f%% de su presupuesto de hoy" % (
            100 * gasto_hoy("x") / hoy)
    return FREQ_COMUNITARIAS_MIN, "normal"


def _uso_comunitarias(cache=None):
    return (cache if cache is not None else _cargar_cache()).get("comunitarias_uso") or {}


def _sumar_uso_comunitarias(tweets, usd, a_comunidad):
    with _LOCK:
        cache = _cargar_cache()
        u = cache.setdefault("comunitarias_uso", {})
        d = u.setdefault(_hoy(), {"consultas": 0, "tweets": 0, "usd": 0.0, "a_comunidad": 0})
        d["consultas"] += 1
        d["tweets"] += int(tweets)
        d["usd"] = round(d["usd"] + usd, 6)
        d["a_comunidad"] += int(a_comunidad or 0)
        for dia in sorted(u)[:-14]:
            del u[dia]
        _guardar_cache(cache)


def pasada_comunitarias(cuentas=None, simular_red=False):
    """Hilo de Comunidad (monitor.comunidad_ciclo), cada minuto decide si toca.
    Devuelve un texto."""
    if not activo() and not simular_red:
        return "desactivado (falta token de Apify)"
    if cuentas is None:
        try:
            import cuentas as _c
            cuentas = _c.comunitarias()
        except Exception:
            cuentas = []
    cuentas = [c for c in cuentas if c.get("usuario")]
    if not cuentas:
        return "sin cuentas comunitarias aprobadas"
    minutos, motivo = ritmo_comunitarias()
    if minutos is None:
        return motivo
    if not _paso_frecuencia("_comunitarias", minutos / 60.0):
        return "todavia no toca"
    horas = max(0.5, 2 * minutos / 60.0)
    partes, tweets_tot, costo_tot, com_tot = [], 0, 0.0, 0
    for tanda in xapi.tandas_cuentas(cuentas):
        costo_max = xapi.costo_estimado(COMUNITARIAS_MAX_ITEMS)
        gastado = 0.0
        if not simular_red:
            tope = presupuesto_hoy("x") * COMUNITARIAS_PARTE_X
            gastado = float(_uso_comunitarias().get(_hoy(), {}).get("usd", 0.0))
            if gastado + costo_max > tope:
                partes.append("saltada: parte de las comunitarias del presupuesto de X de hoy agotada "
                              "($%.4f de $%.4f)" % (gastado, tope))
                break
            ok, razon = cabe("x", costo_max)
            if not ok:
                partes.append("saltada: %s" % razon)
                break
        q = xapi.consulta_cuentas(tanda, horas=horas)
        # Revision de Codex (Fase 23): el techo de cobro que viaja a Apify
        # (maxTotalChargeUsd) era el generico de $0.30; aca se limita a lo que
        # esta capa puede gastar de verdad, asi un cobro anomalo no se come el
        # saldo de EmergenciasEc/Alertas.
        techo = costo_max * 2
        if not simular_red:
            techo = min(techo, max(0.001, presupuesto_restante_mes()),
                        max(0.001, presupuesto_hoy("x") * COMUNITARIAS_PARTE_X - gastado))
        tweets, costo = xapi.buscar_consulta(q, "comunitarias", horas=horas, max_items=COMUNITARIAS_MAX_ITEMS,
                                             simular=simular_red, tope_seguridad_usd=techo)
        if simular_red:
            partes.append("simulacion: %s" % q)
            continue
        if tweets is None:
            partes.append("error: %s" % (xapi.last_error or "sin respuesta"))
            continue
        if costo > 0:
            registrar_gasto("x", costo, "comunitarias_x")
        # Nunca oficiales: oficiales=() a proposito (Fase 23).
        _registrar_alertas_x(tweets, oficiales=())
        n_com = _a_comunidad(tweets) or 0
        _sumar_uso_comunitarias(len(tweets), costo or 0.0, n_com)
        tweets_tot += len(tweets)
        costo_tot += costo or 0.0
        com_tot += n_com
    if not simular_red:
        _marcar_corrida("_comunitarias")
    resumen = "%d cuentas, %d tweets nuevos (%d a Comunidad, $%.4f), ritmo %s cada %d min" % (
        len(cuentas), tweets_tot, com_tot, costo_tot, motivo, minutos)
    return resumen + ("; " + "; ".join(partes) if partes else "")


def comunitarias_dashboard():
    """Numeros honestos de lo que agregan las comunitarias (panel de gasto).
    Sin dias medidos, los promedios van en None (no en cero)."""
    try:
        import cuentas as _c
        n = len(_c.comunitarias())
    except Exception:
        n = 0
    cache = _cargar_cache()
    uso = _uso_comunitarias(cache)
    dias = sorted(uso)[-7:]
    tot_t = sum(uso[d]["tweets"] for d in dias)
    tot_usd = sum(uso[d]["usd"] for d in dias)
    minutos, motivo = ritmo_comunitarias()
    return {"cuentas": n, "frecuencia_min": minutos, "ritmo": motivo,
            "hoy": uso.get(_hoy()),
            "dias_medidos": len(dias),
            "tweets_dia_prom": round(tot_t / len(dias), 1) if dias else None,
            "usd_dia_prom": round(tot_usd / len(dias), 4) if dias else None,
            "usd_mes_proyectado": round(tot_usd / len(dias) * _dias_en_mes(), 2) if dias else None,
            "ultima": (cache.get("frecuencia") or {}).get("_comunitarias"),
            "tope_mes": TOPE_MES_USD, "parte_x": COMUNITARIAS_PARTE_X,
            "por_dia": [dict(uso[d], dia=d) for d in dias]}


def gasto_comunidad_hoy():
    return float((_cargar_cache().get("comunidad_gasto") or {}).get(_hoy(), 0.0))


def _sumar_gasto_comunidad(monto):
    with _LOCK:
        cache = _cargar_cache()
        g = cache.setdefault("comunidad_gasto", {})
        g[_hoy()] = round(g.get(_hoy(), 0.0) + monto, 6)
        for d in sorted(g)[:-7]:  # solo la ultima semana
            del g[d]
        _guardar_cache(cache)


def pasada_comunidad(simular_red=False):
    """Fase 20b: quejas de la gente de Guayaquil en X, cada FREQ_COMUNIDAD_X_MIN
    (def. 10 min). Ventana 'since:' corta (el doble de la frecuencia, para no
    perder nada entre vueltas): Apify cobra POR TWEET DEVUELTO, asi que consultar
    seguido con ventana corta cuesta casi lo mismo que consultar poco con
    ventana larga -- se paga lo nuevo, no la frecuencia. Tope propio: nunca mas
    de COMUNIDAD_PARTE_X del presupuesto diario de X. Devuelve un texto."""
    if not activo() and not simular_red:
        return "desactivado (falta token de Apify)"
    if not _paso_frecuencia("_comunidad_x", FREQ_COMUNIDAD_X_MIN / 60.0):
        return "todavia no toca"
    try:
        import comunidad
    except Exception:
        return "comunidad.py no disponible"
    # Fase 24 (B1): rotacion entre varias consultas (instituciones, tandas de
    # barrios, la vieja con "Guayaquil"), eligiendo por rendimiento medido.
    # Ventana: el doble del ciclo completo, asi ninguna deja huecos entre vueltas.
    candidatas = comunidad.consultas_x(horas=1) if hasattr(comunidad, "consultas_x") else []
    ciclo_h = max(1, len(candidatas)) * FREQ_COMUNIDAD_X_MIN / 60.0
    horas = max(0.5, 2 * ciclo_h)
    if candidatas:
        elegida = _elegir_consulta_comunidad([c["id"] for c in candidatas])
        if elegida is None:
            _marcar_corrida("_comunidad_x")
            return "todas las consultas de Comunidad estan apagadas por bajo rendimiento esta semana"
        consulta = next(c for c in comunidad.consultas_x(horas=horas) if c["id"] == elegida)["q"]
    else:
        elegida, consulta = "guayaquil", comunidad.consulta_x(horas=horas)
    if not consulta:
        return "sin consulta"
    costo_max = xapi.costo_estimado(COMUNIDAD_X_MAX_ITEMS)
    if not simular_red:
        tope = presupuesto_hoy("x") * COMUNIDAD_PARTE_X
        if gasto_comunidad_hoy() + costo_max > tope:
            _marcar_corrida("_comunidad_x")
            return "saltada: parte de Comunidad del presupuesto de X de hoy agotada ($%.4f de $%.4f)" % (
                gasto_comunidad_hoy(), tope)
        ok, razon = cabe("x", costo_max)
        if not ok:
            _marcar_corrida("_comunidad_x")
            return "saltada: %s" % razon
    tweets, costo = xapi.buscar_consulta(consulta, "comunidad", horas=horas, max_items=COMUNIDAD_X_MAX_ITEMS,
                                         simular=simular_red)
    if simular_red:
        return "simulacion: %s" % consulta
    _marcar_corrida("_comunidad_x")
    if tweets is None:
        return "error: %s" % (xapi.last_error or "sin respuesta")
    if costo > 0:
        registrar_gasto("x", costo, "comunidad_x")
        _sumar_gasto_comunidad(costo)
    n = _a_comunidad(tweets)
    _anotar_rendimiento(elegida, len(tweets), n or 0, costo or 0.0)
    return "[%s] %d tweets nuevos, %d de personas de Guayaquil ($%.4f)" % (elegida, len(tweets), n or 0, costo or 0)


# ------------------------- Fase 24 (B3b): funcionarios bajo seguimiento -------------------------
# Una sola consulta "(from:A OR from:B) since:" cada FREQ_FUNCIONARIOS_MIN, por
# encima de Comunidad y debajo de EmergenciasEc (comunidad_ciclo las corre en
# ese orden). Parte propia del presupuesto diario de X. Las cuentas oficiales
# publican poco: la consulta devuelve 0-3 tuits casi siempre. OJO medido en
# vivo: el actor de Apify devuelve hasta 20 aunque se pidan menos, y reporta
# costo real $0 (cortesia); el costo real por corrida hay que mirarlo en la
# consola de Apify.
FREQ_FUNCIONARIOS_MIN = float(os.environ.get("MONITOR_FUNCIONARIOS_MIN", "5"))
FUNCIONARIOS_PARTE_X = float(os.environ.get("MONITOR_FUNCIONARIOS_PARTE", "0.15"))


def gasto_funcionarios_hoy():
    return float((_cargar_cache().get("funcionarios_gasto") or {}).get(_hoy(), 0.0))


def pasada_funcionarios():
    if not activo():
        return "desactivado (falta token de Apify)"
    if not _paso_frecuencia("_funcionarios", FREQ_FUNCIONARIOS_MIN / 60.0):
        return "todavia no toca"
    try:
        import funcionarios
    except Exception:
        return "funcionarios.py no disponible"
    horas = max(0.25, 2 * FREQ_FUNCIONARIOS_MIN / 60.0)
    q = funcionarios.consulta(horas, xapi._since)
    if not q:
        return "sin funcionarios activos"
    costo_max = xapi.costo_estimado(20)
    tope = presupuesto_hoy("x") * FUNCIONARIOS_PARTE_X
    if gasto_funcionarios_hoy() + costo_max > tope:
        _marcar_corrida("_funcionarios")
        return "saltada: parte de funcionarios del presupuesto de X de hoy agotada ($%.4f de $%.4f)" % (
            gasto_funcionarios_hoy(), tope)
    ok, razon = cabe("x", costo_max)
    if not ok:
        _marcar_corrida("_funcionarios")
        return "saltada: %s" % razon
    tweets, costo = xapi.buscar_consulta(q, "funcionarios", horas=horas, max_items=20,
                                         tope_seguridad_usd=max(0.001, costo_max * 2))
    _marcar_corrida("_funcionarios")
    if tweets is None:
        return "error: %s" % (xapi.last_error or "sin respuesta")
    if costo > 0:
        registrar_gasto("x", costo, "funcionarios_x")
    # Revision de Codex (alta): Apify reporta $0 seguido aunque la consola puede
    # cobrar. La parte de funcionarios se descuenta con el costo ESTIMADO cuando
    # el real viene en 0; si no, una consulta cada 5 min (288 por dia) nunca
    # tocaria su tope.
    imputado = costo if costo > 0 else xapi.costo_estimado(max(len(tweets), 1))
    if imputado > 0:
        with _LOCK:
            cache = _cargar_cache()
            g = cache.setdefault("funcionarios_gasto", {})
            g[_hoy()] = round(g.get(_hoy(), 0.0) + imputado, 6)
            for d in sorted(g)[:-7]:
                del g[d]
            _guardar_cache(cache)
    nuevos = funcionarios.procesar_tuits(tweets, xapi.fecha_iso)
    _registrar_alertas_x(tweets, oficiales=())
    return "%d tuits devueltos, %d nuevos de funcionarios ($%.4f)" % (len(tweets), len(nuevos), costo or 0)


# ------------------------- Fase 24 (B1): rendimiento por consulta -------------------------
# Rendimiento = quejas utiles de Guayaquil (las que entran a Comunidad) por cada
# $0.01. Como Apify reporta $0 seguido (cortesia del actor), el costo usado es
# el ESTIMADO por tweet devuelto cuando el real viene en 0 -- asi el
# rendimiento no da infinito. Cada semana se apagan las que rinden poco.
RENDIMIENTO_MIN = float(os.environ.get("MONITOR_COMUNIDAD_RENDIMIENTO_MIN", "1.0"))  # quejas por $0.01
RENDIMIENTO_CORRIDAS_MIN = 6   # no se juzga una consulta con menos corridas que esto
RENDIMIENTO_DIAS = 7


def _rend(cache=None):
    return (cache if cache is not None else _cargar_cache()).setdefault("comunidad_consultas", {})


def _anotar_rendimiento(cid, n_tweets, n_utiles, costo):
    costo_cuenta = costo if costo > 0 else xapi.costo_estimado(max(1, n_tweets))
    with _LOCK:
        cache = _cargar_cache()
        r = _rend(cache).setdefault(cid, {"corridas": 0, "tweets": 0, "utiles": 0, "usd": 0.0, "desde": _ahora().isoformat()})
        r["corridas"] += 1
        r["tweets"] += int(n_tweets)
        r["utiles"] += int(n_utiles)
        r["usd"] = round(r["usd"] + costo_cuenta, 6)
        r["ultima"] = _ahora().isoformat()
        rend = r["utiles"] / (r["usd"] * 100) if r["usd"] else 0.0
        r["rendimiento"] = round(rend, 2)
        if r["corridas"] >= RENDIMIENTO_CORRIDAS_MIN and rend < RENDIMIENTO_MIN:
            r["apagada_hasta"] = (_ahora() + dt.timedelta(days=RENDIMIENTO_DIAS)).isoformat()
            r.update({"corridas": 0, "tweets": 0, "utiles": 0, "usd": 0.0})  # se vuelve a medir de cero al volver
        _guardar_cache(cache)


def _elegir_consulta_comunidad(ids):
    """La que menos recientemente corrio, entre las no apagadas; a igualdad,
    la de mayor rendimiento. None si todas estan apagadas."""
    r = _rend()
    ahora = _ahora().isoformat()
    vivas = [i for i in ids if (r.get(i) or {}).get("apagada_hasta", "") <= ahora]
    if not vivas:
        return None
    return min(vivas, key=lambda i: ((r.get(i) or {}).get("ultima", ""), -((r.get(i) or {}).get("rendimiento") or 0)))


def rendimiento_comunidad():
    """Para el panel: por consulta, corridas, utiles, gasto, rendimiento y si esta apagada."""
    r = _rend()
    ahora = _ahora().isoformat()
    return [dict(v, id=k, apagada=(v.get("apagada_hasta", "") > ahora)) for k, v in sorted(r.items())]


def pasada(historias_top, terminos_alerta, barrios, simular_red=False, eventos=None, cuentas=None):
    """Punto de entrada del hilo TRABAJADOR (nunca run_fast). Orden de
    prioridad (D3-2.3): 1) alertas Guayaquil por X (barato, sensible al
    tiempo) 2) tweets por historia (X) 3) debate en X 4) TikTok (videos +
    comentarios, una vez al dia). Cada capa respeta su propia frecuencia Y
    el presupuesto de HOY para su red -- si no entra, se salta y queda
    reportado, nunca se oculta."""
    if not activo() and not simular_red:
        return "desactivado (falta token de Apify)"
    simular_red = simular_red or os.environ.get("MONITOR_X_SIMULAR") == "1"

    r = {"evento_x": 0, "alertas_x": 0, "cuentas_x": 0, "historias_x": 0, "debate_x": 0,
         "tiktok_videos": 0, "tiktok_comentarios": 0, "errores": [], "saltadas_por_presupuesto": []}
    hubo_x, hubo_tiktok = False, False

    # 0) Fase 18: evento en curso primero (lo mas urgente).
    hubo_x = _pasada_eventos(eventos, terminos_alerta, simular_red, r) or hubo_x

    # 1) Alertas Guayaquil por X -- cada hora, lo mas barato y sensible al tiempo.
    if _paso_frecuencia("_alertas_x", FREQ_ALERTAS_X_H):
        costo_max = xapi.costo_estimado(15)
        ok, razon = (True, "") if simular_red else cabe("x", costo_max)
        if ok:
            tweets, costo = xapi.buscar_alertas(terminos_alerta, "Guayaquil", horas=2, max_items=15,
                                                simular=simular_red)
            if tweets is None and xapi.last_error:
                r["errores"].append("alertas_x: %s" % xapi.last_error)
            elif isinstance(tweets, list):
                nuevas = _registrar_alertas_x(tweets) if not simular_red else 0
                if not simular_red:
                    _a_comunidad(tweets)
                r["alertas_x"] = len(tweets)
                if not simular_red and costo > 0:
                    registrar_gasto("x", costo, "alertas_x")
                hubo_x = hubo_x or bool(tweets)
        else:
            r["saltadas_por_presupuesto"].append("alertas_x: %s" % razon)
        if not simular_red:
            _marcar_corrida("_alertas_x")

    # 1b) Fase 18 (P1-5.2): cuentas hiperlocales (x_cuentas_locales.json) --
    # mas barato y con mas senal que buscar palabras sueltas.
    cuentas = cuentas if cuentas is not None else xapi.cuentas_locales()
    # Fase 21: EmergenciasEc ya tiene su capa propia cada 10 min (pasada_emergencias);
    # leerla tambien aca pagaria dos veces los mismos tweets.
    # Fase 23: las comunitarias tambien tienen capa propia (pasada_comunitarias).
    cuentas = [c for c in cuentas if (c.get("usuario") or "").lstrip("@").lower() != EMERG_CUENTA.lower()
               and _tipo(c) != "comunitaria"]
    if cuentas and _paso_frecuencia("_cuentas_x", FREQ_CUENTAS_X_H):
        costo_max = xapi.costo_estimado(20)
        ok, razon = (True, "") if simular_red else cabe("x", costo_max)
        if ok:
            tweets, costo = xapi.buscar_consulta(xapi.consulta_cuentas(cuentas, horas=2), "cuentas",
                                                 horas=2, max_items=20, simular=simular_red)
            if tweets is None and xapi.last_error:
                r["errores"].append("cuentas_x: %s" % xapi.last_error)
            elif isinstance(tweets, list):
                if not simular_red:
                    _registrar_alertas_x(tweets, oficiales=[c["usuario"].lstrip("@") for c in cuentas if _tipo(c) == "oficial"])
                    _a_comunidad(tweets)
                    if costo > 0:
                        registrar_gasto("x", costo, "cuentas_x")
                r["cuentas_x"] = len(tweets)
                hubo_x = hubo_x or bool(tweets)
        else:
            r["saltadas_por_presupuesto"].append("cuentas_x: %s" % razon)
        if not simular_red:
            _marcar_corrida("_cuentas_x")

    # 2) Tweets por historia (X) -- 6 historias top, cada 12h. El llamador
    # (monitor.py) ya excluye boletines de plantilla de 'historias_top' y
    # (Fase 18) las historias sin una entidad buena (query None).
    if _paso_frecuencia("_historias_x", FREQ_HISTORIAS_X_H):
        for h in historias_top[:6]:
            q = h.get("query")
            if not q:
                continue
            costo_max = xapi.costo_estimado(25)
            ok, razon = (True, "") if simular_red else cabe("x", costo_max)
            if not ok:
                r["saltadas_por_presupuesto"].append("historias_x (%s): %s" % (q, razon))
                continue
            items, costo = xapi.buscar_historia(q, max_items=25, simular=simular_red)
            if items is None and xapi.last_error:
                r["errores"].append("historias_x: %s" % xapi.last_error)
                continue
            if not simular_red and isinstance(items, list):
                link = h.get("link") or q
                xapi.guardar_tweets_historia(link, items)
                _a_comunidad(items)
                if costo > 0:
                    registrar_gasto("x", costo, "historias_x: %s" % q)
                hubo_x = hubo_x or bool(items)
            r["historias_x"] += 1
        if not simular_red:
            _marcar_corrida("_historias_x")

    # 3) Debate en X -- las 3 historias con mas volumen ya recolectado, 1 vez/dia.
    if _paso_frecuencia("_debate_x", FREQ_DEBATE_X_H):
        con_volumen = sorted(
            ((h, len(xapi.tweets_de_historia(h.get("link") or h.get("query") or h.get("titular", ""))))
             for h in historias_top[:6]),
            key=lambda x: x[1], reverse=True,
        )[:3]
        for h, _n in con_volumen:
            tweets = xapi.tweets_de_historia(h.get("link") or h.get("query") or h.get("titular", ""))
            if not tweets:
                continue
            top_tweet = max(tweets, key=lambda t: t.get("replyCount", 0) or 0)
            conv_id = top_tweet.get("conversationId") or top_tweet.get("id")
            if not conv_id:
                continue
            costo_max = xapi.costo_estimado(30)
            ok, razon = (True, "") if simular_red else cabe("x", costo_max)
            if not ok:
                r["saltadas_por_presupuesto"].append("debate_x: %s" % razon)
                continue
            items, costo = xapi.respuestas_de(conv_id, max_items=30, simular=simular_red)
            if items is None and xapi.last_error:
                r["errores"].append("debate_x: %s" % xapi.last_error)
                continue
            if not simular_red and costo > 0:
                registrar_gasto("x", costo, "debate_x")
            r["debate_x"] += 1
        if not simular_red:
            _marcar_corrida("_debate_x")

    # 4) TikTok -- 2 historias top, una vez al dia. Videos primero, despues
    # comentarios del video con MAS comentarios de cada historia (el debate
    # de la gente vale mas que el video en si).
    if tiktok_en_pausa():
        r["tiktok_pausa"] = True
    elif _paso_frecuencia("_tiktok", FREQ_TIKTOK_H):
        for h in historias_top[:2]:
            q = h.get("query") or h.get("titular", "")
            costo_max_v = tiktok.costo_estimado_videos(3)
            ok, razon = (True, "") if simular_red else cabe("tiktok", costo_max_v)
            if not ok:
                r["saltadas_por_presupuesto"].append("tiktok_videos (%s): %s" % (q, razon))
                continue
            videos, costo_v = tiktok.buscar_videos(q, resultados=3, dias_max=7, simular=simular_red)
            if videos is None and tiktok.last_error:
                r["errores"].append("tiktok_videos: %s" % tiktok.last_error)
                continue
            if not simular_red and costo_v > 0:
                registrar_gasto("tiktok", costo_v, "tiktok_videos: %s" % q)
            r["tiktok_videos"] += 1
            hubo_tiktok = hubo_tiktok or bool(videos and not (isinstance(videos, dict)))
            if simular_red or not isinstance(videos, list) or not videos:
                continue
            link = h.get("link") or q
            tiktok.guardar_videos_historia(link, videos)
            video_top = max(videos, key=lambda v: v.get("commentCount", 0) or 0)
            n_comentarios = video_top.get("commentCount", 0) or 0
            video_url = video_top.get("webVideoUrl") or video_top.get("url", "")
            if not video_url or not tiktok.hace_falta_bajar_comentarios(video_url, n_comentarios):
                continue
            costo_max_c = tiktok.costo_estimado_comentarios(20)
            ok, razon = cabe("tiktok", costo_max_c)
            if not ok:
                r["saltadas_por_presupuesto"].append("tiktok_comentarios (%s): %s" % (q, razon))
                continue
            comentarios, costo_c = tiktok.buscar_comentarios(video_url, n_comentarios, max_comentarios=20)
            if comentarios is None and tiktok.last_error:
                r["errores"].append("tiktok_comentarios: %s" % tiktok.last_error)
                continue
            if costo_c > 0:
                registrar_gasto("tiktok", costo_c, "tiktok_comentarios: %s" % q)
            tiktok.guardar_comentarios_video(video_url, comentarios)
            r["tiktok_comentarios"] += 1
            hubo_tiktok = True
        if not simular_red:
            _marcar_corrida("_tiktok")

    if not simular_red:
        capas_x = ("evento_x", "alertas_x", "cuentas_x", "historias_x", "debate_x")
        capas_tiktok = ("tiktok_videos", "tiktok_comentarios")
        if r["errores"] and any(e.split(":")[0] in capas_x for e in r["errores"]):
            marcar_resultado_red("x", False)
        elif hubo_x:
            marcar_resultado_red("x", True)
        if r["errores"] and any(e.split(":")[0] in capas_tiktok for e in r["errores"]):
            marcar_resultado_red("tiktok", False)
        elif hubo_tiktok:
            marcar_resultado_red("tiktok", True)

    estado = ("ok (evento_x:+%d, alertas_x:+%d, cuentas_x:+%d, historias_x:+%d, debate_x:+%d, "
              "tiktok_videos:+%d, tiktok_comentarios:+%d)") % (
        r["evento_x"], r["alertas_x"], r["cuentas_x"], r["historias_x"], r["debate_x"],
        r["tiktok_videos"], r["tiktok_comentarios"])
    if r.get("tiktok_pausa"):
        estado += " -- tiktok en pausa (%d dias malos seguidos)" % MALOS_DIAS_PARA_CEDER
    if r["saltadas_por_presupuesto"]:
        estado += " -- sin presupuesto hoy: %s" % "; ".join(r["saltadas_por_presupuesto"][:3])
    if r["errores"]:
        estado += " -- errores: %s" % "; ".join(r["errores"][:3])
    if simular_red:
        estado = "SIMULACION -- " + estado + " -- gasto proyectado, NADA se cobro de verdad"
    return estado


def estado_dashboard():
    """Texto + numeros honestos para el panel 'Prueba de redes' -- NUNCA el
    token."""
    if not xapi.activo():
        return {"activo": False, "estado": "desactivado: falta token de Apify (MONITOR_APIFY_TOKEN / x_config.json)",
                "gasto_hoy": 0.0, "gasto_mes": 0.0, "tope_mes": TOPE_MES_USD,
                "presupuesto_hoy": 0.0, "reparto": dict(REPARTO_INICIAL)}
    return {
        "activo": True,
        "estado": "ok",
        "gasto_hoy": round(gasto_hoy(), 5),
        "gasto_hoy_x": round(gasto_hoy("x"), 5),
        "gasto_hoy_tiktok": round(gasto_hoy("tiktok"), 5),
        "gasto_mes": round(gasto_mes(), 5),
        "gasto_mes_facebook": round(gasto_mes("facebook"), 5),
        "gasto_mes_x": round(gasto_mes("x"), 5),
        "gasto_mes_tiktok": round(gasto_mes("tiktok"), 5),
        "restante_mes": round(presupuesto_restante_mes(), 5),
        "presupuesto_hoy": round(presupuesto_hoy_total(), 5),
        "tope_mes": TOPE_MES_USD,
        "reparto": reparto_hoy(),
        "dias_restantes_mes": _dias_restantes_mes(),
        "comunitarias": comunitarias_dashboard(),
        # Fase 24 (B1): rendimiento de cada consulta de Comunidad y proyeccion del mes al ritmo actual.
        "consultas_comunidad": rendimiento_comunidad(),
        "proyeccion_mes": round(gasto_mes() / max(1, _ahora().day) * _dias_en_mes(), 3),
        "tope_desde_env": "MONITOR_REDES_TOPE_MES_USD",
    }
