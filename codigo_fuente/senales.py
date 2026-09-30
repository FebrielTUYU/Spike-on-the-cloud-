# -*- coding: utf-8 -*-
"""
Fase 15 -- Motor de señales: une "qué es una oportunidad de reportaje" y "qué
merece avisarle a Fernando al celular" en UN SOLO lugar. Antes esas dos cosas
vivían separadas (Oportunidades calculaba brechas por TEMA abstracto;
movil.py detectaba "historia fuerte"/"pico"/"brecha" con su propio criterio) y
ninguna de las dos bajaba a "esta historia puntual, por esta razón concreta,
empezá por acá".

Por qué standalone (mismo criterio que oficial.py/declaraciones.py/alertas.py):
NUNCA importa monitor.py (evita import circular; monitor.py importa a este
módulo, no al revés). SÍ importa alertas.py (para el evento 6, "una alerta
cambia de estado") porque alertas.py ya resuelve ese problema bien (candado de
"nunca dos veces por el mismo escalón", nunca por debajo de "corroborado") --
reinventarlo en este módulo hubiera duplicado esa lógica ya probada.

Cinco tipos de señal (SOLO para historias de Guayaquil, ver `s["ciudad"]`) +
dos eventos (alertas, guardadas) -- ver TIPOS_SENAL. Cada señal es un dict:
  {"tipo", "historia_id" (story_key), "titulo", "por_que_ahora" (con el
   NUMERO real que la respalda), "primer_paso" (o None si no se pudo generar
   uno confiable), "certeza": {"nivel", "motivo"}, "clave_dedupe", "link",
   "ts" (ISO, cuándo se detectó)}.

Umbrales elegidos con datos REALES del registro de esta PC (no adivinados),
documentados en cada función -- ver también COORDINACION.md/CLAUDE.md Fase 15
para el detalle de cómo se midieron.
"""

import os
import re
import json
import unicodedata
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ESTADO_PATH = os.path.join(HERE, "senales_estado.json")

try:
    import alertas
except Exception:
    alertas = None

TIPOS_SENAL = ("acelera", "un_solo_medio", "brecha_historia", "sin_resolver",
               "actor_repetido", "alerta_estado", "guardada_actualizada")

# Prioridad ntfy por tipo (Paso 4: eventos 6/7 y "acelera" en prioridad alta,
# el resto normal) -- se usa desde monitor.py/movil.py, expuesto acá para que
# quien dispare el aviso no tenga que duplicar esta tabla.
PRIORIDAD_ALTA = {"acelera", "alerta_estado", "guardada_actualizada"}


# ------------------------- utilidades de texto (mismo patrón que alertas.py) -------------------------

def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s)


_STOP = set("de la el en los las del y a que por con para un una se su al es lo como mas tras "
            "sobre este esta estos estas fue son han sera desde hasta entre".split())


def _tokens(texto, minlen=4):
    return {w for w in _norm(texto).split() if len(w) >= minlen and w not in _STOP}


def _numeros(texto):
    return set(re.findall(r"\d+", texto or ""))


def story_key(h):
    """Misma fórmula que monitor.story_key()/storyKey() del dashboard --
    duplicada acá a propósito (standalone, sin importar monitor.py)."""
    f0 = (h.get("fuentes") or [{}])[0]
    return (f0.get("link") or h.get("titular") or "")[:180]


def _parse_iso(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def _es_guayaquil(s):
    return (s.get("ciudad") or "") == "Guayaquil"


# Fase 18 (P0-4): Fernando reporto "ya no identifica oportunidades en
# Ecuador" -- las senales solo miraban Guayaquil. Ahora cubren TODO Ecuador
# (historias locales: es_local o ciudad de Ecuador); Guayaquil va primero en
# el orden y cada senal dice su ambito.
def _es_ecuador(s):
    return bool(s.get("es_local")) or _es_guayaquil(s)


def _ambito(s):
    return "guayaquil" if _es_guayaquil(s) else "ecuador"


# ------------------------- estado propio (dedupe + últimos vistos) -------------------------

def _cargar_estado():
    try:
        with open(ESTADO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"vistas": {}, "guardadas_ultimo_n": {}}


def _guardar_estado(estado):
    tmp = ESTADO_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    os.replace(tmp, ESTADO_PATH)


# ------------------------- Tipo 1: Acelera -------------------------
# Umbral real (medido en esta PC, historias_registro.json, 156 historias
# locales/internacionales con 3+ fuentes): ritmo histórico de llegada de
# fuentes, mediana 0.301 fuentes/hora, p90 1.164/hora. Un caso real medido
# (7 fuentes en 1.1h = 6.6/hora) confirma que una ráfaga real se nota lejos
# de esos valores normales. Se compara la historia CONTRA SÍ MISMA (su propio
# ritmo antes de la última hora), no contra un promedio de tema aparte --
# más simple, y cada historia es su propio control real.
UMBRAL_FUENTES_ACELERA_MIN = 2   # minimo de fuentes NUEVAS en la ultima hora
FACTOR_ACELERA = 3.0             # esa ultima hora tiene que ser >=3x el ritmo previo


def detectar_acelera(stories, ahora=None):
    ahora = ahora or now_utc()
    out = []
    for s in stories:
        if not _es_ecuador(s):
            continue
        fuentes = s.get("fuentes") or []
        fechas = sorted(f for f in (_parse_iso(x.get("date")) for x in fuentes) if f)
        if len(fechas) < UMBRAL_FUENTES_ACELERA_MIN:
            continue
        recientes = [f for f in fechas if (ahora - f).total_seconds() <= 3600]
        n_recientes = len(recientes)
        if n_recientes < UMBRAL_FUENTES_ACELERA_MIN:
            continue
        viejas = [f for f in fechas if f not in recientes]
        if viejas:
            horas_previas = max((ahora - dt.timedelta(hours=1) - min(viejas)).total_seconds() / 3600, 0.1)
            ritmo_previo = len(viejas) / horas_previas
        else:
            # historia con menos de 1h de vida y ya con 2+ fuentes en esa
            # primera hora: no hay "antes" para comparar, pero llegar tan
            # rapido de entrada ya es la señal.
            ritmo_previo = 0.0
        umbral_ok = (ritmo_previo == 0.0) or (n_recientes >= FACTOR_ACELERA * ritmo_previo)
        if not umbral_ok:
            continue
        clave = "acelera:%s" % story_key(s)
        por_que = ("%d fuente(s) nueva(s) en la última hora" % n_recientes) + (
            ", contra un ritmo previo de ~%.2f/hora (misma historia)" % ritmo_previo
            if ritmo_previo > 0 else " -- la historia recién arranca y ya reúne varios medios de entrada")
        nivel = "alta" if n_recientes >= 4 else "media"
        out.append({
            "tipo": "acelera", "historia_id": story_key(s), "titulo": s.get("titular", ""),
            "por_que_ahora": por_que,
            "primer_paso": None,
            "certeza": {"nivel": nivel, "motivo": "ritmo medido contra el historial real de la misma historia"},
            "clave_dedupe": clave, "link": fuentes[0].get("link", "") if fuentes else "",
            "ts": ahora.isoformat(),
        })
    return out


# ------------------------- Tipo 2: Un solo medio -------------------------
# Umbral real (data.json en vivo, 39/85 historias Guayaquil con 1 solo
# medio): mediana de horas de vida 18.4h, p75 40.2h; mediana de interés
# 61.3, p75 71.9. Se usa la ventana 3-48h ("varias horas" pero antes de
# volverse candidata a "sin_resolver") e interés >=60 (cerca de la mediana
# real medida) como filtro de "relevante" -- sin esto, 39 historias
# calificarían de una sola vez, la mayoría trivial.
UMBRAL_HORAS_UN_SOLO_MEDIO_MIN = 3.0
UMBRAL_HORAS_UN_SOLO_MEDIO_MAX = 48.0
UMBRAL_INTERES_UN_SOLO_MEDIO = 60


def detectar_un_solo_medio(stories, ahora=None):
    ahora = ahora or now_utc()
    out = []
    for s in stories:
        if not _es_ecuador(s):
            continue
        n_outlets = s.get("n_outlets")
        if n_outlets is None:
            n_outlets = len(s.get("fuentes") or [])
        if n_outlets != 1:
            continue
        horas = s.get("hours")
        if horas is None:
            # sin el campo precalculado (ej. datos sinteticos/pruebas): se
            # deriva de la fecha real de la unica fuente, mismo dato de fondo.
            fecha_unica = _parse_iso((s.get("fuentes") or [{}])[0].get("date"))
            horas = (ahora - fecha_unica).total_seconds() / 3600 if fecha_unica else None
        if horas is None or not (UMBRAL_HORAS_UN_SOLO_MEDIO_MIN <= horas <= UMBRAL_HORAS_UN_SOLO_MEDIO_MAX):
            continue
        interes = s.get("interes") or 0
        if interes < UMBRAL_INTERES_UN_SOLO_MEDIO:
            continue
        fuentes = s.get("fuentes") or []
        medio = fuentes[0].get("outlet", "") if fuentes else ""
        clave = "un_solo_medio:%s" % story_key(s)
        por_que = ("Solo %s la cubre, hace %.0f horas (interés %.0f)." % (medio or "un medio", horas, interes))
        out.append({
            "tipo": "un_solo_medio", "historia_id": story_key(s), "titulo": s.get("titular", ""),
            "por_que_ahora": por_que,
            "primer_paso": None,
            "certeza": {"nivel": "media", "motivo": "una sola fuente, sin verificación cruzada todavía"},
            "clave_dedupe": clave, "link": fuentes[0].get("link", "") if fuentes else "",
            "ts": ahora.isoformat(),
        })
    return out


# ------------------------- Tipo 3: La gente lo busca y nadie lo cubre (por historia) -------------------------
# Baja la brecha de Trends (ya calibrada en movil.py: demanda>=25) a una
# HISTORIA concreta de Guayaquil, no al tema abstracto: si el tema de la
# historia tiene demanda alta y la historia en sí tiene poca cobertura
# (<=2 medios), la señal apunta a ESA historia como el ángulo concreto.
UMBRAL_DEMANDA_BRECHA = 25
UMBRAL_COBERTURA_BRECHA_MAX = 2


def detectar_brecha_historia(stories, demand, ahora=None):
    ahora = ahora or now_utc()
    demand = demand or {}
    out = []
    for s in stories:
        if not _es_ecuador(s):
            continue
        if (s.get("n_outlets") or 0) > UMBRAL_COBERTURA_BRECHA_MAX:
            continue
        temas = s.get("temas") or []
        mejor_tema, mejor_dem = None, -1
        for t in temas:
            d = demand.get(t)
            if d is not None and d > mejor_dem:
                mejor_tema, mejor_dem = t, d
        if mejor_tema is None or mejor_dem < UMBRAL_DEMANDA_BRECHA:
            continue
        fuentes = s.get("fuentes") or []
        clave = "brecha_historia:%s" % story_key(s)
        por_que = ("El tema \"%s\" tiene demanda de búsqueda %d/100 y esta historia solo tiene %d medio(s)."
                   % (mejor_tema, mejor_dem, s.get("n_outlets") or 0))
        out.append({
            "tipo": "brecha_historia", "historia_id": story_key(s), "titulo": s.get("titular", ""),
            "por_que_ahora": por_que,
            "primer_paso": None,
            "certeza": {"nivel": "media", "motivo": "demanda de búsqueda real, pero la relación con esta historia puntual (no solo el tema) es una inferencia"},
            "clave_dedupe": clave, "link": fuentes[0].get("link", "") if fuentes else "",
            "ts": ahora.isoformat(),
        })
    return out


# ------------------------- Tipo 4: Se apagó sin resolverse -------------------------
# Umbral real: mediana histórica de ritmo de fuentes es ~1 cada 3.3h (ver
# Acelera); 24h de silencio total es ~7x ese intervalo típico para una
# historia que en su momento tuvo cobertura real (3+ fuentes) -- un salto
# claro de "todavía activa" a "dejó de moverse". "Cobertura significativa"
# se fija en 3+ fuentes (más de la mitad de las historias de Guayaquil con
# 2+ medios en esta PC quedan en 2-3, ver Fase 8/9).
UMBRAL_FUENTES_SIN_RESOLVER_MIN = 3
UMBRAL_HORAS_SILENCIO = 24.0


def _validar_cita(cita, material_texto):
    if not cita:
        return False
    return _norm(cita) in _norm(material_texto or "")


def detectar_sin_resolver(registro_entries, ia_fn=None, ahora=None):
    """registro_entries: iterable de entradas del registro persistente (cada
    una con 'fuentes' [{'title','summary','link','date' ISO}], 'ciudad',
    'ultimo' ISO). ia_fn(material_texto) -> {'hubo_desenlace':bool,
    'cita':str|None} o None (fallo/no disponible). CANDADO EN CODIGO: sin
    ia_fn, o si la IA no da una cita real dentro del material, se asume que
    NO hubo desenlace (mejor avisar de más que perder un caso real)."""
    ahora = ahora or now_utc()
    out = []
    for e in registro_entries:
        # Fase 18: cualquier ciudad de Ecuador (el registro solo guarda
        # ciudades de Ecuador en 'ciudad'); antes solo Guayaquil.
        if not (e.get("ciudad") or ""):
            continue
        fuentes = e.get("fuentes") or []
        if len(fuentes) < UMBRAL_FUENTES_SIN_RESOLVER_MIN:
            continue
        ultimo = _parse_iso(e.get("ultimo")) or max(
            (f for f in (_parse_iso(x.get("date")) for x in fuentes) if f), default=None)
        if ultimo is None:
            continue
        horas_silencio = (ahora - ultimo).total_seconds() / 3600
        if horas_silencio < UMBRAL_HORAS_SILENCIO:
            continue
        material = "\n".join("- %s: %s" % (f.get("title", ""), (f.get("summary") or "")[:200])
                              for f in fuentes)
        hubo_desenlace = False
        if ia_fn is not None:
            r = ia_fn(material)
            if r and r.get("hubo_desenlace") and _validar_cita(r.get("cita"), material):
                hubo_desenlace = True
        if hubo_desenlace:
            continue
        rep = e.get("rep_titulo") or (fuentes[0].get("title") if fuentes else "")
        link = fuentes[0].get("link", "") if fuentes else ""
        clave = "sin_resolver:%s" % (link or rep)[:180]
        por_que = ("%d fuente(s) reales, pero sin ninguna nota nueva hace %.0f horas -- sin desenlace confirmado."
                   % (len(fuentes), horas_silencio))
        out.append({
            "tipo": "sin_resolver", "historia_id": (link or rep)[:180], "titulo": rep,
            "por_que_ahora": por_que,
            "primer_paso": None,
            "certeza": {"nivel": "media" if ia_fn is not None else "baja",
                        "motivo": "verificado con IA que no hay desenlace citable" if ia_fn is not None
                                  else "sin verificación de IA disponible, solo silencio de fuentes"},
            "clave_dedupe": clave, "link": link, "ts": ahora.isoformat(),
        })
    return out


# ------------------------- Tipo 5: Actor repetido -------------------------
UMBRAL_DIAS_ACTOR_REPETIDO = 7


def detectar_actor_repetido(entities_registro, stories_guayaquil, dias=UMBRAL_DIAS_ACTOR_REPETIDO, ahora=None):
    """entities_registro: dict crudo de entities.json. stories_guayaquil:
    stories (de cualquier ámbito -- se filtra internamente por ciudad==
    "Guayaquil" acá mismo, nunca se confía en que el llamador ya haya
    filtrado; mismo criterio de "candado en código" del resto del proyecto)."""
    ahora = ahora or now_utc()
    links_gye = {}
    for s in stories_guayaquil:
        if not _es_ecuador(s):
            continue
        for f in (s.get("fuentes") or []):
            if f.get("link"):
                links_gye[f["link"]] = s
    corte = ahora - dt.timedelta(days=dias)
    out = []
    for nombre_norm, apariciones in (entities_registro or {}).items():
        vistos_gye = {}  # link -> (nombre, fecha, titular)
        for ap in apariciones:
            fecha = _parse_iso(ap.get("fecha"))
            if fecha is None or fecha < corte:
                continue
            link = ap.get("link")
            if link in links_gye:
                vistos_gye[link] = ap
        if len(vistos_gye) < 2:
            continue
        nombre_real = apariciones[-1].get("nombre") or nombre_norm
        historias_txt = "; ".join(
            "\"%s\" (%s)" % (ap.get("titular", "")[:70], (ap.get("fecha") or "")[:10])
            for ap in list(vistos_gye.values())[:5])
        clave = "actor_repetido:%s" % nombre_norm
        # representa la señal con la aparición mas reciente como "historia" ancla
        ancla = max(vistos_gye.values(), key=lambda a: a.get("fecha") or "")
        out.append({
            "tipo": "actor_repetido", "historia_id": ancla.get("link", ""), "titulo": nombre_real,
            "por_que_ahora": ("Aparece en %d historias distintas de Guayaquil en los últimos %d días: %s"
                              % (len(vistos_gye), dias, historias_txt)),
            "primer_paso": None,
            "certeza": {"nivel": "alta", "motivo": "cada aparición cita su propia historia y fecha real"},
            "clave_dedupe": clave, "link": ancla.get("link", ""), "ts": ahora.isoformat(),
        })
    return out


# ------------------------- Eventos 6 y 7 -------------------------

def detectar_evento_alertas():
    """Reusa alertas.pendientes_de_aviso('corroborado') -- MISMA regla ya
    validada del proyecto (nunca por debajo de Corroborado, nunca dos veces
    por el mismo escalón). NO llama a alertas.marcar_avisada() acá: eso lo
    hace quien despache la notificación real (monitor.py), después de
    confirmar el envío -- mismo patrón que ya usaba procesar_alertas()."""
    if alertas is None:
        return []
    ahora = now_utc()
    out = []
    for a in alertas.pendientes_de_aviso("corroborado"):
        ultimo_texto = a["senales"][-1]["texto"] if a.get("senales") else ""
        clave = "alerta_estado:%s:%s" % (a.get("id"), a.get("estado"))
        out.append({
            "tipo": "alerta_estado", "historia_id": a.get("id", ""),
            "titulo": "%s en %s" % ((a.get("tipo") or "evento").replace("_", " ").title(),
                                     a.get("lugar") or "Guayaquil"),
            "por_que_ahora": "%s (estado: %s, %d señal(es))." % (
                ultimo_texto, a.get("estado", ""), len(a.get("senales") or [])),
            "primer_paso": None,
            "certeza": {"nivel": "alta", "motivo": "2+ fuentes independientes o fuente oficial, ver alertas.py"},
            "clave_dedupe": clave, "link": a.get("historia_link", ""), "ts": ahora.isoformat(),
            "_alerta_id": a.get("id"),  # para que monitor.py pueda marcar_avisada() tras el envío real
        })
    return out


def detectar_evento_guardadas(saved_items, registro_by_link, estado):
    """saved_items: lista de historias guardadas (saved.json, shape completo
    de historia). registro_by_link: dict {link: entrada_del_registro} para
    cruzar cuántas fuentes tiene AHORA esa historia. estado: dict persistente
    (mismo que _cargar_estado()) -- se lee/actualiza 'guardadas_ultimo_n'."""
    ahora = now_utc()
    ultimos = estado.setdefault("guardadas_ultimo_n", {})
    out = []
    for h in saved_items:
        key = story_key(h)
        n_guardado = len(h.get("fuentes") or [])
        entrada = None
        for f in (h.get("fuentes") or []):
            if f.get("link") in registro_by_link:
                entrada = registro_by_link[f["link"]]
                break
        n_actual = len(entrada.get("fuentes") or []) if entrada else n_guardado
        n_visto = ultimos.get(key, n_guardado)
        if n_actual > n_visto:
            clave = "guardada_actualizada:%s:%d" % (key, n_actual)
            out.append({
                "tipo": "guardada_actualizada", "historia_id": key, "titulo": h.get("titular", ""),
                "por_que_ahora": "Sumó %d fuente(s) nueva(s) desde que la guardaste (ahora %d en total)."
                                 % (n_actual - n_visto, n_actual),
                "primer_paso": None,
                "certeza": {"nivel": "alta", "motivo": "conteo real de fuentes en el registro"},
                "clave_dedupe": clave, "link": (h.get("fuentes") or [{}])[0].get("link", ""),
                "ts": ahora.isoformat(),
            })
        ultimos[key] = n_actual
    return out


# ------------------------- primer_paso (con IA, validado en código) -------------------------

def generar_primer_paso(senal, material_texto, ia_fn):
    """ia_fn(prompt) -> texto libre o None. Candado en código: el texto que
    vuelve tiene que compartir 2+ palabras significativas (o una cifra) con
    el material real -- si no, se descarta (mejor sin primer_paso que uno
    inventado sin base)."""
    if ia_fn is None:
        return None
    prompt = (
        "Sos un editor de noticias en Guayaquil, Ecuador. Te doy una señal detectada sobre una "
        "historia y el material real disponible. Proponé el PRIMER PASO concreto: una pregunta "
        "puntual para hacer, o la persona/institución por donde empezar a verificar -- una sola "
        "frase corta, accionable, citando algo del material real (un nombre, un lugar, un dato). "
        "No inventes datos que el material no tenga.\n\n"
        "SEÑAL: %s\nPOR QUE AHORA: %s\n\nMATERIAL:\n%s\n\nRespondé SOLO la frase del primer paso."
        % (senal.get("tipo", ""), senal.get("por_que_ahora", ""), material_texto[:1500])
    )
    texto = ia_fn(prompt)
    if not texto or not str(texto).strip():
        return None
    texto = str(texto).strip()
    t_material = _tokens(material_texto)
    t_texto = _tokens(texto)
    comparten_palabras = len(t_material & t_texto) >= 2
    comparten_numero = bool(_numeros(texto) & _numeros(material_texto))
    if not (comparten_palabras or comparten_numero):
        return None
    return texto[:400]


# ------------------------- deduplicación -------------------------

def _cambio_significativo(antes, ahora_txt):
    """Compara los NUMEROS que aparecen en 'por_que_ahora' -- determinista,
    sin IA. Un cambio de +50% o más en cualquier numero (o un numero nuevo
    que antes no estaba) cuenta como significativo."""
    if antes == ahora_txt:
        return False
    nums_antes = [int(n) for n in re.findall(r"\d+", antes or "")]
    nums_ahora = [int(n) for n in re.findall(r"\d+", ahora_txt or "")]
    if not nums_antes or not nums_ahora:
        return antes != ahora_txt
    max_antes, max_ahora = max(nums_antes), max(nums_ahora)
    if max_antes == 0:
        return max_ahora > 0
    return abs(max_ahora - max_antes) / max_antes >= 0.5


def deduplicar(candidatas, vistas):
    """vistas: dict PLANO {clave_dedupe: por_que_ahora_de_la_ultima_vez_que_se_vio}
    -- se mantiene simple a propósito (es lo que se persiste en
    senales_estado.json bajo la clave "vistas"). Devuelve solo las
    candidatas NUEVAS o que cambiaron de forma significativa, y actualiza
    'vistas' EN MEMORIA (quien llama decide cuándo persistirlo)."""
    nuevas = []
    for c in candidatas:
        clave = c["clave_dedupe"]
        prev = vistas.get(clave)
        if prev is None or _cambio_significativo(prev, c["por_que_ahora"]):
            nuevas.append(c)
        vistas[clave] = c["por_que_ahora"]
    return nuevas


# ------------------------- resumen (Paso 4: 3 veces al día) -------------------------

def agrupar_para_resumen(senales_periodo):
    """Agrupa una lista de señales (dicts, ya con 'tipo') por tipo, para el
    resumen de texto de 3 veces al día. Devuelve {tipo: [señales]}."""
    out = {}
    for s in senales_periodo:
        out.setdefault(s["tipo"], []).append(s)
    return out


ETIQUETA_TIPO = {
    "acelera": "Acelerando",
    "un_solo_medio": "Un solo medio",
    "brecha_historia": "La gente lo busca y nadie lo cubre",
    "sin_resolver": "Se apagó sin resolverse",
    "actor_repetido": "Actor repetido",
    "alerta_estado": "Alerta temprana",
    "guardada_actualizada": "Guardada con novedades",
}


def texto_resumen(agrupadas):
    """Arma el texto plano del resumen de 3x/día a partir de
    agrupar_para_resumen()."""
    if not agrupadas:
        return "Sin señales nuevas en este período."
    bloques = []
    for tipo, items in agrupadas.items():
        etiqueta = ETIQUETA_TIPO.get(tipo, tipo)
        lineas = "\n".join("  • %s — %s" % (it["titulo"][:70], it["por_que_ahora"][:100]) for it in items[:8])
        extra = "" if len(items) <= 8 else "\n  (+%d más)" % (len(items) - 8)
        bloques.append("%s (%d):\n%s%s" % (etiqueta, len(items), lineas, extra))
    return "\n\n".join(bloques)


# ------------------------- ciclo completo (Fase 18, P0-4) -------------------------
# La Fase 15 dejo los detectores escritos y probados, pero NADIE los llamaba:
# monitor.py nunca importaba este modulo, no existia senales_estado.json y
# Oportunidades nunca mostro una senal. ciclo_senales() junta todo en una
# vuelta: corre los detectores, ordena (Guayaquil primero), conserva el
# primer_paso ya calculado de vueltas anteriores y persiste las ACTIVAS en
# senales_estado.json -- de ahi las lee el hilo rapido para data.json sin
# volver a calcular nada.

_ORDEN_TIPO = {t: i for i, t in enumerate(("alerta_estado", "acelera", "guardada_actualizada",
                                           "brecha_historia", "un_solo_medio", "sin_resolver",
                                           "actor_repetido"))}
_ORDEN_NIVEL = {"alta": 0, "media": 1, "baja": 2}
MAX_ACTIVAS = 40
# Cupo por ambito: sin esto, en la primera prueba con datos reales las 40
# plazas se llenaron SOLO con Guayaquil y el resto de Ecuador no aparecia
# (justo lo que Fernando reporto).
CUPO_GUAYAQUIL = 25
CUPO_ECUADOR = 15
# Boletines de servicio/agenda: no son una oportunidad de reportaje por si
# solos (caso real: "Clima hoy en Guayaquil" y "fechas de los shows" salian
# como "la gente lo busca y nadie lo cubre").
_RX_NO_SENAL = re.compile(r"\b(clima|pronostico|tendra lluvias|fechas y precios|fechas de los shows|"
                          r"horarios?|cartelera|lotto|loteria|feriado)\b")


def _es_boletin(titulo):
    return bool(_RX_NO_SENAL.search(_norm(titulo)))


def _clave_material(texto):
    import hashlib
    return hashlib.sha1((texto or "").encode("utf-8", "ignore")).hexdigest()[:16]


def ciclo_senales(stories, demand=None, registro_entries=None, entities=None, saved=None,
                  registro_by_link=None, ia_desenlace=None, ia_texto=None, max_ia=5,
                  estado_path=None, ahora=None):
    """Una vuelta del motor de senales. Todas las fuentes son de SOLO
    LECTURA (lo que el pipeline ya calculo); la IA es opcional y acotada a
    'max_ia' llamadas nuevas por vuelta (desenlace + primer_paso), con cache
    en el propio estado para no volver a pagar por lo mismo. Devuelve
    {"senales": activas, "nuevas": [...], "estado": texto}."""
    ruta = estado_path or ESTADO_PATH
    ahora = ahora or now_utc()
    try:
        with open(ruta, encoding="utf-8") as f:
            estado = json.load(f)
    except Exception:
        estado = {}
    estado.setdefault("vistas", {})
    estado.setdefault("guardadas_ultimo_n", {})
    cache_desenlace = estado.setdefault("desenlace", {})
    # Dos presupuestos separados: en la primera prueba real, la verificacion
    # de desenlace (sin_resolver) se comia todas las llamadas y ninguna senal
    # recibia primer_paso.
    presupuesto = {"n": max_ia}
    presupuesto_paso = {"n": max_ia}

    def _desenlace(material):
        k = _clave_material(material)
        if k in cache_desenlace:
            return cache_desenlace[k]
        if ia_desenlace is None or presupuesto["n"] <= 0:
            return None
        presupuesto["n"] -= 1
        r = ia_desenlace(material)
        if r is not None:
            cache_desenlace[k] = r
        return r

    por_id = {story_key(s): s for s in stories or []}
    candidatas = []
    candidatas += detectar_acelera(stories or [], ahora=ahora)
    candidatas += detectar_un_solo_medio(stories or [], ahora=ahora)
    candidatas += detectar_brecha_historia(stories or [], demand or {}, ahora=ahora)
    if registro_entries:
        candidatas += detectar_sin_resolver(registro_entries, ia_fn=_desenlace if ia_desenlace else None,
                                            ahora=ahora)
    if entities:
        candidatas += detectar_actor_repetido(entities, stories or [], ahora=ahora)
    candidatas += detectar_evento_alertas()
    if saved:
        candidatas += detectar_evento_guardadas(saved, registro_by_link or {}, estado)

    for c in candidatas:
        s = por_id.get(c.get("historia_id"))
        if s is not None:
            c["ambito"] = _ambito(s)
        elif c["tipo"] == "alerta_estado":
            c["ambito"] = "guayaquil"
        else:
            ciudad = next((e.get("ciudad") for e in (registro_entries or [])
                           if (e.get("fuentes") or [{}])[0].get("link") == c.get("historia_id")), "")
            c["ambito"] = "guayaquil" if ciudad == "Guayaquil" else "ecuador"
        c["prioridad"] = "alta" if c["tipo"] in PRIORIDAD_ALTA else "normal"

    candidatas = [c for c in candidatas if c["tipo"] in ("alerta_estado", "actor_repetido")
                  or not _es_boletin(c.get("titulo", ""))]
    candidatas.sort(key=lambda c: (0 if c.get("ambito") == "guayaquil" else 1,
                                   _ORDEN_TIPO.get(c["tipo"], 9),
                                   _ORDEN_NIVEL.get((c.get("certeza") or {}).get("nivel"), 3),
                                   -((por_id.get(c.get("historia_id")) or {}).get("interes") or 0)))
    gye = [c for c in candidatas if c.get("ambito") == "guayaquil"][:CUPO_GUAYAQUIL]
    ecu = [c for c in candidatas if c.get("ambito") != "guayaquil"][:CUPO_ECUADOR]
    candidatas = (gye + ecu)[:MAX_ACTIVAS]

    # primer_paso: se conserva el de la vuelta anterior (misma clave); los
    # que faltan se piden a la IA mientras quede presupuesto.
    previas = {c.get("clave_dedupe"): c for c in estado.get("activas", [])}
    for c in candidatas:
        prev = previas.get(c["clave_dedupe"])
        if prev and prev.get("primer_paso"):
            c["primer_paso"] = prev["primer_paso"]
            c["ts"] = prev.get("ts", c["ts"])
        elif ia_texto is not None and presupuesto_paso["n"] > 0:
            s = por_id.get(c.get("historia_id")) or {}
            material = "\n".join([c.get("titulo", ""), s.get("resumen", "") or ""] +
                                 ["- %s (%s)" % (f.get("title", ""), f.get("outlet", ""))
                                  for f in (s.get("fuentes") or [])[:6]])
            presupuesto_paso["n"] -= 1
            c["primer_paso"] = generar_primer_paso(c, material, ia_texto)

    nuevas = deduplicar(candidatas, estado["vistas"])
    # 'vistas' no crece sin limite: se queda con las claves activas + las 500 mas recientes
    if len(estado["vistas"]) > 800:
        activas_k = {c["clave_dedupe"] for c in candidatas}
        resto = [k for k in estado["vistas"] if k not in activas_k][-500:]
        estado["vistas"] = {k: estado["vistas"][k] for k in list(activas_k) + resto if k in estado["vistas"]}
    if len(cache_desenlace) > 500:
        estado["desenlace"] = dict(list(cache_desenlace.items())[-500:])
    estado["activas"] = candidatas
    estado["ultima_vuelta"] = ahora.isoformat()
    estado["nuevas_ultima_vuelta"] = len(nuevas)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    os.replace(tmp, ruta)
    texto = "%d activas (%d nuevas; Guayaquil %d, resto de Ecuador %d)" % (
        len(candidatas), len(nuevas), sum(1 for c in candidatas if c.get("ambito") == "guayaquil"),
        sum(1 for c in candidatas if c.get("ambito") != "guayaquil"))
    return {"senales": candidatas, "nuevas": nuevas, "estado": texto}


def activas(estado_path=None):
    """Senales activas de la ultima vuelta (solo lectura, para data.json)."""
    try:
        with open(estado_path or ESTADO_PATH, encoding="utf-8") as f:
            return json.load(f).get("activas", [])
    except Exception:
        return []


def ultima_vuelta(estado_path=None):
    try:
        with open(estado_path or ESTADO_PATH, encoding="utf-8") as f:
            return json.load(f).get("ultima_vuelta")
    except Exception:
        return None
