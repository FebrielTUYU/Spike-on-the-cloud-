# -*- coding: utf-8 -*-
"""
whatsapp.py -- Fase 20b: grupos de WhatsApp de barrio como voz de la gente.

Pedido de Fernando (2026-09-30): "Encuentra una forma de poder integrar
whatsapp". WhatsApp NO tiene ninguna API para leer grupos (ni gratis ni pagada:
la API de WhatsApp Business solo recibe mensajes enviados a UN numero de
empresa, nunca lee grupos), y automatizar una cuenta personal viola los
terminos de WhatsApp y arriesga que bloqueen el numero. La unica via legitima
es la que ya trae el propio WhatsApp: "Exportar chat".

Como se usa:
  1. En el telefono, dentro del grupo de barrio: Mas opciones > Mas > Exportar
     chat > "Sin archivos" (sin fotos).
  2. Mandarse el archivo (.txt o .zip) a la PC y subirlo desde la pestana
     Comunidad Guayaquil ("Importar chat de WhatsApp"), o dejarlo en la carpeta
     whatsapp_import/ junto al programa.
  3. Spike lo lee, se queda solo con los mensajes que nombran un problema, y
     los suma a Comunidad. Volver a exportar el mismo grupo otro dia no duplica
     nada (dedup por autor+texto).

Privacidad (a proposito): los nombres/telefonos de los participantes NUNCA se
guardan -- cada uno se reemplaza por "Vecino N (nombre del grupo)", estable
dentro del grupo (asi se sigue contando "personas distintas"). Si Fernando
necesita contactar a alguien, lo busca en su propio telefono.

Se asume que el grupo es de Guayaquil (lo eligio Fernando); el sector sale del
texto del mensaje o, si no lo nombra, del NOMBRE del grupo.
"""
import hashlib
import io
import os
import re
import unicodedata
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(HERE, "whatsapp_import")

# Android: "29/09/26, 15:04 - Nombre: texto"  /  "29/9/2026 3:04 p. m. - Nombre: texto"
# iOS:     "[29/09/26, 15:04:12] Nombre: texto"
_LINEA = re.compile(
    r"^‎?\[?(?P<d>\d{1,2})[/.-](?P<m>\d{1,2})[/.-](?P<a>\d{2,4}),?\s+"
    r"(?P<h>\d{1,2}):(?P<mi>\d{2})(?::\d{2})?\s*(?P<ampm>[ap]\.?\s?m\.?)?\]?\s*(?:-\s*)?"
    r"(?P<resto>.*)$", re.I)
# Solo cuerpos de mensaje que no son texto real (los avisos de sistema como
# "X se unio" no traen "autor: " y ya se descartan en parsear()).
_SISTEMA = re.compile(
    r"^(<?(multimedia|imagen|audio|video|sticker|gif|documento) omitid|<media omitted>|<adjunto|"
    r"se elimin[oó] este mensaje|eliminaste este mensaje|este mensaje fue eliminado|this message was deleted|"
    r"null$|<se edit)", re.I)


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def nombre_grupo(nombre_archivo):
    """'Chat de WhatsApp con Vecinos Sauces 8.txt' -> 'Vecinos Sauces 8'."""
    base = os.path.splitext(os.path.basename(nombre_archivo or ""))[0]
    base = re.sub(r"^(chat de whatsapp con|whatsapp chat with|chat con|_?chat)\s*", "", base, flags=re.I)
    return base.strip(" -_") or "grupo de WhatsApp"


def _fecha_iso(m):
    d, mes, a = int(m.group("d")), int(m.group("m")), int(m.group("a"))
    if a < 100:
        a += 2000
    if mes > 12 and d <= 12:  # formato mes/dia (telefonos en ingles)
        d, mes = mes, d
    h, mi = int(m.group("h")), int(m.group("mi"))
    ampm = (m.group("ampm") or "").lower().replace(".", "").replace(" ", "")
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    try:
        import datetime as dt
        return dt.datetime(a, mes, d, h, mi, tzinfo=dt.timezone(dt.timedelta(hours=-5))).isoformat()
    except ValueError:
        return ""


def parsear(texto):
    """Texto de un chat exportado -> [{'autor_real', 'texto', 'fecha'}] (los
    mensajes de varias lineas se juntan; los de sistema se descartan)."""
    msgs = []
    for linea in (texto or "").replace("\r\n", "\n").split("\n"):
        linea = linea.replace(" ", " ").replace("‎", "")
        m = _LINEA.match(linea)
        if m and ":" in m.group("resto"):
            autor, _, cuerpo = m.group("resto").partition(": ")
            if not cuerpo and autor.endswith(":"):
                autor, cuerpo = autor[:-1], ""
            msgs.append({"autor_real": autor.strip(), "texto": cuerpo.strip(), "fecha": _fecha_iso(m)})
        elif m:
            msgs.append(None)  # linea de sistema con fecha (sin "autor:"), corta el mensaje anterior
        elif msgs and msgs[-1] is not None and linea.strip():
            msgs[-1]["texto"] += "\n" + linea.strip()
    return [x for x in msgs if x and x["texto"] and not _SISTEMA.search(x["texto"])]


def anonimizar(msgs, grupo):
    """Cambia cada participante por 'Vecino N (grupo)', estable dentro del grupo."""
    orden = {}
    for x in msgs:
        clave = hashlib.sha1(_norm(x["autor_real"]).encode("utf-8")).hexdigest()
        orden.setdefault(clave, len(orden) + 1)
        x["autor"] = "Vecino %d (%s)" % (orden[clave], grupo)
        del x["autor_real"]
    return msgs


def leer_archivo(nombre, contenido):
    """contenido: bytes de un .txt o de un .zip exportado. Devuelve (grupo,
    mensajes anonimizados)."""
    grupo = nombre_grupo(nombre)
    if nombre.lower().endswith(".zip") or contenido[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            txts = [n for n in z.namelist() if n.lower().endswith(".txt")]
            if not txts:
                raise ValueError("el .zip no trae ningun .txt (exportar el chat 'Sin archivos')")
            contenido = z.read(txts[0])
    texto = contenido.decode("utf-8-sig", errors="replace")
    return grupo, anonimizar(parsear(texto), grupo)


def firma(ruta):
    st = os.stat(ruta)
    return "%d:%d" % (st.st_size, int(st.st_mtime))


def archivos_pendientes(procesados):
    """[(ruta, nombre)] de whatsapp_import/ que todavia no se procesaron (o que
    cambiaron desde la ultima vez: se re-exporto el mismo grupo)."""
    try:
        os.makedirs(CARPETA, exist_ok=True)
        nombres = sorted(os.listdir(CARPETA))
    except Exception:
        return []
    out = []
    for n in nombres:
        ruta = os.path.join(CARPETA, n)
        if not n.lower().endswith((".txt", ".zip")) or not os.path.isfile(ruta):
            continue
        if procesados.get(n) != firma(ruta):
            out.append((ruta, n))
    return out
