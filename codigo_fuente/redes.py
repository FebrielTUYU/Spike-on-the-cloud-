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
import os

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

TOPE_MES_USD = float(os.environ.get("MONITOR_REDES_TOPE_MES_USD", "4.70"))
REPARTO_INICIAL = {"x": 0.65, "tiktok": 0.35}
MALOS_DIAS_PARA_CEDER = 2

FREQ_ALERTAS_X_H = 1
FREQ_HISTORIAS_X_H = 12
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
    return max(0.0, TOPE_MES_USD - gasto_mes())


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

def _registrar_alertas_x(tweets):
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
        r = alertas.registrar_senal("x", author.get("userName", "?"), t.get("text", ""),
                                      t.get("url", ""), xapi.fecha_iso(t.get("createdAt", "")), oficial=False)
        if r:
            nuevas += 1
    return nuevas


def pasada(historias_top, terminos_alerta, barrios, simular_red=False):
    """Punto de entrada del hilo TRABAJADOR (nunca run_fast). Orden de
    prioridad (D3-2.3): 1) alertas Guayaquil por X (barato, sensible al
    tiempo) 2) tweets por historia (X) 3) debate en X 4) TikTok (videos +
    comentarios, una vez al dia). Cada capa respeta su propia frecuencia Y
    el presupuesto de HOY para su red -- si no entra, se salta y queda
    reportado, nunca se oculta."""
    if not activo() and not simular_red:
        return "desactivado (falta token de Apify)"
    simular_red = simular_red or os.environ.get("MONITOR_X_SIMULAR") == "1"

    r = {"alertas_x": 0, "historias_x": 0, "debate_x": 0, "tiktok_videos": 0, "tiktok_comentarios": 0,
         "errores": [], "saltadas_por_presupuesto": []}
    hubo_x, hubo_tiktok = False, False

    # 1) Alertas Guayaquil por X -- cada hora, lo mas barato y sensible al tiempo.
    if _paso_frecuencia("_alertas_x", FREQ_ALERTAS_X_H):
        costo_max = xapi.costo_estimado(10)
        ok, razon = (True, "") if simular_red else cabe("x", costo_max)
        if ok:
            tweets, costo = xapi.buscar_alertas_gye(terminos_alerta, barrios, max_items=10, simular=simular_red)
            if tweets is None and xapi.last_error:
                r["errores"].append("alertas_x: %s" % xapi.last_error)
            elif isinstance(tweets, list):
                nuevas = _registrar_alertas_x(tweets) if not simular_red else 0
                r["alertas_x"] = len(tweets)
                if not simular_red and costo > 0:
                    registrar_gasto("x", costo, "alertas_x")
                hubo_x = hubo_x or bool(tweets)
        else:
            r["saltadas_por_presupuesto"].append("alertas_x: %s" % razon)
        if not simular_red:
            _marcar_corrida("_alertas_x")

    # 2) Tweets por historia (X) -- 6 historias top, cada 12h. El llamador
    # (monitor.py) ya excluye boletines de plantilla de 'historias_top'.
    if _paso_frecuencia("_historias_x", FREQ_HISTORIAS_X_H):
        for h in historias_top[:6]:
            q = h.get("query") or h.get("titular", "")
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
    if _paso_frecuencia("_tiktok", FREQ_TIKTOK_H):
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
        capas_x = ("alertas_x", "historias_x", "debate_x")
        capas_tiktok = ("tiktok_videos", "tiktok_comentarios")
        if r["errores"] and any(e.split(":")[0] in capas_x for e in r["errores"]):
            marcar_resultado_red("x", False)
        elif hubo_x:
            marcar_resultado_red("x", True)
        if r["errores"] and any(e.split(":")[0] in capas_tiktok for e in r["errores"]):
            marcar_resultado_red("tiktok", False)
        elif hubo_tiktok:
            marcar_resultado_red("tiktok", True)

    estado = "ok (alertas_x:+%d, historias_x:+%d, debate_x:+%d, tiktok_videos:+%d, tiktok_comentarios:+%d)" % (
        r["alertas_x"], r["historias_x"], r["debate_x"], r["tiktok_videos"], r["tiktok_comentarios"])
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
        "gasto_mes_x": round(gasto_mes("x"), 5),
        "gasto_mes_tiktok": round(gasto_mes("tiktok"), 5),
        "restante_mes": round(presupuesto_restante_mes(), 5),
        "presupuesto_hoy": round(presupuesto_hoy_total(), 5),
        "tope_mes": TOPE_MES_USD,
        "reparto": reparto_hoy(),
        "dias_restantes_mes": _dias_restantes_mes(),
    }
