# -*- coding: utf-8 -*-
"""
funcionarios.py -- Fase 24 (B3b): funcionarios bajo seguimiento en X.

Regla de oro de Fernando: Spike tiene que ver el tuit ANTES de que lo publiquen
los medios. Via Apify (ya integrado): una sola consulta
"(from:A OR from:B ...) since:..." cada FUNC_MIN minutos (la hace
redes.pasada_funcionarios, con su propia parte del presupuesto). Aca se
procesa cada tuit nuevo:
  - tipo por reglas (anuncio / accion / declaracion / dato; ver tipo_rapido);
  - se registra en declaraciones.json a nombre del funcionario;
  - aviso inmediato al celular (ntfy, movil.py) con el texto y el enlace;
  - queda en el panel y se cuelga de la historia relacionada ("Lo que dijo el
    funcionario"); sin historia, cuenta como PRIMICIA (aun sin prensa);
  - se busca la primera nota de prensa que lo reporta (Google News RSS por
    funcionario, SOLO para eso) y se mide el ADELANTO en minutos.

funcionarios.json es editable (Fernando agrega desde el dashboard). No se
inventan usuarios: arranca con los dos del pedido.

Standalone: no importa monitor.py.
"""
import datetime as dt
import json
import os
import re
import threading
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "funcionarios.json")
ESTADO_PATH = os.path.join(HERE, "funcionarios_estado.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Spike/1.0"
PRENSA_CADA_MIN = 15
PRENSA_VENTANA_H = 48
_LOCK = threading.RLock()

_PLANTILLA = {
    "_ayuda": ("Funcionarios cuyos tuits Spike lee cada pocos minutos (via Apify). 'usuario' sin @. "
               "'activa': false para pausar. No agregues usuarios sin comprobar que existen."),
    "funcionarios": [
        {"usuario": "JohnReimberg", "nombre": "John Reimberg", "cargo": "Ministro del Interior", "area": "seguridad",
         "activa": True, "verificado": False},
        {"usuario": "MinInteriorEc", "nombre": "Ministerio del Interior", "cargo": "Ministerio del Interior",
         "area": "seguridad", "activa": True, "verificado": False},
    ],
}

# ------------------------------------------------------------------ tipo (reglas, Parte C1)
_ANUNCIO = re.compile(r"\b(anunci\w*|se viene|proximamente|pronto|vamos a|iremos|seguiremos|se construira|se ejecutara|"
                      r"permitira|sera|seran|llegara|llegaran|iniciara|arrancara|prevemos|preve|planea|proyecta|"
                      r"se realizara|implementaremos|haremos|daremos|tendremos|construiremos)\b")
_ACCION = re.compile(r"\b(capturamos|capturaron|capturado\w*|detuvimos|detenid\w*|aprehendid\w*|aprehendimos|"
                     r"incautamos|incautad\w*|decomisad\w*|allanamos|allanad\w*|desarticulamos|desarticulad\w*|"
                     r"inauguramos|inaugurad\w*|firmamos|firmad\w*|entregamos|entregad\w*|ejecutamos|"
                     r"rescatamos|rescatad\w*|neutralizad\w*|abatid\w*|retiramos|retirad\w*|clausurad\w*|"
                     r"sancionad\w*|aprobad\w*|se retiro|se firmo|se aprobo|culmino|culminamos)\b")
_DECLARACION = re.compile(r"\b(dijo|dije|aseguro|afirmo|segun|denuncio|denunciamos|acuso|acusamos|senalo|indico|"
                          r"advirtio|advertimos|manifesto|sostuvo|critico|rechazamos|rechazo|exigimos|pedimos|creemos|"
                          r"consideramos|lamentamos|repudiamos)\b")
_DATO = re.compile(r"\b\d[\d.,]*\s*(%|por ciento|personas|detenidos|kilos|toneladas|millones|dolares|usd|casos|muertes|"
                   r"homicidios|operativos)\b")


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tipo_rapido(texto):
    """Primera aproximacion SIN IA (Parte C1 hace la version completa):
    accion > dato > anuncio > declaracion; None si no hay senal clara."""
    t = _norm(texto)
    if _ACCION.search(t):
        return "accion"
    if _DATO.search(t):
        return "dato"
    if _ANUNCIO.search(t):
        return "anuncio"
    if _DECLARACION.search(t) or '"' in (texto or "") or "“" in (texto or ""):
        return "declaracion"
    return None


# ------------------------------------------------------------------ config / estado
def config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        d = _PLANTILLA
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    except Exception:
        d = {"funcionarios": []}
    return d


def activos():
    return [f for f in (config().get("funcionarios") or []) if f.get("usuario") and f.get("activa", True)]


def _estado():
    try:
        with open(ESTADO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tuits": {}}


def _guardar(e):
    tmp = ESTADO_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(tmp, ESTADO_PATH)


def consulta(horas, since_fn):
    us = [f["usuario"].lstrip("@") for f in activos()]
    if not us:
        return ""
    bloque = us[0] if len(us) == 1 else "(%s)" % " OR ".join("from:%s" % u for u in us)
    if len(us) == 1:
        bloque = "from:%s" % us[0]
    return "%s %s" % (bloque, since_fn(horas))


# ------------------------------------------------------------------ tuits nuevos
def procesar_tuits(tweets, fecha_iso_fn, notificar=True, ahora=None):
    """Tweets crudos de Apify. Devuelve la lista de los NUEVOS ya procesados."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    por_usuario = {f["usuario"].lower(): f for f in activos()}
    nuevos = []
    with _LOCK:
        e = _estado()
        tu = e.setdefault("tuits", {})
        for t in tweets or []:
            tid = str(t.get("id") or "")
            u = ((t.get("author") or {}).get("userName") or "").lstrip("@")
            f = por_usuario.get(u.lower())
            if not tid or tid in tu or f is None:
                continue  # solo tuits PROPIOS de un funcionario seguido (no respuestas de terceros)
            texto = t.get("text") or ""
            if texto.startswith("RT @"):
                continue
            fecha = fecha_iso_fn(t.get("createdAt", "")) or ahora.isoformat()
            reg = {"id": tid, "usuario": u, "nombre": f.get("nombre") or u, "cargo": f.get("cargo") or "",
                   "area": f.get("area") or "", "texto": texto[:600], "url": t.get("url") or "",
                   "fecha": fecha, "visto": ahora.isoformat(), "tipo": tipo_rapido(texto), "prensa": None,
                   "notificado": False}
            tu[tid] = reg
            nuevos.append(reg)
        # 30 dias de historial
        corte = (ahora - dt.timedelta(days=30)).isoformat()
        for k in [k for k, v in tu.items() if v.get("fecha", "") < corte]:
            del tu[k]
        _guardar(e)
    for reg in nuevos:
        try:
            import declaraciones
            declaraciones.registrar(reg["nombre"], reg["cargo"], reg["texto"], reg["fecha"], "X (@%s)" % reg["usuario"],
                                    reg["url"])
        except Exception:
            pass
        if notificar:
            reg["notificado"] = _avisar(reg)
    if nuevos and notificar:
        with _LOCK:
            e = _estado()
            for reg in nuevos:
                if reg["id"] in e.get("tuits", {}):
                    e["tuits"][reg["id"]]["notificado"] = reg["notificado"]
            _guardar(e)
    return nuevos


def _avisar(reg):
    """ntfy al celular (movil.py). La notificacion en la PC es de la Parte F."""
    try:
        import movil
        conf = movil.cargar_config()
        if not conf.get("avisos_activos"):
            return False
        tipo = {"anuncio": "anuncia", "accion": "informa una accion", "declaracion": "declara",
                "dato": "da un dato"}.get(reg.get("tipo"), "publico")
        return bool(movil.enviar(conf, "%s %s (X)" % (reg["nombre"], tipo), reg["texto"][:300], prioridad=4,
                                 etiquetas=["funcionario"], click=reg["url"]))
    except Exception:
        return False


# ------------------------------------------------------------------ adelanto frente a la prensa
_STOP = set("de la el los las y en a que por para con del se un una al lo su sus es mas como hoy este esta".split())


def _tokens(s):
    return {w for w in re.findall(r"[a-z0-9]{4,}", _norm(s)) if w not in _STOP}


def _gn(q):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "es-419", "gl": "EC", "ceid": "EC:es-419"})


def _rss(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        raiz = ET.fromstring(r.read())
    out = []
    for it in raiz.iter("item"):
        try:
            f = parsedate_to_datetime(it.findtext("pubDate") or "")
        except Exception:
            f = None
        out.append({"titulo": it.findtext("title") or "", "link": it.findtext("link") or "", "fecha": f,
                    "medio": (it.find("source").text if it.find("source") is not None else "")})
    return out


def buscar_prensa(ahora=None, rss_fn=None):
    """Para cada tuit de las ultimas PRENSA_VENTANA_H horas sin prensa todavia:
    la primera nota (Google News, por nombre del funcionario) publicada DESPUES
    del tuit que comparte al menos 3 palabras significativas con el. Devuelve
    cuantas encontro."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    rss_fn = rss_fn or (lambda nombre: _rss(_gn('"%s"' % nombre)))
    e = _estado()
    ult = e.get("prensa_ultima")
    if ult and (ahora - dt.datetime.fromisoformat(ult)).total_seconds() < PRENSA_CADA_MIN * 60:
        return 0
    pend = [t for t in (e.get("tuits") or {}).values() if not t.get("prensa")
            and (ahora - dt.datetime.fromisoformat(t["fecha"])).total_seconds() <= PRENSA_VENTANA_H * 3600]
    encontrados = 0
    por_nombre = {}
    for t in pend:
        por_nombre.setdefault(t["nombre"], []).append(t)
    for nombre, ts in por_nombre.items():
        try:
            notas = rss_fn(nombre)
        except Exception:
            continue
        for t in ts:
            ft = dt.datetime.fromisoformat(t["fecha"])
            tk = _tokens(t["texto"])
            cand = [n for n in notas if n["fecha"] and n["fecha"] >= ft and len(tk & _tokens(n["titulo"])) >= 3]
            if cand:
                n = min(cand, key=lambda x: x["fecha"])
                t["prensa"] = {"titulo": n["titulo"], "link": n["link"], "medio": n["medio"],
                               "fecha": n["fecha"].isoformat(),
                               "adelanto_min": round((n["fecha"] - ft).total_seconds() / 60, 1)}
                encontrados += 1
    with _LOCK:
        e2 = _estado()
        for t in pend:
            if t.get("prensa") and t["id"] in e2.get("tuits", {}):
                e2["tuits"][t["id"]]["prensa"] = t["prensa"]
        e2["prensa_ultima"] = ahora.isoformat()
        _guardar(e2)
    return encontrados


# ------------------------------------------------------------------ historias y panel
def colgar_en_historias(stories, ahora=None):
    """Agrega h['dijo_funcionario'] a la historia relacionada (mismo nombre o
    palabras en comun) y devuelve las primicias: tuits SIN historia que traen un
    hecho (accion, dato o anuncio). Una opinion o un saludo sin historia no lo es."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    tuits = sorted((_estado().get("tuits") or {}).values(), key=lambda t: t["fecha"], reverse=True)
    tuits = [t for t in tuits if (ahora - dt.datetime.fromisoformat(t["fecha"])).total_seconds() <= 72 * 3600]
    primicias = []
    tok_h = [(s, _tokens((s.get("titular") or "") + " " + (s.get("resumen") or ""))) for s in stories]
    for t in tuits:
        tk = _tokens(t["texto"])
        nombre = _norm(t["nombre"])
        mejor, puntos = None, 0
        for s, th in tok_h:
            comun = len(tk & th)
            if nombre and nombre in _norm(s.get("titular", "") + " " + s.get("resumen", "")):
                comun += 2
            if comun > puntos:
                mejor, puntos = s, comun
        if mejor is not None and puntos >= 4:
            mejor.setdefault("dijo_funcionario", []).append(
                {k: t.get(k) for k in ("nombre", "cargo", "usuario", "texto", "url", "fecha", "tipo", "prensa")})
        elif t.get("tipo") in ("accion", "dato", "anuncio"):
            # Revision de Codex: un saludo u opinion sin historia no es primicia.
            # Solo cuenta lo que trae un hecho (accion, dato o anuncio).
            primicias.append(t)
    return primicias


def dashboard(primicias=None):
    e = _estado()
    tuits = sorted((e.get("tuits") or {}).values(), key=lambda t: t["fecha"], reverse=True)
    adelantos = [t["prensa"]["adelanto_min"] for t in tuits if t.get("prensa")]
    adelantos.sort()
    return {"funcionarios": [{k: f.get(k) for k in ("usuario", "nombre", "cargo", "area", "activa")}
                             for f in (config().get("funcionarios") or [])],
            "tuits": tuits[:60], "primicias": [t["id"] for t in (primicias or [])],
            "adelanto": {"n": len(adelantos),
                         "mediana_min": adelantos[len(adelantos) // 2] if adelantos else None,
                         "promedio_min": round(sum(adelantos) / len(adelantos), 1) if adelantos else None},
            "ultima_consulta": e.get("ultima_consulta")}
