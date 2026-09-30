# -*- coding: utf-8 -*-
"""
comunidad.py -- Fase 20 (v2): "Comunidad Guayaquil" = lo que la GENTE dice.

Pedido de Fernando (2026-09-30), segunda vuelta: "no quiero notas de prensa
porque precisamente eso es lo ya cubierto, quiero identificar problemas que
tenga la gente... no solo esos 3 temas, sino mas, todo lo que se pueda
abarcar". La v1 armaba los temas con titulares de prensa: descartado.

Fuente de los temas: SOLO publicaciones de personas (nunca medios ni cuentas
institucionales) que mencionan Guayaquil o uno de sus sectores:
  - X (Apify): consulta de quejas de Guayaquil, capa propia en redes.py
    (registrar_tweets), con el mismo presupuesto de siempre.
  - Bluesky (gratis) y YouTube (comentarios, cuota diaria): recolectar(),
    llamada desde el hilo trabajador.
  - Lo que Spike ya junta en otras partes y hoy se desperdiciaba: senales de
    alertas de la gente, publicaciones de Pulso social y de "Debate real"
    (ingerir_de_pipeline(), sin red, en cada pasada del hilo rapido).

La prensa se usa para UNA sola cosa: decir si el problema YA esta cubierto
("Sin notas de prensa sobre esto en el sector" vs "La prensa ya lo cubrio").
Lo no cubierto sube: esa es la oportunidad de reportaje.

Un tema = (sector, categoria). Sube por personas DISTINTAS que lo mencionan,
dias distintos, recencia y falta de cobertura. Nada de IA: palabras clave,
determinista y gratis. Registro propio: comunidad.json (60 dias, NO es un
cache: no borrar a mano).

Fase 20b (frecuencias y fuentes nuevas): X cada 10 min en un hilo propio
(redes.pasada_comunidad), Bluesky cada 10 min, YouTube cada hora, Facebook
(paginas y grupos PUBLICOS via Apify, facebook.py) y WhatsApp (chats de grupo
EXPORTADOS a mano por Fernando, whatsapp.py -- no existe otra via legitima).

Limite honesto: lo captado es una muestra, no "toda la ciudad". Los conteos
son de lo CAPTADO, nunca de "cuanta gente" piensa algo.

Standalone: no importa monitor.py.
"""
import datetime as dt
import json
import os
import re
import threading
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
COMUNIDAD_PATH = os.path.join(HERE, "comunidad.json")
VERSION = 2

RETENCION_DIAS = int(os.environ.get("MONITOR_COMUNIDAD_DIAS", "60"))
VIGENCIA_DIAS = int(os.environ.get("MONITOR_COMUNIDAD_VIGENCIA", "30"))
COBERTURA_DIAS = 14          # una nota de prensa de hace mas de esto ya no "cubre" el tema
MAX_TEMAS = 150
MAX_POSTS = 6000             # tope del registro en disco
# Fase 20b, pedido de Fernando: "Comentarios cada 8 horas no funciona, deben
# cada hora al menos". YouTube: ~100 unidades de cuota por busqueda + ~1 por
# video de comentarios; cada hora = ~2.500 de las 10.000 diarias gratis.
BSKY_CADA_MIN = float(os.environ.get("MONITOR_COMUNIDAD_BSKY_MIN", "10"))
YT_CADA_H = float(os.environ.get("MONITOR_COMUNIDAD_YT_H", "1"))
# Fase 21 (pedido de Fernando): solo entra como NUEVO lo publicado en las
# ultimas VENTANA_H horas. Lo anterior que ya estaba en el registro no crea
# temas: solo se muestra como antecedente ("ya se mencionaba antes").
VENTANA_H = float(os.environ.get("MONITOR_VENTANA_H", "10"))
# El hilo rapido, el trabajador y comunidad_loop escriben comunidad.json.
_LOCK = threading.RLock()

last_error = None


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9@ ]+", " ", s)


def _patron(termino):
    """'inund*' = prefijo; sin '*' = palabra/frase exacta."""
    t = _norm(termino.rstrip("*")).strip()
    if termino.endswith("*"):
        return re.compile(r"\b" + re.escape(t))
    return re.compile(r"\b" + re.escape(t) + r"\b")


# ---------------------------------------------------------------- categorias
# Orden = prioridad cuando un texto calza en varias (lo mas especifico
# primero: "robaron el medidor de agua" es inseguridad, no agua; "extorsion"
# antes que inseguridad general; "acumulacion de agua" es inundacion).
CATEGORIAS = [
    ("extorsion", "Extorsion y vacunas",
     ["extorsion*", "vacunadores", "cobro de vacunas", "cobran vacuna*", "pagar vacuna*", "vacunas a los negocios"]),
    ("inseguridad", "Inseguridad y robos",
     ["robo", "robos", "robaron", "roban", "robar", "robando", "asalt*", "atraco*", "arranch*", "delincuen*", "ladron*", "motorizados", "inseguridad",
      "balacera*", "balea*", "disparos", "sicari*", "secuestr*", "asesin*", "microtrafico", "zona roja",
      "sacapintas", "bandas", "pandilla*"]),
    ("abuso_autoridad", "Abuso de autoridad y corrupcion",
     ["abuso de autoridad", "coima*", "corrupcion", "metropolitanos", "agentes municipales",
      "prepotencia", "nos quitaron la mercaderia", "decomisaron"]),
    ("emergencias", "Emergencias (incendios, derrumbes, cables)",
     ["incendio*", "derrumbe*", "deslave*", "arbol caido", "arboles caidos", "cable caido", "cables caidos",
      "fuga de gas", "colapso", "se cayo el techo", "explosion"]),
    ("inundaciones", "Lluvias, inundaciones y alcantarillado",
     ["inund*", "anegad*", "acumulacion de agua", "alcantarill*", "aguas servidas", "colector*",
      "desborde*", "se llena de agua", "se inunda", "charco*", "marea alta", "aguaje", "drenaje*",
      "canal de aguas"]),
    ("agua", "Agua potable",
     ["sin agua", "no llega el agua", "no hay agua", "falta de agua", "corte de agua", "cortes de agua",
      "agua potable", "interagua", "tanquero*", "presion del agua", "agua sucia", "agua turbia",
      "agua amarilla", "servicio de agua", "planilla de agua"]),
    ("luz", "Luz y apagones",
     ["sin luz", "no hay luz", "apagon*", "corte de luz", "cortes de luz", "cnel", "transformador*",
      "bajon*", "variacion de voltaje", "sin energia", "planilla de luz"]),
    ("alumbrado", "Alumbrado publico",
     ["alumbrado", "calle oscura", "calles oscuras", "a oscuras", "postes sin luz", "lamparas", "luminarias"]),
    ("basura", "Basura y recoleccion",
     ["basura", "recolector*", "carro de la basura", "botadero*", "escombros", "desechos", "fundas de basura",
      "no pasa el carro", "malos olores"]),
    ("calles", "Calles, veredas y baches",
     ["bache*", "hueco*", "calle destruida", "calles destruidas", "mal estado", "vereda*", "aceras",
      "asfalt*", "lastre", "polvo", "calle de tierra", "pavimento", "adoquin*"]),
    ("obras", "Obras paradas o mal hechas",
     ["obra paralizada", "obras paralizadas", "obra abandonada", "obra inconclusa", "obras inconclusas",
      "dejaron abierto", "zanja*", "trabajos inconclusos", "nunca terminaron", "a medias"]),
    ("transito", "Transito y parqueo",
     ["trafico", "congestion", "trancon*", "semaforo*", "atm", "agentes de transito", "multa*",
      "fotomulta*", "parqueo*", "estacionamiento", "grua*", "accidente de transito", "choque"]),
    ("transporte", "Transporte publico",
     ["bus", "buses", "busetas", "metrovia", "pasaje*", "recorrido*", "parada de bus", "taxirruta*",
      "linea de buses", "no pasan los buses", "transporte publico", "furgoneta*", "tricimoto*"]),
    ("salud", "Salud y hospitales",
     ["hospital*", "centro de salud", "subcentro*", "medicinas", "medicamentos", "turno*", "citas",
      "iess", "dengue", "atencion medica", "emergencia del hospital", "no hay medico*"]),
    ("educacion", "Escuelas y colegios",
     ["escuela*", "colegio*", "profesor*", "maestros", "matricula*", "aulas", "cupo*", "clases",
      "unidad educativa"]),
    ("vivienda", "Vivienda, terrenos e invasiones",
     ["invasion*", "desalojo*", "escritura*", "legalizar", "legalizacion", "terreno*", "traficante* de tierra*",
      "damnificad*", "casa se cae", "vivienda*"]),
    ("espacio_publico", "Parques, canchas y espacio publico",
     ["parque*", "cancha*", "area verde", "areas verdes", "comerciantes informales", "vendedores ambulantes",
      "informales", "aceras ocupadas", "juegos infantiles", "malecon"]),
    ("ruido", "Ruido y contaminacion",
     ["ruido", "bulla", "parlante*", "musica alta", "humo", "contaminacion", "estero", "quema de basura",
      "fetido", "apestoso"]),
    ("animales", "Animales y plagas",
     ["perros callejeros", "perro callejero", "animales abandonados", "maltrato animal", "ratas", "roedores",
      "plaga*", "zancudo*", "mosquito*", "cucaracha*", "fumigacion", "fumigar"]),
    ("tramites", "Tramites y atencion publica",
     ["tramite*", "burocracia", "colas", "filas", "no atienden", "no responden", "registro civil",
      "municipio no", "nadie responde", "mala atencion", "atencion al cliente"]),
    ("telecom", "Internet y telefonia",
     ["sin internet", "internet", "sin señal", "sin senal", "cnt", "netlife", "movistar",
      "fibra optica"]),
    ("costo_vida", "Costo de vida y empleo",
     ["precio", "precios", "carisimo", "muy caro", "desempleo", "sin trabajo", "no hay trabajo", "sueldo*", "canasta",
      "gas domestico", "cilindro de gas", "arriendo*", "alquiler"]),
]
_P_CAT = [(k, etq, [_patron(t) for t in ts]) for k, etq, ts in CATEGORIAS]
ETIQUETA = {k: etq for k, etq, _ in CATEGORIAS}

# Frases de queja/reclamo: suben la confianza de que el post es un problema
# (no es obligatorio -- mucha gente se queja sin estas palabras).
_QUEJA = [_patron(t) for t in [
    "hasta cuando", "nadie hace nada", "denuncio", "denunciamos", "denuncia*", "reclam*", "exigimos", "exigen",
    "pedimos", "piden", "ayuda", "auxilio", "abandonad*", "olvidad*", "llevamos", "dias sin", "semanas sin",
    "meses sin", "todos los dias", "otra vez", "de nuevo", "es un peligro", "peligro", "indignad*", "harto*",
    "cansados", "nadie responde", "no hacen nada", "que alguien", "por favor", "urgente", "vergüenza", "verguenza",
    "@alcaldiagye", "municipio", "alcaldia", "interagua", "cnel", "atm"]]

# Palabras con que la voz de la gente se busca en X/Bluesky (con tilde, como
# se escribe). Una sola consulta con OR -- ver xapi._or.
TERMINOS_QUEJA = ["sin agua", "sin luz", "apagón", "baches", "basura", "inundado", "alcantarillado",
                  "robo", "asaltaron", "extorsión", "vacunas", "buses", "Metrovía", "hueco", "perros callejeros",
                  "ruido", "moradores", "vecinos", "nadie hace nada", "hasta cuándo"]

PISTAS = {
    "extorsion": ["¿Que negocios del sector pagan y desde cuando?", "¿Hubo denuncias formales? ¿Que respondio la Policia?"],
    "inseguridad": ["¿A que horas y en que calles pasa? ¿Hay un patron?", "¿Que presencia policial real hay y que dicen los moradores?",
                    "¿Hay organizaciones barriales o UPC trabajando en el sector?"],
    "abuso_autoridad": ["¿Hay videos o testigos? ¿Que dice la institucion señalada?"],
    "emergencias": ["¿Llegaron los bomberos/ECU 911 a tiempo? ¿Es la primera vez en ese sector?"],
    "inundaciones": ["¿Se inunda cada invierno? ¿Que obra de drenaje se prometio y en que estado esta?",
                     "¿Cuantas familias pierden algo cada vez que llueve?"],
    "agua": ["¿Desde cuando falla y cada cuanto se repite?", "¿Que explica Interagua y que dicen los moradores?",
             "¿Cuanto gastan en tanqueros o botellones mientras tanto?"],
    "luz": ["¿Cuantas horas sin servicio y con que frecuencia?", "¿Hay reclamos presentados a CNEL?"],
    "alumbrado": ["¿Desde cuando esta oscuro? ¿Tiene relacion con robos en la zona?"],
    "basura": ["¿Cada cuanto pasa el recolector? ¿Hay un botadero que crece?"],
    "calles": ["¿Cuanto tiempo lleva asi? ¿Hubo reclamos formales y respuesta del Municipio?"],
    "obras": ["¿Que contratista la tiene, cuanto costaba y por que se paro? (buscar en SERCOP)"],
    "transporte": ["¿Cuanto tardan los moradores en llegar al trabajo o a clases? ¿Que rutas dejaron de pasar?"],
    "transito": ["¿Que punto exacto y a que hora? ¿Que dice la ATM?"],
    "salud": ["¿Que falta exactamente (medicinas, medicos, turnos) y desde cuando?"],
    "educacion": ["¿Cuantos estudiantes afectados y que piden los padres?"],
    "vivienda": ["¿Cuantas familias y desde cuando viven ahi? ¿En que va la legalizacion?"],
    "espacio_publico": ["¿Quien usa ese espacio y que conflicto hay entre vecinos?"],
    "ruido": ["¿De donde viene y quien deberia controlarlo?"],
    "animales": ["¿Hay una colonia de perros/plaga creciendo? ¿Quien deberia intervenir?"],
    "tramites": ["¿Que tramite, cuanto tarda y que dice la institucion?"],
    "telecom": ["¿Que operadora, desde cuando y cuantos usuarios afectados?"],
    "costo_vida": ["¿Que precio subio y cuanto? ¿A quien afecta mas en el barrio?"],
}

# Tipos de alerta (alertas.py) -> categoria.
ALERTA_A_CAT = {"inundacion": "inundaciones", "corte_agua": "agua", "corte_luz": "luz",
                "balacera": "inseguridad", "incendio": "emergencias", "accidente": "transito",
                "protesta": "tramites"}

# ---------------------------------------------------------------- lugares
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
    "Los Vergeles": ["los vergeles"], "Las Orquideas": ["las orquideas"], "Nueva Prosperina": ["nueva prosperina"],
    "Daule": ["daule"], "Mucho Lote": ["mucho lote"], "Bellavista": ["bellavista"], "Miraflores": ["miraflores"],
    "Lomas de Urdesa": ["lomas de urdesa"], "Centenario": ["centenario"], "Cdla. Kennedy": ["cdla kennedy", "ciudadela kennedy"],
    "Juan Montalvo": ["cooperativa juan montalvo"], "Fertisa": ["fertisa"], "El Fortin": ["el fortin"],
    "Paraiso de la Flor": ["paraiso de la flor"], "Las Malvinas": ["las malvinas"], "Batallon del Suburbio": ["batallon del suburbio"],
    "Mapasingue": ["mapasingue"], "La Pradera": ["la pradera"], "Sopeña": ["sopena"], "Cerro del Carmen": ["cerro del carmen"],
    "Urbanor": ["urbanor"], "Alborada": ["alborada"], "Sauces": ["sauces"], "Samanes": ["samanes"],
    "Vergeles": ["vergeles"], "Via a la Costa": ["via a la costa"], "Via a Daule": ["via a daule"],
    "Tarqui": ["parroquia tarqui"], "Ximena": ["parroquia ximena"], "Febres Cordero": ["febres cordero"],
}
BARRIOS = dict(_BARRIOS_BASE)
BARRIOS.update(_BARRIOS_EXTRA)
_P_BARRIOS = sorted([(b, [_patron(t) for t in ts]) for b, ts in BARRIOS.items()],
                    key=lambda x: -max(len(p.pattern) for p in x[1]))
SECTORES = [("Norte de Guayaquil", ["norte de guayaquil", "al norte de la ciudad"]),
            ("Sur de Guayaquil", ["sur de guayaquil", "al sur de la ciudad"]),
            ("Noroeste de Guayaquil", ["noroeste de guayaquil", "noroeste de la ciudad"]),
            ("Centro", ["centro de guayaquil", "centro de la ciudad"]),
            ("Parroquias rurales", ["parroquias rurales"])]
_P_SECTORES = [(s, [_patron(t) for t in ts]) for s, ts in SECTORES]
_P_GYE = [_patron(t) for t in ("guayaquil", "gye", "guayas", "guayaco*", "samborondon", "duran")]
SIN_SECTOR = "Guayaquil (sin sector)"
_COOP = re.compile(r"\b[Cc]ooperativa\s+((?:[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ]*)(?:\s+(?:de\s+|del\s+)?"
                   r"[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ]*){0,3})")


def detectar_barrio(texto):
    m = _COOP.search(texto or "")
    if m:
        return "Coop. " + m.group(1).strip()
    blob = _norm(texto)
    for b, ps in _P_BARRIOS:
        if any(p.search(blob) for p in ps):
            return b
    for s, ps in _P_SECTORES:
        if any(p.search(blob) for p in ps):
            return s
    return None


# Otra ciudad/pais nombrado sin mencionar Guayaquil = no es de aqui (caso
# real: "parroquia Tarqui de Manta"; accidentes en Naranjal; Jaen, Peru).
# "Pedro Carbo" NO va: tambien es una calle del centro de Guayaquil.
_P_OTRA = [_patron(t) for t in ("quito", "cuenca", "manta", "portoviejo", "machala", "esmeraldas", "loja",
                                 "ambato", "riobamba", "ibarra", "latacunga", "babahoyo", "quevedo", "milagro",
                                 "naranjal", "salinas", "la libertad", "santa elena", "playas", "balzar",
                                 "el empalme", "colimes", "salitre", "jaen", "peru", "colombia", "venezuela",
                                 "manabi", "el oro", "los rios", "pichincha", "azuay")]
_P_GYE_EXPLICITO = [_patron(t) for t in ("guayaquil", "gye", "guayaco*")]


def es_de_guayaquil(texto):
    blob = _norm(texto)
    if any(p.search(blob) for p in _P_OTRA) and not any(p.search(blob) for p in _P_GYE_EXPLICITO):
        return False
    return detectar_barrio(texto) is not None or any(p.search(blob) for p in _P_GYE)


def categorizar(texto):
    """Primera categoria que calza (orden de CATEGORIAS) o None."""
    blob = _norm(texto)
    for k, _, ps in _P_CAT:
        if any(p.search(blob) for p in ps):
            return k
    return None


def es_queja(texto):
    blob = _norm(texto)
    return any(p.search(blob) for p in _QUEJA)


# ---------------------------------------------------------------- quien habla
_PALABRAS_INSTITUCION = ("municipio", "alcaldia", "prefectura", "ministerio", "gobierno", "policia",
                         "ecu911", "ecu 911", "bomberos", "interagua", "cnel", "atm ", "noticias",
                         "diario", "radio", "tv", "television", "canal", "prensa", "oficial")


# Paginas de noticias/alertas que en X parecen "personas" (casos reales del
# 30-sep: UniversalGye, TiempoRealEC, el_telegrafo, EcEnDirecto,
# Centralinfec, Ecuador221ec, lanacionecuador, Alerta_Gyaquil7...).
_HANDLE_MEDIO = re.compile(r"(noticia|news|diario|telegrafo|nacion|semanario|alerta|emergencia|info|radio|"
                           r"directo|central|universal|tiemporeal|antena|prensa|medio|canal|^tv|tv$|ecuavisa|"
                           r"teleamazonas|extra|expreso|universo|primicias|metro|mega|reporte|periodic|"
                           r"ecuador|samborondeno|^ec|ec$|oficial|municip|gobierno|policia|ministerio|obras|quito)")
_FORMATO_NOTICIA = re.compile(r"^\s*(#\w+\s*[|:]|urgente|ultima hora|atencion|#atencion)", re.I)


def es_persona(autor, tipo=None, oficial=False):
    """Descarta medios, instituciones y cuentas oficiales. Ante la duda (sin
    autor), no cuenta como voz de la gente."""
    if oficial:
        return False
    if tipo and tipo not in ("persona", "politico"):
        return False
    a = (autor or "").strip()
    if not a:
        return False
    try:
        import social
        if social.es_cuenta_medio(a):
            return False
    except Exception:
        pass
    an = _norm(a)
    if any(p in an for p in _PALABRAS_INSTITUCION):
        return False
    handle = re.sub(r"[^a-z0-9]", "", an)  # "el_telegrafo" -> "eltelegrafo"
    return not _HANDLE_MEDIO.search(handle)


# ---------------------------------------------------------------- registro
def _parse(s):
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def _cargar():
    try:
        with open(COMUNIDAD_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("version") == VERSION and isinstance(d.get("posts"), dict):
            return d
    except Exception:
        pass
    # v1 (temas armados con prensa) se descarta a proposito: otra fuente.
    return {"version": VERSION, "posts": {}, "ultimas": {}}


def _guardar(d):
    tmp = COMUNIDAD_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, COMUNIDAD_PATH)


def _post_id(fuente, url, autor, texto):
    """Por autor+texto (no por URL): la misma publicacion llega por varias
    vias (Pulso, Debate, alertas) a veces con URLs distintas."""
    return "%s:%s|%s" % (fuente, _norm(autor).strip(), _norm(texto)[:120].strip())


def normalizar_post(fuente, autor, texto, url="", fecha="", tipo=None, oficial=False, ahora=None,
                    asumir_gye=False, barrio_defecto=None, persona_segura=False):
    """Convierte cualquier publicacion en un registro de 'voz de la gente', o
    None si no aplica (medio/institucion, no es de Guayaquil, o no nombra
    ningun problema reconocible). asumir_gye/barrio_defecto: fuentes que ya
    son de Guayaquil por eleccion de Fernando (grupo de WhatsApp de un barrio).
    persona_segura: el autor es un participante de un grupo, no una cuenta
    publica (no pasa por el filtro de medios por nombre)."""
    texto = (texto or "").strip()
    if len(texto) < 12:
        return None
    if not persona_segura and not es_persona(autor, tipo, oficial):
        return None
    if _FORMATO_NOTICIA.search(texto):
        return None
    if not asumir_gye and not es_de_guayaquil(texto):
        return None
    cat = categorizar(texto)
    if not cat:
        return None
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    f = _parse(fecha) or ahora
    if (ahora - f).total_seconds() > VENTANA_H * 3600:
        return None  # Fase 21: viejo, no entra como nuevo
    return {"id": _post_id(fuente, url, autor, texto), "fuente": fuente, "autor": autor.strip(),
            "texto": texto[:500], "url": url or "", "fecha": f.isoformat(), "categoria": cat,
            "barrio": detectar_barrio(texto) or barrio_defecto or SIN_SECTOR, "queja": es_queja(texto)}


def _agregar(reg, posts):
    n = 0
    for p in posts:
        if p and p["id"] not in reg["posts"]:
            reg["posts"][p["id"]] = p
            n += 1
    return n


def _purgar(reg, ahora):
    corte = ahora - dt.timedelta(days=RETENCION_DIAS)
    ps = reg["posts"]
    for k in [k for k, p in ps.items() if (_parse(p["fecha"]) or ahora) < corte]:
        del ps[k]
    if len(ps) > MAX_POSTS:
        for k, _ in sorted(ps.items(), key=lambda kv: kv[1]["fecha"])[:len(ps) - MAX_POSTS]:
            del ps[k]


# ------------------------- entrada 1: lo que el pipeline ya junto (sin red) -------------------------
def posts_de_pipeline(alertas=None, social=None, social_historias=None, ahora=None):
    out = []
    for a in alertas or []:
        for s in a.get("senales") or []:
            p = normalizar_post(s.get("fuente") or "alerta", s.get("autor"), s.get("texto"), s.get("url"),
                                s.get("fecha"), oficial=bool(s.get("oficial")), ahora=ahora)
            lugar = a.get("lugar") or ""
            if p and p["barrio"] == SIN_SECTOR and lugar and "sin precisar" not in lugar:
                p["barrio"] = lugar
            out.append(p)
    for d in (social or {}).values():
        for s in d.get("top") or []:
            out.append(normalizar_post(s.get("fuente"), s.get("autor"), s.get("texto"), s.get("url"),
                                       s.get("fecha"), tipo=s.get("tipo"), ahora=ahora))
    for d in (social_historias or {}).values():
        for s in d.get("top") or []:
            out.append(normalizar_post(s.get("fuente"), s.get("autor"), s.get("texto"), s.get("url"),
                                       s.get("fecha"), tipo=s.get("tipo"), ahora=ahora))
        for postura in d.get("posturas") or []:
            for s in postura.get("citas") or []:
                out.append(normalizar_post(s.get("fuente"), s.get("autor"), s.get("texto"), s.get("url"),
                                           s.get("fecha"), ahora=ahora))
    return [p for p in out if p]


# ------------------------- entrada 2: X (llamada desde redes.py) -------------------------
def registrar_tweets(tweets, ahora=None):
    """Tweets crudos de Apify (forma verificada en xapi.py). Devuelve cuantos
    entraron como voz nueva."""
    try:
        import xapi
    except Exception:
        xapi = None
    posts = []
    for t in tweets or []:
        a = t.get("author") or {}
        usuario = a.get("userName") or ""
        tipo = xapi.clasificar_autor(t) if xapi else None
        fecha = xapi.fecha_iso(t.get("createdAt", "")) if xapi else ""
        posts.append(normalizar_post("x", "@" + usuario if usuario else "", t.get("text"), t.get("url"),
                                     fecha, tipo=tipo, ahora=ahora))
    return _sumar_y_guardar([p for p in posts if p])


def _sumar_y_guardar(posts, marcar=None, ahora=None):
    """load-modify-save bajo el candado. marcar: {clave: iso} para 'ultimas'."""
    global last_error
    with _LOCK:
        reg = _cargar()
        n = _agregar(reg, posts)
        if marcar:
            reg.setdefault("ultimas", {}).update(marcar)
        if ahora:
            _purgar(reg, ahora)
        try:
            _guardar(reg)
        except Exception as e:
            last_error = "guardar: %s" % e
    return n


def consulta_x(horas=6):
    """Consulta de quejas de Guayaquil para X (misma sintaxis de xapi)."""
    try:
        import xapi
        return xapi.consulta_alertas(TERMINOS_QUEJA, "Guayaquil", horas=horas)
    except Exception:
        return ""


# ------------------------- entrada 3: Bluesky / YouTube (hilo trabajador) -------------------------
def _toca(reg, clave, minutos, ahora):
    ult = _parse((reg.get("ultimas") or {}).get(clave))
    return ult is None or (ahora - ult).total_seconds() >= minutos * 60


def _ultimas():
    with _LOCK:
        return dict(_cargar().get("ultimas") or {})


def _toca_ult(ultimas, clave, minutos, ahora):
    return _toca({"ultimas": ultimas}, clave, minutos, ahora)


def registrar_facebook(pubs, ahora=None):
    """Publicaciones/comentarios ya parseados por facebook.item_a_publicacion."""
    posts = [normalizar_post("facebook", p.get("autor"), p.get("texto"), p.get("url"), p.get("fecha"), ahora=ahora)
             for p in pubs or []]
    return _sumar_y_guardar([p for p in posts if p])


def importar_whatsapp(nombre, contenido, ahora=None):
    """Un chat exportado (.txt o .zip, bytes). Devuelve {grupo, mensajes,
    utiles, nuevos}. Se asume Guayaquil (el grupo lo eligio Fernando) y, si el
    mensaje no nombra sector, el sector sale del NOMBRE del grupo."""
    import whatsapp
    grupo, msgs = whatsapp.leer_archivo(nombre, contenido)
    barrio_grupo = detectar_barrio(grupo)
    posts = [normalizar_post("whatsapp", m["autor"], m["texto"], "", m["fecha"], ahora=ahora, asumir_gye=True,
                             barrio_defecto=barrio_grupo, persona_segura=True) for m in msgs]
    posts = [p for p in posts if p]
    return {"grupo": grupo, "sector": barrio_grupo or SIN_SECTOR, "mensajes": len(msgs), "utiles": len(posts),
            "nuevos": _sumar_y_guardar(posts)}


def procesar_carpeta_whatsapp(ahora=None):
    """Chats dejados en whatsapp_import/ (sin red). Cada archivo se procesa una
    vez por version (tamano+fecha de modificacion)."""
    import whatsapp
    ult = _ultimas()
    hechos = ult.get("whatsapp_archivos") or {}
    if not isinstance(hechos, dict):
        hechos = {}
    res = []
    for ruta, nombre in whatsapp.archivos_pendientes(hechos):
        try:
            with open(ruta, "rb") as f:
                r = importar_whatsapp(nombre, f.read(), ahora=ahora)
            res.append("%s +%d" % (r["grupo"], r["nuevos"]))
        except Exception as e:
            res.append("%s: error (%s)" % (nombre, e))
        hechos[nombre] = whatsapp.firma(ruta)
    if res:
        _sumar_y_guardar([], marcar={"whatsapp_archivos": hechos})
    return res


def recolectar(ahora=None, youtube=True, facebook=True):
    """Red real, SOLO desde hilos de fondo (comunidad_loop / trabajador), nunca
    el hilo rapido. Cada fuente con su propia frecuencia: Bluesky (gratis) cada
    BSKY_CADA_MIN, YouTube (cuota) cada YT_CADA_H con clave, Facebook (Apify,
    tope propio) cada facebook.CADA_MIN con fuentes configuradas, y los chats de
    WhatsApp de whatsapp_import/ (sin red). La red va FUERA del candado."""
    global last_error
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    try:
        import social
    except Exception:
        social = None
    ult = _ultimas()
    hechos = []
    if social is not None and _toca_ult(ult, "bluesky", BSKY_CADA_MIN, ahora):
        posts = []
        for q in ("Guayaquil", "Guayaquil sin agua", "Guayaquil sin luz", "Guayaquil basura",
                  "Guayaquil baches", "Guayaquil robo", "Guayaquil moradores"):
            try:
                for sp in social.bluesky_buscar(q, limit=40, dias=1) or []:
                    posts.append(normalizar_post("bluesky", sp.autor, sp.texto, sp.url, sp.fecha,
                                                 tipo=sp.tipo, ahora=ahora))
            except Exception as e:
                last_error = "bluesky: %s" % e
        hechos.append("bluesky +%d" % _sumar_y_guardar([p for p in posts if p],
                                                        marcar={"bluesky": ahora.isoformat()}))
    if (social is not None and youtube and os.environ.get("MONITOR_YT_KEY")
            and _toca_ult(ult, "youtube", YT_CADA_H * 60, ahora)):
        posts = []
        # Rota la consulta para no leer siempre los mismos videos.
        consultas = ("Guayaquil moradores denuncian", "Guayaquil barrio problema", "Guayaquil vecinos reclaman")
        q = consultas[int(ahora.timestamp() // 3600) % len(consultas)]
        try:
            for sp in social.youtube_buscar(q, max_videos=3, max_comentarios=20, dias=1) or []:
                posts.append(normalizar_post("youtube", sp.autor, sp.texto, sp.url, sp.fecha,
                                             tipo=sp.tipo, ahora=ahora))
        except Exception as e:
            last_error = "youtube: %s" % e
        hechos.append("youtube +%d" % _sumar_y_guardar([p for p in posts if p],
                                                        marcar={"youtube": ahora.isoformat()}))
    if facebook:
        try:
            import facebook as fb
        except Exception:
            fb = None
        if fb is not None and fb.activo() and _toca_ult(ult, "facebook", fb.CADA_MIN, ahora):
            pubs, est = fb.recolectar()
            n = registrar_facebook(pubs, ahora=ahora)
            _sumar_y_guardar([], marcar={"facebook": ahora.isoformat(), "facebook_estado": est})
            hechos.append("facebook +%d (%s)" % (n, est))
    try:
        for r in procesar_carpeta_whatsapp(ahora=ahora):
            hechos.append("whatsapp %s" % r)
    except Exception as e:
        last_error = "whatsapp: %s" % e
    _sumar_y_guardar([], ahora=ahora)  # purga
    return ", ".join(hechos) if hechos else "sin consulta esta pasada (todavia no toca)"


# ---------------------------------------------------------------- cobertura de prensa
def _cobertura(historias, ahora):
    """{(barrio, cat): [medios]} y {cat: [medios]} con la prensa de Guayaquil
    de los ultimos COBERTURA_DIAS -- solo para decir 'ya cubierto'."""
    por_par, por_cat = {}, {}
    for h in historias or []:
        texto = (h.get("titular") or "") + " " + (h.get("resumen") or "")
        if h.get("ciudad") != "Guayaquil" and not es_de_guayaquil(texto):
            continue
        fechas = [_parse(f.get("date")) for f in (h.get("fuentes") or [])]
        fechas = [f for f in fechas if f]
        if fechas and (ahora - max(fechas)).days > COBERTURA_DIAS:
            continue
        cat = categorizar(h.get("titular") or "")
        if not cat:
            continue
        barrio = detectar_barrio(texto) or SIN_SECTOR
        medios = [f.get("outlet") for f in (h.get("fuentes") or []) if f.get("outlet")]
        info = {"titular": h.get("titular"), "link": (h.get("fuentes") or [{}])[0].get("link"), "medios": medios[:3]}
        por_par.setdefault((barrio, cat), []).append(info)
        por_cat.setdefault(cat, []).append(info)
    return por_par, por_cat


# ---------------------------------------------------------------- temas
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
_EC = dt.timezone(dt.timedelta(hours=-5))


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


FUENTE_ETQ = {"x": "X", "bluesky": "Bluesky", "youtube": "YouTube", "reddit": "Reddit", "telegram": "Telegram",
              "mastodon": "Mastodon", "tiktok": "TikTok", "alerta": "alertas", "facebook": "Facebook",
              "whatsapp": "WhatsApp"}


def armar_temas(posts, historias, ahora):
    """Un tema = (sector, categoria) con al menos una publicacion de las
    ultimas VENTANA_H horas (Fase 21). Las publicaciones anteriores del mismo
    par (hasta VIGENCIA_DIAS) no crean tema: se cuentan como antecedente,
    porque un problema que se repite dias seguidos vale mas para reportaje."""
    por_par, por_cat = _cobertura(historias, ahora)
    corte = ahora - dt.timedelta(hours=VENTANA_H)
    grupos = {}
    for p in posts:
        grupos.setdefault((p["barrio"], p["categoria"]), []).append(p)
    temas = []
    for (barrio, cat), todos in grupos.items():
        todos.sort(key=lambda x: x["fecha"], reverse=True)
        ps = [p for p in todos if _parse(p["fecha"]) >= corte]
        if not ps:
            continue
        antes = [p for p in todos if _parse(p["fecha"]) < corte
                 and (ahora - _parse(p["fecha"])).total_seconds() <= VIGENCIA_DIAS * 86400]
        fechas = [_parse(p["fecha"]) for p in ps]
        ultima = fechas[0]
        edad_h = (ahora - ultima).total_seconds() / 3600
        personas = {p["autor"].lower() for p in ps}
        personas_antes = {p["autor"].lower() for p in antes}
        dias = len({_parse(p["fecha"]).astimezone(_EC).date() for p in ps + antes})
        fuentes = sorted({p["fuente"] for p in ps})
        prensa = por_par.get((barrio, cat)) or ([] if barrio != SIN_SECTOR else por_cat.get(cat) or [])
        quejas = sum(1 for p in ps if p.get("queja"))
        recencia = max(0.0, 1.0 - edad_h / max(VENTANA_H, 1))
        score = (12 * min(len(personas), 10) + 2 * min(len(ps), 20) + 15 * recencia + 3 * min(quejas, 10)
                 + 3 * min(len(personas_antes), 5) + (25 if not prensa else 0) + (5 if barrio != SIN_SECTOR else 0))
        partes = []
        n_per = len(personas)
        partes.append("%d persona%s distinta%s lo mencion%s en las ultimas %d h (%d publicacion%s, %s)."
                      % (n_per, "" if n_per == 1 else "s", "" if n_per == 1 else "s",
                         "o" if n_per == 1 else "aron", VENTANA_H, len(ps), "" if len(ps) == 1 else "es",
                         ", ".join(FUENTE_ETQ.get(f, f) for f in fuentes)))
        partes.append("Ultima: %s." % _hace(ultima, ahora))
        if antes:
            partes.append("Ya se mencionaba antes: %d publicacion%s de %d persona%s desde el %s."
                          % (len(antes), "" if len(antes) == 1 else "es", len(personas_antes),
                             "" if len(personas_antes) == 1 else "s", _fmt_dia(_parse(antes[-1]["fecha"]))))
        if prensa:
            medios = sorted({m for x in prensa for m in x["medios"]})
            partes.append("La prensa ya publico %d nota%s relacionada%s (%s)." % (
                len(prensa), "" if len(prensa) == 1 else "s", "" if len(prensa) == 1 else "s", ", ".join(medios[:4])))
        else:
            partes.append("Sin notas de prensa sobre esto %s en los ultimos %d dias."
                          % ("en este sector" if barrio != SIN_SECTOR else "en Guayaquil", COBERTURA_DIAS))
        if barrio == SIN_SECTOR:
            partes.append("Falta ubicar el sector exacto.")
        temas.append({
            "id": "%s|%s" % (barrio, cat), "categoria": cat, "categoria_label": ETIQUETA.get(cat, cat),
            "barrio": barrio, "titulo": "%s — %s" % (ETIQUETA.get(cat, cat), barrio),
            "personas": n_per, "n": len(ps), "dias": dias, "fuentes": fuentes, "quejas": quejas,
            "antes_n": len(antes), "antes_personas": len(personas_antes),
            "primera": fechas[-1].isoformat(), "ultima": ultima.isoformat(),
            "cubierto": bool(prensa), "prensa": prensa[:3], "score": round(score, 1),
            "por_que": " ".join(partes), "pistas": PISTAS.get(cat, []),
            "publicaciones": [{"autor": p["autor"], "texto": p["texto"], "url": p["url"], "fecha": p["fecha"],
                               "fuente": p["fuente"]} for p in ps[:8]],
        })
    # Variedad: cada tema repetido de la misma categoria vale menos, para que
    # el top no sea todo inseguridad.
    elegidos, usados, pend = [], {}, sorted(temas, key=lambda t: -t["score"])
    while pend and len(elegidos) < MAX_TEMAS:
        mejor = max(pend, key=lambda t: t["score"] * (0.65 ** usados.get(t["categoria"], 0)))
        pend.remove(mejor)
        usados[mejor["categoria"]] = usados.get(mejor["categoria"], 0) + 1
        elegidos.append(mejor)
    return elegidos


def actualizar(historias, alertas=None, social=None, social_historias=None, ahora=None, persistir=True):
    """Hilo rapido: suma lo que el pipeline ya junto (sin red), arma los temas
    y devuelve data.json['comunidad']."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    nuevos_posts = posts_de_pipeline(alertas, social, social_historias, ahora)
    with _LOCK:
        reg = _cargar() if persistir else {"version": VERSION, "posts": {}, "ultimas": {}}
        nuevos = _agregar(reg, nuevos_posts)
        _purgar(reg, ahora)
        if persistir:
            try:
                _guardar(reg)
            except Exception:
                pass
        posts = list(reg["posts"].values())
        ultimas = dict(reg.get("ultimas") or {})
    temas = armar_temas(posts, historias, ahora)
    cats = {}
    for t in temas:
        c = cats.setdefault(t["categoria"], {"categoria": t["categoria"], "label": t["categoria_label"], "n_temas": 0,
                                             "sin_cubrir": 0})
        c["n_temas"] += 1
        c["sin_cubrir"] += 0 if t["cubierto"] else 1
    barrios = {}
    for t in temas:
        b = barrios.setdefault(t["barrio"], {"barrio": t["barrio"], "n_temas": 0, "personas": 0})
        b["n_temas"] += 1
        b["personas"] += t["personas"]
    corte = ahora - dt.timedelta(hours=VENTANA_H)
    recientes = [p for p in posts if (_parse(p["fecha"]) or ahora) >= corte]
    por_fuente = {}
    for p in recientes:
        por_fuente[p["fuente"]] = por_fuente.get(p["fuente"], 0) + 1
    sin_cubrir = sum(1 for t in temas if not t["cubierto"])
    estado = ("%d temas (%d sin cobertura de prensa) a partir de %d publicaciones de personas de Guayaquil "
              "en las ultimas %d h (%s)"
              % (len(temas), sin_cubrir, len(recientes), VENTANA_H,
                 ", ".join("%s %d" % (FUENTE_ETQ.get(f, f), n) for f, n in sorted(por_fuente.items())) or "ninguna fuente todavia"))
    return {"temas": temas,
            "categorias": sorted(cats.values(), key=lambda c: -c["n_temas"]),
            "todas_categorias": [{"categoria": k, "label": etq} for k, etq, _ in CATEGORIAS],
            "barrios": sorted(barrios.values(), key=lambda b: (b["barrio"] == SIN_SECTOR, -b["personas"])),
            "total_publicaciones": len(recientes), "ventana_h": VENTANA_H, "nuevas": nuevos, "por_fuente": por_fuente, "estado": estado,
            "ultimas": {k: v for k, v in ultimas.items() if k in ("bluesky", "youtube", "facebook", "facebook_estado")},
            "whatsapp_grupos": sorted({p["autor"].split("(", 1)[-1].rstrip(")") for p in posts
                                       if p["fuente"] == "whatsapp" and "(" in p["autor"]}),
            "frecuencias": {"x_min": float(os.environ.get("MONITOR_COMUNIDAD_X_MIN", "10")),
                            "bluesky_min": BSKY_CADA_MIN, "youtube_h": YT_CADA_H,
                            "facebook_min": float(os.environ.get("MONITOR_FB_MIN", "60"))}}
