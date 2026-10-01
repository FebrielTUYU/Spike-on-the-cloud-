# -*- coding: utf-8 -*-
"""
notificaciones.py -- Fase 24 (F1): "Ultima hora" se reemplaza por
notificaciones de lo IMPORTANTE, con una definicion editable de que es
importante (notificaciones.json), historial (la campana del dashboard), aviso
al celular por ntfy y notificacion nativa de Windows.

Corre en el hilo rapido (write_outputs) sin esperar a nadie: decidir es local;
el envio (ntfy y Windows) va en un hilo aparte.

Que cuenta como importante (cada regla se prende o apaga):
  - alto_impacto: una historia de Guayaquil marcada de alto impacto (crimen,
    narcotrafico) que es nueva;
  - historia_fuerte: una historia local con al menos N medios;
  - categorias: una historia nueva de Guayaquil en esas categorias, con al
    menos 2 medios;
  - alerta_corroborada: una alerta de la gente corroborada o confirmada;
  - funcionario_primicia: un funcionario publico un hecho que la prensa todavia no tiene.
La primera vez solo se toma la foto (linea base): no se avisa lo que ya estaba.
"""
import datetime as dt
import json
import os
import subprocess
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "notificaciones.json")
ESTADO_PATH = os.path.join(HERE, "notificaciones_estado.json")
TZ_EC = dt.timezone(dt.timedelta(hours=-5))
HISTORIAL_MAX = 200
NUEVA_H = 3.0   # una historia cuenta como nueva si su ultima nota es de las ultimas 3 h

DEFAULTS = {
    "_ayuda": ("Que es 'importante' para Spike. Cada regla se prende (true) o apaga (false). "
               "ntfy = aviso al celular (usa el tema de movil.json); windows = notificacion de Windows en esta PC. "
               "silencio: horas de Ecuador sin avisos al celular (la campana igual los guarda)."),
    "ntfy": True, "windows": True, "max_por_hora": 6, "silencio_desde": 23, "silencio_hasta": 7,
    "reglas": {"alto_impacto": True, "historia_fuerte": True, "historia_fuerte_min_medios": 3,
               "categorias_activo": True, "categorias": ["seguridad", "riesgos_clima", "obras_servicios"],
               "alerta_corroborada": True, "funcionario_primicia": True},
}
_LOCK = threading.RLock()


def config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            c = json.load(f) or {}
    except FileNotFoundError:
        c = {}
        try:
            _guardar(CONFIG_PATH, DEFAULTS)
        except Exception:
            pass
    except Exception:
        c = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in c.items() if k != "reglas"})
    reglas = dict(DEFAULTS["reglas"])
    reglas.update(c.get("reglas") or {})
    out["reglas"] = reglas
    return out


def guardar_config(cambios):
    """Cambia la definicion de 'importante' desde el dashboard. Solo claves conocidas."""
    c = config()
    for k in ("ntfy", "windows"):
        if k in cambios:
            c[k] = bool(cambios[k])
    for k in ("max_por_hora", "silencio_desde", "silencio_hasta"):
        if k in cambios:
            try:
                c[k] = max(0, min(100 if k == "max_por_hora" else 23, int(cambios[k])))
            except (TypeError, ValueError):
                pass
    for k, v in (cambios.get("reglas") or {}).items():
        if k in DEFAULTS["reglas"]:
            if k == "categorias":
                c["reglas"][k] = [str(x) for x in (v or [])][:12]
            elif k == "historia_fuerte_min_medios":
                try:
                    c["reglas"][k] = max(2, min(20, int(v)))
                except (TypeError, ValueError):
                    pass
            else:
                c["reglas"][k] = bool(v)
    _guardar(CONFIG_PATH, c)
    return c


def _guardar(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _estado():
    try:
        with open(ESTADO_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _parse(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def candidatos(stories, alertas=None, funcionarios=None, conf=None):
    """[(id, tipo, titulo, texto, link)] de lo que hoy cuenta como importante."""
    conf = conf or config()
    r = conf["reglas"]
    out = []
    for h in stories or []:
        horas = h.get("hours")
        if horas is None or horas > NUEVA_H or h.get("antigua"):
            continue
        f0 = (h.get("fuentes") or [{}])[0]
        clave = "h:" + (f0.get("link") or h.get("titular", ""))[:180]
        gye = h.get("ciudad") == "Guayaquil"
        local = h.get("ambito") != "internacional"
        n = h.get("n_outlets") or len(h.get("outlets") or []) or 1
        motivo = None
        if r.get("alto_impacto") and gye and h.get("alto_impacto"):
            motivo = "Alto impacto en Guayaquil"
        elif r.get("historia_fuerte") and local and n >= int(r.get("historia_fuerte_min_medios") or 3):
            motivo = "La cuentan %d medios" % n
        elif r.get("categorias_activo") and gye and n >= 2 and h.get("categoria") in (r.get("categorias") or []):
            motivo = "Guayaquil, %s, %d medios" % (h.get("categoria"), n)
        if motivo:
            out.append((clave, "historia", h.get("titular", ""), motivo, f0.get("link", "")))
    if r.get("alerta_corroborada"):
        for a in alertas or []:
            if a.get("estado") in ("corroborado", "confirmado_oficial"):
                s0 = (a.get("senales") or [{}])[0]
                out.append(("a:%s:%s" % (a.get("id") or a.get("tipo"), a.get("estado")), "alerta",
                            "%s en %s" % ((a.get("tipo") or "Alerta").replace("_", " ").capitalize(), a.get("lugar") or "Guayaquil"),
                            "Alerta de la gente %s" % ("confirmada" if a.get("estado") == "confirmado_oficial" else "corroborada"),
                            s0.get("url", "")))
    if r.get("funcionario_primicia"):
        prim = set((funcionarios or {}).get("primicias") or [])
        for t in (funcionarios or {}).get("tuits") or []:
            if t.get("id") in prim:
                out.append(("f:%s" % t["id"], "funcionario", "%s: %s" % (t.get("nombre") or t.get("usuario"), (t.get("texto") or "")[:120]),
                            "Primicia de un funcionario (la prensa todavia no la publico)", t.get("url", "")))
    return out


def procesar(stories, alertas=None, funcionarios=None, ahora=None, enviar=True):
    """Decide que es nuevo e importante, lo agrega al historial y (en un hilo
    aparte) lo manda. Devuelve el dict para data.json['notificaciones']."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    conf = config()
    with _LOCK:
        e = _estado()
        vistos = e.get("vistos") or {}
        hist = e.get("historial") or []
        cands = candidatos(stories, alertas, funcionarios, conf)
        primera = not e.get("iniciado")
        nuevos = [c for c in cands if c[0] not in vistos]
        for c in cands:
            vistos.setdefault(c[0], ahora.isoformat())
        a_mandar = []
        if not primera:
            hace_1h = ahora - dt.timedelta(hours=1)
            en_hora = sum(1 for x in hist if (_parse(x.get("ts")) or ahora) >= hace_1h and x.get("enviado"))
            for (cid, tipo, titulo, texto, link) in nuevos:
                item = {"id": cid, "tipo": tipo, "titulo": titulo, "texto": texto, "link": link,
                        "ts": ahora.isoformat(timespec="seconds"), "enviado": False}
                if en_hora < int(conf.get("max_por_hora") or 0):
                    item["enviado"] = True
                    en_hora += 1
                    a_mandar.append(item)
                hist.append(item)
        hist = hist[-HISTORIAL_MAX:]
        # se olvidan los vistos de mas de 3 dias (una historia vieja no vuelve como nueva)
        corte = ahora - dt.timedelta(days=3)
        vistos = {k: v for k, v in vistos.items() if (_parse(v) or ahora) >= corte}
        e.update({"iniciado": True, "vistos": vistos, "historial": hist})
        try:
            _guardar(ESTADO_PATH, e)
        except Exception:
            pass
    if enviar and a_mandar:
        threading.Thread(target=_mandar, args=(a_mandar, conf, ahora), daemon=True, name="notificaciones").start()
    return {"historial": list(reversed(hist[-60:])), "config": conf,
            "estado": ("linea base tomada (%d importantes ya estaban; no se avisan)" % len(cands)) if primera
            else "%d nuevas, %d enviadas" % (len(nuevos), len(a_mandar))}


def _en_silencio(conf, ahora):
    h = ahora.astimezone(TZ_EC).hour
    d, a = int(conf.get("silencio_desde", 23)), int(conf.get("silencio_hasta", 7))
    return (d <= h or h < a) if d > a else (d <= h < a)


def _mandar(items, conf, ahora):
    if conf.get("ntfy") and not _en_silencio(conf, ahora):
        try:
            import movil
            cm = movil.cargar_config()
            if cm.get("avisos_activos"):
                for it in items:
                    movil.enviar(cm, it["titulo"][:120], it["texto"], prioridad=4 if it["tipo"] != "historia" else 3,
                                 click=it.get("link") or "")
        except Exception:
            pass
    if conf.get("windows") and os.name == "nt":
        for it in items[:3]:
            notificar_windows(it["titulo"], it["texto"])


def _ps_texto(s):
    return str(s or "").replace("'", "''").replace("\n", " ")[:200]


def notificar_windows(titulo, texto):
    """Notificacion nativa de Windows con PowerShell (WinRT), sin ventana.
    Usa el identificador de PowerShell para que Windows la muestre sin
    registrar una app nueva."""
    xml = ("<toast><visual><binding template='ToastGeneric'><text>{t}</text><text>{x}</text>"
           "</binding></visual></toast>").format(t=_esc_xml(titulo), x=_esc_xml(texto))
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
          "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
          "$d = New-Object Windows.Data.Xml.Dom.XmlDocument; $d.LoadXml('%s');"
          "$n = [Windows.UI.Notifications.ToastNotification]::new($d);"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
          "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)") % _ps_texto(xml)
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def _esc_xml(s):
    return (str(s or "")[:200].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))
