# -*- coding: utf-8 -*-
"""
Fase 22c -- mapa de Guayaquil con lo que pasa por sector (pedido de Fernando:
"un mapa de Guayaquil estilo Google Maps donde existan alertas de las noticias
que se dan en cada momento; si sale una noticia de Urdesa, poner la apreciacion
de donde y que sector se cree que es").

Sin red ni IA: corre en el hilo rapido (write_outputs). El sector se detecta
con la MISMA lista de barrios que ya usa Comunidad (comunidad.detectar_barrio),
asi el mapa y la pestaña Comunidad hablan de los mismos lugares.

Honestidad: las coordenadas son el CENTRO APROXIMADO de cada sector, no la
direccion del hecho. El dashboard lo dice en cada punto ("ubicacion aproximada
del sector") y cuenta aparte lo que no se pudo ubicar, en vez de inventar un
punto.
"""
import datetime as dt
import math

try:
    import comunidad as _com
except Exception:  # pragma: no cover
    _com = None
try:  # Fase 24 (B4): lugares con nombre y calles, coordenadas de OpenStreetMap
    import lugares as _lug
except Exception:  # pragma: no cover
    _lug = None

# Centro aproximado de cada sector (lat, lon). Mismos nombres que
# comunidad.BARRIOS / comunidad.SECTORES / alertas.BARRIOS_GYE.
COORDS = {
    "Acacias": (-2.2210, -79.8880), "Alborada": (-2.1355, -79.9010), "Atarazana": (-2.1745, -79.8885),
    "Av. de las Americas": (-2.1650, -79.8930), "Bastion Popular": (-2.0850, -79.9310),
    "Batallon del Suburbio": (-2.2040, -79.9060), "Bellavista": (-2.1770, -79.9160),
    "Cdla. Kennedy": (-2.1720, -79.8980), "Ceibos": (-2.1690, -79.9450), "Centenario": (-2.2150, -79.8850),
    "Centro": (-2.1930, -79.8840), "Cerro Santa Ana": (-2.1800, -79.8760), "Cerro del Carmen": (-2.1830, -79.8840),
    "Chongon": (-2.2300, -80.0780), "Cristo del Consuelo": (-2.2080, -79.9160), "Daule": (-1.8630, -79.9780),
    "Duran": (-2.1720, -79.8310), "El Fortin": (-2.0880, -79.9750), "Febres Cordero": (-2.2090, -79.9230),
    "Fertisa": (-2.2530, -79.8930), "Flor de Bastion": (-2.0740, -79.9510), "Garzota": (-2.1470, -79.8930),
    "Guasmo": (-2.2640, -79.8840), "Guayacanes": (-2.1320, -79.8890), "Isla Trinitaria": (-2.2470, -79.9030),
    "Juan Montalvo": (-2.1000, -79.9450), "Kennedy": (-2.1600, -79.8990), "La Floresta": (-2.2370, -79.8920),
    "La Pradera": (-2.2170, -79.8930), "Las Malvinas": (-2.2230, -79.9090), "Las Orquideas": (-2.0960, -79.9010),
    "Letamendi": (-2.2050, -79.8990), "Lomas de Urdesa": (-2.1630, -79.9170), "Los Esteros": (-2.2330, -79.8990),
    "Los Vergeles": (-2.0920, -79.9150), "Mapasingue": (-2.1570, -79.9300), "Martha de Roldos": (-2.1320, -79.9250),
    "Miraflores": (-2.1740, -79.9150), "Monte Sinai": (-2.1050, -80.0100), "Mucho Lote": (-2.0860, -79.9050),
    "Nueva Prosperina": (-2.1250, -79.9750), "Nueve de Octubre": (-2.1905, -79.8880),
    "Paraiso de la Flor": (-2.0800, -79.9650), "Pascuales": (-2.0570, -79.9650), "Perimetral": (-2.1300, -79.9450),
    "Posorja": (-2.7000, -80.2400), "Prosperina": (-2.1430, -79.9510), "Puerto Hondo": (-2.1910, -80.0450),
    "Puerto Lisa": (-2.2150, -79.9230), "Samanes": (-2.1040, -79.9010), "Samborondon": (-2.1400, -79.8660),
    "Sauces": (-2.1230, -79.8980), "Sergio Toral": (-2.1150, -80.0000), "Socio Vivienda": (-2.0990, -79.9820),
    "Sopeña": (-2.1560, -79.8920), "Suburbio": (-2.2030, -79.9150), "Tarqui": (-2.1600, -79.9000),
    "Tenguel": (-2.9960, -79.7890), "Urbanor": (-2.1230, -79.8900), "Urdesa": (-2.1660, -79.9070),
    "Vergeles": (-2.0920, -79.9150), "Via a Daule": (-2.1100, -79.9400), "Via a la Costa": (-2.1750, -80.0100),
    "Ximena": (-2.2350, -79.8900),
    # Zonas amplias (menos precisas: se marcan como tales).
    "Norte de Guayaquil": (-2.1200, -79.9000), "Sur de Guayaquil": (-2.2400, -79.8900),
    "Noroeste de Guayaquil": (-2.1000, -79.9700),
}
ZONAS_AMPLIAS = {"Norte de Guayaquil", "Sur de Guayaquil", "Noroeste de Guayaquil", "Centro"}
# Localidad del Gran Guayaquil (monitor.LOCALIDAD_NOMBRE) -> sector del mapa.
LOCALIDAD_A_SECTOR = {"Samborondón": "Samborondon", "Samborondon": "Samborondon",
                      "Durán": "Duran", "Duran": "Duran", "Daule": "Daule"}
CENTRO_GYE = (-2.1700, -79.9200)
# Nombres cortos de sector que usan las historias madre (sub_actualizaciones).
_SUB_SECTOR = {"Norte": "Norte de Guayaquil", "Sur": "Sur de Guayaquil", "Noroeste": "Noroeste de Guayaquil",
               "Centro": "Centro", "Samborondon": "Samborondon", "Duran": "Duran", "Daule": "Daule"}
MAX_NOTICIAS = 160
HORAS_NOTICIAS = 72   # Fase 24 (B4): el dashboard elige 10, 24 o 72 h


def _parse(s):
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def sector_de_historia(h):
    """(sector, donde) o (None, None). 'donde' dice de que parte salio la
    apreciacion: la localidad del medio, el titular o el resumen."""
    loc = LOCALIDAD_A_SECTOR.get((h.get("localidad") or "").strip())
    if loc:
        return loc, "localidad"
    if _com is None:
        return None, None
    for campo, donde in (("titular", "titular"), ("resumen", "resumen")):
        s = _com.detectar_barrio(h.get(campo) or "")
        if s and s != getattr(_com, "SIN_SECTOR", ""):
            return s, donde
    return None, None


def ubicar_historia(h):
    """Fase 24 (B4). dict con sector, donde, coords y precision; None si la
    nota no nombra ningun lugar de Guayaquil. Orden: localidad del medio,
    sector en el titular o el resumen, y recien despues un lugar con nombre o
    una calle (coordenadas de OpenStreetMap, ya en cache: sin red aca)."""
    sector, donde = sector_de_historia(h)
    if sector:
        return {"sector": sector, "donde": donde, "coords": COORDS.get(sector),
                "precision": "zona amplia" if sector in ZONAS_AMPLIAS else "sector"}
    if _lug is None:
        return None
    for campo, donde in (("titular", "titular"), ("resumen", "resumen")):
        r = _lug.encontrar(h.get(campo) or "")
        if r:
            nombre, coords, metodo = r
            return {"sector": nombre, "donde": donde, "coords": coords,
                    "precision": "lugar" if metodo == "lugar" else "calle"}
    return None


def _desplazar(puntos):
    """Varios puntos en el mismo sector: una espiral chica para que no se tapen."""
    por = {}
    for p in puntos:
        por.setdefault(p["sector"], []).append(p)
    for grupo in por.values():
        for i, p in enumerate(grupo):
            if i == 0:
                continue
            ang, r = i * 2.4, 0.0011 * math.sqrt(i)
            p["lat"] = round(p["lat"] + r * math.cos(ang), 5)
            p["lon"] = round(p["lon"] + r * math.sin(ang), 5)


def puntos(historias, alertas=None, comunidad=None, ahora=None):
    """Arma data.json['mapa']: puntos por sector de noticias recientes de
    Guayaquil, alertas activas y temas de la comunidad."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    pts, sin_ubicar, sin_sector = [], [], 0

    def _agregar(tipo, sector, donde, coords=None, precision=None, **datos):
        c = coords or COORDS.get(sector)
        if not c:
            sin_ubicar.append({"tipo": tipo, "sector": sector, "titulo": datos.get("titulo", "")})
            return
        pts.append(dict(datos, tipo=tipo, sector=sector, donde=donde, lat=c[0], lon=c[1],
                        precision=precision or ("zona amplia" if sector in ZONAS_AMPLIAS else "sector")))

    def _reciente(h):
        f = _parse(h.get("newest"))
        return f is None or (ahora - f).total_seconds() <= HORAS_NOTICIAS * 3600

    guayaquil = [h for h in (historias or []) if h.get("ciudad") == "Guayaquil" and _reciente(h)]
    guayaquil.sort(key=lambda h: h.get("newest") or "", reverse=True)
    for h in guayaquil[:MAX_NOTICIAS]:
        subs = h.get("sub_actualizaciones") or []
        if subs:
            # Historia madre (evento en curso, Fase 18): cada actualizacion va en
            # su propio sector; la madre no tiene UN lugar.
            for sub in subs:
                sector, donde = sector_de_historia({"titular": sub.get("titular", "")})
                if not sector:
                    sector = _SUB_SECTOR.get(sub.get("sector") or "", sub.get("sector") if sub.get("sector") in COORDS else None)
                    donde = "sector de la actualizacion" if sector else None
                if not sector:
                    sin_sector += 1
                    continue
                _agregar("noticia", sector, donde, titulo=sub.get("titular", ""), link=sub.get("link", ""),
                         medios=len(sub.get("outlets") or []) or 1, hora=sub.get("fecha") or "",
                         seccion=h.get("seccion", ""), evento=h.get("titular", ""),
                         alto_impacto=bool(h.get("alto_impacto")))
            continue
        u = ubicar_historia(h)
        if not u:
            sin_sector += 1
            continue
        f0 = (h.get("fuentes") or [{}])[0]
        _agregar("noticia", u["sector"], u["donde"], coords=u["coords"], precision=u["precision"],
                 titulo=h.get("titular", ""), link=f0.get("link", ""),
                 medios=h.get("n_outlets", 1), hora=h.get("newest") or "",
                 seccion=h.get("seccion", ""), alto_impacto=bool(h.get("alto_impacto")))
    for a in (alertas or []):
        if not a.get("lugar"):
            continue
        s0 = (a.get("senales") or [{}])[0]
        _agregar("alerta", a["lugar"], "alerta", titulo=(s0.get("texto") or "")[:200],
                 link=s0.get("url", ""), tipo_alerta=a.get("tipo", ""), estado=a.get("estado", ""),
                 hora=a.get("ultima_senal") or a.get("primera_deteccion") or "")
    for t in ((comunidad or {}).get("temas") or []):
        b = t.get("barrio")
        if not b or b == getattr(_com, "SIN_SECTOR", ""):
            continue
        _agregar("comunidad", b, "comunidad", titulo=t.get("titulo", ""), personas=t.get("personas", 0),
                 cubierto=bool(t.get("cubierto")), hora=t.get("ultima") or "", tema_id=t.get("id", ""))
    _desplazar(pts)
    cuenta = {}
    for p in pts:
        cuenta[p["tipo"]] = cuenta.get(p["tipo"], 0) + 1
    metodos = {}
    for p in pts:
        if p["tipo"] == "noticia":
            metodos[p["precision"]] = metodos.get(p["precision"], 0) + 1
    estado = ("%d en el mapa (noticias de las ultimas %d h: %d, alertas %d, comunidad %d); %d noticias de Guayaquil "
              "no nombran ningun sector, lugar ni calle (hablan de la ciudad entera)" % (
                  len(pts), HORAS_NOTICIAS, cuenta.get("noticia", 0), cuenta.get("alerta", 0),
                  cuenta.get("comunidad", 0), sin_sector))
    return {"puntos": pts, "centro": list(CENTRO_GYE), "sin_sector": sin_sector, "metodos": metodos,
            "horas_noticias": HORAS_NOTICIAS,
            "sin_ubicar": sin_ubicar[:20], "estado": estado, "generado": ahora.isoformat()}
