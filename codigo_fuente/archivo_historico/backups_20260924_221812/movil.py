# -*- coding: utf-8 -*-
"""
Capa MOVIL del Monitor: avisos al telefono + acceso al dashboard desde el celular.

Por que asi (solo libreria estandar, sin cuentas):
  - Los avisos van por ntfy (https://ntfy.sh): servicio gratis y abierto. El PC
    publica un mensaje en un "tema" (un nombre secreto largo) y la app ntfy del
    iPhone, suscrita a ese tema, lo muestra como notificacion push.
    No hay que crear cuenta ni clave. El nombre del tema ES la llave: quien lo
    sepa puede leer los avisos, por eso se genera al azar y no se comparte.
  - El dashboard se ve en el celular porque el modo `serve` escucha en la red
    (no solo en esta PC) y pide una CLAVE a cualquier aparato que no sea esta PC.

Configuracion: se crea sola en `movil.json` la primera vez. Se puede editar a mano.

Que cuenta como "gran cambio" (se compara contra corridas anteriores):
  1. HISTORIA FUERTE: una historia de Ecuador que ya levantan >= min_medios medios
     y que no se habia avisado. Si ya se aviso y siguio creciendo (+2 medios),
     se avisa una vez mas como "sigue creciendo".
  2. PICO DE TEMA: en las ultimas horas salieron muchas mas historias de un tema
     que su ritmo normal (>= factor_pico veces y al menos pico_min historias).
  3. BRECHA: un tema que el publico busca (>= brecha_demanda) y casi nadie cubre
     (<= brecha_max_cobertura historias): candidato a reportaje. Se repite cada 48 h max.

Anti-spam: cada cosa se avisa una sola vez (enfriamiento de 12 h por tema),
maximo `max_por_corrida` avisos sueltos (lo demas va en un resumen), y horas de
silencio de noche. Lo que se calla de noche se avisa en la primera corrida de la
manana si sigue vigente.

LIMITE HONESTO: los avisos solo salen mientras el Monitor esta corriendo en la PC.
PC apagada o dormida = no hay avisos.
"""

import os, json, re, time, socket, secrets, unicodedata, datetime as dt
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CONF_PATH = os.path.join(HERE, "movil.json")
STATE_PATH = os.path.join(HERE, "movil_estado.json")
UA = "Mozilla/5.0 (Monitor-Noticias/1.0; personal research)"
IGNORAR_TEMAS = {"otros", "general"}  # cajones de sastre: su volumen no significa nada
TZ_EC = dt.timezone(dt.timedelta(hours=-5))  # Ecuador continental, sin horario de verano

DEFAULTS = {
    "avisos_activos": True,
    "ntfy_servidor": "https://ntfy.sh",
    "ntfy_tema": "",            # se genera solo
    "clave_acceso": "",         # se genera sola: la pide el dashboard desde el celular
    "acceso_red": True,         # True = el dashboard se puede abrir desde el celular
    "url_dashboard": "",        # opcional: fuerza el enlace que llevan los avisos
    "min_medios": 2,            # historia fuerte = la cubren al menos N medios
    "crecimiento_medios": 2,    # re-aviso si suma N medios mas
    "ventana_pico_h": 6,        # pico de tema: se miran las ultimas N horas...
    "factor_pico": 2.0,         # ...con N veces mas historias que lo normal en esa ventana
    "muestras_minimas": 12,     # horas de aprendizaje antes de avisar picos
    "pico_min": 4,              # ...y al menos N historias
    "brecha_demanda": 25,       # brecha = busqueda >= N (escala 0-100 de Trends/Wikipedia)...
    "brecha_max_cobertura": 3,  # ...y <= N historias que lo cubren
    "enfriamiento_brecha_horas": 48,
    "max_por_corrida": 3,
    "silencio_desde": 23,       # hora Ecuador (0-23). Igual valor en ambos = sin silencio
    "silencio_hasta": 7,
    "enfriamiento_horas": 12,
    # Fase 0 (velocidad), pedido explicito de Fernando: aviso por nota nueva
    # de Guayaquil/Ecuador, aparte de "historia fuerte" (que exige
    # min_medios y en la practica casi nunca dispara -- ver LIMITACION
    # CONOCIDA mas abajo). Apagado por defecto ("opcional, configurable"):
    # con 44 feeds, notas nuevas de Ecuador solas pueden ser bastantes por
    # hora, no todo el mundo lo quiere.
    "avisos_nota_nueva": False,
    "nota_nueva_ambito": "guayaquil",   # "guayaquil" | "local" (todo Ecuador)
    "nota_nueva_limite_hora": 4,        # limite de avisos por hora SOLO de este tipo
    "nota_nueva_max_horas": 1.0,        # solo notas mas nuevas que esto (recien salidas)
    # Fase 7, Paso D (Asistente de casos): push opcional cuando el puente
    # Dashboard->Asistente detecta que una historia/contrato nuevo menciona
    # una entidad de un caso abierto. Apagado por defecto -- "opcionalmente
    # un push... nada de comentarios constantes: solo avisos ante hechos
    # concretos" (cada aviso de caso YA es un hecho puntual -- una mencion
    # real -- asi que a diferencia de "historia fuerte"/"pico de tema" no
    # necesita un umbral propio de enfriamiento aparte).
    "avisos_casos_activos": False,
}


# ------------------------- configuracion y estado -------------------------

def cargar_config():
    """Lee movil.json; si no existe (o le faltan campos) lo completa y lo guarda."""
    try:
        with open(CONF_PATH, encoding="utf-8") as f:
            conf = json.load(f)
    except Exception:
        conf = {}
    cambio = False
    for k, v in DEFAULTS.items():
        if k not in conf:
            conf[k] = v
            cambio = True
    if not conf.get("ntfy_tema"):
        # nombre largo y al azar: imposible de adivinar = privado en la practica
        conf["ntfy_tema"] = "monitor-ec-" + secrets.token_hex(8)
        cambio = True
    if not conf.get("clave_acceso"):
        conf["clave_acceso"] = secrets.token_urlsafe(9)
        cambio = True
    # variables de entorno por si se quiere probar sin editar el archivo
    if os.environ.get("MONITOR_NO_MOVIL") == "1":
        conf["avisos_activos"] = False
    if cambio:
        guardar_json(CONF_PATH, conf)
    return conf

def guardar_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def cargar_estado():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None  # primera vez


# ------------------------- red: IPs y enlaces -------------------------

def ips_locales():
    """IPs utiles de esta PC para abrir el dashboard desde el celular:
      - la del WiFi/red de casa (la que usa para salir a internet), y
      - la de Tailscale (100.64-127.x), que sirve desde cualquier lugar.
    Se descartan adaptadores virtuales (WSL, VirtualBox, etc.) que no le sirven al celular."""
    ips = set()
    try:  # truco: la IP con la que esta PC sale a internet (no envia nada)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if es_tailscale(info[4][0]):
                ips.add(info[4][0])
    except Exception:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips)

def es_tailscale(ip):
    try:
        a, b = [int(x) for x in ip.split(".")[:2]]
        return a == 100 and 64 <= b <= 127  # rango CGNAT que usa Tailscale
    except Exception:
        return False

def enlaces_dashboard(conf, port):
    """Lista de (etiqueta, url) para abrir el dashboard desde el celular."""
    k = conf.get("clave_acceso", "")
    out = []
    for ip in ips_locales():
        etiqueta = "Tailscale (desde cualquier lugar)" if es_tailscale(ip) else "WiFi de casa"
        out.append((etiqueta, "http://%s:%d/dashboard.html?k=%s" % (ip, port, k)))
    out.sort(key=lambda x: 0 if x[0].startswith("Tailscale") else 1)
    return out

def enlace_principal(conf, port):
    if conf.get("url_dashboard"):
        return conf["url_dashboard"]
    enl = enlaces_dashboard(conf, port)
    return enl[0][1] if enl else ""


# ------------------------- envio (ntfy) -------------------------

def enviar(conf, titulo, mensaje, prioridad=3, etiquetas=None, click=""):
    """Publica un aviso en ntfy. Se usa JSON para que las tildes lleguen bien."""
    body = {"topic": conf["ntfy_tema"], "title": titulo[:120], "message": mensaje[:1500],
            "priority": int(prioridad), "tags": etiquetas or []}
    if click:
        body["click"] = click
    req = urllib.request.Request(conf["ntfy_servidor"].rstrip("/") + "/",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": UA},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300, "ok"
    except urllib.error.HTTPError as e:
        return False, "HTTP %s" % e.code
    except Exception as e:
        return False, str(e)[:80]


# ------------------------- deteccion de grandes cambios -------------------------

def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", s)

_STOP = set("de la el en los las del y a que por con para un una se su al es lo como mas tras sobre".split())

def firma(titular):
    """Conjunto de palabras significativas del titular: sirve para reconocer la
    misma historia aunque el titular cambie un poco entre corridas."""
    return sorted({w for w in _norm(titular).split() if len(w) > 3 and w not in _STOP})

def _parecida(f1, f2):
    a, b = set(f1), set(f2)
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.6

def en_silencio(conf, ahora_ec):
    d, h = int(conf["silencio_desde"]), int(conf["silencio_hasta"])
    if d == h:
        return False
    x = ahora_ec.hour
    return (d <= x < h) if d < h else (x >= d or x < h)

def detectar(stories, demand, estado, conf):
    """Devuelve lista de avisos candidatos (dicts) comparando con el estado previo."""
    ahora = time.time()
    enfr = conf["enfriamiento_horas"] * 3600
    avisados = estado.get("historias", [])      # [{firma, medios, ts}]
    temas_av = estado.get("temas", {})          # {"pico:X": ts, "brecha:X": ts}
    cands = []

    # Fase 0: cupo de avisos "nota nueva" para ESTA corrida -- ver mas abajo.
    # Se cuenta por HORA (no por corrida) para que el limite tenga sentido
    # aunque el feed corra cada 1 min: `nota_nueva_horaria` se resetea sola
    # cuando cambia la hora.
    hora_actual = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H")
    horaria = estado.get("nota_nueva_horaria") or {}
    if horaria.get("hora") != hora_actual:
        horaria = {"hora": hora_actual, "n": 0}
    cupo_nota_nueva = max(0, int(conf.get("nota_nueva_limite_hora", 0)) - horaria.get("n", 0))
    estado["nota_nueva_horaria"] = horaria  # se persiste en procesar() via guardar_json

    # 1) historias fuertes (Ecuador) y las que siguen creciendo
    for s in stories:
        if not s.get("es_local"):
            continue
        n = s.get("n_outlets", 0)
        f = firma(s["titular"])
        prev = next((a for a in avisados if _parecida(a["firma"], f)), None)
        if n >= conf["min_medios"]:
            if prev is None:
                tipo = "nueva"
            elif n >= prev["medios"] + conf["crecimiento_medios"] and not prev.get("crecio"):
                tipo = "crece"
            else:
                continue
        elif (conf.get("avisos_nota_nueva") and prev is None and cupo_nota_nueva > 0
              and s.get("hours") is not None and s["hours"] <= conf.get("nota_nueva_max_horas", 1.0)
              and (s.get("ciudad") == "Guayaquil" if conf.get("nota_nueva_ambito") == "guayaquil" else True)):
            # nota chica (menos de min_medios) pero RECIEN salida en el ambito
            # pedido -- distinto de "historia fuerte": esto es "te enterás
            # rapido", no "varios medios ya lo confirman". Gastar cupo de la
            # hora ahora mismo (no solo al enviar) evita que una corrida con
            # muchas notas nuevas juntas arme mas candidatos de los que el
            # cupo permite.
            tipo = "nota_nueva"
            cupo_nota_nueva -= 1
            horaria["n"] = horaria.get("n", 0) + 1
        else:
            continue
        cands.append({"clase": "historia", "tipo": tipo, "firma": f, "medios": n,
                      "titular": s["titular"], "outlets": s.get("outlets", []),
                      "ciudad": s.get("ciudad", ""),
                      "peso": (n * 10 + (5 if tipo == "nueva" else 0)) if tipo != "nota_nueva" else 2,
                      "link": (s.get("fuentes") or [{}])[0].get("link", "")})

    # 2) picos de tema: cuantas historias del tema salieron en las ultimas
    #    `ventana_pico_h` horas, comparado con lo que suele haber en esa misma
    #    ventana. Ese "lo normal" se APRENDE: cada hora se guarda una muestra en
    #    movil_estado.json. Se compara contra muestras y no contra el total de 3
    #    dias porque los RSS traen sobre todo lo ultimo (siempre hay "mas" reciente).
    ventana = float(conf["ventana_pico_h"])
    total, reciente = {}, {}
    for s in stories:
        for t in s.get("temas", []):
            if t in IGNORAR_TEMAS:
                continue
            total[t] = total.get(t, 0) + 1
            if s.get("hours") is not None and s["hours"] <= ventana:
                reciente[t] = reciente.get(t, 0) + 1
    muestras = estado.get("muestras", [])  # [{"ts":..., "c": {tema: n}}]
    if len(muestras) >= conf["muestras_minimas"]:
        for t, n in reciente.items():
            normal = sum(m["c"].get(t, 0) for m in muestras) / len(muestras)
            if n >= conf["pico_min"] and n >= conf["factor_pico"] * max(normal, 1):
                clave = "pico:" + t
                if ahora - temas_av.get(clave, 0) > enfr:
                    cands.append({"clase": "tema", "clave": clave, "tema": t, "n": n,
                                  "prom": round(normal, 1), "h": int(ventana), "peso": n * 3})
    # guardar muestra (max 1 por hora, ultimos 3 dias); se persiste al final de procesar
    if not muestras or ahora - muestras[-1]["ts"] >= 3600:
        muestras.append({"ts": ahora, "c": reciente})
        estado["muestras"] = muestras[-72:]

    # 3) brechas: el publico lo busca bastante y la prensa casi no lo cubre
    for t, d in (demand or {}).items():
        if t in IGNORAR_TEMAS or d is None or d < conf["brecha_demanda"]:
            continue
        if total.get(t, 0) <= conf["brecha_max_cobertura"]:
            clave = "brecha:" + t
            if ahora - temas_av.get(clave, 0) > conf["enfriamiento_brecha_horas"] * 3600:
                cands.append({"clase": "tema", "clave": clave, "tema": t, "demanda": d,
                              "n": total.get(t, 0), "peso": d / 5})

    cands.sort(key=lambda c: c["peso"], reverse=True)
    return cands

def _texto(c):
    """(titulo, mensaje, prioridad, etiquetas) de un aviso."""
    if c["clase"] == "historia":
        medios = ", ".join(c["outlets"][:5])
        lugar = " (%s)" % c["ciudad"] if c.get("ciudad") else ""
        if c["tipo"] == "nota_nueva":
            return ("Nota nueva%s" % lugar, c["titular"], 2, ["newspaper"])
        if c["tipo"] == "nueva":
            tit = "Historia fuerte: %d medios%s" % (c["medios"], lugar)
        else:
            tit = "Sigue creciendo: ya %d medios%s" % (c["medios"], lugar)
        prio = 4 if c["medios"] >= 5 else 3
        return tit, "%s\n\nLa cubren: %s" % (c["titular"], medios), prio, ["newspaper"]
    if c["clave"].startswith("pico:"):
        return ("Pico de tema: %s" % c["tema"],
                "%d historias en las ultimas %d h (lo normal seria ~%s). Algo se esta moviendo en este tema."
                % (c["n"], c["h"], c["prom"]), 3, ["chart_with_upwards_trend"])
    return ("Brecha: %s" % c["tema"],
            "Interes de busqueda %d/100 y solo %d historia(s) en prensa. "
            "Posible tema desatendido: candidato a reportaje." % (c["demanda"], c["n"]), 3, ["mag"])

def procesar(stories, demand, port=8000):
    """Punto de entrada que llama monitor.py despues de cada corrida.
    Devuelve un texto de estado para mostrar en terminal y dashboard."""
    conf = cargar_config()
    if not conf.get("avisos_activos"):
        return "apagado"
    estado = cargar_estado()
    click = enlace_principal(conf, port) if conf.get("acceso_red") else ""

    if estado is None:
        # PRIMERA VEZ: no bombardear con todo lo que ya existe. Se marca como visto
        # y solo se manda un aviso de "conectado" con el enlace al dashboard.
        estado = {"historias": [], "temas": {}}
        for c in detectar(stories, demand, estado, conf):
            _marcar(estado, c)
        ok, msg = enviar(conf, "Monitor conectado",
                         "A partir de ahora te aviso cuando haya grandes cambios. "
                         "Toca este aviso para abrir el dashboard.", 3, ["white_check_mark"], click)
        guardar_json(STATE_PATH, estado)
        return "conectado (%s)" % msg if ok else "sin enviar: %s" % msg

    cands = detectar(stories, demand, estado, conf)
    guardar_json(STATE_PATH, estado)  # guarda la muestra horaria aunque no se avise nada
    if not cands:
        return "sin cambios grandes"
    if en_silencio(conf, dt.datetime.now(TZ_EC)):
        return "%d cambio(s) en espera (horas de silencio)" % len(cands)

    maxn = int(conf["max_por_corrida"])
    enviados, fallo = 0, ""
    for c in cands[:maxn]:
        tit, msg, prio, tags = _texto(c)
        ok, err = enviar(conf, tit, msg, prio, tags, click or c.get("link", ""))
        if not ok:
            fallo = err
            break
        _marcar(estado, c)
        enviados += 1
    resto = cands[maxn:] if not fallo else []
    if resto:
        lineas = [("- " + _texto(c)[0]) for c in resto[:8]]
        ok, err = enviar(conf, "Y %d cambio(s) mas" % len(resto), "\n".join(lineas), 2,
                         ["bell"], click)
        if ok:
            for c in resto:
                _marcar(estado, c)
            enviados += 1
    guardar_json(STATE_PATH, estado)
    if fallo:
        return "error al enviar (%s); %d enviados" % (fallo, enviados)
    return "%d aviso(s) enviados" % enviados

def _marcar(estado, c):
    now = time.time()
    if c["clase"] == "historia":
        hs = estado.setdefault("historias", [])
        prev = next((a for a in hs if _parecida(a["firma"], c["firma"])), None)
        if prev:
            prev.update({"medios": c["medios"], "ts": now, "crecio": c["tipo"] == "crece"})
        else:
            hs.append({"firma": c["firma"], "medios": c["medios"], "ts": now})
        # olvidar historias de mas de 4 dias (ya salieron del monitor)
        estado["historias"] = [a for a in hs if now - a.get("ts", now) < 4 * 86400][-300:]
    else:
        estado.setdefault("temas", {})[c["clave"]] = now

def probar(port=8000):
    """`python monitor.py movil`: muestra la configuracion y manda un aviso de prueba."""
    conf = cargar_config()
    print("=" * 60)
    print("  CONFIGURAR EL IPHONE (una sola vez)")
    print("=" * 60)
    print("1) Instala la app 'ntfy' desde el App Store.")
    print("2) En la app: toca '+', y escribe este tema (tal cual):\n")
    print("       %s\n" % conf["ntfy_tema"])
    print("   (Servidor: dejar el que viene, ntfy.sh). Permite notificaciones.")
    print("3) Para abrir el dashboard desde el celular (Monitor corriendo):")
    enl = enlaces_dashboard(conf, port)
    if enl:
        for et, u in enl:
            print("     - %s: %s" % (et, u))
    else:
        print("     (no encontre la IP de esta PC)")
    if not any(es_tailscale(ip) for ip in ips_locales()):
        print("   Esos enlaces funcionan con el celular en el MISMO WiFi que la PC.")
        print("   Para verlo fuera de casa, instala Tailscale (ver LEEME).")
    print("\nEnviando aviso de prueba...")
    ok, msg = enviar(conf, "Prueba del Monitor",
                     "Si ves esto en tu iPhone, los avisos funcionan. Toca para abrir el dashboard.",
                     3, ["tada"], enlace_principal(conf, port))
    print("  -> %s" % ("enviado. Revisa el iPhone." if ok else "FALLO: " + msg))
    print("\nTodo esto queda guardado en movil.json (no lo compartas).")


# ------------------------- Tailscale (ver el dashboard fuera de casa) -------------------------

def _tailscale_exe():
    import shutil
    for p in (shutil.which("tailscale"),
              r"C:\Program Files\Tailscale\tailscale.exe",
              r"C:\Program Files (x86)\Tailscale\tailscale.exe",
              "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if p and os.path.exists(p):
            return p
    return None

def activar_tailscale(port=8000):
    """Doble clic en ABRIR_EN_CELULAR_TAILSCALE.bat. Le pide a Tailscale que publique
    el Monitor (localhost:PORT) SOLO dentro de tu red Tailscale ("tailscale serve").
    Por que asi y no abriendo el puerto: el que recibe la conexion es Tailscale,
    no Python, asi que el Firewall de Windows no la bloquea. Queda activo aunque
    reinicies la PC (--bg). Nadie fuera de tus aparatos de Tailscale puede entrar."""
    import subprocess
    exe = _tailscale_exe()
    if not exe:
        print("No encontre Tailscale en esta PC. Instalalo desde tailscale.com e inicia sesion.")
        return
    def run(args):
        r = subprocess.run([exe] + args, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    code, ip = run(["ip", "-4"])
    ip = ip.splitlines()[0].strip() if code == 0 and ip else ""
    if not ip.startswith("100."):
        print("Tailscale no esta conectado en esta PC. Abrelo, inicia sesion y vuelve a intentar.")
        print("(detalle: %s)" % ip)
        return
    print("Tailscale conectado. IP de esta PC: %s" % ip)
    code, out = run(["serve", "--bg", "--http=80", "localhost:%d" % port])
    if code != 0:
        print("Tailscale no quiso publicar el Monitor:\n%s" % out)
        print("Si habla de permisos: clic derecho en este .bat -> Ejecutar como administrador.")
        return
    # OJO: "tailscale serve" responde segun el NOMBRE con que se entra, no la IP.
    # Entrar por http://100.x... da "404 page not found". Hay que usar el nombre
    # MagicDNS de la PC (tipo mi-pc.tail1234.ts.net), que se lee de "status --json".
    nombre = ""
    code, st = run(["status", "--json"])
    if code == 0:
        try:
            nombre = (json.loads(st).get("Self") or {}).get("DNSName", "").rstrip(".")
        except Exception:
            nombre = ""
    if not nombre:
        print("No pude leer el nombre MagicDNS de esta PC. Revisa en tailscale.com/admin/dns")
        print("que MagicDNS este activado y vuelve a correr este archivo.")
        return
    url = "http://%s/dashboard.html" % nombre
    conf = cargar_config()
    conf["url_dashboard"] = url  # los avisos del iPhone abriran este enlace
    guardar_json(CONF_PATH, conf)
    print("\n" + "=" * 60)
    print("  LISTO. En el iPhone (con Tailscale encendido, con datos o")
    print("  cualquier WiFi) abre en Safari:\n")
    print("      %s\n" % url)
    print("  El Monitor (INICIAR.bat) tiene que estar abierto en la PC.")
    print("  Si Safari dice que no encuentra el servidor: en la app Tailscale")
    print("  del iPhone revisa que este conectado (MagicDNS activado).")
    print("  Los avisos del iPhone ahora abren este enlace.")
    print("=" * 60)
