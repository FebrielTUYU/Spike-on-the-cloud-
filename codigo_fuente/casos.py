# -*- coding: utf-8 -*-
"""
Asistente de casos (Fase 7, Pasos B-E) -- espacio de trabajo por reportaje:
documentos propios, entidades a seguir, avisos cuando el Dashboard menciona
algo de un caso abierto, notas y un chat que cita sus fuentes.

Solo libreria estandar, salvo `pypdf` para extraer texto de PDF -- la UNICA
excepcion a la regla de oro del proyecto ("solo stdlib"), autorizada
explicitamente por Fernando al pedir este bloque. Sin pypdf instalado, subir
un PDF a un caso avisa que falta (`pip install pypdf`) sin romper nada mas.

Mismo criterio que oficial.py/declaraciones.py: modulo standalone, NUNCA
importa monitor.py (evita import circular; monitor.py es quien importa a
este modulo). Si importa ia.py directamente para pedir embeddings/redactar
sugerencias -- ia.py tambien es standalone (solo importa feeds.py), asi que
no hay riesgo de ciclo.

Modelo de datos, una subcarpeta por caso en casos/<caso_id>/:
  caso.json       -- id, titulo, descripcion, fecha_creacion, entidades[]
  docs/           -- los documentos originales que Fernando sube
  index.sqlite3   -- fragmentos de esos documentos + su embedding (Paso C)
  docs_estado.json -- progreso de la ingesta de cada documento (Paso C)
  avisos.json     -- avisos deterministicos del puente Dashboard->Asistente (Paso D)
  notas.json      -- notas libres de Fernando sobre el caso
  evidencia.json  -- noticias/contratos que Fernando guardo desde el Dashboard (Paso D)
  tablero.json    -- SOLO el esquema (nodos/conexiones); la interfaz visual
                     del pizarron no es parte de esta etapa (pedido explicito)
"""
import os, re, json, shutil, sqlite3, unicodedata, uuid, math, datetime as dt

try:
    import pypdf
except Exception:
    pypdf = None

try:
    import ia  # embeddings + sugerencias de entidades/conexiones (Paso C/E); opcional
except Exception:
    ia = None

HERE = os.path.dirname(os.path.abspath(__file__))
CASOS_DIR = os.path.join(HERE, "casos")

AVISOS_MAX = 300
EXT_SOPORTADAS = {".txt", ".md", ".docx", ".pdf"}


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def _slug(texto, maxlen=40):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return (t or "caso")[:maxlen]


def _escribir_json(path, data):
    """Mismo patron que saved.json/notas.json en monitor.py: archivo
    temporal + os.replace -- esto es contenido de Fernando (o el registro de
    avisos derivado de el), no un cache recalculable."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _leer_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _dir_caso(caso_id):
    return os.path.join(CASOS_DIR, caso_id)


def _ruta(caso_id, nombre):
    return os.path.join(_dir_caso(caso_id), nombre)


# ------------------------------- CRUD de casos -------------------------------

def crear_caso(titulo, descripcion=""):
    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("el caso necesita un titulo")
    os.makedirs(CASOS_DIR, exist_ok=True)
    caso_id = "%s-%s" % (_slug(titulo), uuid.uuid4().hex[:6])
    d = _dir_caso(caso_id)
    os.makedirs(os.path.join(d, "docs"), exist_ok=True)
    caso = {
        "id": caso_id, "titulo": titulo, "descripcion": (descripcion or "").strip(),
        "fecha_creacion": now_utc().isoformat(), "entidades": [],
    }
    _escribir_json(_ruta(caso_id, "caso.json"), caso)
    _escribir_json(_ruta(caso_id, "avisos.json"), [])
    _escribir_json(_ruta(caso_id, "notas.json"), [])
    _escribir_json(_ruta(caso_id, "evidencia.json"), [])
    _escribir_json(_ruta(caso_id, "tablero.json"), {"nodos": [], "conexiones": []})
    _escribir_json(_ruta(caso_id, "docs_estado.json"), {})
    _init_indice(caso_id)
    return caso


def existe_caso(caso_id):
    caso_id = (caso_id or "").strip()
    return bool(caso_id) and "/" not in caso_id and "\\" not in caso_id \
        and os.path.isfile(_ruta(caso_id, "caso.json"))


def cargar_caso(caso_id):
    if not existe_caso(caso_id):
        return None
    return _leer_json(_ruta(caso_id, "caso.json"), None)


def guardar_caso(caso_id, caso):
    _escribir_json(_ruta(caso_id, "caso.json"), caso)


def listar_casos():
    if not os.path.isdir(CASOS_DIR):
        return []
    out = []
    for caso_id in sorted(os.listdir(CASOS_DIR)):
        caso = cargar_caso(caso_id)
        if not caso:
            continue
        docs_dir = _ruta(caso_id, "docs")
        n_docs = len([f for f in os.listdir(docs_dir)]) if os.path.isdir(docs_dir) else 0
        avisos = cargar_avisos(caso_id)
        out.append({
            "id": caso_id, "titulo": caso.get("titulo", ""), "descripcion": caso.get("descripcion", ""),
            "fecha_creacion": caso.get("fecha_creacion", ""),
            "n_entidades": len(caso.get("entidades") or []),
            "n_docs": n_docs, "n_avisos": len(avisos),
            "n_avisos_sin_ver": sum(1 for a in avisos if not a.get("visto")),
        })
    out.sort(key=lambda c: c.get("fecha_creacion", ""), reverse=True)
    return out


def borrar_caso(caso_id):
    if not existe_caso(caso_id):
        return False
    shutil.rmtree(_dir_caso(caso_id))
    return True


def hoy_en_casos(limite=50):
    """Vista 'Hoy en mis casos' (pedido explicito, seccion 2 del pedido de
    Fernando): todos los avisos de todos los casos, mas nuevos primero, con
    el caso al que pertenecen -- para no tener que entrar caso por caso a
    ver que cambio."""
    out = []
    for c in listar_casos():
        for a in cargar_avisos(c["id"]):
            out.append(dict(a, caso_id=c["id"], caso_titulo=c["titulo"]))
    out.sort(key=lambda a: a.get("ts", ""), reverse=True)
    return out[:limite]


# ------------------------------- entidades -------------------------------

def agregar_entidad(caso_id, nombre, tipo="otro", alias=None):
    caso = cargar_caso(caso_id)
    if caso is None:
        raise ValueError("caso inexistente")
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("la entidad necesita un nombre")
    ya = {e.get("nombre", "").strip().lower() for e in caso.get("entidades", [])}
    if nombre.lower() not in ya:
        caso.setdefault("entidades", []).append({
            "nombre": nombre, "tipo": (tipo or "otro").strip(),
            "alias": [a.strip() for a in (alias or []) if a and a.strip()],
        })
        guardar_caso(caso_id, caso)
    return caso


def quitar_entidad(caso_id, nombre):
    caso = cargar_caso(caso_id)
    if caso is None:
        raise ValueError("caso inexistente")
    nombre = (nombre or "").strip().lower()
    caso["entidades"] = [e for e in caso.get("entidades", []) if e.get("nombre", "").strip().lower() != nombre]
    guardar_caso(caso_id, caso)
    return caso


def entidades_y_alias(caso_id):
    """(alias_o_nombre, nombre_canonico) por cada entidad+alias del caso --
    lo usa el puente Dashboard->Asistente (Paso D, monitor.revisar_casos_avisos)
    para comparar rapido contra el texto de cada historia/contrato nuevo."""
    caso = cargar_caso(caso_id)
    if not caso:
        return []
    out = []
    for e in caso.get("entidades", []):
        nombre = e.get("nombre", "")
        for n in [nombre] + list(e.get("alias") or []):
            n = (n or "").strip()
            if n:
                out.append((n, nombre))
    return out


# ------------------------------- avisos (Paso D) -------------------------------

def cargar_avisos(caso_id):
    return _leer_json(_ruta(caso_id, "avisos.json"), [])


def ya_avisado(caso_id, entidad, origen_key):
    """Evita duplicar un aviso para la MISMA entidad + MISMA fuente (ej. la
    misma historia sigue apareciendo pasada tras pasada del feed rapido
    mientras esta vigente -- sin esto, avisaria de nuevo cada minuto)."""
    return any(a.get("entidad") == entidad and a.get("origen_key") == origen_key
               for a in cargar_avisos(caso_id))


def agregar_aviso(caso_id, aviso):
    """aviso: {tipo, entidad, texto, fuente:{...}, origen_key}. Recorta lo
    mas viejo por encima de AVISOS_MAX (mismo criterio que
    entities.json/ENTITIES_MAX_POR_ENTIDAD en monitor.py)."""
    avisos = cargar_avisos(caso_id)
    aviso = dict(aviso)
    aviso.setdefault("id", uuid.uuid4().hex[:12])
    aviso.setdefault("ts", now_utc().isoformat())
    aviso.setdefault("visto", False)
    avisos.append(aviso)
    if len(avisos) > AVISOS_MAX:
        avisos = avisos[-AVISOS_MAX:]
    _escribir_json(_ruta(caso_id, "avisos.json"), avisos)
    return aviso


def marcar_avisos_vistos(caso_id):
    avisos = cargar_avisos(caso_id)
    for a in avisos:
        a["visto"] = True
    _escribir_json(_ruta(caso_id, "avisos.json"), avisos)
    return avisos


# ------------------------------- notas del caso -------------------------------

def cargar_notas_caso(caso_id):
    return _leer_json(_ruta(caso_id, "notas.json"), [])


def agregar_nota_caso(caso_id, texto):
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("la nota esta vacia")
    notas = cargar_notas_caso(caso_id)
    nota = {"id": uuid.uuid4().hex[:12], "texto": texto, "ts": now_utc().isoformat()}
    notas.append(nota)
    _escribir_json(_ruta(caso_id, "notas.json"), notas)
    return nota


def borrar_nota_caso(caso_id, nota_id):
    notas = [n for n in cargar_notas_caso(caso_id) if n.get("id") != nota_id]
    _escribir_json(_ruta(caso_id, "notas.json"), notas)
    return notas


# ------------------------------- evidencia (Paso D) -------------------------------

def cargar_evidencia(caso_id):
    return _leer_json(_ruta(caso_id, "evidencia.json"), [])


def agregar_evidencia(caso_id, tipo, datos, origen=""):
    """Guarda el item COMPLETO (misma idea que saved.json en monitor.py):
    sobrevive a que la noticia caduque del feed o data.json cambie."""
    ev = cargar_evidencia(caso_id)
    item = {"id": uuid.uuid4().hex[:12], "tipo": tipo or "historia", "datos": datos or {},
            "origen": origen or "", "ts": now_utc().isoformat()}
    ev.append(item)
    _escribir_json(_ruta(caso_id, "evidencia.json"), ev)
    return item


def quitar_evidencia(caso_id, evidencia_id):
    ev = [e for e in cargar_evidencia(caso_id) if e.get("id") != evidencia_id]
    _escribir_json(_ruta(caso_id, "evidencia.json"), ev)
    return ev


# ------------------------------- tablero (solo esquema, Paso B/E) -------------------------------

def cargar_tablero(caso_id):
    return _leer_json(_ruta(caso_id, "tablero.json"), {"nodos": [], "conexiones": []})


def guardar_tablero(caso_id, tablero):
    _escribir_json(_ruta(caso_id, "tablero.json"), tablero)


def agregar_conexion_sugerida(caso_id, origen, destino, tipo, fuente):
    """La IA (Paso E) puede PROPONER una conexion -- queda 'sugerida' hasta
    que Fernando la marque 'verificada' a mano (pedido explicito: 'Solo yo
    las marco como verificada'). Esta funcion NUNCA la marca verificada."""
    t = cargar_tablero(caso_id)
    con = {"id": uuid.uuid4().hex[:12], "origen": (origen or "").strip(), "destino": (destino or "").strip(),
           "tipo": (tipo or "relacion").strip(), "estado": "sugerida", "fuente": fuente or {},
           "ts": now_utc().isoformat()}
    t.setdefault("conexiones", []).append(con)
    guardar_tablero(caso_id, t)
    return con


def marcar_conexion(caso_id, conexion_id, estado):
    if estado not in ("sugerida", "verificada"):
        raise ValueError("estado invalido")
    t = cargar_tablero(caso_id)
    for c in t.get("conexiones", []):
        if c.get("id") == conexion_id:
            c["estado"] = estado
    guardar_tablero(caso_id, t)
    return t


def quitar_conexion(caso_id, conexion_id):
    t = cargar_tablero(caso_id)
    t["conexiones"] = [c for c in t.get("conexiones", []) if c.get("id") != conexion_id]
    guardar_tablero(caso_id, t)
    return t


# ------------------------------- indice de fragmentos (sqlite3, Paso B/C) -------------------------------

def _ruta_indice(caso_id):
    return _ruta(caso_id, "index.sqlite3")


def _init_indice(caso_id):
    con = sqlite3.connect(_ruta_indice(caso_id))
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS fragmentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            doc_nombre TEXT NOT NULL,
            posicion INTEGER NOT NULL,
            texto TEXT NOT NULL,
            embedding TEXT,
            embedding_modelo TEXT,
            ts TEXT NOT NULL
        )""")
        # Fase 10, parte B: bases creadas ANTES de este cambio no tienen la
        # columna -- se agrega sola, sin perder los fragmentos ya indexados
        # (quedan con embedding_modelo=NULL, que buscar_fragmentos() trata
        # igual que "modelo viejo/desconocido": no se compara, hasta que se
        # reindexen). No hay ningun caso real todavia con documentos
        # indexados (verificado en esta sesion, carpeta casos/ vacia) -- este
        # camino es blindaje a futuro, no una migracion de datos reales.
        try:
            con.execute("ALTER TABLE fragmentos ADD COLUMN embedding_modelo TEXT")
        except sqlite3.OperationalError:
            pass  # la columna ya existia
        con.commit()
    finally:
        con.close()


def indexar_fragmentos(caso_id, doc_id, doc_nombre, fragmentos):
    """fragmentos: [{"posicion":int, "texto":str, "embedding": [float,...] o None,
    "embedding_modelo": str o None}]"""
    _init_indice(caso_id)
    con = sqlite3.connect(_ruta_indice(caso_id))
    try:
        ts = now_utc().isoformat()
        con.executemany(
            "INSERT INTO fragmentos (doc_id, doc_nombre, posicion, texto, embedding, embedding_modelo, ts) "
            "VALUES (?,?,?,?,?,?,?)",
            [(doc_id, doc_nombre, f.get("posicion", i), f["texto"],
              json.dumps(f["embedding"]) if f.get("embedding") else None,
              f.get("embedding_modelo") if f.get("embedding") else None, ts)
             for i, f in enumerate(fragmentos)])
        con.commit()
    finally:
        con.close()


def _cos(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def buscar_fragmentos(caso_id, embedding_consulta, top_k=4, modelo_consulta=None):
    """Similaridad coseno en Python puro (sin numpy, regla de oro del
    proyecto) sobre todos los fragmentos del caso -- para el tamano de un
    caso personal (decenas de documentos, no miles) esto es practicamente
    instantaneo.

    Fase 10, parte B -- candado de espacio vectorial: 'modelo_consulta' (por
    defecto ia.EMBED_MODEL, el modelo ACTUAL) se compara SOLO contra
    fragmentos indexados con el mismo 'embedding_modelo' -- un fragmento
    indexado con un modelo viejo/retirado (ej. nomic-embed-text, antes de la
    migracion a Gemini) queda afuera hasta que el documento se reindexe, en
    vez de compararse por coincidencia de dimension y devolver basura."""
    if not os.path.isfile(_ruta_indice(caso_id)) or not embedding_consulta:
        return []
    modelo_consulta = modelo_consulta or (getattr(ia, "EMBED_MODEL", None) if ia else None)
    con = sqlite3.connect(_ruta_indice(caso_id))
    try:
        filas = con.execute(
            "SELECT id, doc_id, doc_nombre, posicion, texto, embedding, embedding_modelo "
            "FROM fragmentos").fetchall()
    finally:
        con.close()
    puntuados = []
    for fid, doc_id, doc_nombre, pos, texto, emb_json, emb_modelo in filas:
        if not emb_json or not modelo_consulta or emb_modelo != modelo_consulta:
            continue
        try:
            emb = json.loads(emb_json)
        except Exception:
            continue
        puntuados.append((_cos(embedding_consulta, emb),
                           {"id": fid, "doc_id": doc_id, "doc_nombre": doc_nombre,
                            "posicion": pos, "texto": texto}))
    puntuados.sort(key=lambda x: x[0], reverse=True)
    return [f for score, f in puntuados[:top_k] if score > 0]


def listar_documentos(caso_id):
    if not os.path.isfile(_ruta_indice(caso_id)):
        return []
    con = sqlite3.connect(_ruta_indice(caso_id))
    try:
        filas = con.execute(
            "SELECT doc_id, doc_nombre, COUNT(*) FROM fragmentos GROUP BY doc_id, doc_nombre").fetchall()
    finally:
        con.close()
    return [{"doc_id": d, "nombre": n, "n_fragmentos": c} for d, n, c in filas]


# ------------------------------- estado de ingesta (Paso C) -------------------------------

def cargar_estado_docs(caso_id):
    return _leer_json(_ruta(caso_id, "docs_estado.json"), {})


def actualizar_estado_doc(caso_id, doc_id, **campos):
    estado = cargar_estado_docs(caso_id)
    d = estado.get(doc_id, {})
    d.update(campos)
    estado[doc_id] = d
    _escribir_json(_ruta(caso_id, "docs_estado.json"), estado)
    return d


# ------------------------------- ingesta de documentos (Paso C) -------------------------------

def extraer_texto(path):
    """Texto plano de .txt/.md/.docx/.pdf, o (None, motivo) si no se pudo.
    Nunca lanza: un documento con problemas no debe tumbar el hilo de
    ingesta de fondo."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".txt", ".md"):
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read(), None
        if ext == ".docx":
            return _extraer_docx(path), None
        if ext == ".pdf":
            if pypdf is None:
                return None, "falta pypdf para leer PDF (instalar con: pip install pypdf)"
            return _extraer_pdf(path), None
        return None, "formato no soportado: %s" % ext
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def _extraer_docx(path):
    """.docx es un .zip con XML adentro -- se puede leer entero con stdlib
    (zipfile + xml.etree), sin ninguna libreria de Word."""
    import zipfile
    from xml.etree import ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    partes = []
    for p in root.iter(ns + "p"):
        texto = "".join(t.text or "" for t in p.iter(ns + "t"))
        if texto:
            partes.append(texto)
    return "\n".join(partes)


def _extraer_pdf(path):
    lector = pypdf.PdfReader(path)
    partes = []
    for pag in lector.pages:
        t = pag.extract_text() or ""
        if t:
            partes.append(t)
    return "\n".join(partes)


def _fragmentar(texto, palabras_por_fragmento=500, solape=50):
    """Fragmentos de ~500 palabras con solape (pedido explicito), para que
    una idea que cruza el corte de un fragmento no se pierda entera de
    ningun lado."""
    palabras = texto.split()
    if not palabras:
        return []
    out, i, pos = [], 0, 0
    while i < len(palabras):
        out.append({"posicion": pos, "texto": " ".join(palabras[i:i + palabras_por_fragmento])})
        pos += 1
        if i + palabras_por_fragmento >= len(palabras):
            break
        i += palabras_por_fragmento - solape
    return out


def iniciar_ingesta(caso_id, nombre_archivo, origen_path):
    """Paso RAPIDO (Paso C): copia el archivo a docs/ y deja el estado
    'en_cola'. El trabajo pesado (extraer texto, fragmentar, pedir
    embeddings a Ollama) lo hace procesar_ingesta() -- el llamador
    (monitor.py) la corre en un hilo aparte para no bloquear la respuesta
    HTTP de la subida. Devuelve (doc_id, motivo_error); doc_id es None si no
    se pudo ni empezar (caso inexistente o formato no soportado)."""
    if cargar_caso(caso_id) is None:
        return None, "caso inexistente"
    ext = os.path.splitext(nombre_archivo)[1].lower()
    if ext not in EXT_SOPORTADAS:
        return None, "formato no soportado: %s (uso .txt/.md/.docx/.pdf)" % ext
    docs_dir = _ruta(caso_id, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    doc_id = uuid.uuid4().hex[:12]
    destino = os.path.join(docs_dir, "%s_%s" % (doc_id, os.path.basename(nombre_archivo)))
    shutil.copyfile(origen_path, destino)
    actualizar_estado_doc(caso_id, doc_id, nombre=nombre_archivo, estado="en_cola",
                           progreso=0, total=0, error=None, aviso=None)
    return doc_id, None


def procesar_ingesta(caso_id, doc_id, nombre_archivo):
    """Trabajo pesado de la ingesta (Paso C), pensado para un hilo de fondo:
    extrae texto, fragmenta y pide el embedding de CADA fragmento a Ollama
    UNO POR UNO -- nunca se manda el documento entero al modelo. Actualiza
    docs_estado.json en cada paso para que el dashboard pueda mostrar el
    progreso real con un simple GET al detalle del caso (sin websockets)."""
    docs_dir = _ruta(caso_id, "docs")
    destino = None
    if os.path.isdir(docs_dir):
        for nombre in os.listdir(docs_dir):
            if nombre.startswith(doc_id + "_"):
                destino = os.path.join(docs_dir, nombre)
                break
    if destino is None:
        actualizar_estado_doc(caso_id, doc_id, estado="error", error="archivo no encontrado")
        return

    actualizar_estado_doc(caso_id, doc_id, estado="extrayendo")
    texto, motivo = extraer_texto(destino)
    if texto is None:
        actualizar_estado_doc(caso_id, doc_id, estado="error", error=motivo)
        return
    fragmentos = _fragmentar(texto)
    if not fragmentos:
        actualizar_estado_doc(caso_id, doc_id, estado="error", error="el documento no tiene texto extraible")
        return

    total = len(fragmentos)
    actualizar_estado_doc(caso_id, doc_id, estado="indexando", progreso=0, total=total)
    con_embedding, n_sin_embedding = [], 0
    for i, frag in enumerate(fragmentos):
        emb, modelo_emb = None, None
        if ia is not None:
            try:
                # Fase 24 (revision de Codex): privacidad EXPLICITA -- un documento de un
                # caso nunca va a un proveedor gratuito, aunque se indexe en segundo plano.
                with ia.modulo("casos"):
                    emb = ia.embed(frag["texto"])
                if emb:
                    modelo_emb = ia.EMBED_MODEL
            except Exception:
                emb = None
        if not emb:
            n_sin_embedding += 1
        # Fase 10, parte B: cada vector se etiqueta con el modelo que lo
        # genero (candado de espacio vectorial, ver buscar_fragmentos) --
        # sin esto, un fragmento indexado con un modelo viejo (ej.
        # nomic-embed-text, retirado con Ollama) podria compararse por
        # coincidencia de dimension contra uno nuevo y dar un resultado sin
        # sentido.
        con_embedding.append({"posicion": frag["posicion"], "texto": frag["texto"],
                               "embedding": emb, "embedding_modelo": modelo_emb})
        actualizar_estado_doc(caso_id, doc_id, progreso=i + 1, total=total)
    indexar_fragmentos(caso_id, doc_id, nombre_archivo, con_embedding)

    aviso = None
    if n_sin_embedding:
        modelo_emb = getattr(ia, "EMBED_MODEL", "gemini-embedding-001") if ia else "gemini-embedding-001"
        aviso = ("La nube (Gemini) no respondio para %d de %d fragmentos: quedaron sin vector y no "
                 "van a aparecer en busquedas del chat hasta reintentar (revisa que GEMINI_API_KEY "
                 "este configurada en .env y que el modelo '%s' este disponible)."
                 % (n_sin_embedding, total, modelo_emb))
    actualizar_estado_doc(caso_id, doc_id, estado="listo", progreso=total, total=total, aviso=aviso)
