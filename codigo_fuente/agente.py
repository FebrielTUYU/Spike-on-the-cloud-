# -*- coding: utf-8 -*-
"""
Asistente de IA (Bloque 2, Parte F) -- el "agente" que Fernando puede
consultar sobre SUS datos, no solo la interpretacion nota-por-nota de ia.py.
Solo libreria estandar de Python 3.

Arquitectura de DOS pasos (se mantiene de la version con Ollama, sin
depender ya de ningun modelo local -- Fase 10, migracion a la nube):
  - CICLO DE HERRAMIENTAS (perfil RAPIDO de ia.py): decide que consultar,
    ronda por ronda, hasta MAX_RONDAS.
  - RESPUESTA FINAL (perfil PROFUNDO de ia.py): redacta una sola vez por
    pregunta, con TODO el material ya juntado, streameada.
Todo el transporte pasa por ia._generar_json()/ia._generar_stream(). Hasta
que la Fase 3 conecte Gemini, ia.disponible() es False y las rutas del
servidor (/api/asistente, /api/buscar_leer, chat de casos) ni siquiera
llegan a llamar aca.

Mismo principio de siempre (Parte B, "el codigo recupera, la IA solo
redacta"): las HERRAMIENTAS (herramientas.py) son funciones Python de solo
lectura sobre datos YA CALCULADOS -- el modelo nunca inventa un dato, solo
decide QUE consultar y despues REDACTA usando el material real que la
funcion le devuelve. Cada respuesta final debe citar de donde sale cada
afirmacion y separar "dato" de "inferencia propia" (ver
_PROMPT_RESPUESTA_FINAL) -- pedido explicito de Fernando.
"""
import json

import ia
import herramientas

MAX_RONDAS = 4

_TEMAS_TXT = ", ".join(ia.TEMA_CATALOG)

_PROMPT_DECISION = """Sos el asistente de investigacion de un periodista ecuatoriano que usa un \
monitor de noticias local. En este paso SOLO decidis que dato consultar para poder responder \
despues -- NO redactes la respuesta todavia.

Herramientas disponibles (nombre: para que sirve y que argumentos acepta):
- buscar_historias: args opcionales tema, ambito ("local" o "internacional"), seccion \
("politica"/"economia"/"seguridad"/"sociedad"/"general"), medio (nombre de un diario), q (texto \
libre), dias (antiguedad maxima), veredicto ("coincide"/"contradice"/"sin_datos"/"pendiente" -- \
usalo para preguntas sobre contradicciones entre medios o con fuentes oficiales), limite (cuantas \
traer). Busca notas del feed actual.
- detalle_historia: arg "clave" (la clave exacta que devolvio buscar_historias o buscar_guardadas). \
Trae el detalle completo de UNA nota: contexto verificado, veredicto de contraste, contratos \
SERCOP, verificaciones FactCheck.
- buscar_guardadas: arg opcional q (texto libre). Busca entre las notas que el periodista guardo \
para reportaje.
- buscar_notas: arg opcional q (texto libre). Busca entre las notas personales del periodista.
- tendencia_tema: arg "tema" (uno EXACTO del catalogo de abajo). Demanda de busqueda, cobertura de \
prensa (GDELT) y pulso social de ese tema.
- angulos_reportaje: args opcionales ambito ("local" o "internacional") y limite (numero, def. 8). Temas \
con brecha entre interes publico (busqueda o redes) y cobertura de medios, ordenados de mas a menos \
desatendidos -- usala para preguntas como "que angulo de reportaje me recomendarias" en vez de adivinar \
a partir de otras herramientas.
- comparar_periodo: args opcionales tema (uno del catalogo) y dias_atras (numero, def. 7). Compara \
la cobertura de hoy contra hace N dias.
- buscar_contratos_sercop: arg "termino" (una palabra o frase). Contratos publicos ya consultados \
sobre ese termino.
- buscar_constitucion: arg "termino" (texto libre, ej. "libertad de expresion"). Articulos de la \
Constitucion del Ecuador que mencionan ese tema, para citar "Art. N".
- buscar_boletines_oficiales: arg "termino" (texto libre). Boletines YA consultados de instituciones \
publicas (Asamblea Nacional, INEC, Banco Central, Registro Oficial) -- para contrastar cifras o \
afirmaciones de una noticia con la fuente oficial.
- buscar_declaraciones: arg "actor" (nombre de una persona con cargo publico, ej. "Daniel Noboa"). \
Declaraciones YA registradas de esa persona (que dijo, cuando, segun que medio), incluyendo si alguna \
quedo marcada como POSIBLE CONTRADICCION con algo que dijo antes -- usala para preguntas sobre si \
alguien se contradijo o cambio de postura.

Catalogo de temas validos: %s

Pregunta del periodista: "%s"

Lo que ya se consulto en este intercambio (herramienta -> resultado resumido):
%s

Devolve SOLO un JSON. Si ya hay material suficiente para responder con datos reales, o ya se \
probaron 2-3 herramientas razonables sin mas que buscar, devolve exactamente:
{"accion": "responder"}
Si hace falta mas dato, devolve:
{"accion": "consultar", "herramienta": "<uno de los nombres de arriba, EXACTO>", "args": {...}}
No inventes herramientas ni argumentos fuera de los listados. No repitas una consulta ya hecha con \
los mismos argumentos."""

_PROMPT_RESPUESTA_FINAL = """Sos el asistente de investigacion de un periodista ecuatoriano que usa \
este monitor de noticias local. Respondes su pregunta usando el material de abajo -- resultado REAL \
de consultar los propios datos del monitor (feed, guardadas, notas, demanda de busqueda, cobertura \
de prensa, pulso social, contratos SERCOP) -- nunca tu conocimiento general sobre Ecuador o el mundo, \
salvo que lo aclares EXPLICITAMENTE como tal ("por mi conocimiento general, no verificado aca...").

Reglas duras (no negociables):
- Cada afirmacion que venga del material va acompanada de su cita (el titular/medio, o el dato \
puntual de donde sale) -- no una fuente generica, la nota o el numero concreto.
- Separa SIEMPRE "dato" (esta literal en el material) de "inferencia" (tu propia lectura/conexion) \
-- marca la inferencia como tal ("mi lectura es que...", "esto podria sugerir...", "vale la pena \
preguntar si..."), nunca la mezcles con un dato como si fueran lo mismo.
- Si el material no alcanza para responder una parte de la pregunta, decilo explicitamente ("no \
tengo datos sobre X en este momento con lo que consulte") -- nunca completes con algo que no este \
en el material.
- Si el material trae versiones distintas o contradictorias entre medios, o entre una nota y un \
contrato SERCOP/una verificacion FactCheck, senalalo de forma explicita -- es exactamente el tipo \
de cosa que un periodista necesita saber.
- Si hay un angulo de reportaje o una fuente concreta a consultar, proponelo, pero marcado como \
sugerencia tuya, no como un hecho ya confirmado.
- Respuesta en espanol, directa, sin relleno. No repitas la pregunta.

Material disponible (herramienta consultada -> resultado real):
%s

Conversacion previa con este periodista:
%s

Pregunta del periodista: "%s"

Respuesta:"""


def _fmt_transcripcion(pasos):
    if not pasos:
        return "(nada consultado todavia)"
    out = []
    for p in pasos:
        out.append("- %s(%s) -> %s" % (
            p["herramienta"], json.dumps(p["args"], ensure_ascii=False),
            json.dumps(p["resultado"], ensure_ascii=False)[:900]))
    return "\n".join(out)


def _decidir_paso(pregunta, pasos, forzado=""):
    """Una ronda del ciclo de herramientas: le pregunta a la IA (perfil
    rapido) que hacer a continuacion. Devuelve {"accion": "responder"} o
    {"accion": "consultar", "herramienta":..., "args":...}. Ante cualquier
    fallo de parseo/red, devuelve {"accion": "responder"} -- mejor responder
    con lo que ya se junto que trabarse en el ciclo. 'forzado' se ignora
    (compatibilidad)."""
    try:
        r = ia._generar_json(_PROMPT_DECISION % (_TEMAS_TXT, pregunta, _fmt_transcripcion(pasos)),
                             perfil=ia.PERFIL_RAPIDO, temperatura=0.1, max_tokens=200, timeout=60)
        if not r:
            return {"accion": "responder"}
        if r.get("accion") == "consultar" and r.get("herramienta") in herramientas.HERRAMIENTAS:
            args = r.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            return {"accion": "consultar", "herramienta": r["herramienta"], "args": args}
        return {"accion": "responder"}
    except Exception:
        return {"accion": "responder"}


def _ejecutar_herramienta(nombre, args):
    """Llama a la funcion real de herramientas.py con los args que decidio el
    modelo, saneados (nunca deja pasar un kwarg que la funcion no acepta:
    evita que un argumento inventado tumbe el ciclo)."""
    fn = herramientas.HERRAMIENTAS.get(nombre)
    if fn is None:
        return {"error": "herramienta desconocida"}
    import inspect
    validos = set(inspect.signature(fn).parameters)
    args_ok = {k: v for k, v in (args or {}).items() if k in validos and v not in (None, "")}
    try:
        return fn(**args_ok)
    except Exception as e:
        return {"error": type(e).__name__}


def ciclo_herramientas(pregunta, on_progreso=None, max_rondas=MAX_RONDAS, forzado_decision=""):
    """Corre el ciclo de decision->herramienta hasta 'max_rondas' veces (o
    hasta que el modelo diga que ya alcanza). 'on_progreso(texto)', si se
    pasa, se llama con una linea corta por cada consulta real (para que el
    dashboard pueda mostrar que esta pasando mientras el ciclo corre, en vez
    de una espera muda). Devuelve la lista de pasos {"herramienta","args",
    "resultado"} -- el material real para la respuesta final."""
    pasos = []
    vistos = set()
    for _ in range(max_rondas):
        decision = _decidir_paso(pregunta, pasos, forzado=forzado_decision)
        if decision.get("accion") != "consultar":
            break
        nombre, args = decision["herramienta"], decision["args"]
        firma = (nombre, json.dumps(args, sort_keys=True, ensure_ascii=False))
        if firma in vistos:
            break  # el modelo repitio la misma consulta: cortar en vez de girar en el vacio
        vistos.add(firma)
        if on_progreso:
            try:
                on_progreso("consultando %s..." % nombre)
            except Exception:
                pass
        resultado = _ejecutar_herramienta(nombre, args)
        pasos.append({"herramienta": nombre, "args": args, "resultado": resultado})
    return pasos


def _responder_final_stream(pregunta, material, historial, on_delta, forzado_final="", timeout=220,
                             modelo_fn=None, num_predict=1600, num_ctx=None):
    """Compartido entre responder_stream (Asistente, Bloque 2),
    leer_busqueda_stream (Fase 4, buscador en vivo) y el chat de casos
    (Fase 7, Paso E): dado un MATERIAL ya armado, redacta y streamea la
    respuesta final citada con el perfil PROFUNDO de ia.py.

    'forzado_final', 'modelo_fn' y 'num_ctx' quedan solo por compatibilidad
    con los llamadores de monitor.py (antes elegian un modelo de Ollama y su
    ventana de contexto); 'num_predict' sigue siendo el tope de salida.
    Devuelve el texto completo, o None si no se genero nada."""
    ia.last_error = None
    turnos = []
    for h in (historial or [])[-8:]:
        rol = "Periodista" if h.get("rol") == "usuario" else "Vos"
        turnos.append("%s: %s" % (rol, str(h.get("texto", ""))[:500]))
    historial_txt = "\n".join(turnos) if turnos else "(sin turnos previos)"

    prompt = _PROMPT_RESPUESTA_FINAL % (material, historial_txt, pregunta)
    texto = ia._generar_stream(prompt, on_delta, perfil=ia.PERFIL_PROFUNDO,
                               temperatura=0.3, max_tokens=num_predict, timeout=timeout)
    return (texto or "").strip() or None


def responder_stream(pregunta, historial, on_delta, on_progreso=None, max_rondas=MAX_RONDAS,
                      forzado_decision="", forzado_final="", timeout=220):
    """Punto de entrada del asistente (Bloque 2): corre el ciclo de
    herramientas y despues STREAMEA la respuesta final (mismo patron que
    ia.chat_stream -- on_delta(texto_parcial) por cada pedazo). 'historial'
    es la conversacion previa de ESTA sesion del asistente (misma idea que
    el chat por item de Parte E: vive en el navegador, se manda entera cada
    vez, se pierde al recargar -- ver Decisiones ya tomadas). Devuelve el
    texto final completo, o None si no se genero nada."""
    pasos = ciclo_herramientas(pregunta, on_progreso=on_progreso, max_rondas=max_rondas,
                                forzado_decision=forzado_decision)
    material = _fmt_transcripcion(pasos) if pasos else "(no hizo falta consultar nada puntual)"
    return _responder_final_stream(pregunta, material, historial, on_delta,
                                    forzado_final=forzado_final, timeout=timeout)


def _fmt_material_busqueda(ambitos):
    """Arma el MATERIAL para leer_busqueda_stream a partir del resultado de
    monitor.buscar_en_vivo() -- mismo criterio que _fmt_transcripcion, texto
    legible con lo que hay REALMENTE (nunca inventa lo que falta)."""
    bloques = []
    for amb, datos in (ambitos or {}).items():
        if datos.get("vacio"):
            bloques.append("=== %s: sin resultados ===" % amb.upper())
            continue
        partes = ["=== %s ===" % amb.upper()]
        for n in (datos.get("noticias") or [])[:8]:
            partes.append("- Noticia: %s (%s)" % (n.get("titulo", ""), n.get("link", "")))
        for p in (datos.get("gente") or [])[:5]:
            partes.append("- %s (%s): %s" % (p.get("fuente", ""), p.get("autor", ""), (p.get("texto") or "")[:200]))
        interes = datos.get("interes")
        if interes:
            partes.append("- Interes de busqueda (%s): %s/100" % (interes.get("fuente"), interes.get("valor")))
        c = datos.get("contraste") or {}
        for a in (c.get("constitucion") or [])[:3]:
            partes.append("- Constitucion Art. %s: %s" % (a.get("numero"), (a.get("texto") or "")[:200]))
        for b in (c.get("boletines") or [])[:3]:
            partes.append("- Boletin oficial (%s): %s" % (b.get("institucion"), b.get("titulo")))
        for s in (c.get("sercop") or [])[:3]:
            partes.append("- SERCOP: %s" % (s.get("entidad") or s.get("objeto") or "contrato"))
        bloques.append("\n".join(partes))
    return "\n\n".join(bloques) if bloques else "(sin material)"


def leer_busqueda_stream(query, ambitos, on_delta, timeout=220):
    """Fase 4: lectura del Asistente sobre los resultados YA TRAIDOS por
    monitor.buscar_en_vivo() -- streameada, separada del endpoint que trae
    los datos (para que la espera del modelo pesado no frene mostrar
    noticias/gente/interes/contraste, que llegan mucho mas rapido). Cita
    cada afirmacion con su fuente, igual que responder_stream."""
    material = _fmt_material_busqueda(ambitos)
    pregunta = ("Resumime que se sabe sobre \"%s\" en cada ambito (Guayaquil/Ecuador/Mundo), "
                "citando de donde sale cada dato, y decime si hay algo destacable o contradictorio "
                "entre ambitos." % query)
    return _responder_final_stream(pregunta, material, [], on_delta, timeout=timeout)
