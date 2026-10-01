# -*- coding: utf-8 -*-
"""
categorias.py -- Fase 24, Parte C.

C2: taxonomia nueva de 12 categorias (la misma del CSV de evaluacion), con la
razon en una linea. Antes: 5 secciones y 239 de 582 historias (41 %) en
"General". Meta: menos del 10 % sin categoria.

C1: tipo de la afirmacion principal (accion, anuncio, declaracion, dato) y QUIEN
la afirma. Distingue "el Municipio retiro el poste" (accion) de "el poste
retraso las obras, segun el Municipio" (declaracion de una parte interesada).

Primero reglas, sin IA y sin red (sirven siempre, tambien en el hilo rapido).
La IA por lotes (ia.analizar_lote) puede corregirlas; monitor.py le pone el
candado: solo valores de estas listas, y "quien" tiene que aparecer en el texto.
"""
import re
import unicodedata

CATEGORIAS = ["politica", "economia", "empleo", "seguridad", "justicia", "obras_servicios", "movilidad",
              "riesgos_clima", "salud", "educacion", "sociedad_cultura", "entretenimiento_deporte"]
LABEL = {"politica": "Politica", "economia": "Economia", "empleo": "Empleo", "seguridad": "Seguridad",
         "justicia": "Justicia", "obras_servicios": "Obras y servicios", "movilidad": "Movilidad",
         "riesgos_clima": "Riesgos y clima", "salud": "Salud", "educacion": "Educacion",
         "sociedad_cultura": "Sociedad y cultura", "entretenimiento_deporte": "Entretenimiento y deporte"}
TIPOS = ["accion", "anuncio", "declaracion", "dato"]

# Palabras por categoria (sin tildes; coinciden por inicio de palabra, como
# kw_hit: "inund" atrapa inundacion/inundaciones). Frases con espacio = frase
# completa. Se incluye ingles basico: la mitad del corpus internacional lo es.
REGLAS = {
    "politica": ["presidente", "presidenta", "noboa", "asamblea", "asambleista", "legislat", "congreso",
                 "parlament", "eleccion", "electoral", "candidat", "campana electoral", "cne ", "gobierno",
                 "ministro", "ministra", "canciller", "alcald", "prefect", "concejal", "partido", "consulta popular",
                 "referendum", "diplomat", "embajad", "cumbre", "sancion", "senado", "senator", "election",
                 "president", "minister", "parliament", "trump", "putin", "zelensk", "onu ", "otan",
                 "votacion", "veto", "decreto", "politic"],
    "economia": ["econom", "inflacion", "precio", "arancel", "impuesto", "tribut", "sri ", "presupuesto",
                 "deuda", "fmi", "banco central", "bolsa", "mercado", "exportac", "importac", "petrole",
                 "crudo", "dolar", "pib", "inversion", "empresa", "comercio", "subsidio", "combustible",
                 "tariff", "economy", "stocks", "oil ", "trade", "biess", "credito", "finanz", "fiscal"],
    "empleo": ["empleo", "desempleo", "trabajador", "salario", "sueldo", "despido", "huelga", "sindicat",
               "plazas de trabajo", "jornada laboral", "iess", "jubil", "pension", "teletrabajo", "contratacion laboral",
               "workers", "jobs", "strike"],
    "seguridad": ["asesin", "homicid", "crimen", "sicari", "balacera", "disparo", "baleado", "balead", "robo",
                  "asalto", "extorsion", "secuestr", "narco", "droga", "cocaina", "banda", "pandilla", "policia",
                  "militar", "operativo", "detenid", "aprehendid", "captur", "carcel", "penitenciar", "presos",
                  "reos", "violencia", "muerto", "ataque", "explosiv", "terroris", "guerra", "bombardeo", "misil",
                  "ejercito", "killed", "attack", "shooting", "police", "war ", "military", "crime", "apunal"],
    "justicia": ["fiscal general", "fiscalia", "juez", "jueza", "tribunal", "corte ", "sentencia", "audiencia",
                 "juicio", "condena", "prision preventiva", "proceso judicial", "demanda", "corrupcion",
                 "peculado", "contraloria", "judicial", "caso ", "supreme court", "court", "judge", "trial",
                 "lawsuit", "indict", "absuel", "apelacion", "habeas"],
    "obras_servicios": ["obra", "municipio", "alcantarill", "agua potable", "sin agua", "interagua", "emapag",
                        "corte de luz", "cortes de luz", "apagon", "energia electrica", "cnel", "electric",
                        "basura", "recoleccion", "bache", "asfalt", "pavimen", "poste", "puente", "parque",
                        "alumbrado", "sanitari", "regeneracion", "vivienda", "megavatios", "termoelectric",
                        "hidroelectric", "servicio de", "infraestructura", "mantenimiento"],
    "movilidad": ["transito", "trafico", "atm ", "metrovia", "aerovia", "bus ", "buses", "transporte",
                  "vehicul", "matricul", "placa", "pico y placa", "carretera", "via ", "vias ", "aeropuerto",
                  "vuelo", "aerolinea", "taxi", "conductor", "accidente de transito", "siniestro vial", "peaje",
                  "flight", "airline", "traffic"],
    "riesgos_clima": ["lluvia", "llovera", "inund", "aguacero", "clima", "pronostico", "inamhi", "nino",
                      "sismo", "temblor", "terremoto", "deslave", "desliz", "incendio forestal", "sequia",
                      "oleaje", "aguaje", "tsunami", "volcan", "huracan", "tormenta", "riesgos", "emergencia",
                      "simulacro", "earthquake", "flood", "storm", "hurricane", "wildfire", "climate"],
    "salud": ["salud", "hospital", "medic", "enfermed", "dengue", "virus", "vacun", "paciente", "msp ",
              "epidem", "brote", "cancer", "farmac", "medicament", "clinica", "health", "disease", "outbreak",
              "tosferina", "sarampion", "hemodialisis", "fibrosis"],
    "educacion": ["educacion", "escuela", "colegio", "universidad", "estudiant", "docente", "profesor",
                  "clases", "matricula escolar", "becas", "espol", "senescyt", "ministerio de educacion",
                  "school", "students", "university"],
    "sociedad_cultura": ["cultura", "festival", "teatro", "museo", "arte", "musica", "libro", "fiestas",
                         "feriado", "tradicion", "migra", "migrante", "religio", "iglesia", "papa ",
                         "comunidad", "familia", "ninos", "mujeres", "indigena", "derechos humanos",
                         "mascota", "animales", "patrimonio", "cine", "pelicula", "concierto", "exposicion"],
    "entretenimiento_deporte": ["futbol", "partido de", "gol", "liga", "barcelona sc", "emelec", "seleccion",
                                "mundial", "copa ", "torneo", "tenis", "atp", "deport", "olimp", "campeon",
                                "jugador", "entrenador", "estadio", "farandula", "actor", "actriz", "cantante",
                                "show", "serie", "netflix", "ronaldo", "messi", "football", "soccer", "nba",
                                "concierto", "celebrity", "humor", "comic"],
}
# Si dos categorias empatan, gana la que esta antes (lo especifico antes que lo general).
PRIORIDAD = ["riesgos_clima", "salud", "educacion", "movilidad", "obras_servicios", "empleo",
             "entretenimiento_deporte", "justicia", "seguridad", "economia", "sociedad_cultura", "politica"]

# Temas viejos (catalogo de 20) como senal debil cuando las palabras no alcanzan.
TEMA_A_CATEGORIA = {
    "Elecciones": "politica", "Asamblea/Leyes": "politica", "Ejecutivo": "politica",
    "Justicia/Corrupcion": "justicia", "Fiscal/Presupuesto": "economia", "Impuestos": "economia",
    "Petroleo/Energia": "economia", "Empleo": "empleo", "Precios/Costo de vida": "economia",
    "Comercio/Inversion": "economia", "Narcotrafico": "seguridad", "Crimen/Violencia": "seguridad",
    "Carceles": "seguridad", "Policia/Militar": "seguridad", "Salud": "salud", "Educacion": "educacion",
    "Ambiente": "riesgos_clima", "Migracion": "sociedad_cultura", "Cultura/Comunidad": "sociedad_cultura",
}


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"[^a-z0-9%]+", " ", s).strip() + " "


_PATRONES = {cat: [(p, re.compile(r"(?<![a-z0-9])" + re.escape(norm(p).strip()) +
                                  (r"(?![a-z0-9])" if p.endswith(" ") else "")))
                   for p in ps] for cat, ps in REGLAS.items()}


def _hits(texto_n, cat):
    return [p.strip() for p, rx in _PATRONES[cat] if rx.search(texto_n)]


def clasificar_reglas(titular, resumen="", temas=None):
    """(categoria o None, razon de una linea). Palabras del titular valen el
    doble que las del resumen."""
    tn, rn = norm(titular), norm(resumen)
    puntos, por_que = {}, {}
    for cat in CATEGORIAS:
        ht, hr = _hits(tn, cat), _hits(rn, cat)
        p = 2 * len(ht) + len(set(hr) - set(ht))
        if p:
            puntos[cat], por_que[cat] = p, (ht + [h for h in hr if h not in ht])[:3]
    if puntos:
        mejor = max(puntos.values())
        cat = next(c for c in PRIORIDAD if puntos.get(c) == mejor)
        return cat, "por palabras: %s" % ", ".join(por_que[cat])
    for t in (temas or []):
        c = TEMA_A_CATEGORIA.get(t)
        if c:
            return c, "por el tema %s" % t
    return None, "ninguna palabra de categoria"


# ------------------------------------------------------------------ C1: tipo y quien
_SEGUN = re.compile(r"\b(?:seg[uú]n|de acuerdo con|asegur[oó]|afirm[oó]|dijo|declar[oó]|denunci[oó]|"
                    r"advirti[oó]|sostuvo|explic[oó]|indic[oó]|se[nñ]al[oó]|aleg[oó]|acus[oó]|"
                    r"exigen?|piden?|reclaman?|denuncian|expone|revela|"
                    r"according to|said|says|claims?)\b", re.I)
_QUIEN_SEGUN = re.compile(r"\b(?:seg[uú]n|de acuerdo con|according to)\s+(?:el|la|los|las|the)?\s*"
                          r"([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+(?:de|del|la|los|y)?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+){0,5})")
_QUIEN_SUJETO = re.compile(r"^([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+(?:de|del|la|los)?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+){0,4})\s+"
                           r"(?:asegura|afirma|dice|dijo|declara|denuncia|advierte|anuncia|anuncio|anunció|"
                           r"revela|reveló|pide|exige|plantea|propone|sostiene|says|said|warns|announces)\b")
_ANUNCIO = re.compile(r"\b(anunci|alista|prepara|preve|planea|planifica|convoca|iniciar[aá]|ser[aá]n?\b|"
                      r"tendr[aá]|llegar[aá]|habr[aá]|proyecta|propone|plantea|ampl[ií]a el plazo|"
                      r"abrir[aá]|cerrar[aá]|condecorar[aá]|podr[ií]an?\b|will |plans? to|to launch|"
                      # cualquier verbo en futuro o condicional: cambiara, llegara, reemplazara, tardaria
                      r"\b\w+(?:ar|er|ir)(?:á|án|ía|ían)\b)", re.I)
_DATO = re.compile(r"(\d+(?:[.,]\d+)?\s*%|\bregistr[aó]|\bincremento\b|\bcrec(?:e|io|ió)\b|\bcay[oó]\b|"
                   r"\bsube\b|\bbaja\b|\bcifra|\bestad[ií]stic|\bencuesta|\bsondeo|\bpromedio\b|"
                   r"\bpoll\b|\bpron[oó]stico|\bsurvey\b|"
                   r"\b\d{2,}(?:[.,]\d+)?\s+(?:casos|personas|muertos|homicidios|millones|d[oó]lares|megavatios|mw)\b)",
                   re.I)


def quien_afirma(titular, resumen=""):
    """Quien hace la afirmacion, tomado LITERAL del texto, o "" si el medio la
    cuenta como hecho propio."""
    for texto in (titular or "", resumen or ""):
        m = _QUIEN_SEGUN.search(texto) or _QUIEN_SUJETO.search(texto)
        if m:
            return m.group(1).strip()
    return ""


def tipo_reglas(titular, resumen=""):
    """(tipo, quien). Mismo orden que el CSV: una cifra que el medio publica es
    'dato'; algo atribuido a alguien ('segun X', 'X asegura') es 'declaracion';
    lo que va a pasar es 'anuncio'; lo que ya paso es 'accion'."""
    t = titular or ""
    quien = quien_afirma(titular, resumen)
    # "Omar Paganini: «America Latina tiene que...»": nombre, dos puntos y cita.
    cita = re.search(r":\s*[«“\"]", t) is not None
    if _SEGUN.search(t) or _QUIEN_SUJETO.search(t) or cita or t.strip().startswith(("“", '"', "«")):
        return "declaracion", quien
    if _DATO.search(t):
        return "dato", quien
    if _ANUNCIO.search(t):
        return "anuncio", quien
    return "accion", quien


def candado(cat, tipo, quien, razon, titular, resumen):
    """Lo que dijo la IA, recortado a valores validos. 'quien' se descarta si
    no aparece en el titular o el resumen (la IA no puede inventar a quien
    atribuirle algo)."""
    cat = cat if cat in CATEGORIAS else None
    tipo = tipo if tipo in TIPOS else None
    quien = str(quien or "").strip()
    # Palabras completas (revision de Codex): norm() deja un espacio a cada lado,
    # asi "Nobo" no pasa por estar dentro de "Noboa".
    if quien and (not norm(quien).strip() or norm(quien) not in norm(titular + " " + resumen)):
        quien = ""
    razon = re.sub(r"\s+", " ", str(razon or "")).strip()[:140]
    return cat, tipo, quien, razon


# ------------------------------------------------------------------ D: util / basura (internacional)
# Fase 24 (D). Antes de la IA, reglas: lo que casi nunca le sirve a un
# periodista de Guayaquil. La IA por lotes decide el resto; Fernando corrige
# con los botones Util/Basura (util_manual.json) y eso manda sobre todo.
_BASURA_PALABRAS = ["divorci", "farandula", "celebridad", "actor ", "actriz", "estrena", "documental",
                    "netflix", "horoscopo", "receta", "como funciona", "que es ", "por que ", "guia de",
                    "resumen del partido", "pronostico del clima", "se viste", "look ", "boda ", "romance",
                    "dies at", "muere a los", "murio a los", "celebrity", "box office", "trailer", "how to"]
_BASURA = [re.compile(r"(?<![a-z0-9])" + re.escape(norm(p).strip()) + (r"(?![a-z0-9])" if p.endswith(" ") else ""))
           for p in _BASURA_PALABRAS]


def util_reglas(titular, resumen="", categoria=""):
    """(util True/False/None, razon). None = las reglas no saben (decide la IA)."""
    t = (titular or "").strip()
    if len(t.split()) <= 3:
        return False, "titular roto o demasiado corto"
    tn = norm(t)
    for rx in _BASURA:
        if rx.search(tn):
            return False, "por palabras: farandula, explicativo o curiosidad"
    if categoria == "entretenimiento_deporte":
        return False, "entretenimiento o deporte de afuera"
    return None, ""


def candado_util(util, importa):
    u = str(util or "").strip().lower()
    u = True if u in ("si", "sí", "true") else (False if u in ("no", "false") else None)
    imp = re.sub(r"\s+", " ", str(importa or "")).strip()[:180] if u else ""
    return u, imp
