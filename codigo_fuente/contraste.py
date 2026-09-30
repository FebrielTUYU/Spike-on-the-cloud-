# -*- coding: utf-8 -*-
"""
Fase 18 (P2-11) -- Contraste rediseñado: documento oficial primero, hallazgo o nada.

Antes: 1333 historias "sin_datos", 212 "pendiente", 18 "coincide" -- y
"coincide" significaba "otro medio dice lo mismo" (medio contra medio), justo
lo que NO sirve como descubrimiento. Criterio de Fernando: si es
gubernamental, se contrasta con documentacion oficial; si son declaraciones,
con medios y con lo que el mismo actor dijo antes; si es un hecho, se
comparan las cifras entre medios.

Estados:
- "hallazgo": discrepancia con cita verificable de las DOS partes (cifras
  distintas entre medios, o un actor que dijo lo contrario antes).
- "documento_oficial": hay respaldo primario (boletin de la Asamblea,
  Registro Oficial, INEC, BCE, contrato SERCOP).
- "corroborado_medios": otros medios dicen lo mismo (el viejo "coincide";
  visualmente secundario, nunca como hallazgo).
- "sin_hallazgo": nada que reportar (para un acto oficial dice
  explicitamente "No se encontro el documento oficial" -- eso ya es un dato:
  se anuncia algo que no esta publicado).

Standalone (no importa monitor.py): todo deterministico y sin red, recibe lo
que el pipeline ya calculo (boletines de oficial_cache.json, contratos
SERCOP de la historia, declaraciones de la Fase 5). La clasificacion puede
refinarse con IA (clase_ia), pero el modulo funciona sin ella.
"""
import re
import unicodedata

CLASES = ("acto_oficial", "declaracion", "hecho")
ESTADOS = ("hallazgo", "documento_oficial", "corroborado_medios", "sin_hallazgo")


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9$ ]+", " ", s)


_STOP = set("""de la el en los las del y a que por con para un una se su al es lo como mas tras sobre este
esta estos estas fue son han sera desde hasta entre sus sin ante bajo segun durante contra cual cuales
donde cuando porque pero tambien ademas hoy ayer esta""".split())
# palabras institucionales demasiado genericas para "probar" que un boletin
# habla del mismo acto
_GENERICAS = set("""asamblea nacional gobierno ecuador ministerio ministro ministra presidente presidenta
republica pais aprueba aprobo aprobada aprobado anuncia anuncio publica nueva nuevo ley leyes debate segundo
primer primero pleno sesion proyecto informe articulo articulos norma actividades invierte invertira
inversion millones dolares cifra cifras""".split())
# sinonimos minimos para no perder un documento por el vocabulario de la nota
# (caso real: la nota dice "menores", el boletin de la Asamblea "ninas, ninos y
# adolescentes")
_SINONIMOS = {"menores": {"ninos", "ninas", "adolescentes"}, "ninos": {"menores"}, "adolescentes": {"menores"},
              "carcel": {"prision", "penas"}, "penas": {"carcel", "prision"}}


def _tokens_exp(texto):
    t = _tokens(texto)
    for w in list(t):
        t |= _SINONIMOS.get(w, set())
    return t


def _tokens(texto):
    return {w for w in _norm(texto).split() if len(w) >= 4 and w not in _STOP}


# ------------------------- 1. clasificar la afirmacion -------------------------
_ACTO_FUERTE = re.compile(r"\b(ley|leyes|reforma|reformas|decreto|decretos|codigo|reglamento|ordenanza|"
                          r"resolucion|contrato|contratos|licitacion|adjudic\w*|presupuesto|"
                          r"registro oficial|corte programado|cortes programados|horarios? de cortes?)\b")
_DECLARACION = re.compile(r"\b(dijo|dice|afirma|afirmo|asegura|aseguro|declaro|declara|denuncia|denuncio|"
                          r"advierte|advirtio|sostiene|sostuvo|senalo|critica|critico|responde|respondio|"
                          r"acusa|acuso|niega|nego|admite|admitio|reconoce|reconocio|promete|prometio)\b")
_ACTO_DEBIL = re.compile(r"\b(obra|obras|iva|subsidio|subsidios|tarifa|tarifas|inec|banco central|bce|"
                         r"cifra oficial|aprueba|aprobo|aprobada|aprobado|sanciona|sancionara)\b")


def clasificar(titular, resumen=""):
    """acto_oficial / declaracion / hecho, por reglas (sin IA). Un acto
    'fuerte' (ley, decreto, contrato...) gana; si no, un verbo de
    declaracion; si no, un acto 'debil'; si no, hecho."""
    t = _norm(titular)
    if _ACTO_FUERTE.search(t):
        return "acto_oficial"
    if _DECLARACION.search(t) or re.search(r"[\"“”«»]", titular or ""):
        return "declaracion"
    if _ACTO_DEBIL.search(t) or _ACTO_FUERTE.search(_norm(resumen)):
        return "acto_oficial"
    return "hecho"


# ------------------------- 2. acto oficial -> documento primario -------------------------
def buscar_documento(texto, boletines, contratos=None, minimo=3):
    """Mejor boletin/contrato que comparte >= 'minimo' palabras especificas
    (sin contar las institucionales genericas) con el texto de la nota.
    None si nada alcanza: mejor "no se encontro" que un documento ajeno."""
    base = _tokens_exp(texto) - _GENERICAS
    mejor, mejor_n = None, 0
    for b in boletines or []:
        comunes = base & (_tokens((b.get("titulo") or "") + " " + (b.get("resumen") or "")) - _GENERICAS)
        if len(comunes) >= minimo and len(comunes) > mejor_n:
            mejor, mejor_n = {"fuente": b.get("fuente", ""), "titulo": b.get("titulo", ""),
                              "link": b.get("link", ""), "fecha": b.get("fecha", ""),
                              "comunes": sorted(comunes)}, len(comunes)
    for c in contratos or []:
        comunes = base & (_tokens((c.get("objeto") or "") + " " + (c.get("entidad") or "")) - _GENERICAS)
        if len(comunes) >= minimo and len(comunes) > mejor_n:
            mejor, mejor_n = {"fuente": "SERCOP", "titulo": c.get("objeto") or c.get("ocid", ""),
                              "link": c.get("link", ""), "fecha": c.get("fecha", ""),
                              "comunes": sorted(comunes)}, len(comunes)
    return mejor


# ------------------------- 3. hecho -> cifras entre medios -------------------------
_NUM_PALABRA = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
                "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "veinte": 20}
_MEDIDAS = {
    "muertos": r"muertos?|fallecidos?|victimas mortales|personas fallecidas|cadaveres",
    "heridos": r"heridos?|lesionados?",
    "detenidos": r"detenidos?|aprehendidos?|capturados?",
    "desaparecidos": r"desaparecidos?",
    "evacuados": r"evacuados?",
    "afectados": r"damnificados?|familias afectadas|viviendas afectadas",
}
_RE_MEDIDA = {k: re.compile(r"\b(\d{1,4}|" + "|".join(_NUM_PALABRA) + r")\s+(?:personas\s+)?(?:" + v + r")\b")
              for k, v in _MEDIDAS.items()}
_RE_MONTO = re.compile(r"(?:usd|\$)\s?(\d[\d.,]*)\s*(millones|mil)?")


# palabras de la propia cifra (medida o numero escrito): compartirlas no
# prueba que dos notas hablen del mismo hecho (caso real: "Seis aprehendidos
# ... droga" vs "Siete aprehendidos ... Metrovia")
_VOCAB_CIFRAS = set(_NUM_PALABRA) | {w for v in _MEDIDAS.values() for w in re.findall(r"[a-z]+", v)} | {
    "personas", "victimas", "mortales", "familias", "viviendas", "aprehendidos", "aprehendido"}


def _valor(txt):
    return _NUM_PALABRA.get(txt) if txt in _NUM_PALABRA else int(txt)


def _monto(num, escala):
    limpio = num.replace(".", "").replace(",", ".") if num.count(".") > 1 or ("," in num and "." in num) else \
        num.replace(",", ".") if num.count(",") == 1 and len(num.split(",")[1]) <= 2 else num.replace(".", "").replace(",", "")
    try:
        v = float(limpio)
    except ValueError:
        return None
    return v * (1e6 if escala == "millones" else 1e3 if escala == "mil" else 1)


def cifras(texto):
    """{medida: set(valores)} de un texto."""
    t = _norm(texto)
    out = {}
    for k, rx in _RE_MEDIDA.items():
        for m in rx.finditer(t):
            out.setdefault(k, set()).add(_valor(m.group(1)))
    for m in _RE_MONTO.finditer(t):
        v = _monto(m.group(1), m.group(2))
        if v:
            out.setdefault("monto", set()).add(round(v))
    return out


def hallazgo_cifras(fuentes):
    """Primera medida en la que DOS medios distintos dan valores sin nada en
    comun. Devuelve (medida, cita_a, cita_b) o None."""
    por_medio = []
    for f in fuentes or []:
        c = cifras((f.get("title") or "") + " " + (f.get("summary") or ""))
        if c:
            por_medio.append((f, c))
    for i in range(len(por_medio)):
        for j in range(i + 1, len(por_medio)):
            fa, ca = por_medio[i]
            fb, cb = por_medio[j]
            if (fa.get("outlet") or "") == (fb.get("outlet") or ""):
                continue
            # tienen que hablar del MISMO hecho (caso real: una historia mal
            # agrupada -- becas vs. red electrica de Azuay -- dio un falso
            # "hallazgo" de monto): 2+ palabras especificas en comun
            ta = _tokens(fa.get("title", "")) - _GENERICAS - _VOCAB_CIFRAS
            tb = _tokens(fb.get("title", "")) - _GENERICAS - _VOCAB_CIFRAS
            if len(ta & tb) < 2:
                continue
            for medida in ca.keys() & cb.keys():
                if not (ca[medida] & cb[medida]):
                    return medida, fa, fb
    return None


def _cita(f):
    return {"outlet": f.get("outlet", ""), "texto": f.get("title", ""), "link": f.get("link", ""),
            "fecha": f.get("date") or f.get("fecha") or ""}


# ------------------------- evaluacion completa -------------------------
def evaluar(h, boletines, clase_ia=None):
    """Contraste de UNA historia. 'boletines': items de oficial_cache.json
    (titulo/link/fecha/resumen/fuente). 'clase_ia': clasificacion hecha por
    la IA en el trabajador (si existe, gana sobre las reglas)."""
    titular, resumen = h.get("titular", ""), h.get("resumen", "") or ""
    fuentes = h.get("fuentes") or []
    clase = clase_ia if clase_ia in CLASES else clasificar(titular, resumen)
    outlets = {f.get("outlet") for f in fuentes if f.get("outlet")}
    res = {"clase": clase, "estado": "sin_hallazgo", "texto": "", "citas": [], "documento": None}

    # (b) declaracion que contradice lo que el mismo actor dijo antes
    contra = [c for c in (h.get("contradiccion_declaracion") or [])
              if (c.get("fuente_previa") or {}).get("texto")]
    if contra:
        previa = contra[0]["fuente_previa"]
        actual = h.get("declaracion") or {}
        res.update(estado="hallazgo", texto="Posible contradicción: %s dijo antes algo distinto (%s). Verificar."
                   % (actual.get("actor") or "el mismo actor", contra[0].get("explicacion") or contra[0].get("motivo") or ""),
                   citas=[{"outlet": actual.get("medio", ""), "texto": actual.get("texto") or titular,
                           "link": (fuentes[0].get("link") if fuentes else ""), "fecha": actual.get("fecha", "")},
                          {"outlet": previa.get("medio", ""), "texto": previa.get("texto", ""),
                           "link": previa.get("link", ""), "fecha": previa.get("fecha", "")}])
        return res

    # (c) cifras que no coinciden entre medios
    hc = hallazgo_cifras(fuentes)
    if hc:
        medida, fa, fb = hc
        res.update(estado="hallazgo",
                   texto="Los medios no coinciden en la cifra de %s. Verificar con la fuente oficial." % medida,
                   citas=[_cita(fa), _cita(fb)])

    # (a) acto oficial -> documento primario
    if clase == "acto_oficial":
        doc = buscar_documento(titular + " " + resumen, boletines, h.get("contratos"))
        res["documento"] = doc
        if res["estado"] != "hallazgo":
            if doc:
                res.update(estado="documento_oficial",
                           texto="Documento oficial encontrado: %s (%s)." % (doc["titulo"], doc["fuente"] or "fuente oficial"))
            else:
                res["texto"] = ("No se encontró el documento oficial en las fuentes revisadas (Asamblea, "
                                "Registro Oficial, INEC, BCE, SERCOP): se anuncia algo que no aparece publicado.")
        return res

    if res["estado"] == "hallazgo":
        return res
    if len(outlets) >= 2:
        res.update(estado="corroborado_medios",
                   texto="%d medios cuentan lo mismo; sin discrepancias en cifras%s." % (
                       len(outlets), " ni declaraciones previas contradictorias" if clase == "declaracion" else ""))
        return res
    res["texto"] = ("Sin declaraciones previas contradictorias registradas y un solo medio."
                    if clase == "declaracion" else "Un solo medio; nada que contrastar todavía.")
    return res
