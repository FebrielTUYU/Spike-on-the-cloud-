# -*- coding: utf-8 -*-
"""
comunidad.py -- Fase 20: la lente "Comunidad" de Guayaquil.

Pedido de Fernando (2026-09-30): "que Spike ayude a identificar temas
comunitarios de Guayaquil para realizar noticias o reportajes: problemas de
barrio, eventos que se den dentro de la ciudad, historias humanas... un
escaneo de las personas en Guayaquil donde se identifique y se pueda
encontrar un tema para explotar".

Que hace (determinista, SIN IA ni red -- corre en el hilo rapido, gratis):
  1. detectar(historia): ¿es de Guayaquil (o su area: Samborondon, Duran,
     Daule)? ¿que clase de tema es? -> problema de barrio (agua, luz,
     inundacion, basura, inseguridad, vias...), evento de la ciudad o
     historia humana; y ¿en que barrio/sector/cooperativa?
  2. actualizar(historias): guarda cada deteccion en comunidad.json (un
     registro que NO caduca con el feed: 90 dias) y arma los TEMAS: un
     problema de barrio se acumula por (barrio, tipo) a lo largo de los dias
     -- una queja que vuelve a aparecer tres semanas seguidas en el mismo
     sector es un reportaje; una nota suelta no. Eventos e historias humanas
     son temas de una sola nota.
  3. Cada tema trae "por_que" (hechos medidos: cuantos dias, que medios,
     si alguien le dio seguimiento, alertas de la gente en el mismo sector)
     y "pistas" (preguntas genericas de reporteo, etiquetadas como tales en
     el dashboard: NO son datos).

Limite honesto: solo ve lo que ya publico un medio o una fuente que Spike lee
(feeds, busquedas de Google News por barrio, alertas de redes). La
conversacion barrial de Facebook/WhatsApp no llega aca.

Standalone: no importa monitor.py (mismo criterio que alertas.py/oficial.py).
"""
import datetime as dt
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
COMUNIDAD_PATH = os.path.join(HERE, "comunidad.json")

RETENCION_DIAS = int(os.environ.get("MONITOR_COMUNIDAD_DIAS", "90"))
# Un problema cuya ultima aparicion tiene mas de esto ya no se propone como tema.
VIGENCIA_DIAS = int(os.environ.get("MONITOR_COMUNIDAD_VIGENCIA", "30"))
MAX_TEMAS = 80


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def _patron(termino):
    """'inund*' = prefijo (inundacion, inundadas...); sin '*' = palabra/frase exacta."""
    t = _norm(termino.rstrip("*")).strip()
    if termino.endswith("*"):
        return re.compile(r"\b" + re.escape(t))
    return re.compile(r"\b" + re.escape(t) + r"\b")


def _compilar(d):
    return {k: [_patron(t) for t in v] for k, v in d.items()}


def _hay(patrones, blob):
    return any(p.search(blob) for p in patrones)


# ---------------------------------------------------------------- categorias
# Orden = prioridad: la primera que coincide gana (ej. "crimen frente a una
# escuela" es inseguridad, no educacion; "acumulacion de agua" es inundacion,
# no falta de agua).
PROBLEMAS = {
    "inundacion": ["inund*", "anegad*", "acumulacion de agua", "desborde*", "canales", "alcantarill*",
                   "drenaje*", "aguas servidas", "marea alta", "aguaje*", "lluvia", "lluvias", "aguacero*",
                   "el nino", "albergues", "alojamientos temporales", "milimetros"],
    "agua": ["sin agua", "no tendran agua", "no tienen agua", "no llega el agua", "falta de agua",
             "corte de agua", "cortes de agua", "agua potable", "interagua", "tuberia*", "acueducto",
             "desabastecimiento", "tanquero*", "servicio de agua"],
    "luz": ["sin luz", "corte de luz", "cortes de luz", "apagon*", "cnel", "alumbrado", "sin energia",
            "racionamiento*"],
    "basura": ["basura", "desechos", "recoleccion", "botadero*", "escombros", "mala disposicion"],
    "incendios": ["incendio*", "incendian"],
    "inseguridad": ["asesin*", "balacera*", "balean", "baleada", "baleado", "sicari*", "extorsion*",
                    "cobro de vacunas", "vacunadores", "robo", "robos", "asalt*", "atraco*", "secuestr*",
                    "bandas", "crimen", "violen*", "sacapintas", "microtrafico", "disparos", "zona roja",
                    "vigilancia", "municiones", "armas", "emboscada", "hallado muerto", "decomis*", "alias"],
    "vias": ["bache*", "socavon*", "hueco*", "asfalt*", "reconstru*", "mal estado", "obra inconclusa",
             "obra abandonada", "obras paralizadas", "paso a desnivel", "pavimentacion", "arbol caido",
             "arboles caidos", "calzada", "parque lineal", "construccion"],
    "transporte": ["metrovia", "bus", "buses", "busetas", "transporte urbano", "taxi*", "taxirruta*", "atm",
                   "transito", "semaforo*", "pasaje*", "terminal", "accidente de transito"],
    "salud": ["hospital*", "centro de salud", "subcentro*", "insumos", "medicinas", "medicamentos",
              "dengue", "pacientes", "dispensario*"],
    "educacion": ["escuela*", "colegio*", "unidad educativa", "aulas", "docentes", "educacion inclusiva"],
    "vivienda": ["invasion*", "desalojo*", "legalizacion", "titulos de propiedad", "damnificad*",
                 "casas patrimoniales", "riesgo de colapso", "vulnerabilidad"],
    "espacio_publico": ["comerciantes informales", "vendedores informales", "obstaculo*", "parque abandonado",
                        "parques abandonados", "espacio publico afectado", "aceras"],
    "ambiente": ["contaminacion", "ruido", "malos olores", "estero salado", "manglar*", "tala",
                 "arboles", "palmeras", "zonas verdes"],
}
EVENTOS = {
    "cultura": ["festival*", "concierto*", "teatro", "gala", "exposicion*", "cartelera", "espectaculo*",
                "poesia", "pasillo", "encuentro cultural", "banda municipal"],
    "deporte": ["maraton*", "42k", "21k", "10k", "carrera atletica", "torneo*", "intercolegial",
                "copa nacional"],
    "fiestas": ["fiestas", "desfile*", "procesion*", "bendicion", "fiestas octubrinas", "independencia de guayaquil"],
    "ferias": ["feria*", "gastronom*", "fest", "summit", "expo", "emprende y vende", "dia mundial"],
}
HUMANA = ["historia de", "su historia", "sueno", "suenos", "superacion", "lucha por", "no se rinde",
          "aprendieron", "aprendio", "ensenan", "emprendedor*", "voluntari*", "vecinos se organizan",
          "se organizan", "minga*", "olla comun", "comedor comunitario", "adulto mayor", "abuelit*",
          "testimonio", "historia de vida", "conmovedor*", "emprendimiento*"]

# Boletines y medidas de alcance nacional: no son temas comunitarios.
EXCLUIR = ["clima hoy", "pronostico del tiempo", "pronostico del clima", "tendra lluvias",
           "temperaturas de hasta", "radiacion uv", "toque de queda", "a que hora", "es feriado",
           "feriado", "iva", "simulacro", "nueva ley", "ley de", "asamblea nacional", "encuesta*",
           "encuestadora", "extradicion", "estas son las provincias", "provincias de ecuador"]

_P_PROB = _compilar(PROBLEMAS)
_P_EVT = _compilar(EVENTOS)
_P_HUM = [_patron(t) for t in HUMANA]
_P_EXCL = [_patron(t) for t in EXCLUIR]
_HUMANA_INICIO = re.compile(r"^\s*[\"“‘'«]")
_HUMANA_PERSONA = re.compile(r"^(el|la|los|las) [a-z]+ que ")

ETIQUETAS = {
    "problema": "Problema del barrio", "evento": "Evento en la ciudad", "humana": "Historia humana",
    "inundacion": "Lluvias, inundaciones y drenaje", "agua": "Agua potable", "luz": "Luz y alumbrado",
    "basura": "Basura", "incendios": "Incendios", "inseguridad": "Inseguridad",
    "vias": "Calles y obras", "transporte": "Transporte y transito", "salud": "Salud",
    "educacion": "Educacion", "vivienda": "Vivienda y terrenos", "espacio_publico": "Espacio publico",
    "ambiente": "Ambiente", "cultura": "Cultura", "deporte": "Deporte", "fiestas": "Fiestas y tradicion",
    "ferias": "Ferias y encuentros", "persona": "Historia de vida",
}

PISTAS = {
    "inundacion": ["¿Es la primera vez que se inunda este sector o pasa cada invierno?",
                   "¿Que obra de drenaje prometio el Municipio para la zona y en que estado esta?",
                   "¿Cuantas familias pierden algo cada vez que llueve?"],
    "agua": ["¿Desde cuando falla el servicio y cada cuanto se repite?",
             "¿Que explica Interagua/el Municipio y que dicen los moradores?",
             "¿Cuanto gastan las familias en tanqueros o botellones mientras tanto?"],
    "luz": ["¿Cuantas horas pasan sin servicio y con que frecuencia?",
            "¿Que dice CNEL sobre el sector y hay reclamos formales presentados?"],
    "basura": ["¿El carro recolector pasa? ¿Cada cuanto?",
               "¿Hay un botadero informal que crece? ¿Quien deberia limpiarlo?"],
    "incendios": ["¿Hay hidrantes y acceso para los bomberos en el sector?",
                  "¿Las conexiones electricas informales tienen que ver?"],
    "inseguridad": ["¿Como cambio la vida diaria del barrio (horarios, negocios cerrados, vacunas)?",
                    "¿Que presencia policial real hay y que dicen los moradores de ella?",
                    "¿Hay organizaciones barriales o iglesias trabajando en prevencion?"],
    "vias": ["¿Cuanto tiempo lleva la calle o la obra asi y cuanto costaba segun el contrato?",
             "¿Que contratista la tiene y que dice el Municipio del retraso?"],
    "transporte": ["¿Cuanto tardan los moradores en llegar al trabajo o a clases?",
                   "¿Que rutas dejaron de pasar y por que?"],
    "salud": ["¿Que falta exactamente (medicinas, medicos, turnos) y desde cuando?",
              "¿A donde tienen que ir los pacientes cuando no los atienden?"],
    "educacion": ["¿En que condiciones estan las aulas y que piden los padres?",
                  "¿Cuantos estudiantes se ven afectados?"],
    "vivienda": ["¿Cuantas familias estan en riesgo y desde cuando viven ahi?",
                 "¿En que va el tramite de legalizacion o reubicacion?"],
    "espacio_publico": ["¿Quien usa ese espacio y que conflicto hay entre los vecinos?"],
    "ambiente": ["¿Desde cuando ocurre y quien es responsable de controlarlo?"],
    "evento": ["¿Quien organiza y quien esta detras (una historia de barrio, un artista local)?",
               "¿Hay un angulo menos visible: los vendedores, los vecinos, los voluntarios?"],
    "humana": ["¿Hay otras personas en el barrio con una historia parecida?",
               "¿Que dice su historia del barrio o de un problema mas grande?"],
}

# Tipos de alerta de la gente (alertas.py) -> subtipo de problema.
ALERTA_A_SUBTIPO = {"inundacion": "inundacion", "corte_agua": "agua", "corte_luz": "luz",
                    "balacera": "inseguridad", "incendio": "incendios", "accidente": "transporte"}

# ---------------------------------------------------------------- lugares
# Base: los sectores reales de alertas.py (misma lista, no se duplica); se
# suman aca los que faltaban para cubrir la ciudad por zonas.
try:
    import alertas as _alertas
    _BARRIOS_BASE = dict(_alertas.BARRIOS_GYE)
except Exception:  # pragma: no cover
    _BARRIOS_BASE = {}
_BARRIOS_EXTRA = {
    "Socio Vivienda": ["socio vivienda"], "Cristo del Consuelo": ["cristo del consuelo"],
    "Cerro Santa Ana": ["cerro santa ana"], "Letamendi": ["letamendi"], "Chongon": ["chongon"],
    "Puerto Hondo": ["puerto hondo"], "Posorja": ["posorja"], "Tenguel": ["tenguel"],
    "La Floresta": ["la floresta"], "Los Esteros": ["los esteros"], "Guayacanes": ["guayacanes"],
    "Los Vergeles": ["los vergeles"], "Las Orquideas": ["las orquideas"],
    "Nueva Prosperina": ["nueva prosperina"], "Parque Forestal": ["parque forestal"],
    "Daule": ["daule"], "Mercado Este": ["mercado este"],
}
BARRIOS = dict(_BARRIOS_BASE)
BARRIOS.update(_BARRIOS_EXTRA)
_P_BARRIOS = [(b, [_patron(t) for t in ts]) for b, ts in BARRIOS.items()]
# Barrios mas especificos primero ("Nueva Prosperina" antes que "Prosperina",
# "Flor de Bastion" antes que "Bastion Popular").
_P_BARRIOS.sort(key=lambda x: -max(len(p.pattern) for p in x[1]))
SECTORES = [("Norte de Guayaquil", ["norte de guayaquil", "al norte de la ciudad"]),
            ("Sur de Guayaquil", ["sur de guayaquil", "al sur de la ciudad"]),
            ("Noroeste de Guayaquil", ["noroeste de guayaquil", "noroeste de la ciudad"]),
            ("Centro", ["centro de guayaquil", "centro de la ciudad"]),
            ("Parroquias rurales", ["parroquias rurales"])]
_P_SECTORES = [(s, [_patron(t) for t in ts]) for s, ts in SECTORES]
_P_GYE = _patron("guayaquil")
SIN_SECTOR = "Guayaquil (sin sector)"
_COOP = re.compile(r"\b[Cc]ooperativa\s+((?:[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ]*)(?:\s+(?:de\s+|del\s+)?"
                   r"[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ]*){0,3})")


def detectar_barrio(texto):
    m = _COOP.search(texto or "")
    if m:
        return "Coop. " + m.group(1).strip()
    blob = _norm(texto)
    for b, ps in _P_BARRIOS:
        if _hay(ps, blob):
            return b
    for s, ps in _P_SECTORES:
        if _hay(ps, blob):
            return s
    return None


# ---------------------------------------------------------------- detectar
def _clave(h):
    f0 = (h.get("fuentes") or [{}])[0]
    return (f0.get("link") or h.get("titular") or "")[:180]


def detectar(h):
    """None si la historia no es un tema comunitario de Guayaquil."""
    titular = h.get("titular") or ""
    texto = titular + " " + (h.get("resumen") or "")
    blob_t = _norm(titular)
    blob = _norm(texto)
    barrio = detectar_barrio(texto)
    ciudad = h.get("ciudad") or ""
    es_gye = ciudad == "Guayaquil" or barrio is not None or (not ciudad and _P_GYE.search(blob))
    if not es_gye:
        return None
    if _hay(_P_EXCL, blob_t):
        return None
    cat = sub = None
    for s, ps in _P_PROB.items():
        if _hay(ps, blob_t):
            cat, sub = "problema", s
            break
    if cat is None and (_HUMANA_INICIO.search(titular) or _HUMANA_PERSONA.search(blob_t)):
        cat, sub = "humana", "persona"
    if cat is None:
        for s, ps in _P_EVT.items():
            if _hay(ps, blob_t):
                cat, sub = "evento", s
                break
    if cat is None and _hay(_P_HUM, blob_t):
        cat, sub = "humana", "persona"
    if cat is None:
        # ultimo intento con el resumen (el titular a veces no dice el tipo)
        for s, ps in _P_PROB.items():
            if _hay(ps, blob):
                cat, sub = "problema", s
                break
    if cat is None:
        return None
    return {"categoria": cat, "subtipo": sub, "barrio": barrio or SIN_SECTOR}


# ---------------------------------------------------------------- registro
def _parse(s):
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def _fecha_historia(h):
    fechas = [_parse(f.get("date")) for f in (h.get("fuentes") or [])]
    fechas = [f for f in fechas if f]
    if fechas:
        return min(fechas)
    return _parse(h.get("creado")) or _parse(h.get("newest"))


def _cargar():
    try:
        with open(COMUNIDAD_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("items"), dict):
            return d
    except Exception:
        pass
    return {"version": 1, "items": {}}


def _guardar(d):
    tmp = COMUNIDAD_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, COMUNIDAD_PATH)


_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_EC = dt.timezone(dt.timedelta(hours=-5))


def _dia_ec(d):
    return d.astimezone(_EC).date()


def _fmt_dia(d):
    d = d.astimezone(_EC)
    return "%d %s" % (d.day, _MESES[d.month - 1])


def _hace(d, ahora):
    h = (ahora - d).total_seconds() / 3600
    if h < 1:
        return "hace menos de 1 h"
    if h < 48:
        return "hace %d h" % h
    return "hace %d dias" % (h // 24)


# ---------------------------------------------------------------- temas
def _armar_temas(items, alertas, ahora):
    grupos = {}
    for k, it in items.items():
        if it["categoria"] == "problema":
            tid = "p|%s|%s" % (it["barrio"], it["subtipo"])
        else:
            tid = "i|" + k
        grupos.setdefault(tid, []).append(it)

    temas = []
    for tid, its in grupos.items():
        its.sort(key=lambda x: x["fecha"], reverse=True)
        fechas = [_parse(x["fecha"]) for x in its]
        ultima, primera = fechas[0], fechas[-1]
        edad_d = (ahora - ultima).total_seconds() / 86400
        cat, sub, barrio = its[0]["categoria"], its[0]["subtipo"], its[0]["barrio"]
        if cat == "problema" and edad_d > VIGENCIA_DIAS:
            continue
        if cat != "problema" and edad_d > 14:
            continue
        dias = len({_dia_ec(f) for f in fechas})
        medios = []
        for x in its:
            for o in x["outlets"]:
                if o not in medios:
                    medios.append(o)
        max_out = max(x["n_outlets"] for x in its)
        n_alertas = 0
        if cat == "problema":
            for a in alertas or []:
                if ALERTA_A_SUBTIPO.get(a.get("tipo")) != sub or a.get("lugar") != barrio:
                    continue
                fa = _parse(a.get("primera_deteccion"))
                if fa and (ahora - fa).total_seconds() <= VIGENCIA_DIAS * 86400:
                    n_alertas += 1
        recencia = max(0.0, 1.0 - edad_d / VIGENCIA_DIAS)
        poca_cobertura = max_out <= 1
        if cat == "problema":
            score = (10 * min(dias, 10) + 3 * min(len(its), 15) + 15 * recencia + 8 * min(n_alertas, 5)
                     + (6 if poca_cobertura else 0) + (4 if barrio != SIN_SECTOR else 0))
            partes = []
            if dias > 1:
                partes.append("Aparecio en %d días distintos (%d notas) entre el %s y el %s."
                              % (dias, len(its), _fmt_dia(primera), _fmt_dia(ultima)))
            else:
                partes.append("Aparecio una vez (%s, %s)." % (_fmt_dia(ultima), _hace(ultima, ahora)))
            if poca_cobertura:
                partes.append("Cada nota la publico un solo medio: nadie junto el caso en una cobertura mayor.")
            if n_alertas:
                partes.append("%d alerta(s) de la gente del mismo tipo en el mismo sector." % n_alertas)
            if barrio == SIN_SECTOR:
                partes.append("Sin barrio identificado: falta ubicar donde pasa.")
            pistas = PISTAS.get(sub, [])
        else:
            score = 20 + 20 * recencia + (10 if poca_cobertura else 0)
            if cat == "humana":
                if poca_cobertura:
                    por = "Solo %s la conto: hay espacio para profundizar o buscar historias parecidas en el barrio." % medios[0]
                else:
                    por = "La contaron %s." % ", ".join(medios[:4])
            else:
                por = "Evento en la ciudad (%s). Sirve para agenda o para la historia detras del evento." % ", ".join(medios[:3])
            partes = [por]
            pistas = PISTAS.get(cat, [])
        temas.append({
            "id": tid, "categoria": cat, "categoria_label": ETIQUETAS[cat],
            "subtipo": sub, "subtipo_label": ETIQUETAS.get(sub, sub), "barrio": barrio,
            "titulo": (ETIQUETAS.get(sub, sub) + " — " + barrio) if cat == "problema" else its[0]["titular"],
            "dias": dias, "n": len(its), "primera": primera.isoformat(), "ultima": ultima.isoformat(),
            "medios": medios[:8], "max_outlets": max_out, "alertas": n_alertas,
            "score": round(score, 1), "por_que": " ".join(partes), "pistas": pistas,
            "apariciones": [{"titular": x["titular"], "link": x["link"], "outlets": x["outlets"],
                             "fecha": x["fecha"]} for x in its[:8]],
        })

    # Variedad: sin esto el top seria todo inseguridad (lo que mas publica la
    # prensa de Guayaquil). Cada tema repetido del mismo subtipo vale menos.
    temas.sort(key=lambda t: -t["score"])
    elegidos, usados = [], {}
    pendientes = temas[:]
    while pendientes and len(elegidos) < MAX_TEMAS:
        mejor = max(pendientes, key=lambda t: t["score"] * (0.6 ** usados.get(t["subtipo"], 0)))
        pendientes.remove(mejor)
        usados[mejor["subtipo"]] = usados.get(mejor["subtipo"], 0) + 1
        elegidos.append(mejor)
    return elegidos


def _barrios(temas):
    out = {}
    for t in temas:
        b = out.setdefault(t["barrio"], {"barrio": t["barrio"], "n_temas": 0, "n_notas": 0, "principal": ""})
        b["n_temas"] += 1
        b["n_notas"] += t["n"]
        if not b["principal"] and t["categoria"] == "problema":
            b["principal"] = t["subtipo_label"]
    return sorted(out.values(), key=lambda b: (b["barrio"] == SIN_SECTOR, -b["n_notas"]))


def actualizar(historias, alertas=None, ahora=None, persistir=True):
    """Registra las historias de Guayaquil de esta pasada y devuelve lo que
    va a data.json["comunidad"]. Barato: sin red ni IA."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    reg = _cargar() if persistir else {"version": 1, "items": {}}
    items = reg["items"]
    nuevos = 0
    for h in historias or []:
        det = detectar(h)
        if not det:
            continue
        f = _fecha_historia(h)
        if not f:
            continue
        k = _clave(h)
        outlets = []
        for fu in h.get("fuentes") or []:
            if fu.get("outlet") and fu["outlet"] not in outlets:
                outlets.append(fu["outlet"])
        prev = items.get(k)
        if prev is None:
            nuevos += 1
        items[k] = {"titular": h.get("titular") or "", "link": (h.get("fuentes") or [{}])[0].get("link") or "",
                    "outlets": outlets if not prev or len(outlets) >= len(prev["outlets"]) else prev["outlets"],
                    "n_outlets": max(len(outlets), prev["n_outlets"] if prev else 0),
                    "fecha": min(f.isoformat(), prev["fecha"]) if prev else f.isoformat(),
                    "vista": prev["vista"] if prev else ahora.isoformat(), **det}
    corte = ahora - dt.timedelta(days=RETENCION_DIAS)
    for k in [k for k, it in items.items() if (_parse(it["fecha"]) or ahora) < corte]:
        del items[k]
    if persistir:
        try:
            _guardar(reg)
        except Exception:
            pass
    temas = _armar_temas(items, alertas, ahora)
    n_prob = sum(1 for t in temas if t["categoria"] == "problema")
    return {"temas": temas, "barrios": _barrios(temas), "total_notas": len(items), "nuevas": nuevos,
            "estado": "%d temas (%d problemas de barrio) a partir de %d notas de Guayaquil guardadas"
                      % (len(temas), n_prob, len(items))}
