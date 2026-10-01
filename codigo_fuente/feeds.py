# -*- coding: utf-8 -*-
"""
Configuracion de fuentes (feeds RSS) del monitor.

- El bloque EL_UNIVERSO esta VERIFICADO: las URLs existen y devuelven
  items de politica y economia (patron Arc / outboundfeeds).
- El resto son CANDIDATOS. El colector prueba cada uno y descarta el que
  falle, e imprime un reporte de cuales funcionaron. Cuando corras en tu PC,
  revisa ese reporte y borra los que no sirvan o agrega los que quieras.

Para agregar un medio: copia una linea y cambia outlet / seccion / url.
seccion debe ser "politica" o "economia" (asi filtra el dashboard).
"""

# seccion puede ser:
#   "politica" / "economia"  -> el feed ya es de esa seccion (se toma tal cual)
#   "auto"                    -> feed general: el programa clasifica cada nota
#                               por palabras clave y descarta lo que no sea
#                               politica ni economia.
# Fase 24 (B3/E): fuentes institucionales = version oficial, nunca "medio".
FEEDS = [
    # ---- El Universo: feeds POR SECCION (verificado) ----
    {"outlet": "El Universo", "seccion": "politica",
     "url": "https://www.eluniverso.com/arc/outboundfeeds/rss-subsection/noticias/politica?outputType=xml"},
    {"outlet": "El Universo", "seccion": "economia",
     "url": "https://www.eluniverso.com/arc/outboundfeeds/rss-subsection/noticias/economia?outputType=xml"},

    # ---- Ecuador: feeds que FUNCIONARON en la corrida de Fernando (2026-09) ----
    {"outlet": "El Comercio", "seccion": "auto", "url": "https://www.elcomercio.com/feed/"},
    {"outlet": "Cronica",     "seccion": "auto", "url": "https://cronica.com.ec/feed/"},
    {"outlet": "El Mercurio", "seccion": "auto", "url": "https://elmercurio.com.ec/feed/"},
    {"outlet": "La Gaceta",   "seccion": "auto", "url": "https://lagaceta.com.ec/feed/"},
    {"outlet": "Plan V",      "seccion": "auto", "url": "https://planv.com.ec/feed/"},
    {"outlet": "Confirmado",  "seccion": "auto", "url": "https://confirmado.net/feed/"},
    {"outlet": "Wambra",      "seccion": "auto", "url": "https://wambra.ec/feed/"},  # 429 transitorio: puede volver
    # ---- Ecuador: agregados 2026-09-23 (Problema 5, "muy pocas noticias") --
    # probados uno por uno con urllib antes de agregarlos (ver CLAUDE.md,
    # "Arreglos del 2026-09-23"): HTTP 200 + XML real confirmado en vivo.
    {"outlet": "Expreso",     "seccion": "auto", "url": "https://www.expreso.ec/rss"},  # Guayaquil
    {"outlet": "El Norte",    "seccion": "auto", "url": "https://elnorte.ec/feed/"},    # antes daba ParseError, ahora sirve XML valido
    {"outlet": "El Diario (Manabi)", "seccion": "auto", "url": "https://www.eldiario.ec/feed/"},
    # ---- Ecuador: agregados 2026-09-23, segunda tanda (pedido explicito de
    # Fernando de mas fuentes de Guayaquil) ----
    {"outlet": "El Universo (Guayaquil)", "seccion": "auto", "ciudad": "Guayaquil",
     "url": "https://www.eluniverso.com/arc/outboundfeeds/rss-subsection/guayaquil/?outputType=xml"},
    # ^ "ciudad":"Guayaquil" (Problema 1/5, tercera ronda): esta ES la
    #   seccion editorial de Guayaquil de El Universo -- se etiqueta la
    #   ciudad a nivel de FEED (ver parse_feed/build_stories) para no
    #   depender de que el texto repita "Guayaquil" (una nota hiperlocal de
    #   un barrio, ej. "remodelacion de la plazoleta de Ceibos", no lo hace).
    #   Probado en vivo: 26 items reales, ninguno con "Guayaquil" en el
    #   titular. La URL "gran-guayaquil" (variante) devolvia 0 items en el
    #   momento de probar -- esta URL "guayaquil/" si tiene contenido real.

    # ---- Ecuador: FALLARON en la corrida (probados 2026-09-23); comentados
    #      para no ensuciar el reporte. Descomenta y prueba si quieres
    #      reintentar o si arreglas la URL. ----
    # {"outlet": "La Hora",      "seccion": "auto", "url": "https://www.lahora.com.ec/feed/"},        # HTTP 404
    # {"outlet": "La Republica", "seccion": "auto", "url": "https://larepublica.ec/feed/"},           # HTTP 200 pero devuelve HTML, no XML (dejo de tener feed)
    # {"outlet": "GK",           "seccion": "auto", "url": "https://gk.city/feed/"},                  # HTTP 403 (bloquea bots)
    # {"outlet": "Vistazo",      "seccion": "auto", "url": "https://www.vistazo.com/feed/"},          # HTTP 404 (probado tambien /rss: 404)
    # {"outlet": "El Productor", "seccion": "auto", "url": "https://elproductor.com/feed/"},          # HTTP 429
    # {"outlet": "Pichincha Com.","seccion":"auto", "url": "https://www.pichinchacomunicaciones.com.ec/feed/"},  # URLError
    # {"outlet": "Ecuavisa",     "seccion": "auto", "url": "https://www.ecuavisa.com/arc/outboundfeeds/rss/?outputType=xml"},  # HTTP 403 (probado tb /rss y /feed: 404)
    # {"outlet": "Primicias",    "seccion": "auto", "url": "https://www.primicias.ec/feed/"},         # HTTP 200 pero devuelve HTML (probado tb /rss: 404)
    # {"outlet": "Teleamazonas", "seccion": "auto", "url": "https://www.teleamazonas.com/feed/"},     # HTTP 404 (probado tb /rss: redirect infinito)
    # {"outlet": "El Telegrafo", "seccion": "auto", "url": "https://www.eltelegrafo.com.ec/feed/"},   # HTTP 404 (probado tb /rss: 404)
    # {"outlet": "Metro Ecuador","seccion": "auto", "url": "https://www.metroecuador.com.ec/feed"},   # HTTP 404

    # ---- Ecuador/Guayaquil: agregados 2026-09-23/24 (Fase 1, pedido explicito
    # de Fernando: "mas noticias y mas voz de la gente" de Guayaquil). Cada URL
    # probada a mano con fetch()+parse_feed() real antes de agregarla. "Extra"
    # ya se habia probado y descartado con /feed/ (404) -- con /rss SI anda. ----
    {"outlet": "Extra", "seccion": "auto", "url": "https://www.extra.ec/rss"},
    # ^ tabloide de Guayaquil (58 items reales probados), cobertura fuerte de
    #   seguridad/crimen local -- NO se le pone "ciudad":"Guayaquil" a proposito:
    #   aunque tiene sede en Guayaquil, tambien cubre nacional (ver "Decisiones
    #   ya tomadas": el ambito se decide por tema, no por el medio).
    {"outlet": "RTS", "seccion": "auto", "url": "https://www.rts.com.ec/feed/"},
    # ^ TV con sede en Guayaquil (20 items reales); mezcla entretenimiento
    #   (reality shows) con seguridad/comunidad real -- lo de farandula ya cae
    #   en categorias bajas via classify_section, no hace falta filtrarlo aparte.
    {"outlet": "TC Television", "seccion": "auto", "url": "https://www.tctelevision.com/feed/"},
    # ^ TV con sede en Guayaquil (30 items reales, cobertura nacional real:
    #   Fiscalia, carcel de Pascuales, salud, Presidencia).
    {"outlet": "Municipio de Guayaquil", "seccion": "auto", "ciudad": "Guayaquil", "institucional": True,
     "url": "https://www.guayaquil.gob.ec/feed/"},
    # ^ "ciudad":"Guayaquil" a proposito: es LITERALMENTE el gobierno de la
    #   ciudad (12 items reales probados, cultura/servicios municipales) --
    #   mismo criterio que El Universo (Guayaquil) arriba, cada nota es de
    #   Guayaquil por definicion, no hace falta que el texto lo repita.
    {"outlet": "Prefectura del Guayas", "seccion": "auto", "institucional": True, "url": "https://www.guayas.gob.ec/feed/"},
    # ^ SIN "ciudad" a proposito: es la PROVINCIA (10 items reales probados,
    #   agua/infraestructura), cubre varios cantones ademas de Guayaquil
    #   (Duran, Samborondon, Milagro...) -- que la clasificacion geografica
    #   normal (is_ecuador/detect_city sobre el texto) decida caso por caso.
    {"outlet": "ECU 911", "seccion": "auto", "institucional": True, "url": "https://www.ecu911.gob.ec/feed/"},
    # ^ servicio de emergencias NACIONAL (10 items reales probados, seguridad
    #   real) -- sin "ciudad", cubre todo el pais.
    {"outlet": "Presidencia Ecuador", "seccion": "auto", "institucional": True, "url": "https://www.presidencia.gob.ec/feed/"},
    # ^ gobierno nacional (10 items reales probados) -- mas cobertura real de
    #   Ejecutivo, no especifico de Guayaquil.
    # Respaldo pedido en Fase 1: busquedas de Google News por termino
    # geografico (pais/idioma Ecuador/es), para cubrir barrios/hechos que
    # ningun feed propio recoge. Probado en vivo: 100 items reales cada una,
    # contenido genuinamente relacionado (inundaciones, crimen, transito) con
    # ruido bajo (~1 en 10, ej. resultados deportivos que mencionan el nombre
    # de la ciudad de pasada). A proposito SIN "ciudad" fijo: a diferencia de
    # El Universo (Guayaquil)/Municipio de Guayaquil (una seccion editorial
    # real o el gobierno mismo, 100% del contenido es del lugar por
    # definicion), esto es una busqueda ALGORITMICA que puede traer falsos
    # positivos reales (confirmado en vivo: una busqueda de "Duran" trajo una
    # nota de un futbolista COLOMBIANO apellidado Duran, nada que ver con el
    # canton) -- se deja que la clasificacion geografica normal por texto
    # (is_ecuador/detect_city) filtre esos casos, en vez de forzarlos.
    # "google_news": True (Fase 9, Problema A2) -- Google News junta
    # "Titulo real - Medio" en el <title>: monitor.py separa el sufijo y usa
    # el medio real como outlet (en vez de contar 100+ items distintos bajo
    # este mismo nombre ficticio), y saca el sufijo del titulo antes de
    # clasificar/agrupar (el nombre del medio metia tokens basura en _sim()).
    {"outlet": "Busqueda: Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=Guayaquil&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: Duran EC", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=Dur%C3%A1n%20Ecuador&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: Samborondon", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=Samborond%C3%B3n&hl=es-419&gl=EC&ceid=EC:es-419"},
    # Fase 20 (foco comunitario en Guayaquil): busquedas por BARRIO y por la
    # palabra que usa la prensa ecuatoriana para la voz del barrio
    # ("moradores"). Solo nombres de sector que no existen como palabra comun
    # ni en otros paises (Guasmo, Isla Trinitaria, Mapasingue...); "Sauces" o
    # "Alborada" quedan fuera de la busqueda por ambiguos (siguen detectandose
    # en el texto por comunidad.py). NO verificadas en vivo desde la sesion
    # en la nube (sin red a Google): si alguna devuelve error, se ve en el
    # reporte de feeds y no rompe nada.
    {"outlet": "Busqueda: barrios sur/oeste GYE", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=%22Guasmo%22%20OR%20%22Isla%20Trinitaria%22%20OR%20%22Cristo%20del%20Consuelo%22%20OR%20%22Socio%20Vivienda%22%20OR%20%22Monte%20Sina%C3%AD%22&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: barrios norte/noroeste GYE", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=%22Mapasingue%22%20OR%20%22Pascuales%22%20OR%20%22Basti%C3%B3n%20Popular%22%20OR%20%22Flor%20de%20Basti%C3%B3n%22%20OR%20%22Mucho%20Lote%22%20OR%20%22Martha%20de%20Rold%C3%B3s%22&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: moradores Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=moradores%20Guayaquil&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: vecinos Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=vecinos%20Guayaquil&hl=es-419&gl=EC&ceid=EC:es-419"},
    # Fase 24 (B3): mas busquedas de Google News por INSTITUCION, por PROBLEMA y por
    # barrio (probadas en vivo el 2026-09-30: todas respondieron con 100 items). El
    # dedup normal del pipeline evita repetir lo que ya trae otro feed.
    {"outlet": "Busqueda: Interagua", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=Interagua&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: CNEL Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=CNEL+Guayaquil&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: ATM Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=ATM+Guayaquil+tr%C3%A1nsito&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: Bomberos Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=Bomberos+Guayaquil&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: problemas Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=Guayaquil+%28%22sin+agua%22+OR+apag%C3%B3n+OR+baches+OR+inundaci%C3%B3n+OR+alcantarillado+OR+basura%29&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: obras Guayaquil", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=obras+Guayaquil+Municipio&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: barrios centro/norte GYE", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=%22Urdesa%22+OR+%22Ceibos%22+OR+%22Garzota%22+OR+%22Kennedy+Norte%22+OR+%22Samanes%22+OR+%22V%C3%ADa+a+la+Costa%22+OR+%22V%C3%ADa+a+Daule%22&hl=es-419&gl=EC&ceid=EC:es-419"},
    {"outlet": "Busqueda: barrios sur/centro GYE", "seccion": "auto", "google_news": True,
     "url": "https://news.google.com/rss/search?q=%22Suburbio%22+OR+%22Batall%C3%B3n+del+Suburbio%22+OR+%22Cerro+Santa+Ana%22+OR+%22Las+Pe%C3%B1as%22+OR+%22Fertisa%22+OR+%22Pradera%22+OR+%22Esteros%22+Guayaquil&hl=es-419&gl=EC&ceid=EC:es-419"},
    # Fase 24 (B3): fuentes INSTITUCIONALES con feed que respondio en vivo (2026-09-30).
    # "institucional": True = es la VERSION OFICIAL de la institucion, NO un medio:
    # nunca cuenta como "medio que corrobora" en Contraste (Parte E). Probadas y
    # descartadas ese dia: EMAPAG, Interagua y Gobernacion del Guayas (no
    # responden), ATM (feed vacio).
    {"outlet": "CNEL EP", "seccion": "auto", "institucional": True, "url": "https://www.cnelep.gob.ec/feed/"},
    {"outlet": "Bomberos Guayaquil", "seccion": "auto", "institucional": True, "url": "https://www.bomberosguayaquil.gob.ec/feed/"},
    {"outlet": "Secretaria de Gestion de Riesgos", "seccion": "auto", "institucional": True, "url": "https://www.gestionderiesgos.gob.ec/feed/"},
    {"outlet": "INAMHI", "seccion": "auto", "institucional": True, "url": "https://www.inamhi.gob.ec/feed/"},
    # Fase 24 (B3): medio local con feed que respondio (80 notas). Probados sin feed
    # util ese dia: La Hora, Teleamazonas, Ecuavisa, Vistazo, El Telegrafo, Primicias, GK.
    {"outlet": "Metro Ecuador", "seccion": "auto", "url": "https://www.metroecuador.com.ec/arc/outboundfeeds/rss/"},

    # ---- INTERNACIONALES ("intl": True) ----
    # Politica y ECONOMIA DEL MUNDO desde medios de afuera. NO se filtran a Ecuador:
    # el clasificador conserva solo politica/economia (descarta deportes, farandula,
    # cultura, etc.) usando palabras clave en espanol e ingles. Apuntan a las
    # secciones de mundo / internacional / negocios de cada diario.
    # Todos son CANDIDATOS: el colector prueba cada URL y descarta la que falle.
    # -- Espana --
    {"outlet": "El Pais (Espana)", "seccion": "auto", "intl": True, "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada"},
    {"outlet": "El Mundo",         "seccion": "auto", "intl": True, "url": "https://e00-elmundo.uecdn.es/elmundo/rss/internacional.xml"},
    # -- Argentina --
    {"outlet": "Clarin",       "seccion": "auto", "intl": True, "url": "https://www.clarin.com/rss/mundo/"},
    {"outlet": "La Nacion (AR)","seccion": "auto", "intl": True, "url": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/el-mundo/?outputType=xml"},
    # -- Mexico --
    # {"outlet": "El Universal (MX)","seccion":"auto","intl":True,"url":"https://www.eluniversal.com.mx/rss.xml"},  # HTTP 404
    {"outlet": "La Jornada",       "seccion": "auto", "intl": True, "url": "https://www.jornada.com.mx/rss/mundo.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # -- Estados Unidos (world + business) --
    {"outlet": "NYT",          "seccion": "auto", "intl": True, "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"outlet": "NYT Business", "seccion": "auto", "intl": True, "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # -- Reino Unido (world + business) --
    {"outlet": "The Guardian","seccion": "auto", "intl": True, "url": "https://www.theguardian.com/world/rss"},
    {"outlet": "BBC News",    "seccion": "auto", "intl": True, "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"outlet": "BBC Business","seccion": "auto", "intl": True, "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # -- Alemania --
    # {"outlet": "Der Spiegel","seccion": "auto", "intl": True, "url": "https://www.spiegel.de/international/index.rss"},  # Fase 24 (D): sigue apagada: lo mas nuevo tenia 7,5 dias (probado 2026-10-01)
    {"outlet": "DW",         "seccion": "auto", "intl": True, "url": "https://rss.dw.com/rdf/rss-sp-all"},
    # -- Japon (ediciones en ingles) --
    {"outlet": "The Japan Times","seccion": "auto", "intl": True, "url": "https://www.japantimes.co.jp/feed/"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # {"outlet": "NHK World",    "seccion":"auto","intl":True,"url":"https://www3.nhk.or.jp/nhkworld/en/news/rss/all.xml"},  # HTTP 404
    # -- agregados 2026-09-23 (Problema 5), probados uno por uno --
    {"outlet": "Al Jazeera",   "seccion": "auto", "intl": True, "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"outlet": "France24 (ES)","seccion": "auto", "intl": True, "url": "https://www.france24.com/es/rss"},
    {"outlet": "SCMP",         "seccion": "auto", "intl": True, "url": "https://www.scmp.com/rss/91/feed"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # -- probados 2026-09-23, fallaron --
    # {"outlet": "Reuters World","seccion":"auto","intl":True,"url":"https://www.reutersagency.com/feed/?best-topics=world&post_type=best"},  # HTTP 404
    # {"outlet": "AP Top",       "seccion":"auto","intl":True,"url":"https://apnews.com/apf-topnews?format=rss"},  # HTTP 403
    # {"outlet": "Infobae America","seccion":"auto","intl":True,"url":"https://www.infobae.com/america/feeds/rss/"},  # HTTP 404 (la URL de abajo SI funciona)

    # ---- agregados 2026-09-23, segunda tanda (pedido explicito de Fernando:
    # "es necesario muchas mas fuentes... lleguemos a las 40") -- cada URL
    # probada a mano (HTTP 200 + XML real + parse_feed() real con items) ----
    # -- Espana / Francia / Italia / Austria (mas Europa) --
    {"outlet": "ABC.es (Internacional)", "seccion": "auto", "intl": True, "url": "https://www.abc.es/rss/feeds/abc_Internacional.xml"},
    {"outlet": "Euronews (ES)",  "seccion": "auto", "intl": True, "url": "https://es.euronews.com/rss"},
    {"outlet": "RFI (ES)",       "seccion": "auto", "intl": True, "url": "https://www.rfi.fr/es/rss"},
    {"outlet": "Le Figaro",      "seccion": "auto", "intl": True, "url": "https://www.lefigaro.fr/rss/figaro_international.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # {"outlet": "Corriere della Sera", "seccion": "auto", "intl": True, "url": "https://xml2.corriereobjects.it/rss/esteri.xml"},  # Fase 24 (D): sigue apagada: el feed no publica desde 2025 (probado 2026-10-01)
    {"outlet": "Der Standard",   "seccion": "auto", "intl": True, "url": "https://www.derstandard.at/rss/international"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # -- Reino Unido / Canada / Australia (mas anglo) --
    {"outlet": "Sky News",       "seccion": "auto", "intl": True, "url": "https://feeds.skynews.com/feeds/rss/world.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    {"outlet": "NPR (World)",    "seccion": "auto", "intl": True, "url": "https://feeds.npr.org/1004/rss.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    {"outlet": "CBC News (World)","seccion": "auto", "intl": True, "url": "https://www.cbc.ca/webfeed/rss/rss-world"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    {"outlet": "ABC News (AU)",  "seccion": "auto", "intl": True, "url": "https://www.abc.net.au/news/feed/51120/rss.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # -- Asia --
    {"outlet": "The Hindu",      "seccion": "auto", "intl": True, "url": "https://www.thehindu.com/news/international/feeder/default.rss"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    {"outlet": "Straits Times",  "seccion": "auto", "intl": True, "url": "https://www.straitstimes.com/news/world/rss.xml"},  # Fase 24 (D): reactivada; el filtro util/basura decide nota por nota
    # -- America Latina (mas fuentes, mas Colombia -- vecino directo) --
    # Fase 18 (P1-9): el feed GENERAL de Infobae/Semana traia sobre todo
    # noticias locales de Mexico/Colombia, plantas, vallenato y farandula
    # (medido en fetch_cache.json del 2026-09-30: Infobae 24 de 80 items
    # /mexico/, 10 /colombia/, 4 /teleshow/; Semana casi todo /nacion/).
    # 'rutas_permitidas': solo se quedan los items de esas secciones de la URL
    # (mundo/region), mas cualquier item que mencione Ecuador. Si Fernando
    # confirma un feed propio de mundo (ver SITEMAPS_Y_FEEDS_CANDIDATOS), se
    # puede cambiar la URL y quitar el filtro.
    {"outlet": "Infobae",        "seccion": "auto", "intl": True, "url": "https://www.infobae.com/arc/outboundfeeds/rss/",
     "rutas_permitidas": ["america", "estados-unidos", "mundo", "economia"]},
    {"outlet": "Semana (Colombia)", "seccion": "auto", "intl": True, "url": "https://www.semana.com/arc/outboundfeeds/rss/",
     "rutas_permitidas": ["mundo"]},
    {"outlet": "El Tiempo (Colombia)", "seccion": "auto", "intl": True, "url": "https://www.eltiempo.com/rss/mundo.xml"},
    # -- probados 2026-09-23 (segunda tanda), fallaron --
    # {"outlet": "DW (ES)",        "seccion":"auto","intl":True,"url":"https://rss.dw.com/xml/rss-es-all"},  # "Error: no feed by that name"
    # {"outlet": "TRT (ES)",       "seccion":"auto","intl":True,"url":"https://www.trt.net.tr/espanol/rss"},  # HTTP 200 pero devuelve HTML
    # {"outlet": "Haaretz",        "seccion":"auto","intl":True,"url":"https://www.haaretz.com/cmlink/1.628752"},  # HTTP 200 pero devuelve HTML
    # {"outlet": "CNN Espanol",    "seccion":"auto","intl":True,"url":"https://cnnespanol.cnn.com/feed/"},  # SSL certificate invalido
    # {"outlet": "Milenio",        "seccion":"auto","intl":True,"url":"https://www.milenio.com/rss/internacional.xml"},  # HTTP 404
    # {"outlet": "El Economista MX","seccion":"auto","intl":True,"url":"https://www.eleconomista.com.mx/rss/ultimasnoticias.xml"},  # HTTP 403
    # {"outlet": "La Tercera (Chile)","seccion":"auto","intl":True,"url":"https://www.latercera.com/arc/outboundfeeds/rss/"},  # HTTP 404
    # {"outlet": "ABC Paraguay",   "seccion":"auto","intl":True,"url":"https://www.abc.com.py/rss.xml"},  # HTTP 404
    # {"outlet": "El Pais Uruguay","seccion":"auto","intl":True,"url":"https://www.elpais.com.uy/rss/mundo"},  # HTTP 403
    # {"outlet": "Andes (agencia estatal EC)","seccion":"auto","url":"https://www.andes.info.ec/es/rss.xml"},  # timeout
    # {"outlet": "Metro Ecuador",  "seccion":"auto","url":"https://www.metroecuador.com.ec/feed"},  # HTTP 404
    # {"outlet": "Expreso (Guayaquil, seccion)","seccion":"auto","url":"https://www.expreso.ec/guayaquil/rss"},  # HTTP 404

    # Nota: si quieres un medio internacional filtrado SOLO a Ecuador, usa
    # "scope": "ec" en vez de (o ademas de) "intl": True en esa linea.
]

# Palabras clave por tema. El texto se compara sin acentos y en minusculas.
# Agrega o quita terminos libremente; cada nota puede quedar en varios temas.
# Cada tema mezcla terminos en espanol y en ingles (para clasificar diarios
# extranjeros). La coincidencia es por INICIO de palabra: "candidato" atrapa
# "candidatos", pero "eleccion" ya NO atrapa "seleccion" (futbol). Por eso se
# omiten terminos traicioneros como "tax" (taxi), "vat" (vatios), "import"
# (importante) o "bill" (billete): usan su forma plural/segura.
KEYWORDS = {
    "politica": {
        "Elecciones": ["eleccion", "elecciones", "candidato", "campana", "voto", "cne", "consulta popular", "referendum",
                       "election", "vote", "ballot", "candidate", "runoff"],
        "Asamblea/Leyes": ["asamblea", "asambleista", "ley", "proyecto de ley", "veto", "reforma",
                           "assembly", "law", "reform", "congress", "lawmaker"],
        "Ejecutivo": ["presidente", "gobierno", "ministro", "ministra", "decreto", "carondelet",
                      "president", "government", "minister", "decree", "cabinet"],
        "Justicia/Corrupcion": ["fiscalia", "corrupcion", "juez", "corte", "sentencia", "peculado", "cohecho",
                                "corruption", "prosecutor", "court", "bribery", "embezzlement"],
    },
    "economia": {
        "Fiscal/Presupuesto": ["presupuesto", "deficit", "deuda", "fmi", "gasto", "subsidio", "focalizacion",
                               "budget", "debt", "imf", "spending", "subsidy", "bailout"],
        "Impuestos": ["impuesto", "iva", "sri", "tributaria", "arancel",
                      "taxes", "taxation", "taxpayer", "tariff"],
        "Petroleo/Energia": ["petroleo", "crudo", "petroecuador", "energia", "apagon", "electricidad",
                             "oil", "crude", "energy", "blackout", "electricity"],
        "Empleo": ["empleo", "desempleo", "trabajo", "salario", "sueldo", "despido", "vacante", "plazas",
                   "unemployment", "jobs", "wage", "layoff", "hiring"],
        "Precios/Costo de vida": ["inflacion", "precio", "precios", "canasta", "costo de vida",
                                  "combustible", "gasolina", "diesel",
                                  "inflation", "price", "cost of living", "fuel", "gasoline"],
        # "inversion" a secas se saco (Problema 4, cuarta pasada, 2026-09-23):
        # demasiado generica -- cualquier programa social que mencione "una
        # inversion de $X millones" (ej. un plan de salud infantil) activaba
        # esta categoria de comercio sin tener nada que ver. Se exige la
        # frase completa (inversion extranjera/inversionista/privada), igual
        # que ya se hizo antes con otros terminos sueltos demasiado amplios
        # (ver EC_TERMS: "sucre", "los rios", "el oro").
        "Comercio/Inversion": ["exportacion", "importacion", "inversion extranjera", "inversionista",
                               "inversion privada", "dolar", "banco", "aranceles", "tratado comercial",
                               "export", "imports", "foreign investment", "investor", "dollar", "trade", "treaty"],
    },
    "seguridad": {
        "Narcotrafico": ["narcotrafico", "narco", "droga", "cartel", "microtrafico", "incautacion",
                         "drug", "trafficking", "cartel"],
        "Crimen/Violencia": ["asesinato", "sicariato", "homicidio", "masacre", "secuestro", "violencia",
                             "balacera", "ataque armado", "crimen", "delincuencia", "extorsion",
                             "murder", "violence", "shooting", "kidnapping", "crime"],
        "Carceles": ["carcel", "prision", "penitenciaria", "reo", "preso", "motin",
                     "prison", "inmate", "jail"],
        "Policia/Militar": ["policia", "militar", "fuerzas armadas", "operativo", "estado de excepcion",
                            "police", "military", "soldier", "troops"],
    },
    "sociedad": {
        "Salud": ["salud", "hospital", "clinica", "iess", "msp", "ministerio de salud",
                  "medico", "medicos", "medicina", "medicamento", "farmaco", "paciente",
                  "vacuna", "vacunacion", "epidemia", "pandemia", "brote", "contagio",
                  "dengue", "sarampion", "influenza", "virus", "enfermedad", "cancer",
                  "desnutricion", "mortalidad", "maternidad", "uci", "sanitario", "salubridad",
                  "health", "hospital", "outbreak", "disease", "vaccine", "patients"],
        "Educacion": ["educacion", "escuela", "colegio", "universidad", "estudiante", "docente",
                      "education", "school", "university", "student"],
        "Ambiente": ["ambiente", "ambiental", "contaminacion", "clima", "mineria", "derrame", "sequia", "inundacion",
                     "environment", "climate", "mining", "flood", "drought"],
        "Migracion": ["migracion", "migrante", "refugiado", "frontera", "deportacion",
                      "migration", "migrant", "refugee", "border", "deportation"],
        # "feriado"/"dia de descanso" agregado (Problema 4, cuarta pasada,
        # 2026-09-23): caso real que quedaba en 'otros' sin ninguna
        # categoria -- "Ecuador suma un nuevo dia de descanso... feriados de
        # 2026" no matcheaba ningun termino existente.
        "Cultura/Comunidad": ["cultura", "comunidad", "patrimonio", "indigena", "fiesta", "festival",
                              "feriado", "feriados", "dia de descanso", "puente vacacional", "asueto",
                              "culture", "community", "heritage", "holiday"],
    },
}

# Termino de busqueda que representa a cada tema en Google Trends (DEMANDA).
# Uno concreto y comun por tema. Editalo si no refleja lo que la gente busca.
# Si un tema no esta aqui, se usa su nombre.
TREND_TERMS = {
    "Elecciones": "elecciones", "Asamblea/Leyes": "asamblea nacional",
    "Ejecutivo": "gobierno", "Justicia/Corrupcion": "corrupcion",
    "Fiscal/Presupuesto": "subsidios", "Impuestos": "impuestos",
    "Petroleo/Energia": "apagones", "Empleo": "empleo",
    "Precios/Costo de vida": "precios", "Comercio/Inversion": "dolar",
    "Narcotrafico": "narcotrafico", "Crimen/Violencia": "inseguridad",
    "Carceles": "carceles", "Policia/Militar": "policia",
    "Salud": "salud", "Educacion": "educacion", "Ambiente": "medio ambiente",
    "Migracion": "migracion", "Cultura/Comunidad": "cultura",
}

# Articulo de Wikipedia (es) que representa a cada tema. Es la fuente ESTABLE de
# interes cuando Google Trends no responde (la API de Wikipedia no se bloquea).
# Elige articulos que existan; si uno no existe, ese tema simplemente no trae dato.
WIKI_TERMS = {
    "Elecciones": "Elecciones en Ecuador",
    "Asamblea/Leyes": "Asamblea Nacional del Ecuador",
    "Ejecutivo": "Presidente del Ecuador",
    "Justicia/Corrupcion": "Corrupción",
    "Fiscal/Presupuesto": "Subsidio",
    "Impuestos": "Impuesto",
    "Petroleo/Energia": "Petroecuador",
    "Empleo": "Desempleo",
    "Precios/Costo de vida": "Inflación",
    "Comercio/Inversion": "Dolarización",
    "Narcotrafico": "Narcotráfico",
    "Crimen/Violencia": "Homicidio",
    "Carceles": "Prisión",
    "Policia/Militar": "Policía Nacional del Ecuador",
    "Salud": "Salud",
    "Educacion": "Educación",
    "Ambiente": "Medio ambiente",
    "Migracion": "Migración humana",
    "Cultura/Comunidad": "Cultura del Ecuador",
}


# ------------------------- Fase 18 (P1-8/P1-9): candidatos a probar desde la PC -------------------------
# NO estan activos: la sesion donde se escribio esto no tenia acceso a los
# medios. `python monitor.py probar_sitemaps` los prueba uno por uno desde la
# PC de Fernando y guarda los que respondan (con notas de las ultimas 48 h) en
# feeds_extra.json, que monitor.py suma a FEEDS al arrancar. Resultado de cada
# prueba: ver la salida del comando (y CLAUDE.md, Fase 18).
SITEMAPS_Y_FEEDS_CANDIDATOS = [
    # news sitemaps ("ultimo minuto", suelen actualizarse antes que el RSS)
    {"outlet": "El Comercio", "seccion": "auto", "tipo": "sitemap", "url": "https://www.elcomercio.com/sitemap-news.xml"},
    {"outlet": "El Universo", "seccion": "auto", "tipo": "sitemap", "url": "https://www.eluniverso.com/arc/outboundfeeds/sitemap-news/?outputType=xml"},
    {"outlet": "El Universo", "seccion": "auto", "tipo": "sitemap", "url": "https://www.eluniverso.com/sitemap-news.xml"},
    {"outlet": "Expreso", "seccion": "auto", "tipo": "sitemap", "url": "https://www.expreso.ec/sitemap-news.xml"},
    {"outlet": "Expreso", "seccion": "auto", "tipo": "sitemap", "url": "https://www.expreso.ec/news-sitemap.xml"},
    {"outlet": "Extra", "seccion": "auto", "tipo": "sitemap", "url": "https://www.extra.ec/sitemap-news.xml"},
    {"outlet": "Extra", "seccion": "auto", "tipo": "sitemap", "url": "https://www.extra.ec/news-sitemap.xml"},
    {"outlet": "Primicias", "seccion": "auto", "tipo": "sitemap", "url": "https://www.primicias.ec/sitemap-news.xml"},
    {"outlet": "Primicias", "seccion": "auto", "tipo": "sitemap", "url": "https://www.primicias.ec/news-sitemap.xml"},
    {"outlet": "Ecuavisa", "seccion": "auto", "tipo": "sitemap", "url": "https://www.ecuavisa.com/sitemap-news.xml"},
    {"outlet": "Ecuavisa", "seccion": "auto", "tipo": "sitemap", "url": "https://www.ecuavisa.com/arc/outboundfeeds/news-sitemap/?outputType=xml"},
    # feeds de mundo de Infobae/Semana (P1-9), para reemplazar el filtro por ruta
    {"outlet": "Infobae", "seccion": "auto", "intl": True, "url": "https://www.infobae.com/arc/outboundfeeds/rss/category/america/"},
    {"outlet": "Semana (Colombia)", "seccion": "auto", "intl": True, "url": "https://www.semana.com/arc/outboundfeeds/rss/category/mundo/"},
]


# Fase 24 (B3/E): nombres de las fuentes institucionales (version oficial de una
# parte; nunca cuentan como "medios que coinciden" en Contraste).
OUTLETS_INSTITUCIONALES = {f["outlet"] for f in FEEDS if f.get("institucional")}
