# -*- coding: utf-8 -*-
"""
estadisticas.py -- Fase 23 (B1): series que la seccion Estadisticas necesita y
que data.json no traia. Sin red ni IA: corre en el hilo rapido (write_outputs)
y solo LEE lo que Spike ya guarda.

Regla de Fernando para esta fase: "nada de datos de relleno". Por eso:
  - El calendario del mes cuenta las NOTAS que Spike vio publicadas cada dia
    (latencia_cache.json: link, medio, fecha de publicacion segun el feed y
    primera vez que Spike la vio). Ese registro guarda solo 7 dias, asi que
    los conteos de cada dia COMPLETO se acumulan en calendario_noticias.json
    para no perderlos. Un dia sin registro va como "sin registro" (None),
    nunca como 0.
  - La actividad por hora es el promedio por dia de las notas publicadas en
    cada hora (hora de Ecuador), con los dias completos del registro.
  - Las alertas por dia salen de alertas.json (primera deteccion).

Standalone: no importa monitor.py.
"""
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CALENDARIO_PATH = os.path.join(HERE, "calendario_noticias.json")
EC = dt.timezone(dt.timedelta(hours=-5))
DIAS_CALENDARIO = 62  # lo que se guarda (dos meses alcanza para el mes actual y el anterior)


def _parse(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def _dia_ec(d):
    return d.astimezone(EC).date()


def _cargar(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def _guardar(ruta, datos):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(tmp, ruta)


def _dias_completos(reg, ahora):
    """(primer dia completo, hoy): un dia D esta completo en el registro de
    latencia si Spike ya estaba registrando antes de que empezara (la primera
    'first_seen' guardada es anterior al comienzo de D). Hoy esta en curso."""
    vistos = [_parse(v.get("first_seen")) for v in (reg or {}).values()]
    vistos = [v for v in vistos if v]
    if not vistos:
        return None, _dia_ec(ahora)
    return _dia_ec(min(vistos)) + dt.timedelta(days=1), _dia_ec(ahora)


def _por_dia_y_hora(reg, ahora):
    desde, hoy = _dias_completos(reg, ahora)
    por_dia, por_hora, dias_hora = {}, [0] * 24, set()
    if desde is None:
        return desde, hoy, por_dia, por_hora, 0
    for v in (reg or {}).values():
        p = _parse(v.get("pub_date"))
        if not p or p > ahora + dt.timedelta(minutes=10):
            continue  # sin fecha o fecha en el futuro (zona horaria mal puesta por el medio)
        d = _dia_ec(p)
        if d < desde or d > hoy:
            continue
        k = d.isoformat()
        por_dia[k] = por_dia.get(k, 0) + 1
        if d < hoy:  # la hora del dia solo con dias completos
            por_hora[p.astimezone(EC).hour] += 1
            dias_hora.add(k)
    return desde, hoy, por_dia, por_hora, len(dias_hora)


def calendario_y_horas(reg, ahora=None, persistir=True, ruta=None):
    """{'calendario': {'dias': {fecha: n}, 'desde': fecha, 'hoy': fecha,
    'en_curso': fecha, 'fuente': texto}, 'por_hora': {'promedio': [24],
    'dias': n, 'fuente': texto}}."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    ruta = ruta or CALENDARIO_PATH
    desde, hoy, por_dia, por_hora, n_dias = _por_dia_y_hora(reg, ahora)
    guardado = _cargar(ruta, {})
    dias = dict(guardado.get("dias") or {})
    cambio = False
    for k, n in por_dia.items():
        if k == hoy.isoformat():
            continue  # hoy no se guarda: todavia no termino
        if n > dias.get(k, 0):
            dias[k] = n
            cambio = True
    corte = (hoy - dt.timedelta(days=DIAS_CALENDARIO)).isoformat()
    for k in [k for k in dias if k < corte]:
        del dias[k]
        cambio = True
    if persistir and cambio:
        try:
            _guardar(ruta, {"dias": dias, "actualizado": ahora.isoformat()})
        except Exception:
            pass
    salida = dict(dias)
    if hoy.isoformat() in por_dia:
        salida[hoy.isoformat()] = por_dia[hoy.isoformat()]
    primero = min(salida) if salida else None
    return {
        "calendario": {"dias": salida, "desde": primero, "hoy": hoy.isoformat(), "en_curso": hoy.isoformat(),
                       "fuente": "notas que Spike vio publicadas cada dia (fecha del propio feed de cada medio)"},
        "por_hora": {"promedio": [round(x / n_dias, 1) for x in por_hora] if n_dias else None,
                     "dias": n_dias,
                     "fuente": "promedio por dia de notas publicadas en cada hora (hora de Ecuador)"},
    }


def alertas_por_dia(ruta_alertas, ahora=None, dias=14, ventana_h=10.0):
    """{fecha: alertas detectadas por primera vez ese dia} + mismo tramo de ayer."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    reg = _cargar(ruta_alertas, {})
    items = reg.values() if isinstance(reg, dict) else (reg or [])
    hoy = _dia_ec(ahora)
    corte = hoy - dt.timedelta(days=dias)
    por_dia, hoy_n, ayer_mismo = {}, 0, 0
    inicio_hoy = dt.datetime.combine(hoy, dt.time(0), EC)
    inicio_ayer = inicio_hoy - dt.timedelta(days=1)
    for a in items:
        p = _parse((a or {}).get("primera_deteccion"))
        if not p:
            continue
        d = _dia_ec(p)
        if d < corte:
            continue
        por_dia[d.isoformat()] = por_dia.get(d.isoformat(), 0) + 1
        if p >= inicio_hoy:
            hoy_n += 1
        elif inicio_ayer <= p < inicio_ayer + (ahora - inicio_hoy):
            ayer_mismo += 1
    # Revision de Codex (Fase 23): el KPI muestra alertas ACTIVAS, asi que la
    # comparacion tiene que ser contra las activas de ayer a esta misma hora
    # (misma regla que alertas.listar_activas: alguna senal en las ultimas
    # ventana_h horas), reconstruida con las fechas de las senales guardadas.
    def activas_en(t):
        desde = t - dt.timedelta(hours=ventana_h)
        n = 0
        for a in items:
            fs = [_parse((s or {}).get("fecha")) for s in (a or {}).get("senales") or []]
            if any(f and desde <= f <= t for f in fs):
                n += 1
        return n
    return {"por_dia": por_dia, "hoy": hoy_n, "ayer_misma_hora": ayer_mismo,
            "activas_ahora": activas_en(ahora), "activas_ayer_misma_hora": activas_en(ahora - dt.timedelta(days=1)),
            "ventana_h": ventana_h, "registro_desde": min(por_dia) if por_dia else None}
