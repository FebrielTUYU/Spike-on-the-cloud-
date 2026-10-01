# -*- coding: utf-8 -*-
"""
cuentas.py -- Fase 23 (Parte A): cuentas COMUNITARIAS de X y fuentes de
Facebook, editables desde el dashboard.

Pedido de Fernando (2026-09-30): "cuentas de noticias comunitarias: paginas o
personas que publican lo que pasa en los barrios (reportes ciudadanos,
denuncias vecinales, cuentas de sector tipo 'Guayaquil Denuncia', grupos de
barrio). Ahi se concentran las quejas." Y: "Nada se agrega solo: Fernando
aprueba cada una."

Dos cosas, sin red ni IA (solo lee lo que Spike ya junto):
  1) candidatas(): sugiere cuentas a partir de datos REALES -- nunca inventa un
     usuario. Fuentes:
       - comunidad.json: autores de X con varias quejas de Guayaquil;
       - x_cache.json (tweets por historia) y el feed de EmergenciasEc
         (redes_cache.json): autores de quejas de Guayaquil, cuentas que
         retuitean o que son mencionadas en esas quejas;
       - redes.red_emergencias(): quien mas interactua con EmergenciasEc.
     Se rankean por quejas de Guayaquil DISTINTAS que aportaron. Se descartan
     medios grandes e instituciones (xapi.clasificar_autor,
     social.es_cuenta_medio, seguidores, nombre institucional).
  2) agregar/descartar/quitar/pausar cuentas en x_cuentas_locales.json (tipo
     "comunitaria") y agregar/quitar URLs en facebook_fuentes.json.

Una cuenta "comunitaria" NUNCA cuenta como oficial en Alertas (es_oficial()),
y sus publicaciones entran a Comunidad como voz de la gente aunque el handle
parezca de noticias (comunidad.es_persona(comunitaria=True)).

Standalone: no importa monitor.py.
"""
import datetime as dt
import json
import os
import re
import threading
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

DIAS = float(os.environ.get("MONITOR_CUENTAS_DIAS", "7"))
MAX_SUGERIDAS = int(os.environ.get("MONITOR_CUENTAS_SUGERIDAS", "25"))
# Mas seguidores que esto = medio grande (dato real del autor, si Apify lo trae).
SEGUIDORES_MEDIO_GRANDE = int(os.environ.get("MONITOR_CUENTAS_SEG_MAX", "50000"))
TIPOS = ("oficial", "comunitaria", "local")

_LOCK = threading.RLock()
_USUARIO = re.compile(r"^@?([A-Za-z0-9_]{1,15})$")  # handles de X: solo ASCII
_MENCION = re.compile(r"@([A-Za-z0-9_]{2,15})")
_RT = re.compile(r"^RT @([A-Za-z0-9_]{2,15}):")
# Palabras genericas que social.es_cuenta_medio toma como "medio" pero que usan
# tambien las paginas de noticias de barrio ("GyeInforma", "NoticiasGuasmo").
# Se quitan del nombre ANTES de preguntar: si sigue pareciendo medio (marca de
# un medio, radio, tv, diario...), es un medio de verdad.
_GENERICOS = ("noticias", "noticia", "news", "informa", "digital", "online", "media", "medio", "press")
_INSTITUCION = re.compile(
    r"(policia|ecu ?911|transito|bombero|municip|alcald|prefect|minist|gobierno|secretar|asamblea|"
    r"fiscalia|judicatura|defensoria|cnel|interagua|emapag|segura ?ep|aeropuerto|dgac|conaie|ejercito|"
    r"armada|presidencia|consejo|contraloria|registro civil|iess|senescyt|riesgos|inamhi|inocar)")
# Bio que se presenta como medio formal (no como pagina de barrio).
_BIO_MEDIO = re.compile(r"(medio de comunicacion|periodico|diario |canal de television|canal de tv|"
                        r"\bradio\b|emisora|television|agencia de noticias|revista)")


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _usuario(u):
    m = _USUARIO.match((u or "").strip())
    return m.group(1) if m else ""


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _parse(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


# ------------------------------------------------------------------ tipos
def tipo_cuenta(c):
    """'oficial' | 'comunitaria' | 'local'. Las entradas viejas (Fase 18) no
    tienen 'tipo': se deduce de 'oficial'."""
    t = str((c or {}).get("tipo") or "").strip().lower()
    if t in TIPOS:
        return t
    return "oficial" if (c or {}).get("oficial") else "local"


def es_oficial(c):
    """Solo el tipo 'oficial' sube una alerta a 'confirmado oficial'. Una
    comunitaria con 'oficial': true por error sigue sin serlo."""
    return tipo_cuenta(c) == "oficial"


# ------------------------------------------------------------------ x_cuentas_locales.json
def _ruta_cuentas():
    import xapi
    return xapi.CUENTAS_PATH


def cargar_config():
    try:
        with open(_ruta_cuentas(), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("cuentas", [])
            d.setdefault("descartadas", [])
            return d
    except Exception:
        pass
    return {"cuentas": [], "descartadas": []}


def _guardar_config(d):
    ruta = _ruta_cuentas()
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)


def comunitarias(solo_activas=True):
    return [c for c in cargar_config()["cuentas"]
            if c.get("usuario") and tipo_cuenta(c) == "comunitaria" and (c.get("activa", True) or not solo_activas)]


def handles_comunitarios():
    """{usuario en minusculas} de las comunitarias activas (para comunidad.py)."""
    return {c["usuario"].lstrip("@").lower() for c in comunitarias()}


def _buscar(cfg, usuario):
    u = usuario.lower()
    for c in cfg["cuentas"]:
        if (c.get("usuario") or "").lstrip("@").lower() == u:
            return c
    return None


def agregar(usuario, nombre="", verificada=False):
    """Agrega una cuenta comunitaria (la aprueba Fernando desde el panel).
    Devuelve (ok, mensaje)."""
    u = _usuario(usuario)
    if not u:
        return False, "usuario invalido (solo letras, numeros y _; hasta 15)"
    with _LOCK:
        cfg = cargar_config()
        previa = _buscar(cfg, u)
        if previa is not None:
            t = tipo_cuenta(previa)
            if t != "comunitaria":
                return False, "@%s ya esta en la lista como %s" % (u, t)
            previa["activa"] = True
            _guardar_config(cfg)
            return True, "@%s ya estaba; quedo activa" % u
        cfg["cuentas"].append({"usuario": u, "nombre": (nombre or "").strip()[:80], "tipo": "comunitaria",
                               "oficial": False, "verificada": bool(verificada), "activa": True,
                               "agregada": _ahora().isoformat(), "origen": "panel (aprobada por Fernando)"})
        cfg["descartadas"] = [d for d in cfg["descartadas"] if (d.get("usuario") or "").lower() != u.lower()]
        _guardar_config(cfg)
    return True, "@%s agregada como comunitaria" % u


def descartar(usuario):
    u = _usuario(usuario)
    if not u:
        return False, "usuario invalido"
    with _LOCK:
        cfg = cargar_config()
        if not any((d.get("usuario") or "").lower() == u.lower() for d in cfg["descartadas"]):
            cfg["descartadas"].append({"usuario": u, "ts": _ahora().isoformat()})
        _guardar_config(cfg)
    return True, "@%s descartada (no se vuelve a sugerir)" % u


def quitar(usuario):
    """Solo comunitarias: las oficiales/locales se editan a mano en el archivo."""
    u = _usuario(usuario)
    with _LOCK:
        cfg = cargar_config()
        c = _buscar(cfg, u) if u else None
        if c is None or tipo_cuenta(c) != "comunitaria":
            return False, "@%s no es una cuenta comunitaria seguida" % (u or usuario)
        cfg["cuentas"].remove(c)
        _guardar_config(cfg)
    return True, "@%s quitada" % u


def activar(usuario, activa):
    u = _usuario(usuario)
    with _LOCK:
        cfg = cargar_config()
        c = _buscar(cfg, u) if u else None
        if c is None or tipo_cuenta(c) != "comunitaria":
            return False, "@%s no es una cuenta comunitaria seguida" % (u or usuario)
        c["activa"] = bool(activa)
        _guardar_config(cfg)
    return True, "@%s %s" % (u, "activa" if activa else "en pausa")


# ------------------------------------------------------------------ Facebook
_FB = re.compile(r"^https?://(?:www\.|m\.|web\.|mbasic\.)?facebook\.com/(.+)$", re.I)


def normalizar_url_facebook(url, tipo):
    """URL publica de Facebook -> forma canonica, o "" si no sirve. Grupos:
    tienen que ser /groups/<algo>. Paginas: cualquier ruta que no sea de
    grupo, login, busqueda ni una publicacion suelta."""
    m = _FB.match((url or "").strip())
    if not m:
        return ""
    ruta = m.group(1).split("?", 1)[0].split("#", 1)[0].strip("/")
    if not ruta:
        return ""
    primero = ruta.split("/", 1)[0].lower()
    if tipo == "grupos":
        partes = ruta.split("/")
        if primero != "groups" or len(partes) < 2 or not partes[1]:
            return ""
        return "https://www.facebook.com/groups/%s" % partes[1]
    if primero in ("groups", "login", "search", "watch", "share", "sharer.php", "hashtag", "events", "marketplace"):
        return ""
    if primero == "profile.php":
        return "https://www.facebook.com/" + m.group(1).split("#", 1)[0].strip("/")
    return "https://www.facebook.com/%s" % ruta.split("/", 1)[0]


def _cargar_fb():
    import facebook
    try:
        with open(facebook.FUENTES_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    base = dict(facebook._PLANTILLA)
    base.update(d)
    base["paginas"] = [u for u in (base.get("paginas") or []) if isinstance(u, str)]
    base["grupos"] = [u for u in (base.get("grupos") or []) if isinstance(u, str)]
    return base, facebook.FUENTES_PATH


def fuentes_facebook():
    d, _ = _cargar_fb()
    return {"paginas": list(d["paginas"]), "grupos": list(d["grupos"])}


def fb_agregar(tipo, url):
    if tipo not in ("paginas", "grupos"):
        return False, "tipo invalido (paginas o grupos)"
    canon = normalizar_url_facebook(url, tipo)
    if not canon:
        return False, ("no es una direccion de %s de Facebook (ej.: %s)"
                       % ("grupo" if tipo == "grupos" else "pagina",
                          "https://www.facebook.com/groups/nombre" if tipo == "grupos"
                          else "https://www.facebook.com/NombreDeLaPagina"))
    with _LOCK:
        d, ruta = _cargar_fb()
        if canon.lower() in {u.lower().rstrip("/") for u in d[tipo]}:
            return False, "ya estaba en la lista"
        d[tipo].append(canon)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    return True, "agregada: %s" % canon


def fb_quitar(tipo, url):
    if tipo not in ("paginas", "grupos"):
        return False, "tipo invalido"
    with _LOCK:
        d, ruta = _cargar_fb()
        antes = len(d[tipo])
        d[tipo] = [u for u in d[tipo] if u.strip().rstrip("/").lower() != (url or "").strip().rstrip("/").lower()]
        if len(d[tipo]) == antes:
            return False, "no estaba en la lista"
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    return True, "quitada"


# ------------------------------------------------------------------ descubrimiento
def _es_medio_o_institucion(usuario, info=None):
    """True si NO sirve como cuenta comunitaria: institucion, medio grande o
    politico. 'info' = author de un tweet real (nombre, bio, seguidores), si se
    tiene."""
    info = dict(info or {})
    nombre = info.get("name") or ""
    # Apify suele traer 'description' vacio y la bio real en profile_bio.
    bio = info.get("description") or ((info.get("profile_bio") or {}).get("description") or "")
    info["description"] = bio
    if _BIO_MEDIO.search(_norm(bio)):
        return True
    try:
        import xapi
        tipo = xapi.clasificar_autor({"author": dict(info, userName=usuario)})
        if tipo in ("institucion", "politico"):
            return True
        if usuario.lower() in xapi.CUENTAS_INSTITUCION:
            return True
    except Exception:
        pass
    if _INSTITUCION.search(_norm(usuario + " " + nombre)):
        return True
    try:
        seg = int(info.get("followers") or 0)
    except Exception:
        seg = 0
    if seg >= SEGUIDORES_MEDIO_GRANDE:
        return True
    try:
        import social
        limpio = [_norm(x) for x in (usuario, nombre)]
        for g in _GENERICOS:
            limpio = [x.replace(g, " ") for x in limpio]
        if social.es_cuenta_medio(*limpio):
            return True
    except Exception:
        pass
    return False


def _clave_texto(texto):
    t = re.sub(r"https?://\S+", " ", _norm(texto))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()[:120]


def _queja_gye(texto):
    """(categoria, barrio) si el texto es una queja de Guayaquil, si no None."""
    import comunidad
    if not texto or not comunidad.es_de_guayaquil(texto):
        return None
    cat = comunidad.categorizar(texto)
    if not cat:
        return None
    return cat, comunidad.detectar_barrio(texto) or comunidad.SIN_SECTOR


def _leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _fecha_tweet(t):
    import xapi
    return _parse(xapi.fecha_iso(t.get("createdAt", "")))


def candidatas(ahora=None, top=MAX_SUGERIDAS, incluir_descartadas=False):
    """Cuentas sugeridas, de mayor a menor numero de quejas de Guayaquil
    DISTINTAS aportadas en los ultimos DIAS dias. Cada una trae de donde
    salio, un ejemplo real y si se la vio como autora de tweets reales
    ('verificada': la cuenta existe). Nunca inventa usuarios: todo sale de los
    archivos que Spike ya escribio."""
    import comunidad
    import redes
    import xapi
    ahora = ahora or _ahora()
    corte = ahora - dt.timedelta(days=DIAS)
    cand = {}
    info_autor = {}

    def c_de(u):
        k = u.lower()
        if k not in cand:
            cand[k] = {"usuario": u, "quejas": set(), "menciones": set(), "interacciones": 0, "ejemplo": None,
                       "barrios": {}, "categorias": {}, "origen": set(), "autor_visto": False}
        return cand[k]

    def aporta(u, texto, url, fecha, origen, cat_barrio):
        c = c_de(u)
        clave = _clave_texto(texto)
        if clave in c["quejas"]:
            return
        c["quejas"].add(clave)
        c["origen"].add(origen)
        cat, barrio = cat_barrio
        c["categorias"][cat] = c["categorias"].get(cat, 0) + 1
        c["barrios"][barrio] = c["barrios"].get(barrio, 0) + 1
        ej = c["ejemplo"]
        if ej is None or (fecha or "") > (ej.get("fecha") or ""):
            c["ejemplo"] = {"texto": (texto or "")[:280], "url": url or "", "fecha": fecha or ""}

    def menciona(u, texto, url, fecha, origen):
        c = c_de(u)
        c["menciones"].add(_clave_texto(texto))
        c["origen"].add(origen)
        if c["ejemplo"] is None:
            c["ejemplo"] = {"texto": (texto or "")[:280], "url": url or "", "fecha": fecha or "", "mencion": True}

    # 1) comunidad.json: autores de X con quejas de Guayaquil (ya son personas).
    reg = _leer_json(comunidad.COMUNIDAD_PATH)
    for p in (reg.get("posts") or {}).values():
        if p.get("fuente") != "x":
            continue
        f = _parse(p.get("fecha"))
        u = _usuario(p.get("autor"))
        if not u or not f or f < corte:
            continue
        aporta(u, p.get("texto"), p.get("url"), p.get("fecha"), "comunidad",
               (p.get("categoria"), p.get("barrio") or comunidad.SIN_SECTOR))
        c_de(u)["autor_visto"] = True

    # 2) x_cache.json: tweets reales ya pagados para otras capas.
    xc = _leer_json(xapi.CACHE_PATH)
    for h in (xc.get("historias") or {}).values():
        for t in (h or {}).get("tweets") or []:
            a = t.get("author") or {}
            u = _usuario(a.get("userName"))
            if u:
                info_autor[u.lower()] = a
            f = _fecha_tweet(t)
            if not f or f < corte:
                continue
            texto = t.get("text") or ""
            q = _queja_gye(texto)
            if not q:
                continue
            fecha = f.isoformat()
            if u:
                aporta(u, texto, t.get("url"), fecha, "x (tweets de historias)", q)
                c_de(u)["autor_visto"] = True
            m = _RT.match(texto)
            if m:
                aporta(m.group(1), texto, t.get("url"), fecha, "x (retuit de una queja)", q)
            for otro in set(_MENCION.findall(texto)) - ({m.group(1)} if m else set()) - {u}:
                menciona(otro, texto, t.get("url"), fecha, "x (mencionada en quejas)")

    # 3) feed de EmergenciasEc (su gente y su red).
    rc = _leer_json(redes.CACHE_PATH)
    yo = redes.EMERG_CUENTA.lower()
    for t in rc.get("emergencias_feed") or []:
        f = _parse(t.get("fecha"))
        if not f or f < corte:
            continue
        texto = t.get("texto") or ""
        u = _usuario(t.get("autor"))
        q = _queja_gye(texto)
        if not q:
            continue
        if u and u.lower() != yo:
            aporta(u, texto, t.get("url"), t.get("fecha"), "EmergenciasEc (su gente)", q)
            c_de(u)["autor_visto"] = True
        m = _RT.match(texto)
        for otro in set(_MENCION.findall(texto)) - {u, m.group(1) if m else ""}:
            if otro.lower() != yo:
                menciona(otro, texto, t.get("url"), t.get("fecha"), "EmergenciasEc (mencionada)")

    # 4) quien mas interactua con EmergenciasEc.
    for u, n in redes.red_emergencias(top=10 ** 6):
        c = c_de(u)
        c["interacciones"] = n
        c["origen"].add("red de EmergenciasEc")

    cfg = cargar_config()
    seguidas = {(c.get("usuario") or "").lstrip("@").lower() for c in cfg["cuentas"]}
    descartadas = {(d.get("usuario") or "").lower() for d in cfg["descartadas"]}
    out = []
    for k, c in cand.items():
        if k in seguidas or k == yo or (k in descartadas and not incluir_descartadas):
            continue
        nq, nm, ni = len(c["quejas"]), len(c["menciones"]), c["interacciones"]
        if not (nq >= 2 or (nq >= 1 and (nm >= 2 or ni >= 2)) or nm >= 3):
            continue
        if _es_medio_o_institucion(c["usuario"], info_autor.get(k)):
            continue
        info = info_autor.get(k) or {}
        out.append({
            "usuario": c["usuario"], "nombre": info.get("name") or "", "quejas": nq, "menciones": nm,
            "interacciones": ni, "ejemplo": c["ejemplo"],
            "barrios": [b for b, _ in sorted(c["barrios"].items(), key=lambda x: -x[1])
                        if b != comunidad.SIN_SECTOR][:3],
            "categorias": [comunidad.ETIQUETA.get(x, x) for x, _ in
                           sorted(c["categorias"].items(), key=lambda x: -x[1])][:3],
            "origen": sorted(c["origen"]), "seguidores": info.get("followers"),
            "verificada": c["autor_visto"], "descartada": k in descartadas,
        })
    out.sort(key=lambda c: (-c["quejas"], -c["menciones"], -c["interacciones"], c["usuario"].lower()))
    return out[:top]


def panel(ahora=None):
    """Todo lo que necesita el panel de Comunidad (GET /api/comunidad/cuentas)."""
    cfg = cargar_config()
    seguidas = [dict(c, tipo=tipo_cuenta(c)) for c in cfg["cuentas"] if tipo_cuenta(c) == "comunitaria"]
    try:
        import redes
        uso = redes.comunitarias_dashboard()
    except Exception as e:
        uso = {"estado": "no disponible (%s)" % e}
    return {"sugeridas": candidatas(ahora=ahora), "seguidas": seguidas,
            "oficiales": [c.get("usuario") for c in cfg["cuentas"] if tipo_cuenta(c) == "oficial"],
            "descartadas": len(cfg["descartadas"]), "facebook": fuentes_facebook(), "uso": uso,
            "dias": DIAS}
