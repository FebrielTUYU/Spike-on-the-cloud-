# Spike — Monitor de noticias Ecuador (contexto para Claude Code)

## Nombre del proyecto (Fase 11, 2026-09-28)
El programa se bautizo oficialmente **"Spike"** (pedido explicito de Fernando). El
codigo fuente sigue viviendo en `monitor.py` (no se renombro el script principal --
cambiar ese nombre tocaria demasiadas referencias sin ningun beneficio real) y todo
este documento se sigue refiriendo al programa como "el Monitor" en el texto historico
de abajo (no reescrito a mano modificacion por modificacion). Lo que SI cambio: el
ejecutable compilado (`compilar.bat`, Fase 11) ahora se llama **`Spike.exe`** (con
icono propio, `logo.ico`, generado desde `logo.png`) en vez de `monitor.exe`, y esa es
la cara visible del programa para Fernando de ahora en mas.

## Qué es esto
Programa **local** en Python (nombre de producto: **Spike**) que monitorea el "mercado"
de noticias de Ecuador y del mundo: recolecta feeds RSS, agrupa la misma historia
contada por varios medios, mide qué se cubre vs. qué busca/dice el público, y sugiere
temas poco cubiertos para hacer reportajes. Es una herramienta personal de un
**estudiante de periodismo**.

## Con quién hablas (importante)
El usuario (Fernando) **no domina la terminal**. No asumas conocimiento de shell.
- Cuando propongas un comando, explica en una línea qué hace y por qué, y dáselo listo para copiar.
- Prefiere **una acción concreta a la vez** sobre listas largas de pasos.
- Si algo puede romper o borrar datos, avísale antes.
- Responde en **español**.

## Regla de oro del proyecto
**Solo librería estándar de Python 3. NO instalar dependencias con pip.** Todo el
código usa `urllib`, `json`, `xml.etree`, `http.server`, `threading`, `dataclasses`.
Si crees que hace falta una librería externa, propón primero una alternativa con stdlib.
**Única excepción, pre-autorizada por Fernando**: `pypdf` (Fase 7, Paso C — leer PDF subido a un caso
del Asistente; instalada con `pip install pypdf`). Cualquier otra excepción, consultar primero.

## Cómo se corre
- `python monitor.py` (Fase 12, sin argumentos) — arranca la **app de
  escritorio**: levanta el servidor en vivo (**dos velocidades**, ver más
  abajo) en http://localhost:8000 y abre una ventana nativa (`pywebview`)
  con el dashboard — esto es lo que hace el doble clic sobre el ejecutable
  compilado. Sin argumentos es ahora EXACTAMENTE lo mismo que
  `python monitor.py serve` (mismo puerto/`MONITOR_FEED_MIN` por defecto).
  Si `pywebview` no está instalado o falla al abrir la ventana, cae solo al
  modo de siempre (abre el navegador, el servidor sigue igual). Cerrar la
  ventana nativa termina el proceso entero (servidor + hilos de fondo
  incluidos) — no queda nada corriendo en segundo plano sin ventana visible.
- `python monitor.py serve` — mismo modo en vivo de arriba, invocado
  explícito (sirve en http://localhost:8000, el feed se publica cada
  `MONITOR_FEED_MIN` sin esperar nunca a la IA). `INICIAR.bat` (Windows)
  sigue llamándolo así, explícito, sin depender del nuevo default.
- `python monitor.py once` (Fase 12 — antes era el comportamiento por
  defecto sin argumentos) — una corrida COMPLETA bloqueante: lee feeds,
  clasifica, calcula IA + contexto + social en vivo, genera
  `dashboard.html`/`data.json` y termina sola, sin servidor ni ventana. Es
  la vía que necesitan scripts/pruebas que generan datos sin abrir nada en
  vivo.
- `MONITOR_SAMPLE=1 python monitor.py once` — datos de ejemplo, sin
  internet (para probar).

## Requisitos en la PC
- **Python 3** instalado y en el PATH (`python --version`).
- **Ollama** para el agente de IA local y la lectura OSINT de redes: instalar Ollama y
  bajar un modelo con `ollama pull qwen2.5:3b` (elegido por su tamaño: 1.9 GB, corre
  entero en GPUs chicas de 4GB VRAM, y sigue bien instrucciones de JSON en español).
  Sin modelo, el programa igual corre; solo se apagan la interpretación IA y el
  análisis OSINT. `ia.py` y `social.py` autodetectan el modelo instalado (lista
  `PREFER` en ia.py); forzar uno puntual con `MONITOR_IA_MODEL`.

## Módulos
- `monitor.py` — motor: colector RSS (en paralelo, `ThreadPoolExecutor`), dedup,
  clustering por titular, prominencia/interés, demanda, GDELT, SERCOP, IA,
  contexto por entidad (Parte B; incluye `registrar_apariciones`/
  `apariciones_previas` sobre `entities.json`, ver Caches más abajo), escucha
  social, dos velocidades (Parte C: `run_fast`/`enrich_pass`/`serve`),
  Guardadas (`saved.json` + endpoint `POST /api/guardar`), chat por item
  (Parte E: `POST /api/chat`, puente a Ollama) — el servidor http corre con
  `ThreadingMixIn` (`ServidorHilos`) para que `/api/chat` no congele el resto
  mientras espera al modelo — y la salida (JSON + HTML).
  `geo_hit()` decide ámbito Ecuador/Mundo por PALABRA COMPLETA (no por
  prefijo como `kw_hit`, que a propósito atrapa plurales de un tema): un
  nombre de lugar no necesita esa flexibilidad, y el prefijo suelto causaba
  colisiones reales (`canar` dentro de "Canarias", España; `napo` dentro de
  "Napoleón"). La usan `is_ecuador`/`is_foreign`/`detect_city`.
  `normalizar_categoria()`/`contar_por_categoria()`/`imprimir_categorias()`
  (Problema 2, 2026-09-23): punto único de normalización de `seccion` y
  conteo por categoría (terminal + `test_categorias.py`).
  `construir_salud_fuentes()` (Problema 3): registro de salud de datos por
  corrida (`data.json["salud_fuentes"]`). `cluster()` (Problema 5): además
  del solape de palabras, une por ventana de tiempo (`CLUSTER_MAX_HORAS`) +
  nombre propio compartido con umbral más bajo (`_nombres_propios`, evita
  Title Case inglés). `get_veredicto()` (Problema 4): estado
  coincide/contradice/sin_datos por historia, cachea en `veredicto_cache.json`.
- `feeds.py` — FEEDS (Ecuador + internacionales con `"intl":True`), KEYWORDS por
  categoría (politica/economia/seguridad/sociedad), TREND_TERMS, WIKI_TERMS.
  Ampliado 2026-09-23 (Problema 5): +Expreso/El Norte/El Diario (Ecuador),
  +Al Jazeera/France24 ES/SCMP (internacional) — cada URL probada a mano
  antes de agregarla, ver el arreglo de esa fecha para las que se probaron
  y NO sirvieron (con el motivo).
- `trends.py` — Google Trends (búsquedas del público). Inestable, da 429 seguido.
- `wiki.py` — vistas de Wikipedia (interés estable, respaldo cuando Trends falla) y
  `resumen(entidad, busqueda="")`: verifica un nombre propio contra Wikipedia
  (endpoint REST de resumen, solo título EXACTO/redirección real — nunca búsqueda
  difusa por defecto, que puede "verificar" una entidad contra un artículo no
  relacionado) para el contexto real. `busqueda` (opcional, Capa 1 del bug de
  Carney — ver Decisiones ya tomadas) usa la API de búsqueda de Wikipedia SOLO
  para elegir el título correcto con más contexto que el nombre suelto; el
  fetch final sigue siendo el mismo título exacto/verificado de siempre.
- `gdelt.py` — GDELT DOC 2.0: volumen de cobertura + tono por tema (`interest`), y
  `articulos()`/`comenciones()`: co-menciones de una entidad en prensa reciente
  (modo lista de artículos), para el contexto real. Gratis, sin clave, pero
  frecuente 429 (rate limit propio de GDELT).
- `sercop.py` — Contrataciones Abiertas (OCDS): contratos públicos para contrastar noticias.
- `factcheck.py` — Google Fact Check Tools API (`claims:search`): verificaciones
  periodísticas (ClaimReview) relacionadas con el titular o la entidad
  principal de una nota, para el sector Contraste junto a SERCOP. Necesita
  `MONITOR_FACTCHECK_KEY` (API distinta de YouTube, hay que habilitarla aparte).
- `ia.py` — agente IA local vía Ollama (`http://localhost:11434`): reclasifica por
  significado, decide Ecuador/mundo por sentido, escribe interpretación por nota
  (`analizar`), extrae entidades candidatas con una búsqueda desambiguada por
  contexto de la nota (`extraer_entidades`, Capa 1 del bug de Carney), redacta el
  contexto grounded SOLO con material ya verificado (`contextualizar`), y decide
  si una página de Wikipedia encontrada es realmente la misma entidad que la nota
  menciona (`coincide_dominio`, Capa 2) — nunca consulta Wikipedia/GDELT por su
  cuenta, eso lo hace monitor.py. `chat_stream()` (Parte E) es la única
  función que conversa en TEXTO LIBRE (sin `format="json"`) Y que STREAMEA
  (Frente B): responde on-demand al chat por item del dashboard llamando a
  `on_delta(texto_parcial)` por cada pedazo que Ollama va generando, en vez
  de devolver el bloque completo. `MODOS_CHAT` ("rapido"/"profundo") decide
  tanto el MODELO (`elegir_modelo_chat()` → "monitor-critico" solo en
  "profundo"; el modelo rápido del pipeline en "rapido") como
  `num_predict`/`num_ctx` — ver Decisiones ya tomadas para el porqué (bajar
  num_predict solo, sin cambiar de modelo, no funciona con un modelo de
  razonamiento). `veredicto_contraste()` (Problema 4, 2026-09-23): redacta
  coincide/contradice/sin_datos citando el material ya verificado que le pasa
  monitor.py (contexto+SERCOP+FactCheck), nunca busca por su cuenta.
  `extraer_entidades_con_evento()` (Problema 6): como `extraer_entidades()`
  pero también propone un candidato de EVENTO (ley/paro/conflicto) con
  posible página propia de Wikipedia, para priorizarlo sobre bios de
  persona en el contexto (`extraer_entidades()` sigue igual, wrapper de
  compatibilidad).
- `herramientas.py` (Bloque 2, Parte F) — funciones de SOLO LECTURA sobre los
  datos YA CALCULADOS del monitor, para que el Asistente pueda consultarlas:
  `buscar_historias` (tema/ámbito/sección/medio/texto/antigüedad),
  `detalle_historia` (contexto verificado + veredicto + SERCOP + FactCheck de
  UNA nota), `buscar_guardadas`/`buscar_notas` (contenido de Fernando),
  `tendencia_tema` (demanda + GDELT + pulso social de un tema, con el mismo
  cálculo de `demandaTema()` del dashboard) y `comparar_periodo` (hoy vs. hace
  N días, usando `history.json`). Mismo principio de Parte B llevado al
  agente: **nunca** llama a una API externa en vivo (Trends/GDELT/SERCOP/
  redes) — lee lo que `run_fast`/`enrich_pass` ya guardaron, así que usar el
  Asistente no agrega latencia ni riesgo de rate-limit nuevo. `_normalizar_tema()`
  tolera que el modelo no reproduzca el nombre EXACTO del catálogo (bug real
  encontrado probando en vivo: pasó `"carceles"` en vez de `"Carceles"`, 0
  resultados hasta agregar la normalización — mismo problema que ya resolvió
  `ia._TEMA_LOOKUP` para la clasificación por lotes).
- `agente.py` (Bloque 2, Parte F) — el Asistente: ciclo de herramientas +
  respuesta final citada. Arquitectura de DOS modelos, elegida con un
  benchmark real en esta PC (ver Decisiones ya tomadas): **qwen2.5:3b**
  decide qué consultar, ronda por ronda (`ciclo_herramientas()`, hasta
  `MAX_RONDAS`=4, corta si el modelo repite la misma consulta); **monitor-critico**
  (el mismo modelo pesado del chat "profundo" de Parte E) redacta la
  respuesta final UNA sola vez, streameada (`responder_stream()`, mismo
  patrón que `ia.chat_stream`), citando cada afirmación y separando dato de
  inferencia (`_PROMPT_RESPUESTA_FINAL`). `on_progreso()` le avisa al
  dashboard qué se está consultando mientras el ciclo corre (si no, la
  espera de varios segundos antes de la respuesta se siente muda).
- `casos.py` (Fase 7, Pasos B-E) — el Asistente de CASOS: un espacio de trabajo por
  reportaje, standalone (no importa monitor.py, sí importa ia.py directo para
  embeddings/sugerencias). Una subcarpeta por caso en `casos/<id>/`
  (caso.json/docs//index.sqlite3/docs_estado.json/avisos.json/notas.json/
  evidencia.json/tablero.json — contenido real de Fernando, no un caché). CRUD de
  casos/entidades/notas/evidencia/avisos/tablero; ingesta de documentos
  (`.txt`/`.md`/`.docx` con stdlib, `.pdf` con `pypdf`) fragmentados (~500
  palabras, solape 50) e indexados con embeddings de Ollama; `buscar_fragmentos()`
  hace similaridad coseno en Python puro sobre el índice sqlite3 del caso. Ver la
  sección "Asistente de casos" más abajo para el detalle completo (API, puente
  Dashboard→Asistente sin IA, chat del caso, pruebas).
- `social.py` — escucha social desde fuentes PÚBLICAS: Bluesky (XRPC público, sin
  cuenta, pilar fiable), Mastodon (timeline pública de hashtag, sin cuenta,
  agregado 2026-09-23), Reddit (.json público, best-effort) y YouTube (Data API
  v3, necesita `MONITOR_YT_KEY`; clasifica canal medio/creador vía
  `_yt_canales_info`, Problema 1). Dataclass `SocialPost` unifica todas;
  `filtrar_ruido()` descarta autopromoción/reacciones de una palabra/puro emoji
  ANTES de que nada las use (aplica en `recolectar()`, asi el panel y el OSINT
  siempre ven lo mismo); `analizar_osint()` manda los textos ya filtrados a
  Ollama y devuelve JSON {sentimiento_general, polarizacion, temas_recurrentes,
  resumen_discusion}. `recolectar()` tambien filtra por antiguedad
  (`_es_reciente`, `MONITOR_SOCIAL_DIAS`) ademas de por ruido — ver Decisiones
  ya tomadas, bug real de publicaciones de años saliendo como "la mejor".
- `dashboard_template.html` — la UI (Noticias / **Pulso social** / Estadísticas /
  Oportunidades / Contraste / **Guardadas**). El motor inyecta el payload
  reemplazando `/*__DATA__*/null`. El HTML consulta `data.json` cada minuto
  para refrescarse en modo `serve`. `renderContexto(h)` muestra `h.contexto` en
  la tarjeta ("analizando…" si el trabajador no llegó todavía, "sin contexto
  disponible" si no encontró nada, o el texto grounded con las entidades
  verificadas como enlace) y, si `c.previas` tiene algo (`entities.json`,
  Parte B), una línea "También apareció" con fecha y enlace a la nota
  anterior — se muestra AUNQUE no haya contexto de Wikipedia/GDELT, es
  justamente el caso de una entidad sin página propia (ver bug de Jordán en
  Decisiones ya tomadas). `renderSocial()` es el panel "¿Qué dice la gente al
  respecto?" — sección propia (no escondida en Estadísticas), segmentado por
  Guayaquil/Ecuador/Internacional igual que el resto del dashboard
  (`tema_ambito_map` en monitor.py decide el ámbito de cada tema; la búsqueda
  real que arma el termino, `_social_query`, se explica en la sección Parte A
  de más abajo). Por tema top: volumen de conversación etiquetado
  "(relativo)", desglose de publicaciones por fuente (ej. "Bluesky 15 ·
  YouTube 27 · Reddit 0"), sentimiento, polarización, temas recurrentes,
  resumen OSINT, y la MEJOR publicación de CADA fuente presente (nunca un top
  mezclado por engagement crudo entre plataformas). "sin conversación
  captada" si un tema no tiene nada tras el filtro de ruido.
  `renderContraste()` agrupa por ámbito (Internacional / Nacional (Ecuador) /
  Guayaquil, ver Decisiones ya tomadas) en tarjetas compactas (reusa
  `cardHTML`) que también muestran `h.factcheck` (Google Fact Check Tools)
  junto a los contratos SERCOP: "Verificaciones relacionadas" con la
  calificación y el verificador, o "sin verificaciones relacionadas". En
  Noticias, un toggle **Recientes/Anteriores** (`s.antigua`, Parte B) separa
  lo fresco (< `MONITOR_FEED_FRESH_H`) de lo más viejo pero aún dentro de
  `MONITOR_MAX_DIAS` — nada se descarta en silencio. Cada tarjeta tiene un
  botón estrella (`cardHTML`, compartido entre Noticias y Guardadas) para
  mandarla a la pestaña **Guardadas** (Parte C, ver más abajo). `renderGap()`
  (Oportunidades) rankea la brecha por "interés público" = la mayor entre
  demanda de búsqueda y volumen de pulso social por tema (ver Decisiones ya
  tomadas), no solo búsqueda. Cualquier tarjeta (historia o tema) se puede
  clickear para abrir un modal de detalle con chat a la IA local (Parte E,
  `abrirDetalleHistoria`/`abrirDetalleTema`, `POST /api/chat`). El chat lee
  la respuesta con `response.body.getReader()` (streaming, Frente B): la
  burbuja de la IA se llena en vivo token a token. Toggle "⚡ Rápido /
  🔍 Profundo" (`chatModo`) decide qué tan magro es el contexto que se manda
  (`contextoChatHistoria`/`Tema(..., profundo)`) — ver Decisiones ya tomadas.

## Caches (archivos que se generan solos, no editar a mano)
`trends_cache.json`, `gdelt_cache.json`, `sercop_cache.json`, `ia_cache.json`,
`contexto_cache.json` (Parte B, por historia/link), `factcheck_cache.json`
(por historia/link), `social_cache.json`, `history.json`, `data.json`,
`dashboard.html`.

`saved.json` es distinto de estos: no es un caché recalculable, es **contenido
que Fernando eligió a mano** (Parte C, "Guardadas"). Guarda la historia
COMPLETA (no un id), así que sobrevive a que la noticia caduque del feed o el
dashboard se regenere. Se escribe con archivo temporal + `os.replace` (más
cuidadoso que el `json.dump` directo de los caches de arriba). Si no existe
todavía (nadie guardó nada), no es un error.

`entities.json` tampoco es un caché recalculable (aunque se parece): es un
**registro de apariciones** (Parte B, caso Jordán) — qué entidad, cuándo, en
qué historia. Se llena en `registrar_apariciones()` con TODOS los candidatos
que extrae la IA por historia (verificados en Wikipedia o no), y se consulta
en `apariciones_previas()` para mostrar "También apareció" en la tarjeta.
Clave por nombre normalizado (`norm()`, sin acentos/mayúsculas) — dos personas
homónimas se mezclarían (riesgo aceptado, bajo para nombres propios completos).
Hasta `ENTITIES_MAX_POR_ENTIDAD` (20) apariciones guardadas por entidad, se
recorta lo más viejo. Si se borra a mano no pasa nada grave: se reconstruye
solo, de a poco, con las notas nuevas.

La carpeta `casos/` (Fase 7, Asistente de casos) tampoco es un caché: cada
`casos/<id>/*.json` (mas `index.sqlite3`) es contenido real que Fernando creó
a mano (casos, documentos, entidades, notas) — nunca se borra ni se
reconstruye solo. Ver la sección "Asistente de casos" más abajo.

## Arquitectura de dos velocidades (Parte C, modo `serve`)
- **Hilo rápido** (`run_fast`, cada `MONITOR_FEED_MIN`): feeds → dedup → cluster →
  clasificación por palabras clave → prominencia → LEE los caches de
  enriquecimiento (`ia_cache.json`, `contexto_cache.json`, `factcheck_cache.json`,
  `social_cache.json`, modo_lectura=True) y publica `data.json`/`dashboard.html`.
  Es el ÚNICO que escribe esos dos archivos. Nunca llama a Ollama.
- **Hilo trabajador** (`enrich_pass`, de fondo, cada `MONITOR_WORKER_PAUSA`):
  lee las historias del último `data.json` (así se enteran sin compartir objetos
  de Python — el punto de entrega es el disco), y calcula demanda/GDELT/SERCOP +
  IA + contexto + FactCheck + social para lo que falte, UNA historia a la vez (el
  modelo local se serializa solo). FactCheck corre despues de contexto para poder
  usar la entidad principal ya verificada como segunda busqueda. Escribe SOLO en
  los caches, nunca en `data.json`/`dashboard.html`.
- **Bug real corregido: el arranque del servidor se colgó 9+ minutos** (reportado
  por Fernando: "el dashboard se ejecutó sin datos de pulso social y sin datos de
  búsqueda y GDELT... no deben ocurrir esos errores"). Causa raíz: demanda
  (`get_demand`)/GDELT (`get_gdelt`)/SERCOP (`get_contracts`) vivían con su
  llamada REAL directo en el hilo rápido (`run_fast`) — cada una con su propio
  caché de horas, así que en la práctica casi siempre solo leían caché, pero el
  día que el caché de GDELT vencía a mitad de una pasada, esa llamada real podía
  tardar varios minutos (medido antes: hasta 559s) y frenaba TODA esa pasada del
  feed — incluido el primer arranque del servidor, que no llega a bindear el
  puerto hasta que `run_fast` termina. Ya estaba anotado como "Pendiente
  conocido" en este archivo; el día de hoy se confirmó en vivo (9+ minutos sin
  puerto abierto con GDELT rate-limited). Arreglado con el MISMO patrón de
  `modo_lectura` que ya usan IA/contexto/social: las tres funciones ahora
  aceptan `modo_lectura=True` (hilo rápido) que SOLO lee su caché en disco —
  fresco o vencido, nunca hace red — y `modo_lectura=False` (hilo trabajador,
  default) que hace la llamada real de siempre. `enrich_pass` las llama sin
  argumentos al principio de cada pasada; como cada una ya se auto-limita por su
  propio TTL (`TREND_TTL`=3h, `SERCOP_TTL`=24h), en la práctica no hacen nada la
  gran mayoría de las pasadas — solo cuando el caché vence de verdad, y ahí sí
  pueden tardar, pero AHORA en el hilo de fondo, sin frenar `run_fast` ni el
  arranque del servidor. Con SERCOP se cuidó ademas no romper el caso ya
  documentado: `modo_lectura=True` nunca borra el caché por vencimiento (antes
  `get_contracts` lo hacía con `cache = {"ts":..., "terms": {}}`) — borrarlo
  desde el hilo rápido haría desaparecer de golpe contratos que ya se le
  mostraban a Fernando, sin haber buscado los nuevos todavía; ese borrado ahora
  solo ocurre en el hilo trabajador, justo antes de repoblarlo.
  Medido en vivo, antes/después con el mismo caché vencido a propósito: antes,
  `run_fast` no bindeaba el puerto durante 9+ minutos; después, con los mismos
  cachés borrados, el servidor respondió `data.json` (395 historias) en el
  primer intento (<5s), con `estado_gdelt`/`estado_interes` diciendo
  honestamente "esperando primera pasada del trabajador" en vez de bloquear —
  y unos minutos después, con el trabajador corriendo de fondo, esos mismos
  campos pasaron solos a `"cache (Google Trends)"` / `"cache (N aplicados)"`
  sin que el feed se haya frenado en ningún momento.

## Variables de entorno
Apagar módulos: `MONITOR_NO_IA`, `MONITOR_NO_GDELT`, `MONITOR_NO_TRENDS`,
`MONITOR_NO_SERCOP`, `MONITOR_NO_SOCIAL`, `MONITOR_NO_CONTEXTO` (=1 para apagar).
Ajustes generales: `MONITOR_IA_MODEL`, `MONITOR_IA_MAX` (análisis IA nuevos por
corrida/pasada, def. 25), `MONITOR_IA_TEMA_MIN` (umbral de confianza 0-1 para
aceptar un tema que puso la IA, def. 0.6), `MONITOR_IA_CTX` (ventana de contexto
de Ollama, def. 4096 — bajo a propósito para que el modelo entre entero en GPUs
chicas; ver nota en ia.py/social.py), `MONITOR_GDELT_PAIS`, `MONITOR_TREND_GEO`,
`MONITOR_MAX_DIAS`, `MONITOR_FEED_TIMEOUT` (timeout por feed RSS, def. 8s),
`MONITOR_SOCIAL_MAX`, `MONITOR_SOCIAL_TTL`, `MONITOR_SOCIAL_SUB`, `MONITOR_SAMPLE`.
`MONITOR_SOCIAL_DIAS` (días de antigüedad máxima para una publicación en la
escucha social, def. 7 — ver "Decisiones ya tomadas", bug real de
publicaciones de hace años saliendo como "la mejor"; se usa en `social.py`
como filtro nativo por fuente y en `monitor.py` para el peso de recencia del
ranking).
`MONITOR_TG_CANALES` (lista de canales de Telegram separados por coma, sin
`@`, ej. `"canal1,canal2"` — vacía por defecto: sin canales configurados,
Telegram se salta limpio, igual que YouTube sin `MONITOR_YT_KEY`; hay que
elegirlos a mano, no hay una lista "segura" para adivinar) y
`MONITOR_NO_TELEGRAM` (=1 para apagarlo aunque haya canales configurados).
Ver "Decisiones ya tomadas" para el porqué de raspar el preview público en
vez de una API.
`MONITOR_CHAT_MODEL` (modelo del chat de Parte E, def. `"monitor-critico"` —
ver `Modelfile.critico` y "Decisiones ya tomadas"; independiente de
`MONITOR_IA_MODEL`, que es solo para el pipeline por lotes).
Parte B (contexto por entidad): `MONITOR_CONTEXTO_MAX` (historias nuevas por
pasada del trabajador, def. 8).
Parte C (dos velocidades, modo `serve`): `MONITOR_FEED_MIN` (minutos entre
pasadas del hilo rápido, def. 2), `MONITOR_WORKER_PAUSA` (segundos de espera del
hilo trabajador entre pasadas cuando no hay nada nuevo, def. 20).
`MONITOR_FEED_FRESH_H` (horas para que una historia cuente como "reciente" en
el feed principal antes de pasar a la pestaña "Anteriores", def. 10 —
independiente de `MONITOR_WORKER_PAUSA`/`MONITOR_FEED_MIN`, ver "Sección
Anteriores" en Decisiones ya tomadas).
Escucha social — YouTube (panel "¿Qué dice la gente al respecto?"):
`MONITOR_YT_KEY` (clave de YouTube Data API v3, gratis; sin ella YouTube se
salta limpio, igual que Reddit sin conexión) y `MONITOR_YT_MAX_BUSQ` (cuántas
de las búsquedas de `get_social()` por pasada disparan una consulta REAL a
YouTube `search.list`, def. 5 — esa llamada cuesta 100 de las 10.000 unidades/
día de cuota; los temas que se quedan sin cupo igual se consultan en Bluesky/
Reddit, que son gratis).
FactCheck (sector Contraste, `MONITOR_NO_FACTCHECK`=1 para apagar):
`MONITOR_FACTCHECK_KEY` (clave de Google Fact Check Tools API — **API DISTINTA**
de YouTube Data API v3; aunque las dos se piden desde la misma consola de
Google Cloud, hay que habilitar "Fact Check Tools API" por separado, y una
clave puede estar restringida solo a una de las dos) y `MONITOR_FACTCHECK_MAX`
(historias nuevas por pasada del trabajador, def. 8). Un HTTP 403 de esta API
casi siempre es falta de habilitarla o restricción de la clave, no un bug del
codigo (`factcheck.py` lo deja explícito en el estado devuelto).

## Decisiones ya tomadas (no revertir sin preguntar)
- Ámbito Ecuador vs. mundo se decide por el **tema** de la nota, no por el medio.
- Coincidencia de palabras clave por **inicio de palabra** (`kw_hit`), no subcadena
  (evita que "selección" active "elección", etc.).
- Se filtran opinión/columnas, deportes, farándula, horóscopos, y notas de más de
  `MONITOR_MAX_DIAS` días (def. 3).
- Redes: **solo fuentes públicas sin login**. Meta (Facebook/Instagram) y X (Twitter)
  quedan descartados por depender de cuentas/tokens y bloqueos de autenticación.
- Reddit es **best-effort**: si empieza a dar 403/429, no es el pilar; Bluesky sí.
  Verificado en vivo: Bluesky trae posts consistentemente, Reddit da 403 seguido.
- La IA de `ia.py` (`analizar`) solo puede QUITAR categorías que ya puso el
  etiquetado por palabras clave, nunca agregar una que las keywords no detectaron
  (decisión explícita). Umbral de confianza `MONITOR_IA_TEMA_MIN` (def. 0.6) sobre
  lo que queda, y candado en código en `monitor.py` (no solo en el prompt) por si
  el modelo desobedece.
- Parte B (contexto por entidad): el código SIEMPRE recupera el material
  (Wikipedia/GDELT) y el modelo SOLO redacta con eso — nunca consulta una API por
  su cuenta. Verificación contra Wikipedia por título exacto/redirección real
  (nunca "lo más parecido por texto" como resultado final — ver bug de Carney
  abajo para el matiz: la búsqueda de texto SÍ se usa, pero solo para ELEGIR
  qué título exacto pedir, con contexto de la nota, no para aceptar cualquier
  resultado parecido). Mejor un falso negativo (entidad real no verificada) que
  un falso positivo.
- **Bug real de Carney** (desambiguación de entidades, dos capas — Parte B): la
  historia "Carney, tras las amenazas arancelarias de Trump" (sobre Mark
  Carney, primer ministro de Canadá) trajo como contexto "Carney, una villa en
  Míchigan de 192 habitantes" — dato falso con sello de "verificado". Causa
  raíz: `extraer_entidades` sacaba el apellido suelto ("Carney", tal como
  aparece en el texto) y `wiki.resumen("Carney")` pedía ESE título exacto; en
  Wikipedia en español, el título/redirección real para el nombre suelto
  "Carney" apunta a la villa de Míchigan, no a Mark Carney — no era un fallo de
  la verificación (la redirección es auténtica), era el nombre de entrada.
  Arreglado en dos capas independientes (probadas en vivo, antes/después con
  este caso exacto):
  - **Capa 1 — resolución con contexto** (`ia.extraer_entidades` +
    `wiki.resumen(entidad, busqueda=...)`): la IA arma, para cada entidad, una
    "búsqueda" desambiguada usando tema/ámbito de la nota (ej. "Mark Carney
    primer ministro de Canadá" en vez de "Carney"); esa búsqueda ahora SÍ pasa
    por la API de texto libre de Wikipedia (`_resolve`) para encontrar el
    título correcto, y RECIÉN con ese título se hace el fetch estricto de
    siempre (verificado, no inventado).
  - **Capa 2 — reja de coherencia** (`ia.coincide_dominio`): respaldo para
    cuando la Capa 1 igual trae una página real pero equivocada. Compara el
    nombre que la nota menciona contra el TÍTULO real de la página encontrada
    (los dos nombres por separado, no uno contra sí mismo) y descarta si no
    son la misma entidad. Probado en vivo con qwen2.5:3b: forzar
    `format="json"` en este prompt, o mencionar la palabra "homónimo"/dar un
    ejemplo de homónimo, sesgaba al modelo a contestar que NO coinciden
    SIEMPRE (hasta para el caso correcto, Mark Carney). En texto libre
    terminando en SI/NO, mostrando el nombre mencionado y el título real por
    separado, el mismo modelo distingue bien los casos. La regla dura ("ante
    la duda, sin contexto") se aplica a nivel de CÓDIGO (default False en
    cualquier camino de error/parseo), no metida en el prompt — meterla en el
    prompt también sesgaba al modelo hacia NO siempre.
  Regla general reafirmada: ante la duda, "sin contexto disponible" — nunca un
  contexto equivocado con apariencia de verificado.
- **Bug real de Jordán** (co-menciones GDELT + registro de entidades — Parte
  B): la captura de un procesado por el caso Villavicencio no traía contexto
  NI la conexión con el caso, en notas que no nombraban a Villavicencio (ej.
  "Xavier Jordán fue detenido por exceder su permiso de estadía..."). Causa
  raíz: `gdelt.comenciones()` (la capa que SÍ puede destapar el vínculo,
  buscando en prensa reciente qué otros nombres aparecen junto al buscado)
  solo se ejecutaba si la entidad ya estaba VERIFICADA en Wikipedia — y un
  recién capturado casi nunca tiene página propia, así que esa capa nunca
  corría para él. Wikipedia sola no alcanzaba porque la nota en cuestión no
  nombraba a Villavicencio. Dos arreglos:
  - **GDELT desacoplado de Wikipedia**: la entidad "principal" para buscar
    co-menciones ahora es la primera candidata VERIFICADA si hay alguna, y si
    no, el primer candidato tal cual lo extrajo la IA (`extraer_entidades`) —
    GDELT no necesita que la entidad tenga página, solo busca su nombre en
    prensa reciente.
  - **`entities.json`** (registro liviano, ver "Caches" más arriba): cada vez
    que se procesa una historia se anota QUÉ entidades menciona (verificadas o
    no), CUÁNDO y en QUÉ historia (`registrar_apariciones`). Antes de escribir
    "sin contexto disponible", se consulta si esa misma entidad ya apareció en
    otra nota del propio monitor (`apariciones_previas`) y, si sí, se muestra
    "también apareció" con fecha y enlace — un mecanismo INDEPENDIENTE de
    GDELT (que en la práctica falla seguido por su rate limit propio, ver
    `gdelt.py`) para no perder el rastro de una entidad recurrente.
  Probado en vivo con las notas reales de Jordán (GDELT rate-limited en el
  momento de la prueba, así que la vía que respondió fue `entities.json`):
  antes, "Xavier Jordán fue detenido por exceder su permiso de estadía..."
  (18-sep) daba `{"texto": "sin contexto disponible", "principal": null,
  "previas": []}` — igual que hoy en Wikipedia sola. Después de procesar
  primero la nota que sí nombra a Villavicencio (17-sep), la misma nota de
  ICE pasó a dar: `"Xavier Jordán, procesado por el asesinato de Fernando
  Villavicencio, también apareció en notas sobre su detención en Estados
  Unidos durante un control migratorio (2026-09-17)."` con `previas` apuntando
  a esa nota anterior. De paso se corrigió un bug propio introducido en este
  mismo cambio: el `return` de "nada encontrado" hardcodeaba
  `"principal": None` y perdía el nombre ya identificado, que `get_factcheck`
  también usa como segunda búsqueda — ahora se conserva.
- **Oportunidades con pulso social** (`renderGap()` en dashboard_template.html):
  antes la brecha del sector Oportunidades solo comparaba demanda de búsqueda
  (Google Trends/Wikipedia) contra cobertura de medios; si no había datos de
  búsqueda esa corrida, la sección quedaba sin poder calcular brecha alguna
  aunque hubiera conversación fuerte en redes para ese tema. Ahora el "interés
  público" de cada tema es la MAYOR entre dos señales independientes: demanda
  de búsqueda y `DATA.social[tema].n_posts` (volumen de conversación,
  **relativo** — normalizado 0-100 contra el máximo entre los pocos temas que
  sí se consultan por corrida, `SOCIAL_MAX`; nunca se presenta como conteo
  absoluto, ver regla de abajo). Se usa la MAYOR de las dos, no un promedio:
  una conversación social fuerte con poca búsqueda (o viceversa) ya es señal
  real de interés por sí sola. Las tarjetas muestran ambas barras cuando hay
  dato de las dos, y el texto aclara cuál señal sostiene la brecha. El filtro
  Ecuador/Mundo de Oportunidades (`gapAmb`) ahora también filtra el pulso
  social por `soc[tema].ambito` (el mismo cálculo de `tema_ambito_map`),
  consistente con el resto del panel.
- **Contraste reordenado y compactado**: antes era una lista de `.gapcard`
  (una fila entera por item, sin orden) mezclando Ecuador y Mundo sin
  criterio. Ahora `renderContraste()` agrupa por ámbito con encabezado y
  cuenta, en el orden pedido: Internacional, Nacional (Ecuador), Guayaquil
  (`contrasteAmbito(h)`, misma lógica de ámbito que el resto del dashboard).
  Cada grupo es una grilla de tarjetas COMPACTAS — se reusa `cardHTML()`
  (la misma de Noticias/Guardadas) con `opts.factcheck=true` para que incluya
  además el detalle de verificaciones (`renderFactcheck`, antes solo vivía en
  Contraste). Los contratos SERCOP ya se mostraban dentro de `cardHTML` (el
  `<details>` "Contraste oficial"); ahora Contraste no duplica ese bloque a
  mano, reusa la tarjeta entera.
- **Click para expandir + chat con la IA por item** (Parte E, todos los
  segmentos): cada tarjeta (`.card`, historias — Noticias/Contraste/Guardadas)
  o tema (`.gapcard[data-tema]`, Oportunidades/Pulso social) se puede
  clickear para abrir un modal con TODOS sus datos (fuentes, contexto,
  contraste, pulso social, seguimiento — reusa `renderContexto`/
  `renderFactcheck`). El click delegado en `document.body` ignora clicks
  dentro de `a,button,summary,details,input` para no pisar los links/detalles
  propios de la tarjeta. Dentro del modal, un chat conversacional con Ollama
  sobre ESE item puntual (para corregir la interpretación, aportar info, o
  discutir si es una oportunidad):
  - **El navegador nunca habla directo con Ollama**: todo pasa por
    `POST /api/chat` en el mismo servidor http (`monitor.py`, junto a
    `/api/guardar`), que arma el prompt (`ia.chat()`, texto libre — a
    diferencia del resto de `ia.py` NO usa `format="json"`, es conversación)
    con el contexto YA CALCULADO de la tarjeta (`contextoChatHistoria`/
    `contextoChatTema` en el HTML arman ese texto del lado del cliente) más
    el historial de turnos previos.
  - **Servidor con hilos**: `/api/chat` puede tardar varios segundos (llamada
    real a un LLM local) — antes el servidor (`socketserver.TCPServer`) era
    de un solo hilo, así que esa espera habría congelado TODO (hasta el poll
    de `data.json` cada minuto). Se cambió a
    `ThreadingMixIn`+`TCPServer` (`ServidorHilos`, `daemon_threads=True`).
    Probado en vivo: un GET a `data.json` responde en ~2ms mientras un
    `/api/chat` sigue en curso (tardó ~6-7s en total).
  - **Es on-demand, nunca durante el feed**: lo dispara el usuario desde el
    dashboard; `run_fast`/`enrich_pass` no lo tocan. Si el modelo local ya
    está ocupado (el hilo trabajador enriqueciendo el feed), Ollama encola la
    consulta de chat en vez de fallar (comportamiento propio de Ollama,
    `num_parallel` por defecto) — puede tardar un poco más, no rompe nada.
  - **Persistencia**: el hilo de chat vive en memoria del navegador
    (`chatHilos`, por item) y se pierde al recargar la página — es lo simple
    pedido para esta primera versión. Guardar el hilo en disco y, sobre todo,
    persistir las correcciones de vuelta en el análisis (que lo que se
    discute en el chat modifique `h.ia`/`h.contexto` de verdad) queda como
    paso posterior, no implementado todavía.
  - **UI del chat: widget flotante, NO modal a pantalla completa** — bug real
    reportado por Fernando: la primera versión metía el chat DENTRO del mismo
    modal del detalle, y el conjunto se sentía "a pantalla completa" y no
    dejaba leer la noticia con tranquilidad. Se separó en dos piezas
    independientes: el modal (`#modalOverlay`, `mostrarDetalle()`) solo
    muestra el detalle del item, y el chat es un widget aparte
    (`#chatWidget`/`#chatBubble`, `abrirChat()`/`minimizarChat()`/
    `cerrarChat()`) fijo en la esquina inferior derecha, chico (`min(350px,
    ...)`), con su propio header que muestra el título/tema activo para que
    quede claro de qué se está hablando. Cerrar el modal (`cerrarModal()`) NO
    cierra el chat a propósito: se puede seguir navegando otras noticias con
    la conversación abierta. Abrir OTRO item re-apunta el chat a ese item
    nuevo (mismo mecanismo de contexto por item de antes, sin cambios) y el
    header del widget lo refleja.
  - **Bug real: cerrar/minimizar no hacía nada** — reportado por Fernando
    justo después del cambio anterior. Causa: `.modaloverlay{display:flex}` y
    `.chatwidget{display:flex}` son reglas de AUTOR con selector de clase; el
    atributo `hidden` depende de la regla `[hidden]{display:none}` del
    NAVEGADOR (hoja de estilos por defecto). En cascada CSS, una regla de
    autor siempre le gana a una del navegador sin importar especificidad —
    así que aunque el JS ponía `hidden=true` correctamente al clickear
    cerrar/minimizar, la ventana seguía viéndose igual (la regla de autor
    seguía forzando `display:flex`). No era un bug de los botones ni de los
    listeners de click, era puramente CSS. Arreglado agregando
    `#modalOverlay[hidden]{display:none}` y `#chatWidget[hidden]
    {display:none}` (selector de ID+atributo, más específico que la clase,
    sigue siendo de autor así que gana la comparación). De paso se encontró
    y arregló el MISMO patrón de bug en dos elementos que ya existían antes
    de hoy: `.live{display:inline-block}` (la etiqueta "EN VIVO") y
    `.vermas{display:block}` (el botón "Ver más") — ambos podían quedar
    visibles siempre sin importar `hidden`. Lección para cualquier elemento
    nuevo que se oculte con `hidden` desde JS: si su clase fija `display`,
    hace falta el mismo override `#id[hidden]{display:none}`.
- **Modelo dedicado "monitor-critico" para el chat (Parte E)**: Fernando
  reportó que la IA "no tiene pensamiento crítico" — solo parafrasea el
  titular en vez de cuestionarlo. Medido en vivo antes de decidir el camino:
  esta PC (GTX 1650 SUPER, **4GB VRAM**) corre `qwen2.5:3b` (el modelo del
  pipeline por lotes) en 2-4s siempre, pero cualquier modelo de ~7-8B
  (`deepseek-r1:8b`, la base del `periodista-pro` que Fernando ya tenía;
  probado también `deepseek-coder:6.7b`) paga **20-27s de SOLO CARGA en cada
  llamada**, sin importar si se llama varias veces seguidas — no entra
  entero en la VRAM. Un modelo así en el pipeline por lotes (decenas de
  historias nuevas cada pocos minutos) atrasaría al hilo trabajador sin
  límite. Decisión (elegida por Fernando entre 3 opciones): el modelo pesado
  **SOLO para el chat on-demand** (Parte E), nunca para
  `analizar`/`extraer_entidades`/`contextualizar`/`coincide_dominio`, que
  siguen en el modelo rápido de siempre.
  - `Modelfile.critico` (en la raíz del proyecto): `FROM deepseek-r1:8b` +
    un `SYSTEM` de "analista crítico" — cuestiona la nota (qué fuentes
    faltan, a quién conviene la versión que cuenta, qué preguntas no
    responde) en vez de resumirla, pero con la misma regla dura del resto
    del proyecto: el escepticismo es sobre la INTERPRETACIÓN, nunca licencia
    para inventar hechos. Se crea con
    `ollama create monitor-critico -f Modelfile.critico` (documentado ahí
    mismo, para poder rehacerlo en otra PC).
  - `ia.py`: `CHAT_MODEL` (env `MONITOR_CHAT_MODEL`, def. `"monitor-critico"`)
    y `elegir_modelo_chat()` — modelo DISTINTO e independiente del
    `MONITOR_IA_MODEL`/`_model` que usa el resto del pipeline. Si
    `monitor-critico` no está instalado, cae solo al modelo rápido de
    siempre (nunca rompe el chat, responde con menos filo crítico nomás).
    `chat()` ya no recibe `forzado=IA_MODEL` desde monitor.py — se
    desacopló a propósito, para que forzar el modelo del pipeline
    (`MONITOR_IA_MODEL`) no pisara el modelo del chat sin querer.
  - **Bug real, encontrado en vivo #1**: `elegir_modelo_chat()` comparaba
    `CHAT_MODEL` (`"monitor-critico"`) contra el string EXACTO que devuelve
    `/api/tags` — pero Ollama lista los modelos CON tag
    (`"monitor-critico:latest"`), así que la comparación nunca daba
    verdadero y el chat usaba el modelo rápido en silencio, sin avisar del
    problema. Arreglado comparando por nombre base (antes de `":"`), misma
    técnica que ya usaba `elegir_modelo()`.
  - **Bug real, encontrado en vivo #2**: con `monitor-critico` (modelo de
    RAZONAMIENTO), Ollama separa el "pensamiento" interno del texto visible
    (campo `thinking` aparte de `response`), pero AMBOS gastan del mismo
    `num_predict`. Con el `num_predict=300` que usaba el resto de `ia.py`,
    el modelo agotaba el presupuesto completo "pensando" y la respuesta
    visible quedaba VACÍA (`done_reason:"length"`, `response:""`) — sin
    ningún error, se veía como si el chat no respondiera nada. Subido a
    `num_predict=1000` (alcanza para pensar y responder: medido ~530-650
    tokens totales) y el `timeout` de `chat()` a 220s.
  - **Tiempo real medido, no estimado**: ~70-100s por respuesta en esta PC
    (17-20s de carga + generación). Bastante más que el "25-40s" que se
    había estimado antes de medir — el dashboard avisa "puede tardar 1-2
    minutos" en el propio chat mientras espera, para que no parezca colgado.
- **Aterrizaje (grounding) del chat contra Wikipedia — bug real de "Alias
  Fito"**: Fernando le preguntó al chat "quién es Alias Fito dentro del
  contexto ecuatoriano" y respondió "Carlos Ospina" — un nombre inventado
  con total confianza (la respuesta correcta es José Adolfo Macías Villamar,
  líder de Los Choneros). Causa raíz: el system prompt del chat (a
  diferencia de TODO el resto del proyecto) explícitamente permitía "usar tu
  conocimiento general para poner el item en perspectiva" — esa es la puerta
  por la que un modelo local chico alucina una identidad completa sin que se
  note. Arreglado con el MISMO patrón que Parte B (código recupera, IA solo
  redacta), pero disparado por la PREGUNTA del chat en vez del texto de una
  nota:
  - `ia.extraer_entidades_chat(mensaje, item_contexto)`: con el modelo
    RÁPIDO del pipeline (nunca `monitor-critico`: esto es un paso previo,
    tiene que ser rápido), reconoce si el mensaje pregunta por una entidad
    puntual y arma una búsqueda desambiguada — mismo mecanismo que
    `extraer_entidades` (Capa 1 del bug de Carney).
  - `monitor.py: _aterrizar_chat(item_contexto, mensaje)`: verifica esa
    entidad contra Wikipedia (`wiki.resumen`) y agrega el resultado —
    verificado, o explícitamente "SIN VERIFICAR" — al contexto de ESA
    pregunta puntual antes de mandarla al chat. Nunca modifica el
    `item_contexto` de forma persistente, solo para ese turno.
  - **Respaldo probado en vivo**: la primera pasada de este arreglo casi
    falla igual — el modelo de extracción adivinó mal el apellido legal
    ("Villamarán" en vez de "Villamar"), y esa búsqueda no encontraba nada
    ("SIN VERIFICAR", el resultado seguro pero no útil). Se agregó un
    segundo intento: si la búsqueda con el nombre completo que adivinó el
    modelo no encuentra nada, reintentar con el ALIAS tal cual lo escribió
    el periodista ("Alias Fito" solo) — medido en vivo: resuelve bien y
    consistente a "Fito (criminal)", más confiable que depender de que el
    modelo chico adivine un nombre legal completo.
  - `_PROMPT_CHAT_SISTEMA` (ia.py) y el `SYSTEM` de `Modelfile.critico` (hay
    que correr `ollama create monitor-critico -f Modelfile.critico` de
    nuevo después de este cambio) tienen ahora una regla dura explícita,
    citando el incidente real: ante una pregunta de identidad sin material
    VERIFICADO, decir "no lo tengo verificado" — nunca completar con un
    nombre que "suene familiar".
  - Probado en vivo, los dos casos: "Alias Fito" (con página real en
    Wikipedia) ahora responde correcto, con el dato verificado; "Xavier
    Jordán" (sin página de Wikipedia, ver Parte B) responde "No tengo
    verificado ese dato en este momento" en vez de inventar — los dos
    resultados son correctos.
- **Recencia en la escucha social — bug real: la "mejor" publicación de un
  tema podía ser de años atrás**: Bluesky con `sort=top` rankea por
  engagement de TODA la historia del término, sin ventana de tiempo — nada
  en el pipeline filtraba por fecha. Reproducido en vivo: para "inseguridad
  Ecuador" la publicación con más likes+reposts era del **2024-11-25** (casi
  2 años antes de hoy). Arreglado en capas (`MONITOR_SOCIAL_DIAS`, def. 7):
  - **Filtro nativo por fuente** (más barato: no se trae ni se paga lo
    viejo): Bluesky usa el parámetro `since` de la API (confirmado en vivo
    que existe y filtra server-side); Reddit mapea `dias` al balde fijo más
    chico que lo cubra (`_reddit_t`: day/week/month/year/all — antes estaba
    fijo en `"month"` sin importar `MONITOR_SOCIAL_DIAS`); YouTube filtra
    cada comentario por su propio `publishedAt` (antes solo filtraba que el
    VIDEO fuera de los últimos `YT_DIAS`=30 días, no cuándo se escribió el
    comentario que terminaba mostrándose).
  - **Filtro de respaldo centralizado** (`social._es_reciente`, en
    `recolectar()`): por si una fuente no filtra perfecto. Sin fecha válida
    = se descarta (ante la duda, no confirmar recencia = no es reciente).
  - **Ranking = recencia + engagement, no solo engagement**
    (`monitor._social_score`, decaimiento lineal 1.0 hoy → 0.5 en el borde
    de la ventana): dentro de la ventana ya filtrada, una publicación más
    vieja pesa menos al elegir la "mejor" de cada fuente. La fecha de la
    publicación ahora se manda al dashboard y se muestra junto a
    likes/reposts, para poder verificarlo a simple vista.
- **Estados "tapados" de Trends/GDELT — no lo tapes, quiero ver el estado
  real**: bug real en `gdelt.interest()` y `monitor.get_demand()`: un éxito
  PARCIAL (ej. GDELT respondía 1 de 19 temas, el resto 429) se reportaba
  igual que un éxito total ("ok" a secas) porque el error solo se guardaba
  si TODOS los temas fallaban. Confirmado en vivo pidiendo 5 temas a GDELT en
  el momento de este cambio: **HTTP 429 en los 5**, y por separado (con la
  caché ya vencida) 1 de 5 sí respondió — antes ambos casos hubieran dicho
  "ok". Ahora `gdelt.py` guarda el primer error aunque el éxito sea parcial,
  y `get_gdelt()`/`get_demand()` arman un estado honesto: `"ok (1/5 temas;
  resto: HTTP 429)"` en vez de `"ok"`. Confirmado por separado que Google
  Trends SÍ respondía en el momento de esta prueba (sin necesidad del
  respaldo de Wikipedia) — el respaldo (`_wiki_demand`) sigue intacto y se
  dispara solo si Trends trae menos de la mitad de los temas, con su propio
  detalle de cuántos/cuántos en el estado final.
- **Chat con streaming + dos modos (Frente B)** — Fernando pidió bajar el
  tiempo de espera del chat ("1-2 minutos es demasiado"): objetivo consulta
  rápida ≤30s, análisis complejo ≤1 min.
  - **Streaming real**: `ia.chat_stream()` usa `stream=true` de Ollama y lee
    la respuesta HTTP línea por línea (NDJSON) según va llegando, llamando a
    `on_delta(texto_parcial)` por cada pedazo. `monitor.py`
    (`_responder_stream`) relay-ea cada pedazo al navegador apenas lo recibe
    — sin `Content-Length`, con `close_connection=True` (la conexión se
    cierra al terminar en vez de armar chunked encoding a mano). El
    navegador (`dashboard_template.html`) lee con
    `response.body.getReader()` y va llenando la burbuja de la IA en vivo.
    Probado en vivo con `curl -N`: los tokens llegan de a uno, no en un solo
    bloque al final.
  - **BUG REAL — la idea original no funcionaba**: el plan era "mismo
    modelo, bajar `num_predict` para el modo rápido". Probado en vivo con
    `monitor-critico` (modelo de razonamiento): con `num_predict=280` tardó
    **74s y devolvió STRING VACÍO** — el modelo gasta ese presupuesto
    "pensando" antes de escribir una sola palabra visible, y al cortarse a
    mitad del pensamiento no queda nada. Se probó también `"think": false`
    (la opción de Ollama para apagar el razonamiento): esta versión del
    modelo la ignora, el `<think>` se filtra igual dentro de `response` y
    sigue cortando a mitad de camino.
  - **Arreglo real**: dos modos que cambian MODELO, no solo num_predict
    (`ia.MODOS_CHAT`). **"rápido"** (por defecto): el modelo RÁPIDO del
    pipeline (qwen2.5:3b típicamente, sin razonamiento) + contexto MAGRO
    (`contextoChatHistoria/Tema(..., profundo=false)`: solo titular/resumen/
    interpretación, sin fuentes/contratos/factcheck) + `num_predict=280,
    num_ctx=2048`. Medido en vivo end-to-end (servidor real, `curl -N`):
    **13.8s**, bien debajo del objetivo de 30s. **"profundo"** (botón aparte
    en el widget del chat): `monitor-critico` + contexto completo +
    `num_predict=700, num_ctx=4096`.
  - **Límite real, no se pudo evitar**: "profundo" mide **~100-120s en esta
    PC** (medido dos veces seguidas, con el modelo ya "caliente": 118.6s y
    123.2s) — por ENCIMA del objetivo de 1 min pedido. Confirmado que NO es
    por num_predict cortando de golpe (`done_reason: "stop"`, no `"length"`
    — el modelo termina solo, usa ~550 de los 700 tokens disponibles) ni por
    carga en frío del modelo: es la velocidad de generación real de un
    modelo de razonamiento de ~8B en una GPU de 4GB VRAM (35/65 CPU/GPU,
    ~5 tokens/segundo) — no hay margen para bajarlo sin cortar el
    pensamiento a la mitad (que ya se probó que devuelve vacío). El
    streaming ayuda a que la espera se SIENTA mejor (hay progreso visible en
    vez de una pantalla estática), pero no baja el tiempo total. Si 100-120s
    sigue siendo demasiado para el uso diario, la palanca real que queda es
    cambiar de modelo para "profundo" (uno más chico, sin razonamiento, que
    sacrifique parte del análisis crítico a cambio de velocidad) — no
    implementado, a la espera de que Fernando decida si vale la pena ese
    cambio.
- Nunca presentar un número modelado como si fuera medido: toda estimación va
  etiquetada como tal (aplica sobre todo a la Parte A, pendiente de esta lista).
- `ambito_de(blob)` decide Ecuador vs Mundo **solo** por palabras clave del
  texto (`is_ecuador`/`EC_TERMS`); **nunca** por qué medios publicaron la nota.
  Bug real corregido: antes, sin señal de ningún lado, caía en "local" a
  ciegas (una nota sobre el franquismo español, sin ninguna palabra de
  Ecuador, terminaba en la sección Ecuador). Ahora el default sin señal es
  "internacional" — mejor una nota local rara sin palabra clave quede ahí
  (falso negativo) que inflar Ecuador con temas ajenos (falso positivo).
  `EC_TERMS` se reforzó con las provincias y siglas institucionales más
  seguras (evitando términos ambiguos como "Bolívar", que colisiona con Simón
  Bolívar en noticias de otros países).
- Escucha social: el panel "Pulso social" NUNCA rankea publicaciones por
  engagement crudo mezclando plataformas (likes de YouTube y reposts de
  Bluesky no son comparables) — muestra la mejor publicación de CADA fuente
  presente, con su desglose de conteo por fuente siempre visible.
- `is_ecuador`/`is_foreign`/`detect_city` matchean por PALABRA COMPLETA
  (`geo_hit`, límite al inicio Y al final), no por prefijo suelto. Bugs reales
  corregidos: "canar" (provincia Cañar) matcheaba como prefijo dentro de
  "Canarias" (España); "napo" (provincia/río) dentro de "Napoleón". Además se
  sacaron de `EC_TERMS` tres términos que colisionaban aunque fueran palabra
  completa: "sucre" (Sucre, capital de Bolivia — más frecuente en prensa que
  el uso histórico de la moneda ecuatoriana), "los rios" y "el oro" (frases
  genéricas: "el oro alcanza un precio récord..." es titular típico de
  economía mundial). "El Oro"/"Los Ríos" siguen detectándose por sus
  ciudades (Machala, Babahoyo, Quevedo). "Asamblea Nacional" también es el
  parlamento de VENEZUELA (muy cubierto en prensa internacional): si el
  texto además menciona Venezuela/Maduro, esa coincidencia sola ya no cuenta
  como señal de Ecuador (sigue evaluándose el resto de `EC_TERMS`).
  Pendiente de menor riesgo, no corregido: "orellana" (apellido común) y
  "santa elena" (también la isla del exilio de Napoleón) quedan sin acotar —
  baja frecuencia esperada en la agenda diaria, pero si aparece un falso
  positivo real, revisar ahí primero.
- Escucha social: la BÚSQUEDA (no solo el ámbito de la historia) también debe
  estar acotada a Ecuador. Bug real detectado en vivo: el tema "Ambiente"
  tenía ámbito "guayaquil" por notas locales genuinas (minería en
  Quimsacocha), pero la búsqueda social usaba el término genérico del tema
  ("medio ambiente", de `TREND_TERMS`) — en Bluesky/YouTube eso lo domina la
  conversación de otros países con mucho más volumen (se vio trayendo
  política ESPAÑOLA y luego MEXICANA — PRI, Morena, Tren Maya — bajo un tema
  marcado como Guayaquil). Arreglado en dos capas (`_social_query` +
  `_post_es_foraneo` en monitor.py): para temas con ámbito ecuador/guayaquil
  se agrega "Ecuador" al término de búsqueda (defensa principal — probado en
  vivo: "medio ambiente" trae 70 posts dominados por España, "medio ambiente
  Ecuador" trae 13 posts realmente relacionados a Ecuador), y como respaldo
  se descarta cualquier post que mencione claramente OTRO país
  (`is_foreign`) sin ninguna señal de Ecuador (`is_ecuador`). El respaldo no
  es perfecto: un comentario puede hablar de política extranjera sin nombrar
  el país (ej. solo "PRI"/"Morena", sin decir "México") y a eso no llega el
  filtro de texto — por eso la query scopeada es la defensa principal, no el
  filtro.
- **Sección "Anteriores"** (Parte B): antes, toda historia más vieja que
  `MONITOR_MAX_DIAS` (def. 3 días) se descartaba en `build_stories` y se
  perdía sin dejar rastro. Ahora solo se descarta de verdad más allá de
  `MONITOR_MAX_DIAS`; entre `MONITOR_FEED_FRESH_H` (def. 10h) y
  `MONITOR_MAX_DIAS` la historia queda marcada `s["antigua"]=True` y el
  dashboard la muestra en un toggle Recientes/Anteriores dentro de Noticias
  (mismos filtros de categoría/ámbito/búsqueda que el resto) en vez de
  perderla de vista. Nada desaparece en silencio.
- **Guardadas / para reportaje** (Parte C): botón estrella en cada tarjeta
  (`cardHTML`, compartido entre Noticias y la pestaña Guardadas). Guarda la
  historia COMPLETA (no un id) para que sobreviva a que la noticia caduque
  del feed o el dashboard se regenere. Persistencia según cómo se abrió el
  dashboard (se decide una vez al cargar la página, `cargarGuardadas()`, sin
  cambiar de modo a mitad de sesión):
  - `python monitor.py serve` (modo normal, `location.protocol` es http):
    **`saved.json` en disco**, vía `POST /api/guardar` en el mismo servidor
    (`http.server`, bind 127.0.0.1 como el resto). Sobrevive a reinicios del
    programa y es el mismo archivo para cualquier navegador.
  - `dashboard.html` abierto directo (`file://`, sin servidor — típico de una
    corrida única con `python monitor.py` sin `serve`): no hay forma de
    escribir a disco desde el navegador, así que cae a **`localStorage`** —
    solo vive en ESE navegador y ESA compu; se pierde si se limpian datos del
    sitio o se abre desde otro navegador/perfil. El dashboard se lo dice al
    usuario en la propia pestaña Guardadas.
- **Bug real: Capa 2 dejó pasar "Indios ugandeses" como si fuera Mamdani**
  (desambiguación de entidades, Parte B — reportado indirectamente por
  Fernando al notar contexto sin relación con la nota). La nota "Trump se
  reunió con Mamdani en Nueva York..." (sobre Zohran Mamdani, alcalde electo
  de Nueva York) traía como candidato el apellido suelto "Mamdani"; Capa 1
  (`ia.extraer_entidades`) alucinó una búsqueda desambiguada incorrecta
  ("Abdul Razaq Mamdani"), y `wiki.resumen` terminó resolviendo a "Indios
  ugandeses" (el artículo sobre la comunidad étnica, un apellido común entre
  esa diáspora — no una persona). La Capa 2 (`ia.coincide_dominio`, el
  modelo chico qwen2.5:3b) DEBÍA descartar ese caso comparando "Mamdani"
  contra el título real "Indios ugandeses", pero respondió (probado en vivo,
  reproducido con el texto real) que sí coincidían — un error de juicio del
  modelo, no de la lógica. Arreglado con un backstop determinista y barato,
  SIN IA: `_nombre_se_solapa(nombre_mencionado, titulo_wiki)` en monitor.py
  compara por palabra (normalizada, `norm()`, ≥3 letras) si el nombre
  mencionado en la nota aparece en el título real de Wikipedia; si ninguna
  palabra se solapa, se descarta el resultado SIN gastar la llamada a
  `coincide_dominio` (el caso es demasiado obvio para necesitar el modelo).
  No reemplaza la Capa 2 (que sigue corriendo para los casos con solape
  parcial que sí necesitan juicio), la complementa como última barrera para
  cuando el modelo se equivoca. Mismo criterio de siempre ante nombres sin
  palabras útiles para comparar: no bloquea (mejor un falso negativo que uno
  positivo). Se agregó también en `_aterrizar_chat` (Parte E): ese camino
  del chat nunca había tenido NINGÚN chequeo de coherencia (ni siquiera
  `coincide_dominio`), así que tenía la misma clase de vulnerabilidad
  esperando a reproducirse ahí — se le sumó el mismo backstop barato, sin
  IA extra, para no atrasar la respuesta del chat.
  Probado en vivo con el caso real y los casos ya conocidos, todos correctos
  después del arreglo: `_nombre_se_solapa("Mamdani", "Indios ugandeses")` →
  False (se descarta, antes pasaba); `_nombre_se_solapa("Mamdani", "Zohran
  Mamdani")`, `("Mark Carney", "Mark Carney")`, `("Alias Fito", "Fito
  (criminal)")`, `("Daniel Noboa", "Daniel Noboa")` → True (siguen pasando
  bien, el arreglo no rompió ningún caso correcto anterior).
- **Contexto que solo explica "quién es X", nunca la situación** (Parte B —
  reportado por Fernando: "el contexto aportado no es más que explica quién
  es X persona, pero no explica el contexto de la situación... lo mismo que
  nada"). Causa raíz doble: (1) el MATERIAL que `_construir_contexto` le
  daba al modelo para redactar era solo bios de Wikipedia + nombres sueltos
  co-mencionados por GDELT — no había ningún dato sobre QUÉ ESTÁ PASANDO
  alrededor del hecho, así que ni el mejor prompt podía sacar más que una
  biografía; (2) `_PROMPT_CONTEXTO` (ia.py) solo pedía "qué contexto agrega
  el material sobre quién es tal persona/lugar", sin pedir nunca conectar
  eso con la situación de la nota. Arreglo en dos partes:
  - **Más material real, sin gastar una llamada extra a GDELT**:
    `gdelt.comenciones()` se refactorizó en `gdelt.contexto_prensa()` — la
    MISMA búsqueda en GDELT (ArtList) que ya se hacía para sacar nombres
    co-mencionados ahora también devuelve los TITULARES reales y recientes
    (con fecha) de esos mismos artículos. `_construir_contexto` arma con eso
    un bloque nuevo ("Cobertura reciente de prensa sobre X: titular1 (fecha),
    titular2 (fecha)...") — son hechos reales publicados por la prensa, no
    un resumen inventado, así que el modelo los puede citar como evidencia
    de la situación sin salirse de la regla de oro de Parte B (el código
    recupera, la IA solo redacta).
  - **`_PROMPT_CONTEXTO` reescrito**: ahora pide explícitamente explicar POR
    QUÉ pasa esto ahora / qué antecedente inmediato tiene (si los titulares
    muestran una escalada, un conflicto en curso, etc.), usando los
    titulares como evidencia citable ("esto se da luego de que...") — y
    solo cae a la bio simple si el material de verdad no trae nada más
    (nunca inventa una conexión que el material no respalda).
  Probado en vivo con el caso real de Carney (mismo caso del bug de
  desambiguación, con material de prueba con titulares de escalada
  arancelaria): antes, el contexto era pura bio ("Mark Carney es un
  economista y político canadiense, primer ministro de Canadá desde
  2025"); después, con la MISMA nota, el contexto pasó a ser: "Mark Carney
  respondió a las amenazas arancelarias de Trump, luego de que el
  presidente de Estados Unidos amenazara con nuevas rondas de aranceles a
  Canadá tras negociaciones fallidas" — conecta con la situación real de la
  nota, no solo con quién es la persona.
- **Interpretación de la IA literal, solo parafraseaba categorías** (`analizar()`
  en ia.py — reportado por Fernando: "la interpretación de la IA ante las
  noticias sigue siendo literal"). Causa raíz: `_PROMPT` solo pedía "una
  sola frase de por qué importa y su contexto", sin ninguna guía de qué
  distingue una interpretación real de un resumen — el modelo (razonablemente)
  optaba por lo más fácil: reformular el titular/categoría. Arreglado
  agregando reglas explícitas al prompt: pedir qué está en juego, a quién
  beneficia/perjudica, qué tensión de fondo revela o qué pregunta queda
  abierta — "pensá como un editor que le dice a un reportero por qué esta
  nota importa, no como alguien que la resume" — más un ejemplo de mal
  resultado (resumen) y uno de buen resultado (interpretación real) directo
  en el prompt. Sigue con la misma regla dura de siempre: solo puede usar lo
  que el titular/resumen ya afirma, nunca inventa datos/antecedentes que no
  estén ahí (si el texto es muy escueto, puede decir explícitamente que
  falta información en vez de forzar una interpretación vacía).
  Probado en vivo (titular real de ejemplo, "Gobierno de Ecuador anuncia
  subsidio focalizado al diésel para transporte pesado..."): la
  interpretación salió "El subsidio... beneficiará principalmente a
  empresas y transportistas, mientras reducirá significativamente los
  gastos fiscales del gobierno, lo que puede presionar a otras áreas del
  presupuesto para cubrir el déficit" — señala a quién beneficia y una
  consecuencia fiscal implícita, no una reformulación del titular.
- **Contraste (FactCheck) con datos no relacionados a la historia**
  (`get_factcheck` en monitor.py — reportado por Fernando: "algunas
  secciones de contraste de notas aportan datos que no son relacionados con
  el contexto de la historia"). Causa raíz: cuando la búsqueda por el
  titular completo no encontraba nada, el respaldo buscaba por la entidad
  PRINCIPAL sola (`s["contexto"]["principal"]`) — a veces una sola palabra
  genérica (ej. "Alemania") — y Google Fact Check Tools (`claims:search`)
  hace coincidencia laxa por palabra suelta: devolvía cualquier ClaimReview
  que mencionara "Alemania", sin relación alguna con la nota puntual.
  Arreglado con `_factcheck_relevante(s, resultados, excluir=principal)`:
  se queda solo con los resultados del fallback por entidad que comparten
  ADEMÁS otra palabra significativa (mismo criterio que `tokens()`: ≥4
  letras, sin stopwords) con el titular+resumen de esa historia —
  excluyendo del conteo el propio nombre que se usó como búsqueda (que
  siempre "coincide" por definición y no sirve como filtro). Se aplica solo
  al fallback por entidad (el más propenso a este bug); la búsqueda por
  titular completo no se toca, porque ya es una frase completa y no un
  término suelto.
  Probado en vivo con datos sintéticos que reproducen el caso real: de dos
  resultados para la entidad "Alemania" ("Alemania ganó el mundial de
  handball femenino" — sin relación; "El canciller alemán confirmó recorte
  en gasto de defensa" — sí relacionado con la nota de recorte militar), el
  filtro descartó el primero y conservó el segundo.
- **Bug real: tema con posts salía con sentimiento=None, sin ninguna pista
  de por qué** (Fernando: tema "Ambiente" con 119 posts). Causa raíz:
  `social.analizar_osint()` atrapa CUALQUIER excepción (timeout, HTTP,
  JSON mal formado) y devuelve `None` guardando el motivo en
  `social.last_error` — pero `get_social()` en monitor.py, si el ÚNICO
  reintento también fallaba, tiraba ese `last_error` sin guardarlo en
  ningún lado: el `entry` del tema quedaba sin las claves
  `sentimiento`/`polarizacion`/`resumen`, indistinguible en el dashboard de
  "no se intentó". El HTML ya mostraba un mensaje de respaldo, pero
  genérico ("puede faltar Ollama o haber fallado la lectura puntual"),
  siempre igual sin importar la causa real. De paso se encontró y limpió
  una variable muerta (`sin_modelo` en `get_social`): se calculaba pero
  nunca se usaba en ningún lado.
  Arreglado: cuando los dos intentos de `analizar_osint` fallan, el
  `entry` del tema guarda `osint_error` con el `social.last_error` real de
  ESE intento puntual; `renderSocial()` en el dashboard lo muestra tal cual
  ("Sin lectura OSINT esta vez (motivo: osint TimeoutError)") en vez de
  adivinar. Probado en vivo forzando `analizar_osint` a fallar con un
  motivo conocido (`"osint TimeoutError"`): el `entry` resultante trajo
  `osint_error: "osint TimeoutError"` en vez de perder el dato.
  No se pudo reproducir el fallo ORIGINAL de dos intentos seguidos (una
  prueba en vivo con 119 posts sintéticos sobre "Ambiente" sí consiguió
  OSINT al primer intento) — es consistente con que sea intermitente
  (hipo puntual de Ollama, ya documentado más arriba), no un bug de
  tamaño de los datos; lo que se arregló es que ahora, la próxima vez que
  pase, se va a poder ver la causa real en vez de perderla.
- **Estado "esperando primera pasada del trabajador" para siempre durante
  un corte largo de GDELT/Trends**: relacionado con el bug del arranque
  colgado (arriba) — una vez que la llamada real se movió al hilo
  trabajador, quedó un hueco de honestidad distinto: si GDELT fallaba
  TOTALMENTE (0 de N temas, ej. HTTP 429 sostenido) o Trends/GDELT recién
  estaban vencidos, `get_gdelt()`/`get_demand()` en modo_lectura NO
  contaban CUÁNTOS temas se habían conseguido ni el motivo del resto —
  devolvían un "cache" plano, o si nunca hubo ni un solo éxito, se
  quedaban en "esperando primera pasada del trabajador" para siempre,
  indistinguible de "el trabajador todavía ni arrancó". Arreglado en dos
  partes: (1) `gdelt_cache.json`/`trends_cache.json` ahora guardan también
  `intentados` (cuántos temas se pidieron) y `err`/`detalle` (el motivo si
  no fue un éxito total), así el hilo rápido reconstruye el mismo estado
  honesto ("cache (Google Trends, 20/20 temas)") leyendo el cache en vez
  de mostrar "cache" a secas; (2) si GDELT falla TOTALMENTE, igual se
  guarda el intento (`ts_intento`/`err`) sin inventar datos, para que
  modo_lectura pueda decir "sin datos aún (intentado, sigue fallando: HTTP
  429)" en vez de "esperando primera pasada" indefinidamente.
  Probado en vivo, antes/después: `estado_interes` pasó de "cache (Google
  Trends)" a "cache (Google Trends, 20/20 temas)" con datos reales del
  feed; en el mismo arranque se confirmó con una llamada directa a
  `gdelt.interest()` que el rate limit de GDELT sigue siendo real ahora
  mismo (`HTTP 429` en una prueba, y en otra `{}` con `last_error=None` —
  GDELT a veces tarda ~12s por tema y devuelve vacío sin ni siquiera un
  código de error, no siempre es un 429 explícito) — dato que antes de
  este cambio quedaba completamente oculto detrás de un genérico
  "esperando".
- **Telegram (Etapa 4, fuente nueva)**: se integró como una fuente más de
  `social.py` (`telegram_buscar`, misma `SocialPost`, mismo filtro de
  recencia/ruido en `recolectar()`), pero con una diferencia de fondo que el
  dashboard etiqueta explícitamente: los canales de Telegram son **broadcast**
  (la voz del canal, no del público) — sirven para el eje de seguridad y la
  recencia (medios/fuentes ecuatorianas suelen postear primero ahí), nunca
  para medir opinión ciudadana.
  - **Sin API, vía preview público**: `t.me/s/<canal>` es la página HTML que
    el propio Telegram sirve sin login para "embeber" un canal en otros
    sitios. Se parsea con regex (mismo criterio que `gdelt.py` para nombres
    propios: sin librería de NLP/HTML en la stdlib más allá de
    `html.parser`, y la estructura de esta página puntual es simple y
    estable) — no es la API real: no hay búsqueda propia de canal (se trae
    lo reciente y se filtra localmente por palabra), no hay reply/forward
    counts, y las "vistas" son un conteo que el propio Telegram ya redondea
    (ej. "1.2K"). Probado en vivo contra un canal público real
    (`t.me/s/telegram`): extrae texto, fecha y vistas correctamente (vistas
    en millones parseadas bien, ej. "1.3M" → 1300000), el filtro de
    recencia descarta correctamente posts viejos (0/10 posts de
    julio/agosto pasaron con `MONITOR_SOCIAL_DIAS=7`), y el filtro por
    palabra encuentra el único post relevante entre 10 (búsqueda "GIFs").
  - `MONITOR_TG_CANALES` vacía por defecto a propósito: no hay una lista
    "seria" de canales ecuatorianos que valga la pena adivinar, la elige
    Fernando a mano. Sin canales configurados (o con `MONITOR_NO_TELEGRAM=1`)
    se salta limpio, mismo comportamiento que YouTube sin `MONITOR_YT_KEY`.
  - Como las vistas son el único conteo real que expone el preview (no hay
    "me gusta" ni reenvíos), se reutiliza el campo `likes` de `SocialPost`
    para guardarlas (documentado en el código; `reposts` queda en 0) — el
    dashboard lo etiqueta distinto (👁 vistas, no ♥) para no confundirlo con
    una reacción real.
  - **Upgrade futuro anotado, NO implementado** (decisión pendiente de
    Fernando): Telethon (pip + `api_id`/`api_hash` de
    https://my.telegram.org) daría acceso a la API real — mensajes
    completos, reacciones, reply/forward counts — pero deja de ser stdlib y
    pide credenciales de una cuenta de Telegram real.

## Pendientes
- **Resolución de entidad genérica en vez de la persona (caso Burnham, ver
  arreglo del 2026-09-23 segunda pasada)**: `_construir_contexto` resolvió
  "Burnham" a la página de Wikipedia "Primer ministro del Reino Unido" (un
  cargo/rol, no la persona) en vez de a "Andy Burnham" — probablemente porque
  el candidato de la persona no verificó bien (desambiguación) mientras que
  el candidato institucional sí encontró una página real. El síntoma
  (FactCheck trayendo verificaciones de Keir Starmer) ya está arreglado
  aparte (filtro de relevancia mas fuerte + re-filtro en cache), pero la
  causa de fondo — por qué "Burnham" no verificó bien como persona — no se
  investigó todavía. Revisar `ia.extraer_entidades`/`wiki.resumen` para ese
  caso puntual si vuelve a pasar con otra persona.
- **GDELT bajo corte total en esta sesión**: la rotación de orden (arreglo de
  hoy) es un bug real corregido, pero no puede hacer nada si GDELT rechaza
  el 100% de los intentos (medido: 0/5 con HTTP 429 incluso con rotación).
  Revisar el panel "Mercado de cobertura" en unos días para confirmar que,
  con la rotación, distintos temas van acumulando datos con el tiempo.
- **Parte A (tamaño de público y brecha real)**: todavía no construida —
  `_wiki_demand` sigue aplastando las vistas de Wikipedia a 0-100 en vez de
  conservar el conteo absoluto; falta el denominador `MONITOR_POB_ONLINE` y la
  demanda a nivel de historia (entidad principal), no solo de tema.
- **Etapa 3 de escucha social** (integrar volumen de conversación a las
  brechas) — en pausa a pedido del usuario hasta ver el panel funcionando.
- **Asimetría en el candado de geografía de la IA** (`get_ia`/`_apply`): el
  candado impide que la IA declare "local"/"guayaquil" sin respaldo de
  `EC_TERMS`, pero NO impide que declare "internacional" aunque el texto
  mencione Ecuador explícitamente (caso real: "Estados Unidos intercepta
  embarcación **de Ecuador**" quedó en Internacional porque la IA lo etiquetó
  así). No corregido todavía — evaluar si el candado debería ser simétrico.
- **Telegram (Etapa 4, implementado)**: por ahora scraping del preview
  público `t.me/s/<canal>` con regex (ver `social.telegram_buscar` y
  "Decisiones ya tomadas"). Sin canales propios en `MONITOR_TG_CANALES`
  todavía (vacía por defecto, Fernando los carga a mano). Upgrade futuro
  anotado, NO implementado: Telethon (pip + `api_id`/`api_hash` de
  https://my.telegram.org) daría la API real completa — mensajes, reacciones,
  reply/forward counts — a cambio de dejar de ser stdlib y pedir credenciales
  de una cuenta real. Decisión pendiente de Fernando, no urgente mientras el
  preview alcance.
- **Verificar en vivo con Ollama corriendo (Problemas 4 y 6, sesión 2026-09-23)**:
  `ia.veredicto_contraste()` y `ia.extraer_entidades_con_evento()` se probaron con
  la llamada a Ollama mockeada (Ollama no estaba corriendo en esta sesión) — el
  *wiring* (monitor.py <-> ia.py <-> dashboard) está probado de punta a punta con
  `MONITOR_SAMPLE=1` y una corrida real (feeds/GDELT/SERCOP/FactCheck reales), pero
  la CALIDAD del texto que redacta el modelo (¿el veredicto es razonable? ¿el
  modelo de 3B propone eventos sensatos, o alucina nombres de sucesos que no
  existen?) todavía no se vio con un caso real. Correr una pasada con Ollama
  activo y revisar unos cuantos veredictos/contextos a mano es el siguiente paso.
- **Clustering por embeddings (Problema 5, sugerencia de Fernando, no
  implementada)**: el agrupamiento se mejoró por palabras+ventana de
  tiempo+nombre propio compartido (ver el arreglo de hoy), sin necesitar
  Ollama. Si Fernando instala un modelo de embeddings (`ollama pull
  nomic-embed-text`) más adelante, usarlo como señal adicional (o de
  respaldo cuando el solape de palabras es bajo) es un paso natural — `ia.py`
  ya tiene el patrón de llamada a Ollama (`_post`) listo para copiar a un
  `ia.embed()`.
- **API de búsqueda web para el contexto (Problema 6, fase siguiente, pedido
  explícito de Fernando de NO implementar todavía)**: opciones y costos
  anotados en el arreglo de hoy (Google Custom Search: 100 consultas/día
  gratis, luego $5/1000; Bing Search API: descontinuada 2025, movida a Azure
  AI). Ninguna es stdlib en el sentido de "gratis sin clave" como
  Wikipedia/GDELT — las dos son HTTP+JSON vía `urllib` (no hace falta
  librería nueva), pero piden clave y tienen límite/costo.
- **Reddit best-effort, confirmado de nuevo en esta sesión**: durante todas
  las pruebas de hoy, Reddit devolvió HTTP 403 en el 100% de los intentos
  (incluso `about.json` sin ningún parámetro) — no se pudo confirmar en vivo
  si `r/Guayaquil`/`r/worldnews+europe` (nuevo, Problema 1) tienen actividad
  real; el código ya maneja esto con su mismo trato best-effort de siempre
  (ver "Decisiones ya tomadas"). Revisar cuando Reddit vuelva a responder.

## Arreglos del 2026-09-23, segunda pasada (feedback de Fernando tras la primera tanda: literal, pulso social, cobertura, Contraste erroneo, 40 fuentes)

Fernando probó la primera tanda con Ollama corriendo y encontró problemas reales, dos de ellos serios. Diagnosticado y arreglado cada uno con datos/llamadas reales (Ollama SÍ estaba corriendo esta vez).

- **BUG GRAVE — "los contextos siguen literales" (confirmado, causa real encontrada):**
  `ia.interpretar()` + `ia.es_literal()` (la lectura editorial con ejemplos resueltos y
  filtro anti-paráfrasis) estaban completas y bien escritas en `ia.py` desde el
  arreglo documentado como hecho el 2026-09-22 — pero **`monitor.py` nunca las
  llamaba**. `get_ia()._apply()` seguía leyendo `r.get("interpretacion", "")` de
  la respuesta de `ia.analizar()`, una clave que ese prompt ya NO devuelve (se
  sacó a propósito en el mismo arreglo del 22). Para notas nuevas esto daba
  `s["ia"] = ""` siempre; para notas viejas cacheadas de ANTES del 22 arrastraba
  el texto LITERAL de la versión vieja del prompt ("Noticia internacional sobre
  reunión de primer ministro británico con Trump en la ONU" — el ejemplo real
  que trajo Fernando). Arreglado: `get_ia()` ahora llama a `ia.interpretar()`
  de verdad, acotado aparte (`IA_INTERP_MAX`, def. 12/pasada, env
  `MONITOR_IA_INTERP_MAX`) con marca de versión (`interp_v`) para no confundir
  interpretaciones viejas con las nuevas. Probado en vivo (Ollama real,
  qwen2.5:3b) con el titular exacto de Fernando: antes → "Noticia internacional
  sobre reunión de primer ministro británico con Trump en la ONU"; después →
  "¿Quién beneficia con Burnham alineándose con Trump? ¿Cómo puede afectar esta
  alianza a la relación UE-EEUU?" — lectura editorial real, no paráfrasis.

- **BUG GRAVE — Contraste calificaba "Falso" algo sin relación (Trump/Burnham
  marcado falso por una foto de Burnham con camiseta de Croacia):** causa raíz
  DOBLE, confirmada con la clave real de FactCheck:
  1. `_factcheck_relevante` (el filtro que exige palabras en común con la nota)
     **solo se aplicaba al fallback por entidad**, nunca a la búsqueda primaria
     por titular completo — la primaria se usaba tal cual viniera de Google
     Fact Check Tools, sin ningún filtro.
  2. El filtro exigía apenas **1 palabra compartida** — muy débil.
  3. `factcheck_cache.json` **no tiene versión ni vencimiento**: una entrada
     mala cacheada de antes de que existiera el filtro (o de un bug del
     filtro) se queda ahí para siempre, inmune a que el código se arregle
     después — y este caso ERA una de esas entradas viejas.
  Reproducido en vivo con la clave real de Fernando: buscar por la entidad
  "Primer ministro del Reino Unido" (a la que se resolvió mal "Burnham" — ver
  Pendientes) trae 5 ClaimReview reales, todos sobre **Keir Starmer** (la
  camiseta de Croacia, una dimisión, Macron y cocaína, árabe como lengua
  oficial, Boris Johnson bailando) — CERO relación con Burnham ni con la nota.
  Arreglado: el filtro ahora se aplica a AMBAS búsquedas (primaria y
  fallback), exige **2+ palabras significativas en común** (no 1), y —
  importante — **se re-aplica también al LEER del caché**, no solo al
  escribirlo, así una entrada vieja mala se autolimpia sola sin tener que
  borrar el archivo a mano. Verificado en vivo con la clave real: el mismo
  caso pasó de **5 resultados falsos → 0**. `test_factcheck_relevante.py`
  (3 pruebas, incluye el caso real de Fernando).

- **Pulso social seguía sin Guayaquil/Ecuador — causa real: Mastodon.** El
  arreglo de la primera tanda (subreddit/región por ámbito) sí funcionaba, pero
  Mastodon busca por HASHTAG (no texto libre) y recibía el `query` YA con el
  sufijo de ámbito que arma `_social_query` para Bluesky/YouTube ("carceles
  Ecuador") — al convertirlo en hashtag daba `#carcelesecuador`, que
  prácticamente nadie usa. Medido en vivo: `"carceles Ecuador"` → **0 posts**;
  `"carceles"` solo → **20 posts reales**. Arreglado: `recolectar()` ahora
  recibe también `term_base` (el término SIN el sufijo de ámbito) y se lo pasa
  solo a Mastodon; el filtro geográfico para Mastodon queda a cargo del
  respaldo por texto (`_post_es_foraneo`), igual que ya hacían Bluesky/Reddit
  cuando el término solo no alcanza. Probado en vivo, tema "Ambiente"
  (ámbito Guayaquil): 0 → 20 posts de Mastodon. **Limite real reconocido**: al
  sacar el sufijo de país, Mastodon ya no filtra por geografía en la búsqueda
  misma (solo por el respaldo de texto, que no es perfecto) — es una mejora
  real (pasar de 0 a contenido real) pero no da precisión geográfica perfecta
  en esta fuente puntual.

- **"Mercado de cobertura" sigue mostrando solo Política — causa real
  adicional encontrada (más allá del merge-cache de la primera tanda):**
  `gdelt.interest()` recibe los temas en el MISMO orden alfabético siempre
  (`sorted(...)` en monitor.py) y corta en el primer HTTP 429 — con GDELT
  rate-limited casi toda corrida, los temas que van DESPU�S del primero que
  falla nunca llegan a intentarse, ni esta pasada ni ninguna otra, porque el
  orden nunca cambia. Arreglado: `gdelt.interest()` ahora mezcla el orden de
  los temas en cada llamada (`random.shuffle`), así en el tiempo todos tienen
  chance de ser los primeros. **Verificado en vivo, resultado honesto:** en el
  momento de esta prueba GDELT rechazó **0 de 5 temas** (HTTP 429 total,
  incluso con la rotación) — el bug de orden fijo está corregido (confirmado
  por código y lógica), pero el rate limit de GDELT en sí sigue siendo un
  límite externo real que la rotación no puede superar cuando GDELT está en un
  corte total. Con la rotación, cuando GDELT SÍ deje pasar algo, va a ser un
  tema distinto cada vez en vez de siempre el mismo — y gracias al merge-cache
  de la primera tanda, eso ahora SÍ se acumula en vez de perderse.

- **Más fuentes — pedido explícito: llegar a 40.** 28 → **44 feeds
  configurados** (cada URL nueva probada a mano con `urllib` + `parse_feed()`
  real antes de agregarla, igual que la tanda anterior): Ecuador/Guayaquil
  +1 (El Universo Gran Guayaquil, sección real pero sin items al momento de
  probarla — puede empezar a publicar en cualquier momento); internacionales
  +15 (ABC.es Internacional, Euronews ES, RFI ES, Le Figaro, Corriere della
  Sera, Der Standard, Sky News, NPR World, CBC News World, ABC News Australia,
  The Hindu, Straits Times, Infobae, Semana Colombia, El Tiempo Colombia).
  Medido con `monitor.collect()` real: **578 → 1314 artículos crudos por
  corrida**, 43/44 feeds OK (Wambra sigue con su 429 transitorio de siempre).
  Clustering sobre el dataset mas grande: 116/1059 historias con 2+ medios,
  sin problemas de performance (collect 3.6s + cluster 1.7s para 1286
  artículos). Quedan anotados en `feeds.py` (comentados, con el motivo) los
  que se probaron y fallaron esta tanda: DW-ES, TRT-ES, Haaretz (devuelven
  HTML, no RSS, pese a HTTP 200), CNN Español (certificado SSL inválido),
  Milenio/La Tercera/ABC Paraguay (404), El Economista MX/El País Uruguay
  (403), Andes agencia estatal EC (timeout).

## Arreglos del 2026-09-23, tercera pasada (feedback de Fernando: pulso social "no funciona", Guayaquil no se recoge, Colombia se mezcla con Ecuador, Contraste con errores y sin categorizar)

Cinco reclamos, con causas reales encontradas (dos de ellas eran bugs "documentados como resueltos" que en realidad nunca se habían conectado — mismo patrón que `ia.interpretar()` de la ronda anterior).

- **BUG GRAVE — pulso social "no funciona", causa real de fondo:**
  `get_social()` seguía tomando `themes[:SOCIAL_MAX]` — los primeros 5 temas
  en orden ALFABÉTICO (`themes_present` ya llega ordenado), SIEMPRE los
  mismos, pase lo que pase. Confirmado con `social_cache.json` real:
  "Ambiente, Asamblea/Leyes, Carceles, Comercio/Inversion, Crimen/Violencia"
  — exactamente los 5 primeros alfabéticos del catálogo de 20 temas — y los
  otros 15 JAMÁS se consultaban, en ninguna pasada, nunca. CLAUDE.md ya
  documentaba esto como arreglado con una función `_temas_por_relevancia()`
  que en los hechos **nunca se había escrito**. Esto explica de raíz por
  qué Guayaquil/Internacional podían quedar sin una sola publicación para
  siempre: si por casualidad alfabética ningún tema de ese ámbito caía en
  el prefijo fijo, quedaba excluido total y permanentemente, no de forma
  intermitente. Implementado de verdad: `_temas_por_relevancia()` ahora
  garantiza AL MENOS un tema de CADA ámbito presente (elegido al azar
  dentro de ese ámbito, no el primero alfabético) y rota el resto también al
  azar. Probado (`test_social_temas.py`, 4 pruebas): antes, 200 llamadas
  daban el mismo resultado las 200 veces; después, en 200 pasadas los 3
  ámbitos aparecen las 200/200 veces, y en 300 pasadas ningún tema del set
  de prueba quedó en cero.
- **Mastodon (arreglo de la ronda anterior) + el ambito badge**: además de
  la corrección de la ronda anterior, cada tarjeta de tema en el panel
  ahora muestra su propio rótulo de ámbito (Ecuador/Guayaquil/Mundo) —
  antes, viendo "Todos", no había forma de saber a qué ámbito pertenecía
  cada tarjeta sin ir tocando cada botón del toggle uno por uno.

- **"No acogés las noticias de Guayaquil" — causa real:** el ámbito/ciudad
  se decidía 100% por texto (`detect_city`/`is_ecuador` sobre el titular y
  resumen), sin usar nunca la sección del propio medio. Una nota hiperlocal
  de un barrio puntual (ej. "Remodelación de la plazoleta de Ceibos genera
  cuestionamientos") no necesariamente repite la palabra "Guayaquil" en
  ningún lado, así que quedaba mal clasificada. Arreglado: los feeds de
  `feeds.py` ahora pueden llevar `"ciudad": "Guayaquil"` cuando SON
  literalmente la sección editorial de Guayaquil de un diario (el medio ya
  hizo esa clasificación al publicar ahí) — `build_stories()` usa esa señal
  como DURA (no depende del texto). Se agregó la sección real de El
  Universo (`eluniverso.com/.../guayaquil/`, 26 items reales probados en
  vivo, ninguno con "Guayaquil" en el titular). Medido con el pipeline real
  completo (`collect`+`cluster`+`build_stories`): **12 → 31 historias
  etiquetadas Guayaquil**, incluyendo casos reales fusionados de 2-3 medios
  (la inundación de "Sauces 6", el reportaje del "Escudo de las Américas").
  `test_ciudad_feed.py` (3 pruebas).

- **"Las de Colombia se mezclan con Ecuador" — causa real encontrada y
  confirmada con el caso exacto de Fernando:** una nota de Semana
  (Colombia) sobre Álvaro Uribe hablando del "Escudo de las Américas"
  (alianza de seguridad de ~15 países) quedaba marcada como historia LOCAL
  de Ecuador porque el resumen real (280 caracteres, capturado en vivo)
  enumera "Argentina, Bolivia, Chile, Costa Rica, Ecuador, El Salvador,
  Guyana..." — Ecuador es UNO MÁS en una lista larga, no el foco de la
  nota. `is_ecuador()` (`ambito_de` no diferenciaba "país mencionado
  al pasar en una enumeración" de "país foco de la nota"). Arreglado:
  `_es_enumeracion_paises()` detecta si el texto nombra 3+ países
  extranjeros distintos (señal de lista/ranking/alianza multilateral); en
  ese caso, un match SOLO por el nombre "ecuador"/"ecuatorian" (sin ciudad
  ni institución específica) ya no alcanza para clasificar local. Probado
  en vivo con el caso real (ahora da `False`, antes daba `True`) y con 5
  casos reales de Ecuador que NO deben romperse (bilaterales, locales,
  con ciudad) — todos siguen dando `True`. `test_geo_enumeracion.py`
  (4 pruebas).

- **Contraste "aún presenta errores" — causa real encontrada en los
  textos reales generados:** revisando 30 veredictos ya procesados en
  vivo, varios traían texto roto/genérico: `"segun el contexto verificado
  de la situacion... (40 palabras)"`, `"...(La Jornada); (La Nacion (AR));
  (El Pais (Espana));"` — el modelo (qwen2.5:3b) estaba **copiando
  literalmente** las frases de ejemplo y el placeholder de instrucción
  `"(maximo 40 palabras, citando la fuente)"` que el prompt de
  `ia.veredicto_contraste()` tenía escritos DENTRO del propio ejemplo de
  JSON — un modelo chico no distingue bien "esto es una instrucción sobre
  el campo" de "esto es texto literal para copiar". Arreglado: mismo
  patrón que ya funciona en `ia.interpretar()` (ejemplos resueltos
  completos, no instrucciones sueltas dentro del template) — el prompt
  ahora trae DOS ejemplos completos (afirmación + material + JSON de
  salida ya resuelto, uno "contradice" y uno "sin_datos") y pide
  explícitamente el HECHO CONCRETO (un número, una fecha, una
  calificación), no una frase genérica sin terminar. Probado en vivo
  reconstruyendo el material real de 3 casos que habían salido rotos:
  "Consumo eléctrico: 185 empresas..." pasó de `"segun el contexto
  verificado de la situacion... (40 palabras)"` a `"El acuerdo menciona
  que 185 empresas reducirán su consumo un día a la semana para aliviar
  la demanda del Sistema Nacional Interconectado, lo que coincide con la
  afirmación."` con citas reales `["El Universo", "Expreso"]`; los otros
  dos casos rotos ("Ahead of Xi's...", "Modi plans Canada trip...") ahora
  dan `sin_datos` con una frase completa y específica en vez de texto
  cortado.

- **Contraste "página eterna, sin categorizar" — arreglado:** `#secContraste`
  ahora tiene el mismo toggle Todos/Ecuador/Guayaquil/Internacional que ya
  usan Pulso social y Oportunidades (`#contrasteseg`, `contrasteAmb`) — con
  un ámbito elegido, la página muestra SOLO ese grupo en vez de las 3
  listas apiladas. Se agregó además un límite de `CONTRASTE_PAGE=12`
  tarjetas por grupo con botón "Ver más" (mismo patrón que Noticias,
  `PAGE=12`) para que ni el grupo Internacional (el más grande, ~33 notas
  en la medición de hoy) sea una lista larga sin fin.

- **GDELT ("Mercado de cobertura" sigue igual) — verificado, sigue siendo
  el límite externo ya documentado:** la rotación de orden (arreglo de la
  ronda anterior) sigue corregida y confirmada por código; en el momento
  de esta ronda, GDELT sigue rechazando el 100% de los intentos (cache real:
  `{"g": {"Ejecutivo": ...}, "err": "HTTP 429"}`, sin cambios desde la
  ronda anterior). No es un bug de código pendiente — es un bloqueo
  sostenido del lado de GDELT que ninguna de las dos rondas de arreglos
  puede forzar a ceder. Si sigue igual en unos días, valdría la pena
  revisar si es un bloqueo por IP (probar desde otra red) más que rate
  limit normal.

## Estilo de código
Comentarios en español, claros, explicando el *por qué*. Nada de dependencias nuevas.
Cambios acotados y probados con `MONITOR_SAMPLE=1` antes de correr con internet.

## Capa móvil (avisos al iPhone + dashboard en el celular) — `movil.py`
- Avisos por **ntfy** (ntfy.sh, publicación JSON vía urllib, sin cuenta). El tema
  secreto y la clave se generan solos en `movil.json` (config editable; NO es cache).
  Estado anti-spam y muestras horarias para "lo normal" en `movil_estado.json` (cache).
- Se llama desde `write_outputs` → `avisar_movil()` en cada pasada del feed rápido.
  Nunca rompe la corrida; se apaga en MONITOR_SAMPLE y con `MONITOR_NO_MOVIL=1`.
- Disparadores: historia local con ≥ `min_medios` medios (def. 2) y "sigue creciendo";
  pico de tema (historias en últimas 6 h vs. promedio APRENDIDO de muestras horarias,
  requiere 12 muestras; no se compara con el total de 3 días porque los RSS sesgan
  hacia lo reciente); brecha (demanda ≥ 25 y ≤ 3 historias, enfriamiento 48 h).
  Temas "otros"/"general" ignorados. Primera corrida = línea base + aviso "conectado".
- Horas de silencio 23–7 (hora EC): lo pendiente se avisa al terminar el silencio.
- Servidor: con `acceso_red=true` escucha en 0.0.0.0. Esta PC (loopback) sin cambios.
  Otros aparatos: necesitan la clave (`?k=` una vez → cookie `mk`, HttpOnly, 1 año),
  solo pueden leer dashboard.html/data.json/logo.png/saved.json, y los POST
  (/api/guardar, /api/chat) también piden clave.
- `python monitor.py movil` (o `CONECTAR_IPHONE.bat`) muestra el tema y los enlaces y
  manda un aviso de prueba.
- LIMITACIÓN conocida: casi todas las historias locales tienen n_outlets=1 (el
  agrupamiento entre medios EC casi no une), así que "historia fuerte" rara vez
  dispara hasta mejorar el clustering.

## Arreglos del 2026-09-22 (reclamo de Fernando: IA literal, graficos, reinicio de 15 min, Contraste, pulso social)
- **Reinicio / 15 min**: causa raiz = GDELT sin cache (`gdelt_cache.json` nunca se escribia porque TODO daba 429 con
  PAUSA=1.5 s) -> cada pasada del trabajador reintentaba ~40 consultas y la IA esperaba detras. Arreglo: (1) hilo nuevo
  `enrich_red()`/`red_loop` para Trends/GDELT/SERCOP/social, separado de la IA (`enrich_pass` ya no las llama);
  (2) `gdelt._esperar_turno()` espacia >=5.5 s TODAS las consultas (ambos hilos) y `interest()` corta al primer 429;
  (3) enfriamiento `REINTENTO_FALLO` (`MONITOR_REINTENTO_MIN`, def. 40) en `get_gdelt`/`get_demand`: el fallo queda
  anotado (`fallo_ts`) y no se reintenta en cada vuelta -- **superado por el merge-cache por tema del Problema 3
  (2026-09-23, segunda tanda, ver mas abajo): `REINTENTO_FALLO`/`fallo_ts` ya NO existen en el codigo actual (confirmado
  por grep en la cuarta pasada, 2026-09-23); el enfriamiento real hoy es el TTL normal de cada cache (con `_ts` por
  tema) sumado al fallo que ya queda anotado ahi mismo, sin un mecanismo aparte** ; (4) `POST /api/refrescar` + boton "Actualizar ahora"
  (evento `REFRESCAR`) despierta al hilo rapido; (5) `enrich_pass` prioriza notas de <=6 h.
- **IA literal**: el campo `interpretacion` salia del MISMO JSON que clasificaba temas/geo y el modelo de 3B lo usaba
  para justificar la etiqueta ("Noticia internacional sobre X, sin impacto en Ecuador"). Ahora `ia.analizar()` solo
  clasifica e `ia.interpretar()` es una llamada aparte (`/api/chat`, texto libre, 3 ejemplos resueltos) con filtro
  `ia.es_literal()` (reintenta una vez a mas temperatura; si sigue literal, no muestra nada). Cache: `interp`/`interp_v=2`
  en `ia_cache.json`; las interpretaciones viejas NO se muestran. `MONITOR_IA_INTERP_MAX` (def. 12/pasada),
  `MONITOR_IA_INTERP_MODEL` (modelo aparte para esto, opcional). Botones de preguntas rapidas en el detalle (modo profundo).
- **Graficos**: `trends.py` ahora `today 1-m` (diario) y descarta el punto `isPartial`; el dashboard ya no toma el
  ULTIMO punto como demanda (`demandaTema()` usa `DATA.demanda_tema`, promedio de la ultima semana completa). Barras
  `.bars .fill` no se veian (span sin display:block). `lineChart()` interactivo (tooltip con fecha/valor, eje, max/prom).
  GDELT guarda `fechas` por punto.
- **Contraste**: `_factcheck_relevante` exige nombre propio en comun + palabra de contenido + >=3 palabras en comun,
  se aplica a TODAS las busquedas y tambien al leer el cache (data real: 195 -> 3). Max 3 por nota, plegadas.
- **Interaccion**: el poll ya no redibuja si data.json no cambio; si estas leyendo/escribiendo aparece "Hay datos
  nuevos"; conserva desplegables abiertos y scroll. `data.json` se escribe atomico (`_escribir_atomico`).
- **Notas**: `notas.json` (contenido de Fernando, no cache) via `POST /api/nota`; boton ✎ en tarjetas, caja en el
  detalle de historia y de tema, lista "Mis notas" en Guardadas.
- **Pulso social**: `SocialPost.tipo` persona/medio (`social.es_cuenta_medio`, heuristica por nombre de cuenta);
  OSINT solo con personas si hay >=3; conteo personas/medios en el panel. BUG: `get_social` recibia temas en orden
  ALFABETICO y miraba los 5 primeros; ahora `_temas_por_relevancia()`. Limite real: X/TikTok/Facebook/Instagram no
  tienen acceso abierto.

## Arreglos del 2026-09-23 (segunda tanda: 6 pedidos de Fernando, orden de trabajo 2→3→5→4→1→6)

Cada uno se diagnostico primero con datos reales (`data.json`/cachés/corridas en vivo), despues se arreglo, despues
se comprobo con una corrida nueva — igual que pidio Fernando. Nota de proceso: para probar sin arriesgar el
`data.json`/`dashboard.html`/`history.json` reales (el usuario tenia `python monitor.py serve` corriendo en vivo
todo este tiempo), las corridas de prueba se hicieron en una COPIA aislada del proyecto en el scratchpad, nunca en
la carpeta real salvo un despiste al principio (ver abajo) que el propio `serve` autocorrigio en su siguiente
pasada.

- **Bug real propio, primer paso de esta sesion**: se corrio por error `MONITOR_SAMPLE=1 python monitor.py` (para
  probar el arreglo del Problema 2) DIRECTO en la carpeta real, mientras `serve` seguia corriendo — sobreescribio
  `data.json`/`dashboard.html` con las 9 historias de muestra y agrego una entrada de muestra a `history.json`.
  El propio `run_fast` de `serve` (cada `MONITOR_FEED_MIN`) volvio a publicar datos reales unos minutos despues sin
  intervencion; la entrada de muestra en `history.json` se boro a mano (autorizado por Fernando). Desde ahi, todas
  las pruebas de este cambio se corrieron en una copia del proyecto fuera de la carpeta real. Leccion: nunca correr
  `python monitor.py` (con o sin `MONITOR_SAMPLE`) en la carpeta real si `serve` puede estar corriendo.

- **Problema 2 — Estadisticas: la cobertura solo mostraba Politica.** Diagnostico con `data.json` real: la
  distribucion de `seccion` en si SI estaba sana (politica 153, general 157/158, economia ~50, seguridad ~30,
  sociedad 27 sobre ~418 historias) — el bug NO estaba en el etiquetado de categorias, sino en el panel "Mercado de
  cobertura" (GDELT) de Estadisticas: `gdelt_cache.json` solo tenia datos de 1 tema de 20 (`Ejecutivo`, que mapea a
  Politica) porque GDELT viene devolviendo HTTP 429 en casi todos los intentos (`estado_gdelt`: "cache vencido
  (1/20 temas; resto: HTTP 429)") — root cause real: `get_gdelt` PISABA el cache entero con el resultado de cada
  pasada (ver Problema 3, es la MISMA causa). Se agrego de todos modos, por pedido explicito: `normalizar_categoria()`
  (monitor.py) como punto UNICO de normalizacion de la clave `seccion` (mayusculas/tildes/sinonimos -> una de las 5
  claves fijas del dashboard), usado en `parse_feed` y en `append_history`; `contar_por_categoria()`/
  `imprimir_categorias()` para el conteo en terminal (se ve en cada corrida, `python test_categorias.py -v`);
  `test_categorias.py` (falla si una categoria con notas da 0). El arreglo REAL del panel GDELT viene del fix de
  cache del Problema 3 (accumula en vez de pisar).

- **Problema 3 — Oportunidades: faltan datos en cada sesion.** BUG REAL raiz encontrado (misma causa para GDELT,
  Trends y Pulso social): `get_gdelt`/`get_demand`/`get_social` escribian su cache JSON PISANDO el diccionario
  entero (`"g": data`, `"vals": vals`, `"s": out`) con SOLO lo conseguido en esa pasada puntual, en vez de sumarse
  a lo que ya habia. Con GDELT rate-limited a ~1 tema exitoso por pasada, cada pasada BORRABA el tema bueno de la
  pasada anterior — medido en produccion: `gdelt_cache.json` nunca paso de 1 tema en dias; `social_cache.json`
  (limitado ademas a `SOCIAL_MAX=5` temas por pasada) solo tenia 5 de 20 temas posibles, y como los 5 elegidos
  varian segun relevancia, los otros ~15 se borraban y reaparecian sin ton ni son. Arreglado: las tres funciones
  ahora MERGEAN el resultado de la pasada en el cache existente (`merged_g = dict(cache.get("g") or {});
  merged_g.update(data)`, mismo patron para `vals`/`tend` y `s`), y guardan ademas un timestamp POR TEMA
  (`g_ts`/`vals_ts`/`s_ts`) para poder mostrar "hace X" por tema (`_fmt_horas`/`_edad_mas_vieja`, monitor.py) —
  implementa el "usar el ultimo dato bueno, marcado con su antiguedad" que pidio Fernando. Probado en vivo con
  cache temporal aislado (`test_merge_cache.py`, 5 pruebas: simulan dos pasadas con 429 parcial y confirman que el
  tema de la pasada 1 sigue presente despues de la pasada 2 — el caso real que fallaba antes). **Registro de salud
  por corrida**: `construir_salud_fuentes()` arma `data.json["salud_fuentes"]` (por fuente: ok/error/desactivado +
  detalle) a partir de los mismos estados que ya se calculaban; el panel de Oportunidades lo muestra arriba de todo
  (`renderSaludFuentes()`). **No inventar oportunidades incompletas**: `renderGap()` ahora separa los temas con
  historias pero SIN ninguna senal de interes (ni busqueda ni redes) en un bloque aparte "Incompletas — falta
  senal de interes" (antes esos temas simplemente desaparecian del panel en silencio).

- **Problema 5 — muy pocas noticias y demasiados duplicados.**
  - *Mas feeds*: se probaron uno por uno (HTTP real, `urllib`) los candidatos EC que estaban comentados como
    fallidos y varios nuevos. Resultado real: **Expreso** (`expreso.ec/rss`, medio de Guayaquil), **El Norte**
    (`elnorte.ec/feed/` — antes daba `ParseError`, ver abajo) y **El Diario** (Manabi, `eldiario.ec/feed/`)
    funcionan; se agregaron. Tambien **Al Jazeera**, **France24 en español** y **SCMP** (internacionales). Medido
    con `monitor.collect()` real: **22 -> 28 feeds configurados, 578 -> 799 articulos crudos por corrida** (27/28
    feeds OK, Wambra sigue con 429 transitorio como ya estaba documentado). Se probaron y quedaron fuera (con el
    motivo anotado en `feeds.py`): La Hora, GK, Vistazo, Extra, Ecuavisa, Primicias, Teleamazonas, El Telegrafo
    (404/403, o HTTP 200 pero ya no traen RSS real).
  - *Bug real de paso, `parse_feed`*: El Norte manda un salto de linea ANTES de `<?xml ...?>` — `ElementTree` lo
    rechaza (`XML or text declaration not at start of entity`) aunque el resto del documento sea XML valido.
    Arreglado con `raw.lstrip()` antes de parsear (mas robusto para cualquier feed futuro con el mismo problema).
  - *Agrupamiento (una tarjeta por noticia)*: diagnostico real: **402 de 420 historias con un solo medio** (95.7%),
    peor que la medicion de Fernando (372/399). Causa: el umbral de similitud de titulares (0.30, solape/Jaccard)
    era sensible a que dos medios titulen MUY parecido, pero periodistas distintos rara vez repiten las mismas 4+
    palabras. Arreglado con **ventana de tiempo** (`CLUSTER_MAX_HORAS`, def. 72h, `MONITOR_CLUSTER_MAX_H`) + un
    umbral MAS BAJO (0.20) pero mas exigente en otro sentido: solo aplica si ADEMAS comparten un **nombre propio**
    (`_nombres_propios`, regex de palabras capitalizadas, sin contar Title Case ingles — ver bug real abajo). Sin
    tocar el umbral general (0.30) para no aflojar el corpus internacional (~370 de las historias), que es la
    mayoria. **BUG REAL encontrado en vivo durante la prueba**: los titulares en INGLES van en Title Case (casi
    toda palabra capitalizada) — la primera version de `_nombres_propios` trataba "Memoir"/"From"/"Takeaways"
    (capitalizadas por convencion tipografica, no por ser nombres propios) como si fueran nombres propios, y unio
    FALSAMENTE un titular sobre el libro de Ari Emanuel con titulares sobre el libro de Charles Spencer/Princess
    Diana (compartian "Memoir"+"From"). Arreglado detectando si el titular "parece" Title Case (mayoria de palabras
    elegibles capitalizadas) y, en ese caso, no extrayendo ningun nombre propio de el. Medido antes/despues con
    `monitor.collect()`+`cluster()` real (mismos 777 articulos tras dedup): **18/420 -> 70/636 historias con 2+
    medios** (union falsa de Spencer/Emanuel confirmada resuelta), incluyendo casos nuevos reales como "Expreso +
    El Universo" sobre el Escudo de las Americas (gracias a los feeds nuevos) y "Expreso + Clarin + El Diario"
    sobre Santa Marta, Colombia. Revisados a mano 10 grupos al azar de 2+ medios: todos correctos (ningun caso de
    union falsa quedo). Pruebas: `test_cluster.py` (4 casos: el caso real de Guayaquil/inundacion que fallaba
    antes, el caso Title Case que se arreglo, la ventana de tiempo, y el caso normal que ya andaba bien).
    **No implementado esta fase**: embeddings de Ollama (`nomic-embed-text`) como respaldo/mejora sobre el
    matching por palabras — Ollama no estaba corriendo durante esta sesion (no se pudo probar en vivo); el enfoque
    por palabras+ventana+nombre propio ya deja una mejora real y medida sin esa dependencia. Si Fernando instala
    `nomic-embed-text` mas adelante, es un paso natural para sumar despues (`ia.py` ya tiene el patron de llamada a
    Ollama listo para copiar a un `ia.embed()`).

- **Problema 4 — Verificacion y Contraste desordenado y sin contexto.** Nueva pieza: `ia.veredicto_contraste()`
  (mismo patron de siempre: el CODIGO junta el material ya verificado — contexto de Parte B, otros medios del
  mismo grupo de la historia, contratos SERCOP, resultados FactCheck —, la IA SOLO redacta un veredicto
  coincide/contradice/sin_datos citando que parte del material uso) + `monitor.get_veredicto()` (cachea en
  `veredicto_cache.json`, corre en el hilo trabajador DESPUES de contexto/SERCOP/FactCheck porque los necesita ya
  calculados, `MONITOR_VEREDICTO_MAX` historias nuevas por pasada, def. 8). Candado en CODIGO (no solo en el
  prompt): sin NINGUN material (ni contexto, ni contratos, ni FactCheck), el estado es `sin_datos` sin siquiera
  llamar a Ollama. **Estructura fija en el dashboard** (`contrasteCardHTML()`, dashboard_template.html, reemplaza
  el uso de `cardHTML` en Contraste): afirmacion (titular+resumen) -> contexto actual (`renderContexto`, ya
  incluye "tambien aparecio" de `entities.json`) -> fuentes oficiales SERCOP (plegado si hay muchas) ->
  verificadores FactCheck (plegado) -> estado (badge de color: rojo=contradice, verde=coincide, gris=sin datos,
  ambar=pendiente, con el texto del veredicto y las citas). `renderContraste()` ahora ordena cada grupo de ambito
  primero por ESTADO (contradicciones primero) y despues por relevancia (interes) — antes solo agrupaba por
  ambito sin ningun orden interno. **No se pudo probar en vivo el veredicto real de la IA** (Ollama no estaba
  corriendo esta sesion): se probo el flujo completo con `MONITOR_SAMPLE=1` (wiring end-to-end sin errores,
  `estado_veredicto` y `h.veredicto` llegan bien a `data.json`) y la sintaxis/estructura del HTML/JS se valido con
  `node --check`; falta que Fernando lo vea con Ollama corriendo para confirmar que el texto del veredicto es
  bueno de verdad.

- **Problema 1 — Pulso social solo Ecuador y solo medios.** Diagnostico: los selectores de alcance
  (Internacional/Ecuador/Guayaquil) YA EXISTIAN en el dashboard (`#socialseg`, `socialAmb`) pero no hacian nada
  distinto de verdad — `get_social` siempre buscaba en el mismo subreddit fijo (`SOCIAL_SUBREDDIT`, "ecuador") y
  YouTube siempre con `regionCode=EC`/`relevanceLanguage=es`, sin importar el ambito del tema. Y **bug real
  encontrado en el propio dashboard**: el bloque de personas-vs-medios (`d.n_personas`/`d.n_medios`, ya escrito en
  `dashboard_template.html` segun el registro del 2026-09-22) nunca se mostraba porque `monitor.py` JAMAS calculaba
  esos dos numeros — confirmado con `data.json` real (ningun tema tenia esas claves). Arreglado:
  - `social.py`: `REDDIT_SUB_POR_AMBITO`/`YT_REGION_POR_AMBITO` (nuevo) — Reddit usa r/worldnews+r/europe para
    Internacional (sintaxis multi-subreddit nativa de Reddit) y r/ecuador para Ecuador/Guayaquil (no hay un
    subreddit de Guayaquil con actividad real confirmada; queda configurable por `MONITOR_REDDIT_SUB_GYE` si
    Fernando quiere probar uno); YouTube deja de fijar `regionCode`/`relevanceLanguage` para Internacional (antes
    los tenia fijos SIEMPRE en EC/es, perdiendo creadores en otros idiomas). `recolectar(..., ambito=...)` nuevo
    parametro que resuelve ambos; `monitor.get_social` ya pasaba el `ambito` calculado, solo faltaba mandarlo.
  - **Mastodon, fuente nueva** (`social.mastodon_buscar`): Mastodon no tiene busqueda de texto libre sin token en
    casi ninguna instancia desde la version 3.x — se usa la timeline PUBLICA de un hashtag
    (`/api/v1/timelines/tag/:hashtag`, sin cuenta), derivando el hashtag del termino de busqueda. Probado en VIVO
    (sin clave, gratis): `mastodon_buscar("Ecuador")` trajo 10 posts reales de instancias distintas, clasificados
    persona/medio correctamente.
  - **YouTube: canales de medios vs. creadores** (`social._yt_canales_info`, nuevo): `channels.list` (1 unidad de
    cuota, barato, hasta 50 canales por llamada) trae nombre + suscriptores de cada canal de la busqueda; se
    clasifica `canal_tipo` "medio"/"creador" por nombre (misma heuristica que Bluesky, `es_cuenta_medio`) — los
    suscriptores se guardan y se muestran (`canal_subs`) pero NO deciden solos el tipo (un creador independiente
    grande tambien puede tener muchos suscriptores). Cada comentario sigue clasificandose persona/medio por
    separado segun si lo escribio el propio canal (sin cambios ahi). Probado en VIVO (con `MONITOR_YT_KEY` real):
    busqueda "inseguridad Ecuador" -> canales "Ecuavisa" (2.14M suscriptores) y "Hechos Ecuador Noticias" (179K)
    correctamente clasificados `medio`; comentarios de espectadores reales clasificados `persona` (salvo el propio
    canal comentando en su video, clasificado `medio`, como ya funcionaba antes).
  - **`get_social` (monitor.py)**: ahora calcula `n_personas`/`n_medios` de verdad (activa el bloque `vozTxt` del
    dashboard que llevaba dias sin mostrarse nunca) y corre el OSINT SOLO sobre publicaciones de personas si hay
    >=3 (si no, sobre todo lo recolectado, avisando en el propio texto — esto YA estaba en la intencion documentada
    pero no en el codigo). Probado en vivo (ambito internacional, tema "Ambiente"): 45 posts (14 Bluesky, 11
    YouTube, 20 Mastodon), 43 personas / 2 medios.
  - **Dashboard**: el panel de una publicacion por fuente ahora separa dos bloques con encabezado propio — "🗣 Lo
    que dice la gente" y "📰 Lo que dicen los medios" — en vez de una lista unica con una etiqueta inline; se
    calcula la mejor publicacion por (fuente, tipo) en vez de solo por fuente, asi ambos bloques pueden tener
    contenido real de cada plataforma. Nota nueva plegable en el panel: "Por que no estan X, TikTok, Instagram ni
    Facebook" con lo que haria falta para cada una (ver mas abajo, mismo texto).
  - **Redes sin API abierta y gratis — que haria falta**: **X (Twitter)**: plan de pago Basic desde ~$200 USD/mes,
    cupo de lectura bajo para ese precio; el nivel gratis actual no permite busqueda. **TikTok**: la Research API
    es gratis pero solo para investigacion academica verificada (afiliacion universitaria/instituto aprobado por
    TikTok), no hay acceso equivalente para un proyecto personal. **Instagram/Facebook** (Meta Graph API): requiere
    una app de Meta revisada y aprobada, y en la practica solo da datos de paginas/cuentas propias o con permiso
    explicito del dueño, no busqueda abierta de lo que publica el publico. El modulo ya esta separado por fuente
    (una funcion por red) para poder sumar una de estas despues sin tocar el resto.

- **Problema 6 — el contexto de Wikipedia describe a la persona, no la situacion.** Dos arreglos:
  - `_construir_contexto` (monitor.py) ahora incluye, PRIMERO en el material (antes que cualquier bio de
    Wikipedia), los titulares de **otros medios del mismo grupo de la historia** (`s["fuentes"][1:5]` — el
    clustering YA los junto, no cuesta ninguna llamada de red nueva): "que mas se publico sobre esto, ahora mismo,
    contado por otro periodista" es la señal mas directa de la SITUACION que hay disponible gratis. El bloque de
    biografia de Wikipedia ahora se etiqueta explicitamente en el material como "usar solo como dato secundario,
    no como el centro de la respuesta" (antes no tenia esa aclaracion).
  - `ia.extraer_entidades_con_evento()` (nueva; `extraer_entidades()` sigue igual para el resto del pipeline, es
    un wrapper de compatibilidad) le pide al modelo, ADEMAS de las entidades con nombre propio de siempre, un
    candidato de EVENTO por separado (una ley, un paro, un conflicto, un desastre — con su propia pagina posible
    de Wikipedia, ej. "Paro nacional de Ecuador de 2022"), o `null` si la nota no tiene esa clase de identidad. En
    `_construir_contexto`, el evento (si existe y pasa las mismas dos capas de verificacion de Wikipedia que
    cualquier otra entidad) va PRIMERO en el material, etiquetado "articulo del SUCESO/EVENTO mismo — esta es la
    fuente principal", antes que cualquier bio de persona.
  - **No se pudo probar en vivo** (Ollama no estaba corriendo esta sesion): se probo la funcion nueva con la
    llamada a Ollama mockeada (`test_evento.py`, 4 casos: entidades+evento juntos, evento `null`, evento sin
    nombre se descarta, y que `extraer_entidades()` (compatibilidad) sigue devolviendo solo la lista). Falta que
    Fernando lo corra con Ollama real para ver si el modelo de 3B propone eventos razonables en la practica (es un
    pedido nuevo al mismo prompt, puede necesitar ajuste fino de ejemplo/formato una vez se vea el resultado real).
  - **Para la siguiente fase (pedido explicito de Fernando, no implementado ahora)**: una API de busqueda web
    (Google Custom Search JSON API, Bing Search, o similar) para el contexto, en vez de depender solo de que
    Wikipedia tenga un articulo dedicado. Notas rapidas: Google Custom Search API tiene un nivel gratis de 100
    consultas/dia (pago desde $5 por 1000 consultas extra); Bing Search API quedo descontinuada por Microsoft en
    2025 (movida a Azure AI services, con otro modelo de precios); cualquiera de las dos deja de ser "gratis sin
    limite" como Wikipedia/GDELT, y ninguna es stdlib (siguen siendo HTTP+JSON via `urllib`, asi que no hace falta
    una libreria nueva, solo una clave de API paga o con cupo diario).

## Estado al cierre del 2026-09-23
Tres rondas de arreglos hoy (ver secciones de arriba para el detalle). Resumen breve:
- **Categorias/salud de datos/duplicados/feeds**: `normalizar_categoria`, cache de GDELT/Trends/social ya no se
  pisa entre pasadas, agrupamiento por nombre propio + ventana de tiempo, feeds 22 → 44.
- **Contraste**: veredicto IA (`get_veredicto`) con estructura fija, filtro de FactCheck mas estricto (2+ palabras,
  se re-aplica al leer cache), prompt reescrito (dejo de copiar texto de ejemplo), toggle de ambito + paginado.
- **Interpretacion IA**: `ia.interpretar()` conectada de verdad (antes existia en `ia.py` pero `monitor.py` nunca
  la llamaba).
- **Pulso social**: alcance real por ambito (Reddit/YouTube/Mastodon), `_temas_por_relevancia()` implementada de
  verdad (antes siempre los mismos 5 temas alfabeticos), badge de ambito visible por tarjeta.
- **Geografia**: enumeraciones de 3+ paises ya no cuentan como señal local; secciones editoriales de un medio
  (`"ciudad"` en `feeds.py`) fuerzan ciudad sin depender del texto.
- **Pendiente real**: GDELT sigue bloqueado (HTTP 429 sostenido, limite externo, no de codigo); veredicto/contexto
  de evento sin verificar a fondo con uso real prolongado de Ollama.
- 32 pruebas automatizadas (8 archivos `test_*.py`) pasando. **Requiere reiniciar `python monitor.py serve`** para
  tomar todo lo de hoy.

## Arreglos del 2026-09-23, cuarta pasada (Bloque 1 del pedido de Fernando: diagnostico con datos reales de una
## corrida `serve` en vivo, despues arreglos, verificado todo con un reinicio real del servidor)

Diagnostico primero (con `serve` corriendo en vivo, sin tocarlo: cachés reales, `data.json` real, llamadas HTTP de
solo lectura), arreglos despues, y verificacion final con un reinicio real de `python monitor.py serve` (parado y
vuelto a levantar) -- confirmado con `data.json`/`notas.json` reales de la corrida nueva, no solo con las pruebas
unitarias. Se encontraron y detuvieron ademas **dos procesos `python monitor.py serve` corriendo a la vez** (arboles
de proceso distintos, no relacionados entre si) antes de reiniciar -- riesgo real de que dos instancias escriban
`data.json`/`dashboard.html` a la vez y se pisen; quedo UNA sola instancia corriendo al terminar.

- **Punto 1 (salud de fuentes), diagnostico**: feeds RSS 43/44 OK (Wambra 429 transitorio, ya documentado);
  Trends/Wikipedia 20/20 temas OK; GDELT 1/20 temas (HTTP 429 sostenido, limite externo, sigue igual que en rondas
  anteriores); SERCOP OK; FactCheck OK con la clave real (`MONITOR_FACTCHECK_KEY` configurada y funcionando, incluso
  trae verificaciones de Ecuador Chequea via el indice de Google). El unico bug real de fuentes fue el pulso social
  (ver Problema 3 mas abajo). De paso: el `CLAUDE.md` documentaba `REINTENTO_FALLO`/`fallo_ts` como mecanismo activo
  de enfriamiento (arreglo del 22/9) -- confirmado por grep que ya no existe en el codigo, superado hace tiempo por
  el merge-cache por tema del Problema 3 (segunda tanda). Corregido arriba, en la seccion original.

- **Problema 3a — pulso social sin lectura OSINT, congelado hasta 6h**: `get_social()` (`monitor.py`, cerca de
  `SOCIAL_TTL`) escribia el MISMO `ts` global tanto si el analisis OSINT tuvo exito como si fallo (ej. Ollama
  todavia no habia arrancado cuando partio el servidor) -- el panel quedaba sin lectura OSINT hasta 6 horas despues,
  aunque Ollama ya estuviera disponible hace rato. Arreglado con `SOCIAL_OSINT_RETRY_TTL` (`MONITOR_SOCIAL_OSINT_RETRY_MIN`,
  def. 20 min): si algun tema en cache tiene `osint_error` sin `resumen`, el TTL efectivo de TODO el cache baja a 20
  min en vez de las 6h completas, para que el trabajador lo reintente pronto. No cambia nada cuando todo viene bien.
- **Problema 3b — segmentacion por tema×ambito**: confirmado que `_temas_por_relevancia()` ya funciona bien (no era
  un bug nuevo); lo que se veia como "solo trae informacion general" era la MISMA causa que 3a (cache congelado con
  una foto vieja de solo 5 temas, todos Ecuador/Guayaquil). Se resuelve solo con el arreglo de 3a.

- **Problema 2 — "Mercado de cobertura" enganoso**: con GDELT en 1 de 20 temas, el grafico de torta de
  `renderPies()` (dashboard_template.html) mostraba ESE unico tema al 100% sin ninguna aclaracion -- se veia como
  "todo es Politica" en vez de "solo tenemos dato de un tema". A diferencia del resto del dashboard (`renderGdelt`,
  `renderGap`), este punto nunca usaba `DATA.estado_gdelt` (que ya trae el motivo real). Arreglado: se cuenta
  cuantos de los temas que aparecen HOY en las historias tienen dato real de GDELT: si tiene 0, se muestra el mismo
  mensaje honesto que ya usa el resto del dashboard; si tiene ALGO pero menos de la mitad, se muestra igual la
  torta parcial pero con un aviso debajo ("Datos de GDELT de solo N de M temas... el grafico no representa el
  mercado completo").

- **Problema 4a — BUG GRAVE de fondo, mas serio de lo que parecia**: el reclamo de Fernando ("la noticia #1 de
  Ecuador era de Infobae, que no es un medio local") tenia DOS causas, y la mas importante no era la que se
  sospechaba inicialmente (una colision de `EC_TERMS`/`_ASAMBLEA_AMBIGUA`) sino un **bug real de agrupamiento**
  (`cluster()`, `monitor.py`): en dias de un evento grande cubierto por muchos medios a la vez (la semana de la
  Asamblea General de la ONU, con Ecuador, Venezuela, Cuba, Iran y la realeza europea todos presentes en Nueva
  York), decenas de titulares DISTINTOS compartian palabras de SEDE/EVENTO ("Nueva York", "Asamblea General",
  "ONU") sin ser la misma historia -- el enlace por MAXIMO (single-linkage) de `cluster()` los encadenaba a TODOS
  en un solo grupo gigante. Reproducido con los 21 titulares reales de esa corrida (guardados en
  `test_cluster_evento_generico.py`): una nota de El Universo sobre Daniel Noboa/Ecuador en la ONU terminaba en el
  MISMO cluster que Delcy Rodriguez/Trump, Iran, Cuba y la realeza europea (9 medios, 7 internacionales) -- y como
  el grupo mezclado SI mencionaba "Ecuador" en una nota, TODA la historia se clasificaba como ambito local,
  encabezando Ecuador sin que ningun medio ecuatoriano cubriera realmente ese angulo puntual.
  Se probaron dos arreglos antes de quedarse con el bueno: (1) excluir por FRECUENCIA los tokens/nombres que
  aparecen en muchos titulares de la misma corrida -- descartado porque rompia el caso normal (una historia real
  cubierta por 10+ medios legitimamente comparte su propio nombre muchas veces, indistinguible por frecuencia sola
  de una palabra generica de evento); (2) el que quedo: `EVENTO_GENERICO` (`monitor.py`, junto a `STOPWORDS`), una
  lista chica y curada de palabras de sede/evento ("nueva", "york", "onu", "asamblea", "general", "naciones",
  "unidas") que se resta tanto del solape de palabras (`_tok`) como del nombre propio compartido (`_nom`) SOLO
  dentro de `cluster()` -- mismo mecanismo que ya usa el proyecto para "ecuador"/"ecuatoriano" en `STOPWORDS`
  (demasiado genericos para identificar una historia puntual) y para `_ASAMBLEA_AMBIGUA` (misma clase de problema,
  resuelta con el mismo estilo de excepcion curada en vez de un mecanismo generico). Verificado con un reinicio
  real de `serve`: los titulares de Noboa/Ecuador en la ONU ahora son historias PROPIAS y separadas (la mayoria con
  ambito internacional correctamente, salvo las que de verdad tienen angulo local con medios ecuatorianos
  cubriendolas), y la nota de Delcy Rodriguez/Trump quedo en su propio cluster de ambito internacional, sin
  arrastrar a Ecuador. `test_cluster_evento_generico.py` (2 pruebas: el caso real no se encadena; la historia real
  con varios medios genuinos sigue uniendose).
- **Problema 4b — el ranking no pesaba medios locales vs. internacionales**: `build_stories()` ya calculaba
  `outlets_intl` pero `s["interes"]` (la formula real de ranking, duplicada en `run_once` y `run_fast`) usaba
  `s["n_outlets"]` a secas -- un medio internacional pesaba EXACTAMENTE igual que uno local. Arreglado con
  `_peso_outlets(s)`: en historias de ambito LOCAL, cada medio ecuatoriano sigue pesando 40 puntos, cada
  internacional pesa 5 (un octavo) -- 7 medios internacionales (35 puntos) siguen pesando MENOS que 1 solo medio
  ecuatoriano (40 puntos), asi que una nota de Ecuador con mayoria de cobertura internacional ya no puede encabezar
  sola sin cobertura local. En ambito internacional no cambia nada (ahi la cobertura extranjera SI es la señal
  relevante). Verificado con un reinicio real: el top 10 de Ecuador por interes paso a ser el 100% historias con
  CERO medios internacionales (antes mezclaba Infobae/ABC.es/Clarin en el tope). `test_ranking_medios.py`
  (3 pruebas).
- **Problema 4c — dos categorias mal cubiertas por `KEYWORDS`**: "Ecuador suma un nuevo dia de descanso... feriados
  de 2026" no matcheaba NINGUN termino (quedaba en 'otros' con `temas=[]`) -- se agrego "feriado"/"feriados"/"dia
  de descanso"/"puente vacacional"/"asueto" a `Cultura/Comunidad` en `feeds.py`. Por separado, "inversion" a secas
  en `Comercio/Inversion` era demasiado generica: cualquier nota que mencionara "una inversion de $X millones" (ej.
  un plan de salud infantil) activaba esa categoria sin tener nada que ver -- se exigio la frase completa
  ("inversion extranjera"/"inversionista"/"inversion privada"), mismo criterio ya usado antes para depurar
  `EC_TERMS` ("sucre", "los rios", "el oro"). Verificado que ambos casos reales clasifican limpio ahora
  (`themes_for()` devuelve una sola categoria correcta en vez de vacio o una categoria falsa de mas).
  **No resuelto del todo**: un tercer caso real ("Ejercito inhabilita... mineria ilegal en Putumayo") SI clasifica
  bien por `themes_for()` (→ Ambiente) pero terminaba en 'otros' en `data.json` real -- la perdida ocurre DESPUES,
  en la reclasificacion de la IA (`get_ia`/`_apply`, que solo puede QUITAR categorias, nunca agregar). No se
  investigo la causa exacta (requiere una corrida con Ollama real para observar que decidio el modelo en ese caso
  puntual) -- queda como pendiente.

- **Problema 5 — verificaciones (Contraste) "sin datos" en Ecuador**: confirmado que la clave de FactCheck
  funciona bien (no es un problema de cuota/clave). De 19 historias Ecuador con veredicto `sin_datos` revisadas 10
  a mano: genuinamente no tienen contrato SERCOP ni verificacion viral asociada (notas de feriados, certamenes,
  clima) -- el `sin_datos` ahi es HONESTO, no un bug del filtro `_factcheck_relevante`. Ecuador Chequea ya esta
  cubierto indirectamente (Google Fact Check Tools lo indexa). **No se investigo** si el Registro Oficial o
  boletines de Presidencia/Asamblea tienen RSS/API abierta -- queda pendiente, no evaluado en esta pasada.

- **Problema 6 — el mas grave del diagnostico, `/api/nota` nunca existio**: el frontend (`dashboard_template.html`)
  ya mandaba las notas a `POST /api/nota` desde la sesion del 22/9 (documentado ahi como implementado), pero el
  servidor (`monitor.py`, `_do_POST`) NUNCA agrego esa ruta -- solo conocia `/api/guardar` y `/api/chat`; cualquier
  nota que Fernando escribia recibia un 404 y se perdia al instante. Mismo patron de "documentado como resuelto
  pero nunca conectado" que ya paso antes con `ia.interpretar()` y `_temas_por_relevancia()`. Arreglado: `NOTAS_PATH`
  = `notas.json`, `load_notas()`/`save_notas()` (mismo patron que `saved.json`: contenido del usuario, no cache,
  archivo temporal + `os.replace`), ruta `/api/nota` en `_do_POST` (guarda si hay texto, borra la clave si el texto
  queda vacio), y `notas.json` agregado a `RUTAS_MOVIL` para que tambien se pueda leer desde el celular. Verificado
  en vivo contra el servidor real reiniciado: `POST /api/nota` con una nota de prueba respondio `{"ok":true,...}`,
  `GET notas.json` la devolvio, y se borro la nota de prueba antes de terminar (no quedo contenido de prueba en el
  `notas.json` real de Fernando).
  **Bug relacionado, encontrado de paso (la sospecha original de Fernando, aunque no era la causa del 404)**:
  `story_key()`/`storyKey()` (la clave que comparten Guardadas Y Notas) usan `fuentes[0].link` -- pero `fuentes` no
  tenia un orden garantizado (dependia de como `cluster()` fue armando el grupo), asi que si una historia en
  desarrollo sumaba un medio NUEVO y mas reciente, esa fuente podia pasar a ocupar la posicion 0 y CAMBIAR la clave,
  dejando huerfana una nota/guardado ya hecho. Arreglado en `build_stories()`: `fuentes` ahora se ordena por fecha
  ASCENDENTE (la fuente MAS VIEJA queda en la posicion 0) -- la fuente que arranco el cluster casi no cambia entre
  corridas, es la eleccion mas estable disponible sin agregar un id propio a cada historia. `test_notas.py`
  (5 pruebas: round-trip de notas.json + que fuentes[0] es la mas vieja + que la clave no cambia al sumar un medio).

- **Verificacion final, reinicio real de `serve`**: se detuvieron los DOS procesos `python monitor.py serve` que
  estaban corriendo a la vez (ver arriba) y se levanto una instancia nueva y unica con todo el codigo de hoy. El
  servidor bindeo el puerto en menos de 30s (cache de GDELT/Trends no estaba vencido de forma total esta vez, asi
  que no aplico el escenario de 9+ minutos ya documentado). Confirmado con `data.json` real de la corrida nueva:
  top 10 de Ecuador con 0 medios internacionales (antes mezclaba varios), el caso Noboa/Delcy separado en historias
  propias, "Ecuador suma un nuevo dia de descanso" y "Plan de Primera Infancia" ahora con categoria real en vez de
  'otros', y `estado_gdelt`/`estado_social` mostrando el mismo texto honesto de siempre. `/api/nota` probado con
  una llamada HTTP real de punta a punta. 39 pruebas automatizadas (11 archivos `test_*.py`, sumando los 4 archivos
  nuevos de hoy) pasando.

- **Pendientes reales que quedan de esta pasada** (no resueltos, anotados para no perderlos):
  1. La IA (`get_ia`/`_apply`) a veces quita TODAS las categorias de una nota que `themes_for()` si habia
     clasificado bien (caso real: "mineria ilegal en Putumayo" → Ambiente por keywords, pero 'otros' en
     `data.json`) -- no investigado a fondo, requiere una corrida con Ollama real y revisar que decidio el modelo
     para ese caso puntual.
  2. No se evaluo si el Registro Oficial de Ecuador o boletines de Presidencia/Asamblea Nacional tienen RSS/API
     abierta y gratuita para sumar como fuente de Contraste.
  3. GDELT sigue en corte casi total (1/20 temas), limite externo confirmado de nuevo, no arreglable por codigo.
  4. Bloque 2 del pedido de Fernando (agente IA con herramientas sobre `data.json`/`history.json`/
     `guardadas`/`notas`/Trends/GDELT/SERCOP/pulso social, cruce de informacion, citas obligatorias, 10 preguntas
     de prueba antes/despues) **no arrancado todavia** -- queda como siguiente fase.

## Bloque 2 — el Asistente (2026-09-23, quinta pasada): agente con herramientas sobre los datos propios

Implementado, probado en vivo (Ollama corriendo de verdad) y verificado con un reinicio real de `serve`.
Modulos nuevos: `herramientas.py` (herramientas de solo lectura) y `agente.py` (ciclo de herramientas +
respuesta final), mas la ruta `/api/asistente` en `monitor.py` y una pestaña nueva "Asistente" en el
dashboard (ver sus entradas en "Módulos" mas arriba para el detalle tecnico). Resumen de las decisiones:

- **Hardware de esta PC** (relevante para elegir modelo): 16.4 GB RAM, GPU GTX 1650 SUPER con 4GB VRAM
  (dato de sesiones previas, reconfirmado). Modelos instalados en Ollama mas alla de los dos que ya usa el
  proyecto (`qwen2.5:3b`, `monitor-critico` 8.2B): `deepseek-r1:8b`, `gemma2:9b`, `qwen2.5-coder:7b`,
  `deepseek-coder:6.7b`, `command-r` (18GB), `command-r-plus` (59GB), `periodista-pro`, `gemma4`, entre otros.

- **Benchmark real, medido en esta sesion** (no estimado): `qwen2.5:3b` cargo en 18.8-19.6s y genero 38-41
  tokens en total ~22s; `gemma2:9b` cargo en 78.6s la PRIMERA vez (disco frio) y 27.9s la segunda (ya en
  cache del SO), sin ninguna ventaja de calidad clara sobre qwen2.5:3b en la prueba directa. Dato clave:
  **en esta GPU de 4GB VRAM solo entra UN modelo resiente a la vez** -- cargar `gemma2:9b` desalojo a
  `qwen2.5:3b`, que tuvo que recargar de cero en la siguiente llamada. `command-r`/`command-r-plus`
  (18GB/59GB) se descartaron SIN medirlos en vivo: si un modelo de 8B (5.2GB) ya corre ~65% en CPU (~5
  tokens/seg, medido antes para `monitor-critico`), un modelo de 18-59GB corre casi enteramente en CPU --
  la aritmetica ya lo descarta para uso interactivo sin hacer esperar varios minutos solo para confirmarlo.

- **Decision de arquitectura: DOS modelos, no uno solo.** `qwen2.5:3b` (el mismo modelo rapido del pipeline
  por lotes) maneja el CICLO DE HERRAMIENTAS -- decide que consultar, ronda por ronda, hasta 4 rondas
  (`agente.MAX_RONDAS`). `monitor-critico` (el mismo modelo pesado que ya usa el chat "profundo" de Parte E)
  redacta la RESPUESTA FINAL, una sola vez por pregunta, con todo el material ya juntado. Paga la recarga
  pesada (~20-30s) una sola vez por pregunta en vez de en cada ronda de decision, y es el que de verdad
  necesita criterio para cruzar datos y notar contradicciones -- no solo repetir el material.

- **Herramientas** (`herramientas.py`, ver "Módulos" para el detalle completo): `buscar_historias` (con
  filtro `veredicto` agregado despues de la prueba en vivo, ver abajo), `detalle_historia`,
  `buscar_guardadas`, `buscar_notas`, `tendencia_tema`, `comparar_periodo`, `buscar_contratos_sercop`. Mismo
  principio de Parte B llevado al agente: **nunca** disparan una llamada nueva a Trends/GDELT/SERCOP/redes
  en vivo, solo leen lo que el pipeline normal ya calculo -- usar el Asistente no agrega latencia ni riesgo
  de rate-limit nuevo a esas fuentes.

- **Bug real encontrado probando el ciclo en vivo**: el modelo que decide que consultar no siempre
  reproduce el nombre EXACTO del catalogo de temas (paso `"carceles"` en vez de `"Carceles"`) ni el valor
  exacto de ambito (`"Ecuador"` en vez de `"local"`) -- 0 resultados hasta agregar `_normalizar_tema()` y un
  mapeo de sinonimos de ambito (mismo problema, mismo tipo de arreglo, que ya resolvio `ia._TEMA_LOOKUP`
  para la clasificacion por lotes). Confirmado antes/despues con el mismo caso real.

- **Hallazgo real de la comparacion antes/despues** (ver abajo): al pedirle "hay contradicciones entre
  medios", el agente respondio que no tenia forma de saberlo -- no habia ninguna herramienta que expusiera
  directamente el `veredicto` (coincide/contradice/sin_datos/pendiente) que Contraste YA calcula por
  historia. Se agrego el argumento `veredicto` a `buscar_historias` (con `test_herramientas.py` cubriendo el
  caso) para que una pregunta de este tipo se pueda responder de forma directa en vez de que el agente
  tenga que adivinar con otra herramienta.

- **Streaming + progreso**: mismo protocolo NDJSON que el chat por item (`/api/chat`), con un tipo de linea
  nuevo `{"progreso": "..."}` que el dashboard muestra mientras el ciclo de herramientas corre (si no, la
  espera de varios segundos antes de la respuesta final se siente muda -- mismo criterio que ya establecio
  el streaming de Parte E). Probado en vivo con `curl -N` contra el servidor real reiniciado: la linea de
  progreso llega primero, despues los tokens de la respuesta de a uno, despues `{"done":true,"ok":true}`.

- **Memoria de la conversacion**: igual que el chat por item (Parte E, "Decisiones ya tomadas") -- vive en
  el navegador (`asistenteHilo` en `dashboard_template.html`), se manda entera en cada pregunta, se pierde
  al recargar la pagina. Mismo criterio de simplicidad deliberada, no una limitacion nueva de este bloque.

- **Comparacion antes/despues, 3 de las 10 preguntas probadas EN VIVO con Ollama real** (las otras 7 quedan
  preparadas para que Fernando las pruebe el mismo, ver la lista completa abajo -- correr las 10 en vivo
  hubiera tomado ~25-30 min mas de tiempo de modelo, y 3 ya alcanzan para mostrar el patron real):

  1. *"Que se sabe hoy sobre carceles en Ecuador? Cita las fuentes."*
     - **Antes** (mismo modelo pesado, SIN herramientas, item vacio -- el chat de hoy siempre necesita un
       item abierto): *"no tengo los datos específicos que el periodista ha calculado para esta consulta...
       ¿Podrías compartir los datos calculados?"* -- inutil para una pregunta abierta, el modelo no tiene de
       donde sacar el dato.
     - **Despues**: cito el titular real, el medio (El Comercio) y el link de una nota sobre un militar
       separado del cargo por un caso de abuso sexual en una carcel de Guayaquil, marco aparte una segunda
       nota como "incompleta... no tengo suficiente informacion", y cerro con una "Lectura critica"
       explicitamente etiquetada como tal (no mezclada con el dato) proponiendo una pregunta de seguimiento.
  2. *"Hay contradicciones entre lo que reportan distintos medios sobre algun tema de seguridad esta
     semana?"*
     - **Antes**: mismo rechazo generico, sin dato.
     - **Despues**: contesto honesto que no tenia con que responder esa pregunta puntual (ver el hallazgo
       real de arriba, ya corregido agregando el filtro `veredicto`).
  3. *"Que angulo de reportaje me recomendarias sobre economia/comercio esta semana, con que fuentes
     empezar?"*
     - **Antes**: **no genero ninguna respuesta** (string vacio).
     - **Despues**: contesto honesto que no tenia datos especificos de esa semana puntual y sugirio revisar
       la demanda de busqueda como punto de partida -- correcto en el sentido de "no inventar", aunque
       generico; con el catalogo de herramientas de hoy el agente no tiene una funcion dedicada a "sugerir
       un angulo" mas alla de lo que ya trae el material (ver Pendientes).
  4. *"Que contratos SERCOP hay relacionados con el Ministerio de Salud?"* (probada aparte, via `curl -N`
     directo contra `/api/asistente`, confirmando el protocolo NDJSON de punta a punta): *"No tengo datos
     sobre contratos SERCOP relacionados con salud en este momento."* -- honesto, el termino nunca se habia
     consultado en una corrida anterior del trabajador (`sercop_cache.json` no lo tenia).

  **Las 10 preguntas de prueba** (1-4 ya probadas arriba; 5-10 quedan listas para que Fernando las corra
  desde la pestaña Asistente):
  5. ¿Cómo cambió la cobertura de noticias sobre Cárceles comparado con hace una semana?
  6. ¿Qué dice el pulso social sobre el desempleo en Ecuador esta semana?
  7. ¿Hay alguna nota guardada o nota personal sobre corrupción que deba retomar?
  8. ¿Qué brecha hay entre lo que busca la gente en internet y lo que cubren los medios esta semana?
  9. ¿Qué medios están cubriendo el tema Asamblea/Leyes y qué dicen?
  10. ¿Cuál es la demanda de búsqueda sobre inflación y cómo se compara con la cobertura de prensa?

  **Tiempo real medido, no estimado**: 110-175s por respuesta completa en esta PC (antes: 110-164s incluso
  SIN hacer nada util; despues: 122-175s, el ciclo de herramientas agrega ~10-20s sobre el tiempo que ya
  tomaba el chat "profundo" de Parte E). Mas lento que el objetivo implicito de una consulta interactiva --
  es el mismo limite de hardware ya documentado para `monitor-critico` (deepseek-r1:8b, ~5 tokens/seg,
  65% CPU), no algo nuevo de este bloque. El streaming ayuda a que la espera se sienta mejor (la linea de
  progreso aparece primero), pero no baja el tiempo total.

- **Pendientes reales, no resueltos en esta pasada**:
  1. Solo se corrieron 3 de las 10 preguntas de prueba en vivo con Ollama real (mas una cuarta via `curl`
     directo) -- las otras 6 quedan listas en la lista de arriba para que Fernando las pruebe.
  2. El agente no tiene una herramienta dedicada a "proponer angulos de reportaje" mas alla de razonar sobre
     el material que ya trajeron las otras herramientas -- si la pregunta 3 de la prueba se repite seguido,
     vale la pena revisar si hace falta una herramienta que cruce demanda alta + poca cobertura (la misma
     logica que ya usa `renderGap()`/Oportunidades en el dashboard) en vez de dejar que el agente lo infiera
     solo del material que ya tiene.
  3. El material que arma `_fmt_transcripcion()` en `agente.py` a veces incluye campos "crudos" del dato
     (ej. `veredicto_contraste: pendiente, veredicto_texto: Todavia no procesado`) que el modelo termina
     citando casi textual en la respuesta -- funciona, pero no es la redaccion mas prolija; podria filtrarse
     antes de armar el material (descartar campos sin valor real, ej. `veredicto=="pendiente"`) para que la
     respuesta final quede mas limpia. No se hizo en esta pasada por tiempo.
  4. No se probo el comportamiento del ciclo de herramientas con una pregunta que genuinamente necesite 3-4
     rondas encadenadas (las probadas en vivo resolvieron todas en 1 ronda) -- vale la pena una prueba
     puntual con una pregunta mas compleja (ej. "compara la cobertura de Ejecutivo de hoy contra hace 10
     dias y decime si hay alguna nota guardada relacionada") para confirmar que el corte de rondas repetidas
     (`vistos`, en `ciclo_herramientas`) no corta antes de tiempo un caso legitimo de varias consultas.
  5. Se encontraron y detuvieron, de nuevo, DOS instancias de `python monitor.py serve` corriendo a la vez
     antes de este reinicio (mismo riesgo de la pasada anterior: escritura simultanea de `data.json`/
     `dashboard.html`). Si esto sigue repitiendose, vale la pena revisar si `INICIAR.bat`/algun acceso
     directo esta arrancando el programa mas de una vez sin que Fernando lo note.

## Bloque 2, continuacion (2026-09-23, quinta pasada): modelo mejor para la Lectura IA de cada tarjeta

Pedido de Fernando tras ver el reporte de arriba: *"aun estas corriendo qwen [2.]5:3[b], necesitamos un
mejor modelo para la IA local para que funcione mejor"*. Antes de tocar nada se le explico el mapa completo
(4 lugares donde el proyecto usa un modelo, cada uno con una razon distinta de velocidad) y confirmo:
activar el modelo pesado para la Lectura IA de las tarjetas (`ia.interpretar()`, acotada a
`MONITOR_IA_INTERP_MAX`=12 notas nuevas por pasada), dejando la clasificacion de tema/Ecuador-Mundo
(`ia.analizar()`, corre sobre MUCHO mas volumen por pasada) en el modelo rapido como esta hoy.

- **BUG REAL encontrado antes de poder activar nada**: `INTERP_MODEL`/`MONITOR_IA_INTERP_MODEL` existia en
  `ia.py` desde el arreglo de "IA literal" (documentado como una opcion disponible), pero **nunca podia
  hacer efecto** -- `monitor.py` llamaba a `ia.interpretar(..., forzado=IA_MODEL)` SIEMPRE, y `forzado` le
  gana a `INTERP_MODEL` en la resolucion del modelo. Mismo patron de "quedo documentado pero nunca
  conectado" que ya paso con `ia.interpretar()` en si (2026-09-22), `_temas_por_relevancia()` (2026-09-23,
  segunda tanda) y `/api/nota` (2026-09-23, cuarta pasada) -- cuarta vez que aparece esta clase de bug en el
  proyecto, vale la pena tenerlo presente al revisar cualquier "ya deberia estar andando".
- **Arreglo, dos lados**: se saco `forzado=IA_MODEL` del llamado en `monitor.py` (`get_ia`), y en `ia.py` la
  resolucion de modelo de `interpretar()` paso a ser `forzado > INTERP_MODEL (env) > elegir_modelo_chat()`
  (el mismo modelo pesado del chat "profundo", `monitor-critico`, con el fallback automatico al rapido que
  `elegir_modelo_chat()` ya hacia si no esta instalado). Cuando el modelo resuelto NO es el rapido del
  pipeline, `num_predict` sube de 140 a 600 y el timeout minimo sube a 220s -- **sin esto el cambio se
  rompe solo**: con poco num_predict, un modelo de razonamiento gasta todo el presupuesto "pensando" y
  devuelve string VACIO sin ningun error (el mismo bug real ya documentado para `chat_stream`/`MODOS_CHAT`,
  se repite aqui si no se replica el mismo arreglo).
- **Probado en vivo, mismo titular, antes/despues real** (no simulado):
  - Titular: *"Gobierno de Ecuador anuncia subsidio focalizado al diesel para transporte pesado"*.
  - **Antes** (`qwen2.5:3b`, 6.4s): *"¿Quién será beneficiado con el subsidio y cuáles son las
    restricciones? ¿Cómo afectará esto a los transportistas y el fisco?"* -- preguntas razonables pero sin
    comprometerse con una lectura concreta.
  - **Despues** (`monitor-critico`, 103.3s): *"El subsidio a los camiones de carga puede favorecer a los
    transportistas, pero no resolverá el transporte nacional ni la logística de importación. Quienes se
    beneficiarán son los que usan camiones, pero a los ciudadanos les subirá el costo indirecto."* -- toma
    posicion: nombra a quien beneficia, que NO resuelve, y una consecuencia indirecta concreta.
  - Confirmado con `ia.elegir_modelo_chat()` que el modelo resuelto es efectivamente `monitor-critico`
    (no una casualidad de que ambos dieran texto parecido).
- **Costo real, no estimado**: ~16x mas lento por nota (6.4s vs 103.3s). Con `MONITOR_IA_INTERP_MAX`=12
  notas nuevas por pasada del trabajador, el peor caso ronda los 12-20 minutos SOLO para interpretacion en
  esa pasada (corre en el hilo trabajador de fondo, Parte C -- nunca bloquea el feed/`run_fast`, pero SI
  puede atrasar el resto del trabajo de esa misma pasada -- contexto, FactCheck, veredicto, social -- que
  corre despues en la misma funcion `enrich_pass`). Si en el uso real esto se siente demasiado lento para
  que el resto del trabajador avance, la palanca es bajar `MONITOR_IA_INTERP_MAX` (ej. a 4-6) via variable
  de entorno -- no se cambio el default en esta pasada, queda como ajuste fino pendiente de ver en uso real.
- `test_interpretar_modelo.py` (4 pruebas, sin golpear Ollama: monkeypatchea `ia._post` para capturar que
  modelo/num_predict/timeout arma `interpretar()` en cada combinacion) + prueba en vivo con Ollama real
  documentada arriba. Verificado con un reinicio real de `serve` (se encontraron y detuvieron, otra vez,
  dos instancias corriendo a la vez -- tercera vez que pasa en esta sesion, ver Pendientes del bloque
  anterior).
- **Pendiente**: no se probo si 12 notas/pasada con el modelo pesado genera un atraso perceptible en el
  resto del trabajador durante uso real prolongado (solo se midio el costo de UNA llamada) -- revisar en
  unos dias de uso real si `estado_ia`/`estado_contexto`/etc. se sienten mas atrasados que antes, y si es
  asi, bajar `MONITOR_IA_INTERP_MAX`.

## Causa real de las instancias duplicadas de `serve` (2026-09-23, quinta pasada)

Fernando pidio revisar por que `INICIAR.bat` parecia arrancar el Monitor dos veces (encontrado y corregido
a mano tres veces en esta sesion, ver Pendientes de los dos bloques anteriores).

- **Causa real, confirmada leyendo el .bat**: `INICIAR.bat`/`CONECTAR_IPHONE.bat`/
  `ABRIR_EN_CELULAR_TAILSCALE.bat` usaban el patron `python ... || py ...` ("si el primer comando termina
  con error, corre el segundo"). Para un comando de un solo golpe (como `monitor.py movil`) esto es
  inofensivo. Para `INICIAR.bat`, que lanza `monitor.py serve` -- un servidor que deberia quedar corriendo
  INDEFINIDAMENTE hasta que Fernando cierre la ventana -- es peligroso: en esta PC, `python` resuelve al
  alias de Windows Store (`...\WindowsApps\python.exe`), que reenvia la ejecucion al interprete real
  (`...\pythoncore-3.14-64\python.exe`) como un proceso hijo. Si ese alias devuelve un codigo de salida
  distinto de cero en el momento del reenvio (comportamiento conocido de los alias de Windows Store, no
  exclusivo de este proyecto) AUNQUE el programa real haya arrancado bien de fondo, `||` interpreta eso como
  "fallo" y dispara el segundo comando (`py monitor.py serve`) -- una SEGUNDA instancia completa, corriendo
  en paralelo a la primera, ambas escribiendo `data.json`/`dashboard.html`/`history.json` a la vez.
- **Arreglo**: los tres `.bat` ahora eligen UN SOLO interprete de antemano con `where python` (si existe,
  usa `python`; si no, `py`) y lo usan una sola vez -- nunca los dos en la misma ejecucion, sin importar el
  codigo de salida de nada. `INICIAR.bat` ademas suma un chequeo de seguridad: antes de arrancar nada,
  prueba si el puerto 8000 ya esta contestando (`Test... TcpClient` via PowerShell, sin depender de
  `curl`/`netstat` que pueden no estar disponibles) -- si YA hay un Monitor corriendo, no lo duplica, solo
  abre el dashboard en el navegador. Probado en vivo: con el servidor real corriendo, `INICIAR.bat` detecto
  el puerto ocupado y mostro el mensaje correcto ("El Monitor ya esta corriendo... Abriendo el dashboard")
  en vez de arrancar una instancia nueva.
- **No confirmado con el 100% de certeza que esta fuera la causa** de las tres duplicaciones vistas en esta
  sesion -- no se pudo reproducir el fallo EXACTO del alias de Windows Store bajo demanda (es intermitente
  por naturaleza), pero es la explicacion mas consistente con la evidencia (el patron `||` estaba ahi,
  "python" es el alias en esta PC). De todos modos, el chequeo de puerto nuevo hace que, sea cual sea la
  causa exacta, ya no pueda volver a pasar -- no depende de entender por que "python" devuelve codigo de
  error, solo de no arrancar nada nuevo si el puerto 8000 ya esta ocupado.

## Fase 0 (2026-09-23, sexta pasada) — velocidad: por que una noticia podia tardar horas en verse

Fernando reporto una noticia de un medio de Ecuador que aparecio 2h despues de publicada, con meta de <3
min entre publicacion real y aparicion en el dashboard. Diagnostico con datos/pruebas reales primero,
despues arreglos, siguiendo el orden de causas candidatas del propio pedido.

### Diagnostico (evidencia real, no estimada)

- **(b) MONITOR_FEED_MIN/run_fast, DESCARTADO**: medido en vivo, el pipeline completo (`collect()` +
  `dedup()` + `cluster()` + `build_stories()`, los 44 feeds) tarda **10.2s** de punta a punta. Con
  MONITOR_FEED_MIN=2 (el valor de antes), hay margen de sobra -- esto NO explica una demora de horas.
- **(c) zona horaria, CONFIRMADO Y ARREGLADO**: `parse_date()` usaba `%Z` de `strptime` para las fechas con
  sigla de zona horaria ("EDT", "PST", etc.) -- Python's `%Z` en parseo SOLO reconoce un puñado fijo
  (basicamente UTC/GMT), confirmado con una prueba directa (`strptime(..., "%Z")` con "EDT" -> `ValueError`,
  con "GMT" -> OK). **CBC News mandaba TODAS sus fechas en este formato** ("Wed, 23 Sep 2026 13:06:11 EDT")
  -- el 100% de sus notas quedaba con `date=None`. Consecuencia real en `build_stories()`: con `date=None`,
  el `recency_bonus` (el peso de "que tan nueva es") cae a 0 -- el PEOR valor posible, igual que si la nota
  tuviera dias -- y ademas nunca se marca `antigua=True` (por el mismo `hours=None`). Una nota de CBC
  reciente de verdad se hundia en el ranking sin ningun error visible. Arreglado con un diccionario de
  siglas comunes (`_TZ_ABBREV`: EST/EDT/CST/CDT/MST/MDT/PST/PDT/GMT/UTC/BST/CET/CEST) que traduce la sigla a
  un offset numerico ANTES de intentar los formatos -- asi %z (confiable) la agarra en vez de depender de
  %Z. Verificado en vivo: CBC paso de 0/20 a 20/20 notas con fecha real parseada, y se confirmo de nuevo con
  el servidor real reiniciado (`latencia_feeds["CBC News (World)"].sin_fecha == 0`). `test_parse_date_tz.py`
  (5 pruebas). De paso, revisando los 44 feeds en vivo se encontraron dos casos que NO son bugs de codigo:
  **Corriere della Sera** (`xml2.corriereobjects.it/rss/esteri.xml`) sirve contenido genuinamente viejo
  (~566 dias, confirmado con las fechas crudas del feed: marzo 2025-diciembre 2024) -- el feed en si esta
  abandonado/no se actualiza, no hay nada que nuestro codigo pueda arreglar ahi; **La Gaceta** simplemente
  no habia publicado nada nuevo en ~23h al momento de medir -- puede ser normal para un medio chico, no
  necesariamente un problema.
- **(f) el dashboard no avisa de lo nuevo, CONFIRMADO -- la explicacion mas probable del caso real de
  Fernando**: `usuarioOcupado()` (dashboard_template.html) devuelve `true` si `window.scrollY > 400` -- con
  eso, el `poll()` de cada 45s (antes) NUNCA aplicaba datos nuevos solo, mostraba la pildora "Hay datos
  nuevos" (facil de no notar leyendo) y se quedaba ahi. Si Fernando tenia la pestaña abierta, scrolleado
  leyendo, la nota podia estar lista en el `data.json` real en minutos pero la pestaña seguia mostrando la
  foto vieja hasta que el volviera a scrollear arriba y la aplicara a mano -- perfectamente consistente con
  "tardo 2 horas en aparecer" siendo, en realidad, un problema de que la pestaña abierta no se actualizaba
  sola, no de que el dato tardara. Este mecanismo es CORRECTO para el resto del dashboard (no interrumpir la
  lectura a proposito, ver Decisiones ya tomadas del 2026-09-22) -- el arreglo no lo toca, agrega una vista
  aparte pensada justamente para esto (ver "Última hora" abajo).
- **(d)/(e) ranking bajo / cluster se pego a una historia vieja, DESCARTADOS por diseño**: revisado el
  codigo de `build_stories()`/`cluster()` -- `newest` (y por lo tanto `hours`/`antigua`/`recency_bonus`) se
  recalcula sobre el MAXIMO de fechas de TODOS los articulos del cluster en cada pasada, incluida una nota
  nueva que se una a un grupo viejo -- no se encontro ningun caso donde una nota nueva quedara "atrapada"
  con la fecha vieja del grupo. No se encontro evidencia de un bug aca (a diferencia de (c) y (f), que si
  tenian evidencia real).
- **BUG REAL de paso, encontrado revisando `write_outputs()`**: el CLAUDE.md documentaba "data.json se
  escribe atomico (`_escribir_atomico`)" como ya hecho (arreglo del 2026-09-22) -- confirmado por grep que
  esa funcion **nunca existio en el codigo**, `write_outputs()` seguia escribiendo `data.json`/
  `dashboard.html` directo. Sexta vez que aparece el patron "documentado pero nunca conectado" en este
  proyecto. Riesgo real (bajo pero real): el `poll()` del dashboard puede pedir `data.json` a mitad de una
  escritura y recibir JSON invalido (ya lo tolera, reintenta solo en el siguiente poll, pero mejor que no
  pase). Arreglado con archivo temporal + `os.replace`, mismo patron que `saved.json`/`notas.json`.

### Arreglos implementados

1. **`fetch_cache.json` (nuevo) + peticion condicional (ETag/If-Modified-Since)**: `fetch()` ahora manda
   `If-None-Match`/`If-Modified-Since` si los tiene guardados de la vuelta anterior; si el servidor
   contesta 304 (sin cambios), no baja el cuerpo entero. Probado en vivo: de 44 feeds, **15 devolvieron 304
   real** en una segunda consulta inmediata (los otros 28 no lo soportan bien o de verdad cambiaron algo en
   esos segundos -- comun en CMS de noticias, no es un bug nuestro). Esto es lo que permite chequear mas
   seguido sin abusar de los servidores de los medios.
2. **Frecuencia propia por feed**: cada feed puede llevar `"frecuencia_seg"` en `feeds.py` (ninguno lo tiene
   todavia -- no hay historial real para clasificar cuales son "rapidos"/"lentos" con evidencia, se
   preferio dejar el mecanismo listo antes que adivinar). Sin frecuencia propia, un feed se chequea cada
   vez que le toca el tick global.
3. **Tick global bajado de 2 a 1 minuto** (`MONITOR_FEED_MIN`, ahora acepta fracciones -- ej. `0.5` para
   30s): justificado por el punto (b) del diagnostico (pipeline completo mide 10s, hay margen de sobra).
   `python monitor.py` (una corrida unica, sin `serve`) SIEMPRE trae todo fresco (`collect(respetar_frecuencia=False)`)
   -- el "esperar el turno" es solo para el modo continuo.
4. **`history.json` protegido de la mayor frecuencia**: `append_history()` ahora se salta el guardado si no
   pasaron `MONITOR_HIST_MIN` (def. 2, el mismo espaciado de antes) desde el ultimo snapshot -- sin esto,
   bajar el tick a 1 min hubiera duplicado la velocidad de crecimiento del archivo y, con `HIST_MAX` fijo,
   RECORTADO A LA MITAD cuanto tiempo atras llega el historial (justo lo que necesitan la Fase 2 y
   `comparar_periodo` del Asistente).
5. **`latencia_cache.json` (nuevo) + `calcular_latencia_por_feed()`**: registro real de cuando un medio
   publico una nota (segun su feed) vs. cuando el monitor la vio por primera vez (`first_seen`, nunca se
   pisa una vez registrado). Es la materia prima real para medir demora -- antes el proyecto no guardaba
   esto en ningun lado. Expuesto en `data.json["latencia_feeds"]` y en un panel nuevo dentro de
   Estadisticas ("Demora real por medio"). **IMPORTANTE, limitacion metodologica real**: la PRIMERA vez que
   esto corre despues de instalarse, los numeros salen inflados (horas/dias) porque "primera vez que lo
   vimos" incluye TODO el backlog que cada feed ya traia en su ventana de RSS, no solo lo genuinamente
   nuevo -- confirmado en vivo (ej. "Corriere della Sera" salio con una mediana de 816477 min == el backlog
   stale ya documentado arriba). Los numeros se vuelven representativos de la demora REAL recien despues de
   que el sistema lleva un rato corriendo continuo y la mayoria de entradas nuevas en `latencia_cache.json`
   son genuinamente nuevas, no backlog -- por eso la verificacion pide `serve` corriendo 1h+ antes de sacar
   conclusiones (ver Pendientes).
6. **"Última hora" (pestaña nueva)**: lista ordenada SOLO por hora de publicacion (`h.newest`), sin pasar
   por el ranking de interes -- exactamente para el caso (f) de arriba. Su badge (`#uhBadge`) se actualiza
   en CADA poll SIN respetar `usuarioOcupado()` (a proposito, es la pestaña pensada para enterarse rapido) y
   su contenido se refresca solo si esa pestaña esta activa, tambien sin el bloqueo de scroll.
7. **Hora explicita en America/Guayaquil**: `toLocaleString("es-EC")` sin `timeZone` usa la zona del
   SISTEMA del navegador, no necesariamente Ecuador -- `fmtHoraEC()` (nuevo) fuerza
   `timeZone:"America/Guayaquil"` explicito en los dos lugares que mostraban hora absoluta.
8. **Poll mas seguido**: 45s -> 20s (el backend ahora puede publicar cada 1 min en vez de 2, el poll le
   sigue el paso).
9. **Aviso al iPhone por nota nueva de Guayaquil/Ecuador** (`movil.py`, pedido explicito, apagado por
   defecto): `avisos_nota_nueva` en `movil.json` -- a diferencia de "historia fuerte" (exige `min_medios`,
   en la practica casi nunca dispara segun la LIMITACION ya documentada), esto avisa con una sola fuente
   si es reciente (`nota_nueva_max_horas`, def. 1h) y del ambito pedido (`nota_nueva_ambito`, def.
   "guayaquil"), con cupo propio por hora (`nota_nueva_limite_hora`, def. 4) para no bombardear. `test_movil_nota_nueva.py`
   (7 pruebas).
10. **`_escribir_atomico` de verdad** (ver bug real arriba): `data.json`/`dashboard.html` ahora se escriben
    con archivo temporal + `os.replace`.
11. **WebSub/sitemap, investigado, NO implementado**: se probaron 8 feeds ecuatorianos en vivo por un link
    `rel="hub"` (WebSub) -- **ninguno lo ofrece**, la via queda descartada de raiz (ademas de la limitacion
    ya conocida de no tener un endpoint publico para recibir el callback en la PC de Fernando). Como
    hallazgo real aparte: **El Comercio SI tiene un sitemap de noticias real y actualizado**
    (`elcomercio.com/sitemap-news.xml`, HTTP 200, generado con fecha de HOY, fechas ya en hora de Ecuador
    explicita `-05:00`, mas categorias que las que trae el RSS clasificado) -- El Universo y Expreso NO
    tienen el suyo (404/403). Queda anotado como una fuente complementaria real para El Comercio si mas
    adelante hace falta exprimir mas velocidad ahi -- no se integro esta pasada (requiere un parser de
    sitemap aparte del de RSS, mas alcance del que da esta fase).

### Pendientes reales de la Fase 0

1. **La "verificacion con serve 1h+" (tabla antes/despues real) todavia no se puede reportar con numeros
   honestos**: `latencia_feeds` recien empezo a registrar datos en esta misma sesion, y la primera lectura
   esta inflada por el backlog (ver limitacion metodologica arriba). Hace falta dejar `serve` corriendo un
   rato real antes de que los numeros signifiquen "demora de deteccion" en vez de "que tan viejo era el
   backlog". `serve` quedo corriendo al cierre de esta pasada -- revisar `data.json["latencia_feeds"]` en
   una hora o mas para la tabla real.
2. **Ninguna frecuencia (`frecuencia_seg`) esta configurada todavia por feed** -- una vez que
   `latencia_feeds` tenga datos representativos (ver pendiente 1), se puede usar esa evidencia real para
   decidir cuales feeds merecen chequeo mas seguido y cuales pueden espaciarse, en vez de adivinar.
3. **La sección tecnica del dashboard (demora por medio) esta en Estadisticas** (no un lugar aparte) --
   funciona, pero valdria la pena revisar si Fernando prefiere que sea mas visible.
4. Sitemap de El Comercio: hallazgo real, no integrado (ver arriba).
5. **`serve` no se pudo reiniciar de inmediato con el codigo de la Fase 1**: la RAM libre volvio a
   bajar (1.6 GB) justo despues de terminar la Fase 1 -- se dejo corriendo la instancia vieja (sin los
   cambios de Fase 1) en vez de arriesgar otro corte, ver Fase 1 mas abajo para el detalle. Reiniciar
   cuando la memoria de la PC lo permita.

## Fase 1 (2026-09-23/24) — Guayaquil: mas fuentes y mas voz de la gente

### Noticias — resultado medido

- **44 -> 53 feeds configurados**, cada URL probada a mano con `fetch()`+`parse_feed()` real antes de
  agregarla (mismo criterio de siempre). Nuevos: **Extra** (tabloide de Guayaquil -- ya se habia
  descartado con `/feed/`, con `/rss` SI funciona: 58 items reales, fuerte en seguridad/crimen local),
  **RTS** y **TC Television** (canales con sede en Guayaquil), **Municipio de Guayaquil** (con
  `"ciudad":"Guayaquil"`, es literalmente el gobierno de la ciudad), **Prefectura del Guayas**, **ECU
  911**, **Presidencia Ecuador**, y tres busquedas de **Google News RSS** geo-scopeadas (Guayaquil, Duran
  Ecuador, Samborondon) como respaldo pedido explicitamente en la Fase 1 -- 100 items reales cada una.
- **Medido antes/despues, mismo momento, pipeline real completo** (`collect`+`dedup`+`cluster`+
  `build_stories`): **42 -> 90 historias de Guayaquil** (+114%), con agrupamiento real de 2-3 medios por
  historia en varios casos (ej. "Municipio de Guayaquil retira monticulo de cemento..." con El Universo
  (Guayaquil) + Expreso + Municipio de Guayaquil). 43/44 feeds viejos + 9/9 nuevos respondieron OK (solo
  Wambra con su 429 transitorio ya documentado). 20 ejemplos reales revisados a mano, todos genuinamente
  de Guayaquil (inundaciones, seguridad, transito, salud, municipales) -- ver el detalle completo en el
  log de esta sesion si hace falta revisar mas.
- **`detect_city()` ampliado con barrios reales** (evidencia de titulares del dia: Pascuales, Urdesa,
  Isla Trinitaria, Kennedy Norte, Flor de Bastion) -- todas en frase completa o palabras poco comunes,
  mismo cuidado de siempre contra colisiones (`test_detect_city_barrios.py`, 3 pruebas, incluye el caso
  de que "Kennedy" solo NO debe matchear por el riesgo real de JFK/familia Kennedy en prensa
  internacional).
- **BUG REAL encontrado probando las busquedas de Google News en vivo**: buscar "Duran" (el canton junto
  a Guayaquil) trae, entre resultados reales, una nota sobre el futbolista COLOMBIANO Jhon Duran -- nada
  que ver con el canton. "Duran" NO se agrego a `CITIES` por esto (documentado en el codigo con el caso
  real) -- es un apellido comun ademas de un topónimo, deja pasar falsos positivos si se usa como
  termino geografico suelto. Las notas de Google News para "Duran Ecuador" se dejan sin forzar
  `"ciudad":"Guayaquil"` a nivel de feed (a diferencia de las secciones editoriales reales) -- se apoyan
  en la clasificacion geografica normal por texto para autocorregirse.

### Voz de la gente — resultado medido

- **Medido en vivo, busqueda "Guayaquil" ambito guayaquil** (`social.recolectar`): **66 publicaciones**
  reales -- Bluesky 21 personas + 4 medios, Mastodon 7 medios (0 personas en esta muestra puntual),
  YouTube 34 personas + 0 medios, Reddit 0 (bloqueado, ver abajo). **55 de 66 (83%) son de personas**,
  no de medios.
- **Reddit 403, causa real confirmada (no es el User-Agent)**: probado con 3 User-Agent distintos
  (generico, de navegador real, declarado como bot) -- los tres dan el mismo `403 Blocked`. La respuesta
  trae `server-timing: reddit-ct;desc="dn=FT,p=BOG,cs=MISS"` (enrutamiento geografico visible, `p=BOG` =
  Bogota) -- consistente con un bloqueo por IP/geografia o el endurecimiento general de Reddit contra
  scraping no autenticado del `.json` publico, no con headers. **La unica via real es la API oficial con
  OAuth** (gratis, cupo generoso para lectura, pero pide que Fernando cree una app de Reddit -- mismo tipo
  de paso que ya hizo para `MONITOR_YT_KEY`/`MONITOR_FACTCHECK_KEY`) -- no implementado, es una decision
  suya (necesita que el registre la app con su cuenta).
- **YouTube confirmado funcionando bien para Guayaquil**: probado en vivo con `MONITOR_YT_KEY` real,
  busqueda "noticias Guayaquil" -> 12 comentarios reales, el 100% clasificados correctamente como
  "persona" (comentarios de espectadores en videos de Teleamazonas/Ecuavisa/Noticias Mundionline sobre
  seguridad en Guayaquil).
- **Telegram: probados 20 nombres de canal candidatos, 1 real encontrado** ("alertaecuador" -- 10 posts
  reales, alertas de crimen que SI mencionan Guayaquil/Pascuales/Samborondon, aunque es de alcance
  nacional, no exclusivo de Guayaquil, y tenia una publicidad/spam mezclada). **Diagnostico sincero**:
  adivinar nombres de canal tiene una tasa de acierto muy baja (1/20 en esta prueba) -- no hay forma de
  buscar en el directorio de Telegram sin una API propia (Telethon, ya documentado como upgrade futuro NO
  implementado). Confirma lo que ya decia el proyecto: `MONITOR_TG_CANALES` sigue vacio por defecto, la
  mejor fuente de nombres reales de canales de Guayaquil es que Fernando revise los que YA sigue en su
  propio Telegram.
  - **Bug real encontrado de PASO, en el script de prueba propio (no en `social.py`)**: al escribir la
    prueba, concatenar `"ULTIMO ERROR: " + social.last_error` cuando `last_error` seguia en `None`
    (canal sin posts pero sin error real, ej. no existe) tiraba `TypeError`. Confirmado con una
    reproduccion directa que `social.py` en si NO tiene este bug -- devuelve `[]` limpio para un canal
    sin resultados, es responsabilidad del que lo llama chequear `last_error` antes de usarlo. Sin
    cambios de codigo en el proyecto, solo queda anotado por si alguien mas escribe un script de
    diagnostico parecido.
- **OSINT por segmento (tema × ambito), confirmado en vivo funcionando** despues del arreglo de la pasada
  anterior (`SOCIAL_OSINT_RETRY_TTL`): 13 de 15 temas con lectura OSINT real en el momento de revisar,
  cubriendo los 3 ambitos (guayaquil: Carceles/Crimen-Violencia/Policia-Militar/Cultura-Comunidad/Salud/
  otros; ecuador: Asamblea-Leyes/Comercio-Inversion/Fiscal-Presupuesto/Elecciones/Narcotrafico/Precios;
  internacional: Migracion/Impuestos).
- **Redes fuera de alcance, diagnostico sincero (ya investigado en una ronda anterior, reafirmado, sin
  cambios)**: X/Twitter (plan pago Basic desde ~$200 USD/mes), TikTok (Research API gratis pero solo para
  afiliacion academica verificada), Instagram/Facebook (Meta Graph API pide app revisada y aprobada, y en
  la practica solo da datos de paginas propias, no busqueda publica abierta). Ver "Arreglos del
  2026-09-23, segunda tanda, Problema 1" para el detalle completo -- sigue vigente.

### Pendientes reales de la Fase 1

1. Reddit: decision de Fernando si vale la pena registrar una app OAuth (gratis) para tener el pilar real
   en vez de best-effort.
2. Telegram: Fernando revisa sus propios canales seguidos y le pasa nombres reales -- adivinar no
   funciona bien (1/20 de tasa de acierto medida).
3. ~~No se corrio todavia una verificacion en vivo de `serve`~~ -- **resuelto**: la memoria se recupero
   (4.55 GB libres) y se pudo reiniciar `serve` con Fase 0+1+2 juntas. Confirmado con el servidor real:
   **89 historias de Guayaquil** (consistente con las 90 medidas antes con el pipeline directo) y una
   sola instancia limpia corriendo.

## Fase 2 (2026-09-23/24) — Marco de cobertura con datos propios (no GDELT)

- **"Mercado de cobertura" dejo de depender de GDELT**: antes ese panel (dentro de Estadisticas) mostraba
  el volumen de GDELT por categoria -- con GDELT bloqueado la mayor parte del tiempo (documentado en
  varias rondas anteriores), el panel quedaba vacio o con datos parciales enganosos la mayoria de las
  veces. Ahora usa **datos propios**: la suma de `n_articles` (volumen real de articulos ya recolectados
  por el monitor, antes del clustering) por categoria -- siempre disponible, nunca depende de una fuente
  externa. GDELT paso a ser una nota COMPLEMENTARIA debajo del grafico (cuantos temas respondio hoy), sin
  bloquear ni vaciar el panel principal.
- **"Cada sector aparece siempre, aunque tenga cero"**: se encontraron y arreglaron dos lugares del
  dashboard que filtraban en silencio una categoria sin historias (`CAT_ORDER.filter(c=>cnt[c])`) -- el
  panel "Historias por categoria" y el nuevo "Mercado de cobertura" ahora siempre muestran las 5
  categorias fijas (`CATEGORIAS_VALIDAS`/`CAT_ORDER`, la misma lista de siempre, ya compartida entre
  Python y el dashboard), con 0 si no hay nada -- un cero real ahora se ve igual de claro que cualquier
  otro numero, no desaparece.
- **Marco por ambito + evolucion en el tiempo**: `#statseg` (el toggle de Estadisticas) suma un boton
  **Guayaquil** (antes solo Todo/Ecuador/Mundo). `append_history()` ahora guarda, ademas del agregado de
  siempre, `secciones_ambito` (el mismo conteo por categoria pero desglosado Guayaquil/Ecuador-sin-Guayaquil/
  Internacional) y `cobertura` (volumen de articulos, no GDELT) en cada snapshot -- nuevo panel "Evolución
  por categoría" grafica esas 5 categorias en el tiempo, respetando el filtro de ambito activo. Los
  snapshots viejos (de antes de este cambio) no tienen `secciones_ambito` -- el panel lo dice explicitamente
  ("todavia no hay suficiente historial") en vez de graficar con huecos silenciosos; se va a ir llenando
  solo con las pasadas nuevas. `test_fase2_cobertura.py` (4 pruebas, incluye que Guayaquil no se cuenta dos
  veces dentro de "local").
- **BUG REAL, la IA borraba categorias correctas — reproducido en vivo con Ollama real**: el caso ya
  documentado como pendiente ("mineria ilegal en Putumayo", que `themes_for()` clasificaba bien como
  Ambiente pero terminaba en 'otros') se reprodujo llamando a `ia.analizar()` de verdad: el modelo devolvio
  `{"cat": "Policia/Militar", "score": 1.0}` -- una categoria que NO estaba en las que las keywords ya
  habian detectado (`["Ambiente"]`). El candado del codigo (correctamente) descarta "Policia/Militar" por
  no estar en el set permitido, pero como no quedaba NINGUNA categoria en comun, el resultado caia en
  'otros' -- perdiendo una clasificacion valida que la IA nunca dijo explicitamente que estuviera mal
  (score bajo), solo no la reconfirmo. Arreglado: si la interseccion queda vacia, se preserva la
  clasificacion de keywords tal cual en vez de caer en 'otros' -- el candado sigue siendo "la IA solo
  puede QUITAR", pero ahora "no reconfirmar nada" ya no equivale a "vaciar todo".
- **BUG REAL, candado de geografia asimetrico — confirmado y arreglado**: `_apply()` exigia respaldo real
  de texto (`detect_city`/`is_ecuador`) para aceptar que la IA marque "local"/"guayaquil", pero aceptaba
  "internacional" SIN ninguna condicion -- el caso ya documentado ("Estados Unidos intercepta embarcacion
  de Ecuador" quedando Internacional pese a mencionar Ecuador) confirma el patron. Arreglado con el mismo
  criterio en los dos sentidos: `"internacional" in geo and not is_ecuador(texto)` -- si el texto SI
  menciona Ecuador de verdad, "internacional" tampoco se acepta a ciegas, se deja la clasificacion de
  palabras clave. `test_fase2_candado_ia.py` (5 pruebas: los dos casos reales reproducidos + que el
  comportamiento normal/correcto no se rompe en ningun caso).
- **Verificado con un reinicio real de `serve`**: 89 historias de Guayaquil sirviendose en vivo (consistente
  con la medicion directa de la Fase 1), y de las historias locales, solo 2 quedaron en 'otros' en el
  momento de revisar (numero que deberia seguir bajando a medida que el trabajador de fondo re-procese
  historias con el candado ya arreglado).

### Pendientes reales de la Fase 2

1. El marco por Mundo/Ecuador/Guayaquil recien empieza a acumular historial desglosado
   (`secciones_ambito`) desde este reinicio -- el panel de evolucion en el tiempo va a estar vacio/con
   pocos puntos hasta que pasen varias pasadas mas del feed.
2. **No hacia falta limpieza retroactiva de `ia_cache.json`**: `_apply()` se vuelve a correr con el
   candado arreglado cada vez que `get_ia()` lee una historia (incluso en modo_lectura/cache hit) -- el
   arreglo se aplica solo en la siguiente pasada de `run_fast`, sin reprocesar nada con Ollama.

## Fase 3 (2026-09-23/24) — Base de contraste oficial

Modulo nuevo: `oficial.py` (solo stdlib). Dos piezas:

- **Constitucion del Ecuador (2008) indexada por articulo**: fuente real encontrada y probada en vivo
  -- Wikisource (`es.wikisource.org`) tiene el texto completo transcrito, dividido en 9 sub-paginas por
  TITULO (no una sola pagina), con un patron limpio y consistente (`'''Art. N.-''' texto`). Se descarga UNA
  VEZ (`reconstruir_constitucion()`, ~9 llamadas a la API de Wikisource) y se guarda en
  `constitucion.json` -- se reconstruye sola si pasan mas de 180 dias (la Constitucion casi no cambia, pero
  puede haber enmiendas) o si no existe todavia. **300 de ~444 articulos reales indexados** (cobertura
  parcial, no completa -- algunos articulos con formato de wikitexto distinto al patron esperado no se
  detectan; confirmado que los mas citados en la practica SI estan: Art. 1, 66, 83, 424). Se etiqueta
  siempre como "transcripcion verificada, no el PDF oficial escaneado" -- mejor una fuente secundaria
  confiable con esa aclaracion que ninguna.
- **Boletines de instituciones publicas**: 4 fuentes reales con RSS que SI funciona, cada URL probada a
  mano (`fetch()`+parse real): **Asamblea Nacional** (10 items, noticias legislativas reales), **INEC**
  (10 items, boletines estadisticos), **Banco Central del Ecuador** (10 items, cifras economicas reales --
  crecimiento, exportaciones, comercio exterior), **Registro Oficial** (20 items, el boletin legal oficial
  -- por ahora solo el LISTADO de ediciones/suplementos con link, no el contenido de cada PDF). Cacheados en
  `oficial_cache.json` con frecuencia propia bien espaciada (1-6 horas segun la fuente, mucho mas lento que
  las noticias -- estas instituciones publican pocas veces al dia). **Probadas SIN RSS publico en la URL
  obvia** (HTTP 200 pero HTML, no XML): Fiscalia General, Corte Constitucional, Contraloria General, CNE.
  Funcion Judicial dio error de conexion. Documentado en `oficial.py` por si aparece una URL real para
  alguna despues.
- **Integrado**: `monitor.py` construye la Constitucion una vez al arrancar el hilo trabajador (si hace
  falta) y llama a `oficial.actualizar()` en cada pasada de `enrich_pass` (se auto-limita por la
  frecuencia propia de cada fuente, igual que collect() de Fase 0). `data.json["oficial"]` expone que hay
  disponible (honesto: 0 si todavia no se construyo/consulto nada). Dos herramientas NUEVAS del Asistente
  (`herramientas.py`/`agente.py`): `buscar_constitucion(termino)` y `buscar_boletines_oficiales(termino)`
  -- probadas en vivo end-to-end sin necesitar el servidor corriendo. Panel nuevo en Contraste
  (`#oficialEstado`) que muestra la disponibilidad real y como consultarlo desde el Asistente.
  `test_oficial.py` (9 pruebas, sin golpear la red).
- **No implementado esta fase (decision consciente por tiempo)**: integracion PROFUNDA por-nota (ej. que
  cada tarjeta de Contraste muestre automaticamente el articulo constitucional o boletin relacionado) --
  por ahora es una herramienta que el Asistente puede usar cuando se le pregunta, no un cruce automatico
  contra cada historia. Ese cruce automatico es mas del tipo de cosa que pide la Fase 5 (contraste de
  declaraciones con el pasado) -- tiene mas sentido construirlo ahi, con el mismo motor, que duplicarlo
  aca.

### Pendientes reales de la Fase 3

1. Cobertura de la Constitucion parcial (300/~444 articulos) -- revisar el patron de wikitexto de los
   articulos faltantes si se necesita citar alguno que no aparece.
2. Registro Oficial solo trae el LISTADO de ediciones (titulo + link), no el contenido -- para citar un
   articulo de una ley puntual publicada ahi haria falta bajar y parsear el PDF de cada edicion, no
   implementado.
3. Fiscalia/Corte Constitucional/Contraloria/CNE sin RSS encontrado en la URL obvia -- no se probaron
   variantes (ej. `/rss`, sitemaps) por tiempo, a diferencia de lo que si se hizo en la Fase 1 para los
   medios de Guayaquil. Revisar si vale la pena la misma busqueda exhaustiva aca.
4. No se pudo verificar con un reinicio real de `serve` en esta pasada (memoria de la PC volvio a estar
   justa, 1.8 GB libres) -- las herramientas del Asistente SI se probaron end-to-end de forma directa (sin
   el servidor). Reiniciar `serve` cuando la memoria lo permita para confirmar `data.json["oficial"]` y el
   panel de Contraste en vivo. (contrario a lo que se penso al principio):
   `_apply()` se vuelve a correr con el candado arreglado CADA VEZ que `get_ia()` lee una historia, incluso
   en modo_lectura (cache hit) -- lo que se guarda en cache es la respuesta CRUDA de la IA, no el resultado
   ya filtrado. El arreglo se aplica solo, en la siguiente pasada de `run_fast`, a TODAS las historias
   cacheadas de antes, sin reprocesar nada con Ollama. Confirmado que los 2 casos de 'otros' que quedaban
   en la corrida real eran historias sin cache todavia (`interp_v` sin llegar), no un efecto de cache vieja.

## Fase 4 (2026-09-23/24) — Buscador por tema en vivo (Mundo | Ecuador | Guayaquil)

Pestana nueva "Buscar": el usuario escribe un tema y el programa investiga EN VIVO (llamadas reales
nuevas, a diferencia del Asistente de Bloque 2 que solo lee lo que el pipeline ya calculo). Resultados en
3 columnas fijas, nunca mezcladas: Guayaquil | Ecuador | Mundo.

- **`monitor.buscar_en_vivo(query)`** (nuevo, seccion propia antes de `def serve`): orquesta 4 llamadas
  por ambito (12 en total por busqueda):
  - `_buscar_noticias_vivo(query, ambito)`: Google News RSS geo-scopeado
    (`news.google.com/rss/search?q=...&hl=es-419&gl=EC&ceid=EC:es-419`) -- para Guayaquil/Ecuador se le
    agrega el nombre del lugar al termino (`"clima Guayaquil"`, `"clima Ecuador"`), para Mundo va el
    termino solo. Reusa `fetch()`/`parse_feed()` de siempre, asi que hereda el cache condicional
    (ETag/If-Modified-Since) de la Fase 0 sin codigo nuevo.
  - `_buscar_gente_vivo(query, ambito)`: reusa `social.recolectar()` + `_social_query`/
    `_post_es_foraneo`/`_social_score` (el MISMO mecanismo que ya arma el pulso social por tema, Parte A) --
    nada de codigo social nuevo, solo un termino de busqueda ad-hoc en vez de uno del catalogo fijo de 20
    temas.
  - `_buscar_interes_vivo(query)`: Google Trends con respaldo Wikipedia, mismo patron que `get_demand()`.
  - `_buscar_contraste_vivo(query)`: `oficial.buscar_constitucion()` + `oficial.buscar_oficial()` (Fase 3)
    + `sercop.buscar(query, limit=5)` -- **solo para Guayaquil/Ecuador**, Mundo nunca consulta contraste
    oficial ecuatoriano (no tiene sentido para un tema sin relacion con Ecuador).
  - Cada busqueda se persiste en `busquedas.json` (`_guardar_busqueda`, recorte a `BUSQUEDAS_MAX`=50, mismo
    patron atomico que `saved.json`/`notas.json`) para poder reabrirla despues y comparar en el tiempo --
    agregado a `RUTAS_MOVIL`.

- **BUG REAL encontrado escribiendo `_buscar_interes_vivo`** (firma de funcion asumida mal, no un bug de
  las funciones en si): se asumio que `trends.interest_over_time([query])` devuelve una tupla de 3
  `(vals, tend, tstat)` -- en realidad devuelve un DICCIONARIO `{termino: {"avg","series","times"}}` (una
  entrada por termino pedido, no una tupla posicional). Mismo error con `wiki.interest(query)`: se asumio
  que toma un string, en realidad pide un DICCIONARIO `{tema: termino}` (mapea nombre de tema a termino de
  busqueda, para poder pedir varios temas con nombres distintos a la vez). Encontrado en vivo: la primera
  version devolvia `interes=None` para los 3 ambitos sin ningun error visible; una llamada de depuracion
  directa broto `ValueError: not enough values to unpack (expected 3, got 1)`, lo que llevo a revisar la
  firma real con grep+lectura del codigo de `trends.py`/`wiki.py` en vez de seguir asumiendo. Corregido y
  verificado en vivo: `_buscar_interes_vivo("prueba")` devuelve `{'fuente': 'Google Trends', 'valor': 18,
  'serie': [...]}` con datos reales.

- **Dashboard** (`dashboard_template.html`): `#secBuscar` nueva (input + boton "Investigar", resultado en 3
  columnas via `buscarColumnaHTML()`/`renderResultadoBusqueda()`, historial de busquedas previas
  clickeable via `cargarHistorialBusquedas()`). Cada columna muestra Noticias / 🗣 Lo que dice la gente /
  📈 Interes / ⚖️ Contraste oficial (esta ultima ausente en Mundo, mismo criterio del backend); si un
  segmento no tiene resultados, dice explicitamente "Sin resultados/Sin noticias/Sin conversacion
  captada/Sin dato de interes/Sin contraste oficial relacionado" en vez de desaparecer en silencio (misma
  regla de honestidad que el resto del proyecto).

- **"Leer con el Asistente" (lectura streameada con fuentes citadas)**: boton aparte debajo de las 3
  columnas (`#buscarLeerBtn`), NO automatico -- el pedido original decia explicitamente que puede "llegar
  despues, por streaming, sin frenar lo demas", asi que las 3 columnas con datos crudos aparecen primero
  (15-25s) y la sintesis del modelo pesado (1-2 min mas) es opcional, a pedido.
  - `agente.py`: se extrajo `_responder_final_stream(pregunta, material, historial, on_delta,
    forzado_final="", timeout=220)` como funcion compartida (mismo cuerpo que ya tenia
    `responder_stream()` para el Asistente de Bloque 2, ahora generica sobre el `material`).
    `responder_stream()` (Asistente) sigue igual por fuera, solo delega a este helper. Nuevo
    `_fmt_material_busqueda(ambitos)` (formatea el resultado de `buscar_en_vivo()` en bloques de texto
    legibles por ambito: noticias/gente/interes/contraste) y `leer_busqueda_stream(query, ambitos,
    on_delta, timeout=220)` (arma el material con lo anterior, una pregunta de sintesis, y llama al mismo
    `_responder_final_stream` -- mismo modelo pesado `monitor-critico` que el chat "profundo"/Asistente,
    sin ciclo de herramientas: el material ya esta armado de antemano, no hace falta que decida que
    consultar).
  - `monitor.py`: ruta nueva `POST /api/buscar_leer` (recibe `{"query", "ambitos"}` -- el NAVEGADOR le
    manda de vuelta lo que `/api/buscar` ya le dio, no se vuelve a buscar nada de red) ->
    `_responder_buscar_leer_stream()`, mismo protocolo NDJSON que `/api/chat`/`/api/asistente`
    (`{"delta":...}` por token, `{"done":true,"ok":...}` al final). Antes de streamear, chequea
    `ia.disponible(IA_MODEL)` y devuelve un error JSON claro si Ollama no responde, en vez de abrir un
    stream vacio.
  - JS (`dashboard_template.html`): `leerBusquedaConAsistente()`, mismo patron `getReader()`/
    `TextDecoder()` que ya usa el chat de Parte E y el Asistente de Bloque 2 -- la respuesta se llena en
    vivo, token a token, dentro de `#buscarLeerOut`.

- **Pruebas**: `test_fase4_buscador.py` (7 pruebas, sin golpear la red real -- `fetch()`/`social.recolectar`
  reemplazados por versiones sinteticas): los 3 ambitos siempre presentes en el resultado; cada ambito trae
  noticias de su propia busqueda geo-scopeada; Mundo nunca consulta contraste oficial; se guarda en
  `busquedas.json`; las busquedas se acumulan para comparar despues; se recorta a `BUSQUEDAS_MAX`; la URL
  de noticias lleva el lugar para Ecuador/Guayaquil pero no para Mundo. 74.9s de tiempo real (algunas
  llamadas de red no mockeadas, ej. resolucion DNS de dominios reales aunque `fetch` este reemplazado) --
  mas lento que el resto de la suite pero sin fallos.

### Pendientes reales de la Fase 4

1. **No verificado en vivo con `serve` corriendo** (solo con pruebas unitarias + syntax-check): falta
   reiniciar el servidor real, escribir un tema real en la pestana Buscar, y confirmar en vivo que las 3
   columnas traen datos reales y que "Leer con el Asistente" produce una sintesis razonable con Ollama
   corriendo -- mismo estandar de verificacion que el resto del proyecto (memoria de la PC estuvo muy justa
   en el momento de escribir esta seccion, ver "Regla de oro" arriba: no reiniciar sin espacio).
2. El boton "Leer con el Asistente" no se probo con Ollama real todavia -- igual que paso con el veredicto
   de Contraste (Problema 4) y el evento de contexto (Problema 6) en sesiones anteriores, el *wiring* esta
   probado de punta a punta pero la CALIDAD del texto que redacta el modelo con este material especifico
   (3 ambitos, 4 tipos de dato cada uno) no se vio todavia con un caso real.
3. `_buscar_gente_vivo`/`_buscar_noticias_vivo` no tienen limite de frecuencia propio mas alla del que ya
   trae `fetch()` (cache condicional) y `social.recolectar()` (sus propios filtros de ruido/recencia) --
   si Fernando busca el mismo tema muy seguido, cada busqueda SI dispara llamadas de red reales nuevas
   (es el comportamiento pedido explicitamente: "a diferencia de las herramientas del Asistente, que solo
   leen cache"), pero no hay un enfriamiento minimo entre dos busquedas IDENTICAS seguidas -- si en el uso
   real esto genera 429s notorios, agregar un TTL corto (ej. 2-3 min) por termino exacto es la palanca
   obvia.

## Fase 5 (2026-09-23/24) — Contraste de declaraciones con el pasado

Modulo nuevo: `declaraciones.py` (solo stdlib, sin importar monitor.py -- mismo criterio que `oficial.py`
para evitar import circular). Registro de declaraciones ATRIBUIDAS (quien, cargo, que dijo, fecha, medio)
extraidas de las notas -- `declaraciones.json`, que **NUNCA se purga por MONITOR_MAX_DIAS** (a diferencia
de las historias del feed, que caducan a los pocos dias): el objetivo es poder comparar lo que un actor
dice HOY contra lo que dijo hace semanas o meses, aunque esa nota vieja ya haya salido de `data.json`.

- **Extraccion** (`ia.extraer_declaracion`, modelo RAPIDO del pipeline): lee titular+resumen y devuelve
  `{"actor","cargo","texto"}` SOLO si la nota atribuye explicitamente una declaracion/anuncio/promesa a
  una persona con nombre (candado en el prompt: "NO inventes un actor ni fuerces una declaracion que el
  texto no tiene"). Corre en `monitor.get_declaraciones()` (hilo trabajador, `MONITOR_DECL_MAX`=6 historias
  nuevas por pasada) y registra el resultado con `decl.registrar()`.
- **Filtro barato, sin IA** (`declaraciones.candidatos_contradiccion`): antes de gastar la llamada cara al
  modelo pesado, el CODIGO decide que comparar -- mismo actor (clave normalizada) + 2 o mas palabras
  significativas en comun (>=4 letras, sin stopwords) + fecha ESTRICTAMENTE anterior (orden temporal real:
  la declaracion nueva se contrasta contra lo que se dijo ANTES, nunca al reves). Sin este filtro, dos
  declaraciones del mismo actor sobre temas totalmente distintos pasarian igual al modelo caro.
- **Comparacion con el modelo PESADO** (`ia.comparar_declaraciones`, `monitor-critico` via
  `elegir_modelo_chat()`, mismo patron que `interpretar()`/chat "profundo": num_predict/timeout suben si el
  modelo resuelto no es el rapido del pipeline, para evitar el bug ya conocido de un modelo de razonamiento
  devolviendo string vacio por gastar el presupuesto "pensando"). Solo se llama sobre los candidatos que ya
  pasaron el filtro barato, acotado a `MONITOR_DECL_CONTRASTE_MAX`=3 comparaciones por pasada (¡~100s cada
  una!) y cacheado por PAR (actor+link_nuevo+link_viejo) en `declaraciones_contraste_cache.json` para no
  repetir la llamada cara en cada pasada del trabajador.
- **Candado en CODIGO, nunca "falso"**: `estado` solo puede ser `posible_contradiccion`/`consistente`/
  `sin_relacion` -- si el modelo responde otra cosa (ej. "falso"), se recorta a `sin_relacion` (el mas
  seguro, ninguna acusacion). El dashboard SIEMPRE muestra una `posible_contradiccion` como "⚠️ POSIBLE
  CONTRADICCIÓN — verificar" (nunca como un hecho confirmado) -- la calificacion final es de Fernando, no
  del programa. `consistente`/`sin_relacion` no se le muestran como si fueran un hallazgo (ruido
  innecesario): solo `posible_contradiccion` llega a `s["contradiccion_declaracion"]`.
- **Cache re-aplicable por link** (`_por_historia` dentro de `declaraciones_contraste_cache.json`), mismo
  patron que `get_veredicto`/`get_contexto`: `run_fast` reconstruye `stories` DESDE CERO en cada pasada
  (nuevos objetos Python desde `build_stories()`), asi que sin este re-pegado por link lo que el trabajador
  calculo se perderia en la siguiente pasada del hilo rapido. `modo_lectura=True` (hilo rapido) SOLO relee
  este cache, nunca llama a Ollama.
- **BUG REAL propio, encontrado durante esta misma pasada (antes de correr ninguna prueba)**: la variable
  local `dstatus` ya estaba en uso en `run_once()`/`run_fast()` para el estado de Trends/demanda
  (`demand, tend, dstatus, fuente = get_demand(...)`) -- la primera version de este cambio reutilizo el
  mismo nombre para el estado de declaraciones, PISANDO el status de Trends antes de que `write_outputs()`
  lo recibiera (`print("Interes/busquedas: %s" % dstatus)` hubiera mostrado el estado de declaraciones en
  vez del de Trends). Encontrado por grep antes de correr nada (no en produccion): se renombro la variable
  de declaraciones a `declstatus` en `run_once`/`run_fast`, y se paso a `write_outputs()` como el nuevo
  parametro `dstatus=declstatus` (el nombre del PARAMETRO de la funcion sigue siendo `dstatus`, pero eso no
  colisiona con nada al ser keyword-only en la llamada). Mismo tipo de error de nombres que ya paso una vez
  en el proyecto (aunque nunca llego a produccion esta vez) -- vale la pena revisar nombres de variables
  compartidos entre funciones largas como `run_once`/`run_fast` antes de reusar uno.
- **Herramienta nueva para el Asistente** (`herramientas.buscar_declaraciones(actor)`, Bloque 2): solo
  lectura, nunca dispara una consulta nueva -- lee `declaraciones.json` via `decl.de_actor()`. Registrada en
  `agente._PROMPT_DECISION` junto a las demas herramientas, para preguntas del tipo "¿el ministro se
  contradijo sobre X?".
- **Dashboard**: `renderDeclaracion(h)` (dashboard_template.html) muestra "🗣 Declaración" (actor, cargo,
  texto, fecha, medio) dentro de `contrasteCardHTML()`, justo despues de `renderContexto()`; si hay
  contradicciones, cada una aparece como un bloque separado con borde rojo "⚠️ POSIBLE CONTRADICCIÓN —
  verificar" citando el texto de la declaracion anterior completo (fecha + medio) para que Fernando pueda
  verificar el par con sus propios ojos, no solo confiar en el veredicto del modelo. El panel de Contraste
  (`#oficialEstado`) ahora tambien muestra cuantos actores/declaraciones hay registrados en total.
- **Pruebas**: `test_fase5_declaraciones.py` (24 pruebas, sin golpear Ollama -- Ollama no estaba disponible
  de forma confiable en el entorno de esta sesion, mismo criterio que ya se uso para los Problemas 4 y 6 en
  sesiones anteriores). Tres capas: `declaraciones.py` en aislamiento (registro, dedup por link,
  normalizacion de actor, filtro barato con sus 3 condiciones -- mismo actor, 2+ palabras, fecha anterior --,
  nunca se purga por fecha vieja, recorte a `MAX_POR_ACTOR`); `ia.py` con `_post` mockeado (extraccion
  devuelve `None` sin atribucion clara, resuelve el modelo pesado por defecto con num_predict/timeout
  correctos, el candado de vocabulario fijo nunca deja pasar "falso"); y el *wiring* completo en
  `monitor.get_declaraciones()` con **10 casos realistas** (pedido explicito de Fernando: "probar con 10
  casos reales antes de integrarlo") cubriendo contradiccion real detectada, sin_relacion filtrado antes de
  llegar al modelo caro, consistente registrado pero no mostrado como hallazgo, actores distintos que nunca
  se comparan entre si, nota sin atribucion que no registra nada, actor nuevo sin historial que no gasta
  una llamada al modelo pesado, declaracion con fecha igual que no cuenta como "anterior", normalizacion de
  actor pese a variacion de espacios/mayusculas, el limite `MONITOR_DECL_MAX` respetado entre historias de
  la misma pasada, y el cache por PAR reutilizandose entre dos pasadas sobre la misma historia sin volver a
  llamar a Ollama -- mas una prueba aparte de `modo_lectura=True` reaplicando desde el cache por link sobre
  un objeto `stories` reconstruido de cero (el escenario real de `run_fast`).

### Pendientes reales de la Fase 5

1. **Los 10 casos de prueba son sinteticos-pero-realistas, con Ollama mockeado** -- no se corrio ni un solo
   caso con Ollama real en esta pasada (mismo estado que quedo Problema 4/6 en sesiones anteriores: el
   *wiring* esta probado de punta a punta, la CALIDAD del juicio del modelo pesado sobre un caso real
   ecuatoriano todavia no se vio). Correr con Ollama activo, revisar unos cuantos veredictos a mano, es el
   siguiente paso antes de confiar en el texto que redacta el modelo para un caso real.
2. **No verificado en vivo con `serve` corriendo** -- falta un reinicio real del servidor con este codigo
   (memoria de la PC estuvo justa durante esta sesion, ver Fase 4). Cuando haya margen, reiniciar y
   confirmar en `data.json` que `declaraciones_estado`/`s.declaracion`/`s.contradiccion_declaracion` llegan
   bien al dashboard, y que el panel de Contraste los muestra como se diseño.
3. **Filtro barato es solo por palabras compartidas, no por tema real**: dos declaraciones del mismo actor
   sobre temas *distintos* pero que casualmente comparten 2 palabras largas (ej. dos notas que mencionan
   "gobierno" y "nacional" sin relacion real) podrian pasar el filtro barato y llegar al modelo pesado sin
   necesidad -- no es grave (el modelo pesado igual puede responder `sin_relacion`, y el codigo ya descarta
   ese caso de la UI), pero SI gasta una llamada cara de ~100s en vano. Si en uso real esto pasa seguido,
   subir el minimo de palabras compartidas (hoy 2) es la palanca obvia.
4. **`MONITOR_DECL_MAX`/`MONITOR_DECL_CONTRASTE_MAX` (6/3 por defecto) no se midieron en una pasada real del
   trabajador junto al resto de Parte C** (IA/contexto/FactCheck/veredicto/social ya compiten por el mismo
   modelo/GPU) -- si esto atrasa perceptiblemente al resto del trabajador, bajar estos valores via variable
   de entorno es la palanca, mismo criterio que ya se uso para `MONITOR_IA_INTERP_MAX`.
5. **El registro de declaraciones no tiene limite de tamaño total en disco** (solo `MAX_POR_ACTOR`=40 y
   `MAX_TOTAL_ACTORES`=500 actores DISTINTOS) -- con uso real prolongado (meses), vale la pena revisar el
   tamaño real de `declaraciones.json` y si esos limites siguen siendo razonables.

## Fase 6 (2026-09-23/24) — Pendientes del Asistente (Bloque 2)

Tres pendientes que habian quedado anotados al cerrar el Bloque 2 en la sesion del 23/9: falta una
herramienta de "angulos de reportaje", el material que se le manda al modelo trae campos crudos sin
filtrar, y no se habia probado el ciclo de herramientas con una pregunta que necesite varias rondas.

- **`herramientas.angulos_reportaje(ambito=None, limite=8)`** (nueva): cruza demanda de busqueda/pulso
  social vs. cobertura de medios -- la MISMA logica que ya usa el panel Oportunidades del dashboard
  (`renderGap()`), portada a Python para que el Asistente pueda responder "que angulo de reportaje me
  recomendarias" cruzando el dato el mismo en vez de inferirlo llamando `tendencia_tema` tema por tema (lo
  que hacia que la pregunta 3 de la prueba original del Bloque 2 saliera generica). Registrada en
  `agente._PROMPT_DECISION` junto al resto de herramientas.
- **Filtro de campos crudos antes de armar el material** (`herramientas._resumen_historia`/
  `detalle_historia`): un `veredicto.estado=="pendiente"` (o `"Todavia no procesado"`) y un
  `contexto.texto=="sin contexto disponible"` ya no llegan al material -- antes el modelo los citaba casi
  textual en la respuesta final como si fueran informacion real (pendiente anotado explicitamente en el
  cierre del Bloque 2). Ahora esos campos salen como `None` cuando no tienen valor real, y el modelo (que ya
  sabe distinguir "dato" de "sin dato" por el resto del prompt) no tiene un string vacio con apariencia de
  dato para citar.
- **Ciclo de varias rondas encadenadas, probado**: `test_fase6_asistente.py` (`TestCicloVariasRondas`)
  scriptea con `ia._post` mockeado una secuencia de 4 consultas DISTINTAS (`buscar_historias` ->
  `tendencia_tema` -> `comparar_periodo` -> `buscar_guardadas`) y confirma que `ciclo_herramientas()` las
  corre TODAS sin cortarse de mas por el chequeo de repeticion (`vistos`); por separado confirma que SI
  corta cuando el modelo repite la misma consulta con los mismos argumentos, y que nunca supera
  `max_rondas` aunque el modelo pida seguir consultando indefinidamente.
- **Pruebas**: `test_fase6_asistente.py` (11 pruebas): `angulos_reportaje` (brecha maxima cuando hay
  demanda alta y cero cobertura, lista vacia honesta con `nota` cuando no hay ninguna señal esta corrida,
  filtro por ambito local/internacional, notas ya publicadas incluidas para citar); filtro de campos crudos
  (`veredicto`/`contexto` genericos se omiten, los reales se conservan, en `buscar_historias` y
  `detalle_historia`); ciclo de varias rondas (las 3 pruebas de arriba).
- **VERIFICADO EN VIVO, con Ollama real corriendo** (a diferencia de las Fases 4/5, que quedaron con el
  *wiring* probado pero sin Ollama disponible en esa sesion -- esta vez SI estaba corriendo, se aprovecho
  para probar de punta a punta):
  - Se reinicio `python monitor.py serve` con TODO el codigo de las Fases 0 a 6 junto (se encontro un
    servidor viejo de la sesion anterior sirviendo desde antes de Fase 3/4/5 -- se detuvo y se levanto uno
    nuevo). Bindeo el puerto en <15s. `data.json` confirmo en vivo: `oficial` con la Constitucion indexada
    (300 articulos) y 4 fuentes de boletines en cache (Fase 3); `estado_declaraciones: "cache (0/1089)"`
    honesto (el registro recien arranca, ver Fase 5).
  - **`/api/buscar` (Fase 4) probado con una consulta real** ("seguridad"): trajo 12 noticias + 10
    publicaciones sociales por cada uno de los 3 ambitos (Guayaquil/Ecuador/Mundo), e interes real de
    Wikipedia para Ecuador (159/100) -- Guayaquil/Mundo sin dato de interes esa corrida, mostrado
    honestamente como `None` en vez de inventar un numero.
  - **`/api/buscar_leer` (Fase 4, lectura streameada) probado en vivo con Ollama real**: los tokens
    llegaron de a uno por NDJSON (confirmado con `curl -N`), citando una fuente REAL de los resultados de
    busqueda ("En Guayaquil, según un reportaje de El Universo, se investiga un presunto plan terrorista
    que involucraría explosivos yihadistas...") -- exactamente el patron de "grounding" pedido (cita la
    fuente real, no inventa). La respuesta completa tarda mas de 200s (timeout de la prueba cortó la
    conexion a mitad de generar, no un error del servidor -- el mismo patron de tiempo ya documentado para
    el chat "profundo"/Asistente con `monitor-critico`).
  - **`/api/asistente` con la pregunta real** "¿Qué ángulo de reportaje me recomendarías esta semana, con
    qué fuentes empezar?" -- intentada DOS veces, ninguna llego a completarse (ver "Corte por memoria" mas
    abajo). No confirmado en vivo esta pasada.

- **Corte por memoria, a mitad de esta verificacion (fuera de nuestro control)**: mientras se esperaba la
  respuesta del Asistente, el propio harness detuvo `serve` (y con el la consulta al Asistente que
  dependia de el) por presion critica de memoria del sistema -- **no** un fallo del codigo ni de la
  llamada en si. Confirmado con PowerShell inmediatamente despues: la RAM libre habia bajado a ~2.2GB en
  el momento de arrancar estas pruebas (ya se sabia que estaba justa, documentado en Fases 3/4/5) y
  correr DOS llamadas pesadas seguidas a Ollama (`/api/buscar_leer` + `/api/asistente`, cada una carga un
  modelo de ~8B) probablemente la termino de ajustar. Tras el corte, la RAM libre subio sola a 6.16GB
  (confirma que el corte fue real por presion, no una casualidad). Por instruccion explicita del entorno,
  **no se reinicio `serve` de nuevo esta pasada** -- queda apagado hasta que Fernando lo pida.

### Pendientes reales de la Fase 6

1. **`serve` quedo APAGADO al cierre de esta sesion** (detenido por presion de memoria mientras se
   verificaba en vivo, ver arriba) -- Fernando tiene que arrancarlo de nuevo el mismo (`python monitor.py
   serve`, o `INICIAR.bat`) para seguir usando el dashboard. Todo el codigo de las Fases 0 a 6 ya esta
   guardado en los archivos, no se pierde nada al reiniciar.
2. **La lectura del Asistente (`/api/buscar_leer`) SI se confirmo funcionando en vivo** (streaming real,
   citando una fuente real de los resultados de busqueda) antes del corte -- eso ya quedo verificado. Lo
   que NO se alcanzo a confirmar fue la respuesta COMPLETA de `/api/asistente` con la herramienta nueva
   `angulos_reportaje` (dos intentos, ambos cortados por el problema de memoria antes de que llegara ni un
   solo token) -- probarlo de nuevo es lo primero que vale la pena hacer la proxima vez que se abra el
   proyecto con memoria de sobra.
3. **Registro de declaraciones (Fase 5) seguia en 0 actores al momento del corte** (~10 minutos de
   `serve` corriendo, compitiendo por el modelo con las pruebas manuales de este mismo cierre) -- no es un
   bug, es simplemente que el trabajador no llego a acumular suficientes pasadas; debería empezar a verse
   contenido real despues de que `serve` corra un rato sin pruebas manuales pesadas compitiendo por
   Ollama.
4. **Solo se probo 1 pregunta en vivo del catalogo de 10 del Bloque 2** (mas la de angulos_reportaje, sin
   completar) -- las demas (2, y 5 a 10 de la lista original) siguen sin probarse con Ollama real; quedan
   listas para que Fernando las corra el mismo desde la pestaña Asistente.
5. **El filtro de campos crudos es solo para `veredicto`/`contexto`** -- no se reviso si `_fmt_transcripcion`
   (agente.py, arma la transcripcion de herramientas consultadas) tiene otros campos igual de crudos en el
   material de OTRAS herramientas (ej. `tendencia_tema`/`comparar_periodo` con campos `None` que el modelo
   podria malinterpretar) -- revisar si aparece el mismo patron en uso real prolongado.
6. **Leccion para la proxima sesion en esta PC**: con la memoria tan ajustada, evitar correr dos llamadas
   pesadas a Ollama EN PARALELO/seguidas durante una verificacion en vivo -- mejor una por vez, con margen
   entre cada una, para no forzar al harness a cortar `serve` a mitad de una prueba.

## Navegación (Fase 7, 2026-09-24) — reorganización en DOS PRODUCTOS: Dashboard + Asistente

Pedido de Fernando: dejar de tener todo apilado en pestañas horizontales y separar el programa en dos
espacios de verdad — **Dashboard** (todo lo de siempre: Noticias, Última hora, Pulso social, Estadísticas,
Oportunidades, Contraste, Guardadas y notas, Buscar — misma navegación interna horizontal de siempre,
sin cambios de comportamiento) y **Asistente** (un espacio de trabajo aparte, ya no una pestaña más, que en
los próximos pasos se convierte en el gestor de "casos" descrito abajo). Esto es el **Paso A** de esa
reorganización (Pasos B-E, el modelo de casos en sí, van en la sección "Asistente de casos" más abajo).

- **Barra lateral fija** (`#sidebar`, dos botones `data-prod="dashboard"`/`data-prod="asistente"`) en
  escritorio, con un botón ☰ (`#sidebarToggle`) que la pliega a solo íconos (`.sidebar.collapsed`,
  preferencia guardada en `localStorage["sidebarColapsada"]` — es una conveniencia de ESTE navegador, no
  algo que necesite viajar entre dispositivos, mismo criterio ya usado para `chatModo`/`modoGuardado`).
- **En el celular** (`@media max-width:800px`, mismo umbral amplio que el resto del dashboard para pantallas
  chicas — el breakpoint viejo de 600px seguía usándose para ajustes finos de la vista Noticias, sin tocar)
  la barra lateral se oculta entera y aparece `#mobileBar`: un botón compacto arriba de todo
  (`#mobileMenuBtn`, muestra el producto activo) que al tocarlo despliega un menú (`#mobileMenu`) con los
  dos productos — se cierra solo al elegir uno o al tocar fuera. Antes de este cambio ya se probó en el
  iPhone de Fernando por Tailscale (ver "Capa móvil" más arriba); este menú usa el mismo criterio de no
  romper esa vía: mismo servidor, mismo puerto, nada nuevo que dependa de red.
- **El producto abierto se recuerda en la URL** (`#dashboard` / `#asistente`, `location.hash`) — al
  recargar la página (F5, o volver a abrir el link guardado en el celular) no vuelve siempre al Dashboard.
  `showProducto()`/`productoFromHash()` en `dashboard_template.html`; sin hash, por defecto es Dashboard.
  Los sub-tabs DENTRO de cada producto (ej. qué pestaña de Noticias/Estadísticas está abierta) siguen sin
  persistir en la URL — no fue parte de este pedido, y agregarlo es una mejora aparte si hace falta después.
- **Se sacó la pestaña "Asistente" de la navegación interna del Dashboard** (`#mainnav` ya no tiene
  `data-sec="asistente"`, y `showSection()`/`renderAll()` ya no la mencionan) y su contenido — el chat de
  Bloque 2 que consulta feed/Guardadas/notas/demanda/GDELT/pulso social/SERCOP con ciclo de herramientas —
  se movió tal cual a `#productAsistente` (la lógica de `renderAsistente()`/el `POST /api/asistente` no
  cambiaron, solo dónde vive el HTML que los usa). Esto es exactamente lo que pedía el Paso A: "lo que
  sirva de ella pásalo al nuevo apartado" — nada de esto se descartó porque el Asistente de casos (Pasos
  B-E) lo va a seguir necesitando como base del chat.
- **El resto del Dashboard no se tocó de comportamiento**, solo de contenedor: todas las secciones
  (`secNoticias`...`secBuscar`) y su JS (`showSection`, filtros, paginación, modal de detalle, chat
  flotante por item, poll de `data.json` cada 20s sin interrumpir lectura) quedaron exactamente igual,
  ahora dentro de `#productDashboard` en vez de directo en `<body>`.
- **Verificado con un reinicio real de `serve`** (no solo sintaxis): se confirmó que no había ninguna
  instancia de `monitor.py` corriendo (`serve` había quedado apagado al cierre de la sesión anterior por
  presión de memoria, ver Fase 6), se arrancó una instancia real (`python monitor.py serve`, con RAM
  libre de sobra, 4.7GB), bindeó el puerto y sirvió `data.json` con 1160 historias reales. Se pidió
  `http://127.0.0.1:8000/dashboard.html` (no `/` — **hallazgo real de paso**: la raíz `/` del servidor
  devuelve el LISTADO del directorio, no el dashboard; el link correcto para abrir a mano siempre fue
  `/dashboard.html`, esto no cambió con este trabajo, solo se confirmó mientras se verificaba) y se
  confirmó por HTTP real (no solo mirando el archivo en disco) que la página servida trae la barra
  lateral nueva, los dos contenedores de producto y el toggle del celular. Se paró la instancia de
  verificación al terminar (ver Pendientes) para no dejarla corriendo sin que Fernando lo pidiera.
- **`node --check` sobre el `<script>` inline** (mismo patrón de verificación ya usado en Problema 4/6 de
  sesiones anteriores) confirmó que no se rompió la sintaxis del JS con los cambios de rutas/sidebar.
- **No implementado en este paso, a propósito**: el contenido real del Asistente de casos (lista de
  casos, documentos, entidades, tablero) — ver "Asistente de casos" más abajo, son los Pasos B-E.

### Cómo probarlo
1. Arrancar el Monitor como siempre: `python monitor.py serve` (o doble clic en `INICIAR.bat`).
2. Abrir `http://localhost:8000/dashboard.html` (o el link de Tailscale de siempre desde el iPhone).
3. Deberías ver una barra angosta a la izquierda con dos botones: 📊 Dashboard y 🧭 Asistente. Con
   Dashboard activo (por defecto), Noticias/Estadísticas/Oportunidades/etc. se ven y se navegan
   EXACTAMENTE igual que antes (mismos filtros, mismo refresco cada 20s, mismo chat flotante por noticia).
4. Click en 🧭 Asistente: cambia a un espacio separado con el chat de preguntas sobre tus datos (el mismo
   que antes estaba como pestaña). La URL debería mostrar `#asistente` — si recargás la página ahí, se
   queda en Asistente en vez de volver a Dashboard.
5. Click en el botón ☰ arriba de la barra lateral: la pliega a solo íconos (probalo, y recargá la página —
   debería recordar que la dejaste plegada).
6. En el celular (o achicando la ventana del navegador a menos de ~800px): la barra lateral desaparece y
   aparece un botón arriba con el producto actual — tocalo para ver el menú desplegable con las dos
   opciones.

## Asistente de casos (Fase 7, Pasos B-E) — implementado 2026-09-24

Los 5 pasos (A→E) del pedido de Fernando: convertir "Asistente" en un espacio de trabajo por reportaje
("caso") — documentos propios, entidades a seguir, avisos automáticos cuando el Dashboard menciona algo
de un caso abierto, notas, un chat que cita sus fuentes, y un tablero (solo el esquema de datos en esta
fase, sin interfaz visual todavía — pedido explícito). Trabajado en orden, confirmando cada paso con
Fernando; al llegar a B/C, dos decisiones que su propio pedido dejaba abiertas se resolvieron con él antes
de escribir código: **sqlite3** (no JSON plano) para el índice de fragmentos, y **pypdf** (no `pdftotext`)
para leer PDF — la única librería no-stdlib de todo el proyecto, pre-autorizada explícitamente por él en
el pedido original (instalada con `pip install pypdf`, versión 6.19.0 al momento de escribir esto).

Módulo nuevo: `casos.py` — standalone (nunca importa monitor.py, mismo criterio que oficial.py/
declaraciones.py; sí importa ia.py directamente para pedir embeddings y redactar sugerencias, sin riesgo
de ciclo porque ia.py tampoco importa monitor.py). Una subcarpeta por caso en `casos/<caso_id>/`:
`caso.json` (id/titulo/descripcion/fecha_creacion/entidades[]), `docs/` (los archivos originales),
`index.sqlite3` (fragmentos + su embedding, ver más abajo), `docs_estado.json` (progreso de ingesta por
documento), `avisos.json`, `notas.json`, `evidencia.json` (noticias/contratos guardados desde el
Dashboard) y `tablero.json` (`{"nodos":[], "conexiones":[{"id","origen","destino","tipo","estado":
"sugerida"|"verificada","fuente","ts"}]}`). `casos/` (como `saved.json`/`notas.json`) es contenido real de
Fernando, no un caché — nunca se borra/reconstruye solo. `CASOS_DIR` es aislable en pruebas (los tests
lo apuntan a un tmpdir, nunca tocan la carpeta `casos/` real).

### Paso B — modelo de datos
CRUD completo en `casos.py` (`crear_caso`/`listar_casos`/`cargar_caso`/`guardar_caso`/`borrar_caso`,
`agregar_entidad`/`quitar_entidad`/`entidades_y_alias`, avisos/notas/evidencia/tablero con sus getters +
setters). Todo con el mismo patrón atómico (`archivo.tmp` + `os.replace`) que `saved.json`/`notas.json` en
monitor.py. `hoy_en_casos(limite=50)`: junta los avisos de TODOS los casos, más nuevo primero, con el
título del caso al que pertenece cada uno — la vista "Hoy en mis casos" del pedido (sección 2).

### Paso C — ingesta de documentos
`.txt`/`.md` con `open()` normal; `.docx` con `zipfile`+`xml.etree` (es un .zip de XML, no hace falta
librería de Word); `.pdf` con `pypdf`. `_fragmentar()`: ~500 palabras con 50 de solape (para que una idea
que cruza el corte de un fragmento no se pierda entera de ningún lado). Cada fragmento se manda a Ollama
(`ia.embed()`, nuevo — `/api/embed`, modelo `nomic-embed-text` por defecto, `MONITOR_EMBED_MODEL`) UNO POR
UNO — nunca se le pasa un documento entero al modelo, ni para extraer texto ni para embeddings.

**Subida sin multipart**: el módulo `cgi` que Python usaba para parsear `multipart/form-data` se sacó de
la librería estándar en Python 3.13+ (esta PC corre 3.14) — la salida stdlib-only fue mandar el archivo
como **base64 dentro de un JSON normal** (`POST /api/casos/<id>/docs`, `{"nombre","contenido_b64"}`), igual
que cualquier otra ruta de este servidor. Límite de 20MB por archivo (rechazado con error claro, no
silencioso).

**Ingesta en dos fases, en segundo plano**: `iniciar_ingesta()` (rápida: copia el archivo a `docs/`, arranca
`docs_estado.json` en `"en_cola"`) corre síncrono dentro del POST — responde con el `doc_id` casi al
instante. `procesar_ingesta()` (lenta: extraer texto, fragmentar, pedir un embedding por fragmento) corre
en un `threading.Thread` de fondo lanzado por monitor.py (`_procesar_ingesta_bg`), actualizando
`docs_estado.json` en cada fragmento — el dashboard muestra el progreso real ("se muestra el progreso",
pedido explícito) con un simple GET al detalle del caso cada 2s mientras algo esté `"en_cola"`/
`"extrayendo"`/`"indexando"` (sin websockets). **Si Ollama no responde para algún fragmento, ese fragmento
se guarda IGUAL, sin vector** — el documento no se pierde ni la ingesta se corta; queda un aviso honesto
("Ollama no respondió para N de M fragmentos...") en el estado del documento, mismo criterio de "avisar el
hueco real" que ya usa el proyecto para GDELT/Trends. Probado en vivo (con Ollama apagado, el estado real
de esta sesión): un `.txt` de prueba terminó en `"listo"` con ese aviso, en vez de romperse o quedar
colgado — y sin Ollama, `ia.embed()` ni siquiera intenta la llamada de red (falla rápido con un mensaje
claro).

Índice `index.sqlite3` por caso, una tabla `fragmentos` (doc_id, doc_nombre, posicion, texto, embedding
como JSON de floats, ts). `buscar_fragmentos(caso_id, embedding_consulta, top_k=4)`: similaridad coseno en
**Python puro** (sin numpy, regla de oro del proyecto) sobre todos los fragmentos del caso — para el
tamaño de un caso personal (decenas de documentos, no miles) es prácticamente instantáneo; si algún caso
crece mucho, sqlite3 ya deja la puerta abierta a filtrar por `doc_id` antes sin cambiar cómo se llama.

### Paso D — puente Dashboard → Asistente (determinista, SIN IA)
`monitor.revisar_casos_avisos(stories)`, al final de `run_fast()` (cuando cada historia ya tiene
contratos/contexto pegados por las llamadas de arriba, todas en `modo_lectura=True` — así una sola pasada
cubre feed + SERCOP + GDELT + social sin repetir lógica de búsqueda por fuente). Por cada caso, junta sus
entidades+alias (`casos.entidades_y_alias`) y usa `geo_hit()` (coincidencia por PALABRA/FRASE COMPLETA,
la misma función que ya usa el proyecto para lugares — reutilizada tal cual, un alias corto no necesita
tratamiento distinto a un topónimo) contra el titular+resumen de cada historia, y por separado contra cada
contrato SERCOP ya colgado de ella (`s["contratos"]`, comparando el JSON completo del contrato — no
depende de saber el nombre exacto de cada campo). Alias de menos de 3 letras se ignoran (mismo umbral que
`EC_TERMS`/`geo_hit`: demasiado corto para ser señal). Deduplicado real por `(caso_id, entidad,
origen_key)` — sin esto, la MISMA historia (que sigue viva en el feed pasada tras pasada mientras esté
vigente) avisaría de nuevo cada minuto; probado en vivo que una segunda pasada con las mismas historias no
duplica nada.

**Push opcional al iPhone** (`movil.py`, `avisos_casos_activos`, default `False` — "opcionalmente...
nada de comentarios constantes: solo avisos ante hechos concretos", y cada aviso de caso YA es un hecho
puntual, no necesita un umbral de enfriamiento propio como sí tienen "historia fuerte"/"pico de tema"):
si está activo, cada aviso nuevo dispara `movil.enviar()` con el título del caso y un link a la fuente.

**Botón "Agregar a caso…"** (`cardHTML()`, dashboard_template.html): ícono 📁 junto a la estrella/nota en
cada tarjeta de Noticias/Guardadas/Contraste. Abre un modal chico (`#casoPickerOverlay`) que lista los
casos existentes (o deja crear uno nuevo ahí mismo) y llama a `POST /api/casos/<id>/evidencia` con la
historia COMPLETA como `datos` — mismo criterio que `saved.json`, sobrevive a que la noticia caduque del
feed. **Alcance de esta pasada**: el botón agrega la HISTORIA entera (que ya incluye sus `contratos`
SERCOP adentro, si los tiene) — no se construyó un botón aparte por-contrato dentro del `<details>` de
SERCOP; documentado como simplificación consciente, no un olvido.

**Probado en vivo con datos REALES, no sintéticos** (servidor real corriendo, feed real de esa corrida):
se creó un caso siguiendo a "Donald Trump" (nombre que en ese momento aparecía en la cobertura real de la
Asamblea General de la ONU) y una pasada real del feed generó **41 avisos reales** citando historias
genuinas de Infobae, La Nación, etc. que lo mencionaban — confirmado también que `GET /api/hoy` los agrega
bien. Caso de prueba borrado al terminar.

### Paso E — chat del caso
Modelo **independiente** del resto del proyecto: `ia.elegir_modelo_caso()`/`CASO_MODEL`
(`MONITOR_CASO_MODEL`, default `qwen3:8b` — pedido explícito para esta PC nueva de Fernando, Ryzen 3 PRO
4350G/16GB RAM/**sin GPU**, distinta de la GTX 1650 SUPER que documenta el resto de este archivo; cae al
modelo rápido del pipeline si `qwen3:8b` no está instalado, mismo patrón de respaldo que
`elegir_modelo_chat()`). Las tareas de fondo del pipeline (`MONITOR_IA_MODEL`) y `OLLAMA_MAX_LOADED_MODELS=
1` (recomendado, variable de Ollama mismo, no algo que el código controle) quedan como ajuste de Fernando
en esta PC — no se cambió ningún default existente del resto del proyecto.

`monitor._material_caso(caso_id, mensaje)` arma el material (resumen del caso + entidades + los 4
fragmentos más relevantes A LA PREGUNTA puntual, via `ia.embed(mensaje)` + `casos.buscar_fragmentos` + los
5 avisos/evidencia más recientes) — mismo criterio de siempre ("el código recupera, la IA solo redacta") y
mismo formato legible que `agente._fmt_material_busqueda`. Si no hay fragmento claramente relacionado (o
el modelo de embeddings no responde), lo dice explícitamente en vez de mandar contenido al azar.

La respuesta final reusa `agente._responder_final_stream` (la MISMA función que ya usa el Asistente de
Bloque 2 y la lectura de Fase 4) — se le agregaron parámetros `modelo_fn`/`num_predict`/`num_ctx` (todos
opcionales, con los valores de antes como default, así los llamadores viejos no cambian de comportamiento)
para que el chat de casos pueda pasar `ia.elegir_modelo_caso` y **8192 de contexto** (pedido explícito,
"un contexto máximo de 8K") sin duplicar la lógica de streaming.

**Sugerencias de entidades/conexiones** (pedido: "La IA puede PROPONER entidades o conexiones, quedan
'sugerida'. Solo yo las marco como verificada"): después de cada respuesta del chat, un paso APARTE y
barato con el modelo RÁPIDO del pipeline — nunca el de casos — (`ia.extraer_sugerencias_caso`, `format=
"json"`, mismo patrón que `extraer_entidades_chat`) revisa el intercambio y propone 0-3 entidades/0-2
conexiones respaldadas por ESE texto, nunca inventadas. Se guardan de una como `"sugerida"`
(`casos.agregar_entidad`/`casos.agregar_conexion_sugerida`) — nunca se auto-verifican; el dashboard muestra
cada conexión sugerida con un botón "Verificar" (la marca `"verificada"`) y "Descartar" (la borra). Probado
con `ia._post` mockeado (`test_fase7_casos.py`): las sugerencias quedan realmente persistidas en
`caso.json`/`tablero.json`, con estado `"sugerida"`.

**Pausa del trabajador mientras se chatea** (pedido explícito, PC sin GPU — un solo modelo cargado a la
vez): contador global (`monitor._pausar_trabajador`/`_reanudar_trabajador`/`_trabajador_pausado`, no un
booleano, por si hay más de una pestaña de chat abierta a la vez) — `_responder_caso_chat_stream` lo
incrementa al empezar y lo decrementa en un `finally` (nunca queda pausado para siempre si algo falla a
mitad de camino); el `worker_loop` de `enrich_pass` chequea cada 2s en vez de esperar
`MONITOR_WORKER_PAUSA` completo, para retomar apenas el chat libera. **Alcance de esta pasada**: solo pausa
mientras dura el chat de casos (lo único que el pedido mencionaba) — el chat por item de Parte E y el
Asistente general de Bloque 2 siguen sin coordinarse con el trabajador (límite ya aceptado en fases
anteriores); extenderlo a esos dos es una mejora natural si hace falta, no implementada.

### API (`monitor.py`, todas bajo el mismo criterio de auth que el resto: esta PC siempre puede, otro
aparato necesita la clave de `movil.json`)
`GET /api/casos` (listar), `POST /api/casos` (crear, `{titulo,descripcion}`), `GET /api/casos/<id>`
(detalle completo — caso + avisos + notas + evidencia + tablero + documentos + docs_estado en un solo
request), `GET /api/hoy` ("Hoy en mis casos"), y bajo `POST /api/casos/<id>/...`: `entidades`
(`accion:"agregar"|"quitar"`), `notas` (`accion:"agregar"|"borrar"`), `avisos` (marca todos vistos),
`evidencia` (`accion:"agregar"|"quitar"`), `tablero` (`accion:"marcar"|"quitar"`, `conexion_id`, `estado`),
`docs` (subir documento, ver Paso C), `chat` (streaming NDJSON, ver Paso E). `do_GET` se reorganizó para
interceptar CUALQUIER `/api/...` con el mismo chequeo de auth que ya usaba `do_POST`, antes de decidir si
es una ruta de casos o cae al servido estático de siempre.

### Dashboard (`dashboard_template.html`)
`#productAsistente` ahora tiene un toggle interno (`.seg`, mismo estilo que Ecuador/Guayaquil/Mundo en
otros paneles) — **"Mis casos"** (nuevo, vista por defecto) y **"Consulta general"** (lo que servía del
chat de Bloque 2 viejo, reubicado tal cual en el Paso A — se mantiene como vía secundaria para preguntas
que no son de un caso puntual, "no es un chat suelto" se refiere a que la vía PRINCIPAL ahora es por
caso). "Mis casos": panel "Hoy en mis casos" + lista de casos (crear uno nuevo ahí mismo) + al abrir uno,
el detalle completo (entidades con chips removibles, avisos, documentos con barra de progreso real,
evidencia, notas, tablero de conexiones con Verificar/Descartar, y el chat del caso al final — mismo
patrón de streaming NDJSON que el resto del proyecto). Todo el estado de "qué caso está abierto" vive en
JS (se pierde al recargar, mismo criterio de simplicidad deliberada que el resto de los chats del
proyecto) — la URL solo recuerda el PRODUCTO (`#asistente`), no el caso puntual dentro de él.

### Verificado en esta sesión
- **27 pruebas nuevas** (`test_fase7_casos.py`, sin golpear Ollama) + las 23 que ya existían, las 24 en
  total pasando. Cubren CRUD de casos/entidades/notas/evidencia/avisos/tablero, dedup de avisos, extracción
  de `.txt`/`.docx`/formato no soportado, fragmentación con solape, ingesta completa sin Ollama (termina en
  `"listo"` con aviso honesto, nunca en error), el puente Dashboard→Asistente con historias+contratos
  sintéticos, el contador de pausa del trabajador, y las sugerencias del chat con `ia._post` mockeado.
- **Servidor real, de punta a punta**: `python monitor.py serve` real (sin duplicar instancias, verificado
  antes de arrancar), los 3 endpoints GET y los 7 sub-endpoints POST probados con `curl` real (crear caso,
  agregar/quitar entidad, notas, evidencia, tablero con estado inválido rechazado limpio, subir un `.txt`
  real con progreso de ingesta visible paso a paso, formato no soportado rechazado con mensaje claro, ruta
  inválida y caso inexistente devolviendo 404). El puente de avisos (Paso D) se probó con datos REALES del
  feed (ver arriba, caso "Donald Trump", 41 avisos reales). El chat de un caso sin Ollama corriendo
  devuelve el error JSON esperado sin tumbar el servidor.
- **No verificado con Ollama real corriendo** (no estaba disponible en esta sesión, mismo límite ya
  documentado para Fases 4-6): la CALIDAD del material que arma `_material_caso`/la respuesta del chat de
  casos/las sugerencias de entidades con un modelo real (`qwen3:8b`) — el *wiring* está probado de punta a
  punta (incluida la ruta de "sin Ollama" devolviendo el error correcto), falta que Fernando lo pruebe con
  Ollama activo y revise si el modelo propone sugerencias sensatas.
- **No probado visualmente en un navegador real** (esta sesión no tiene una herramienta de navegador): la
  estructura HTML/CSS/JS se verificó con balance de tags automatizado + `node --check` sobre el `<script>`
  servido de verdad por el servidor real, y toda la lógica de datos que el botón 📁/el picker/el detalle
  del caso disparan ya se probó por HTTP directo — pero la experiencia visual (que el modal se vea bien,
  que la barra de progreso se anime, que el toggle Mis casos/Consulta general se sienta bien) queda
  pendiente de que Fernando la mire en su navegador.

### Pendientes reales
1. Probar con Ollama real corriendo en esta PC nueva (calidad de `qwen3:8b` para el chat de casos y las
   sugerencias de entidades/conexiones).
2. Revisión visual en navegador real (recomendado: `python monitor.py serve`, abrir el Asistente, crear un
   caso de prueba, subir un documento chico, ver el chat).
3. El botón "Agregar a caso…" agrega la historia completa, no contratos SERCOP individuales por separado
   (ver Paso D) — revisar si hace falta un botón aparte ahí si en el uso real se siente una falta real.
4. La pausa del trabajador (Paso E) solo cubre el chat de casos, no el chat por item ni el Asistente
   general de Bloque 2 — extenderla ahí es una mejora natural si hace falta en esta PC sin GPU.
5. El tablero sigue siendo solo el esquema de datos (nodos/conexiones) — sin interfaz visual de pizarrón,
   tal como pedía esta etapa explícitamente.

**No se tocó ningún archivo de ejecución** (`data.json`, `history.json`, `*_cache.json`, `notas.json`,
`movil.json`) en ninguno de estos pasos — regla explícita de Fernando, coherente con cómo el resto del
proyecto trata esos archivos (ver "Caches" más arriba).

## Fase 8 (2026-09-25) — tres problemas reportados por Fernando: duplicados, geografía errónea, alertas tempranas

Pedido explícito: diagnosticar con datos reales antes de tocar código, arreglar, y mostrar antes/después con
un caso de prueba que reproduzca el fallo original. Los tres problemas se trabajaron en el orden pedido.
Esta PC tenía Ollama corriendo AL EMPEZAR la sesión (con `nomic-embed-text` instalado) — se aprovechó para
medir similitud de embeddings con pares reales antes de decidir el umbral, pero Ollama se cayó a mitad de
sesión (proceso ya no estaba corriendo, puerto 11434 sin escucha) y no volvió a estar disponible para la
verificación final en vivo — ver Pendientes de cada problema.

### Problema 1 — noticias repetidas entre medios y entre corridas

**Diagnóstico real** (con `data.json` de una corrida en vivo, 1113 historias, comparando pares de titulares
por debajo del umbral de `cluster()`):
- **"Circulaba con placas adulteradas... $41.070..." (El Universo Guayaquil) vs "Carro debía 41.000 en
  multas... ATM lo retiene..." (Expreso)**: mismo auto, misma multa, contado por dos medios con palabras
  casi sin superposición (sim=0.23, entre los dos umbrales de `cluster()`) y SIN nombre propio en común (el
  hecho que comparten es una CIFRA, "41.000"/"41.070", no un nombre) — nunca se unían.
- **"Lavinia Valbonesi asume liderazgo de ALMA..." (TC Television) vs "...asumirá la presidencia de ALMA en
  Nueva York" (El Universo)**: BUG REAL encontrado en `_nombres_propios()` — el segundo titular tiene 4 de 7
  palabras capitalizadas (68%: el nombre completo + "Nueva York"), suficiente para que el detector de
  "titular en Title Case inglés" (pensado para casos reales como "5 Takeaways From Ari Emanuel's Memoir")
  lo tratara como inglés y le VACIARA el set de nombres propios enteros — perdiendo la señal que hubiera
  unido las dos notas. Medido con casos reales: Title Case inglés auténtico da 1.00 de proporción de
  palabras capitalizadas; titulares en español con 2-3 nombres propios reales dan 0.57-0.60. Con el umbral
  viejo (>0.5) el segundo caso se confundía con el primero.
- **"Daniel Noboa se reúne con Zelenski en Nueva York..." vs "Daniel Noboa arranca su agenda en la ONU..."**:
  comparten "Noboa" pero cuentan hechos DISTINTOS del mismo día — el caso real que motiva pedir
  "Actualización" en vez de fusión ciega, no un bug de umbral.
- **Estructural** (confirmado leyendo `collect()`/`run_fast()`, no un par puntual): `cluster()` siempre
  agrupa desde cero, solo contra los artículos que ESTA pasada trajo `collect()` — nunca contra historias ya
  publicadas en pasadas anteriores. Si el artículo de un medio rota fuera de la ventana RSS de su feed antes
  de que otro medio cubra el mismo hecho, `cluster()` jamás los ve juntos: dos tarjetas de una sola fuente
  cada una, para siempre. Esto explica "duplicados entre corridas" de raíz — no es un problema de umbral,
  es que no había memoria entre pasadas.

**Arreglo — registro persistente de historias (`historias_registro.json`, nuevo)**: reemplaza a `cluster()`
en el pipeline real (`run_once`/`run_fast`, vía la función nueva `agrupar_con_memoria()` en `monitor.py`).
`cluster()`/`_merge_close()`/`_mismo_hecho()` NO se tocaron y siguen usándose por sus propias pruebas
(`test_cluster.py`, `test_cluster_evento_generico.py`) — el modo muestra (`MONITOR_SAMPLE=1`) también sigue
usando `cluster()` a propósito, para no ensuciar el registro real con datos ficticios.
- Cada artículo nuevo se compara contra las entradas del registro con `ultimo` dentro de
  `REGISTRO_MAX_HORAS` (72h por defecto, = `CLUSTER_MAX_HORAS`) — no solo contra los artículos de esta
  misma corrida. Si matchea, se suma como fuente nueva (sube `n_outlets`); si además trae información nueva
  (ver `_es_actualizacion`), se agrega también a `actualizaciones` (fecha+outlet+título) sin crear tarjeta
  nueva. Si no matchea nada, crea una entrada nueva.
- **Señales de match, en capas** (todas dentro de `_match_registro`, todas baratas — nunca llaman a
  red/Ollama desde el hilo rápido):
  1. Solape de palabras del titular representante (`_sim`, igual que `cluster()`), umbral 0.30, o 0.20 si
     además comparte un nombre propio (igual que antes).
  2. **Nuevo**: 0.20 si además comparte una CIFRA de 3+ dígitos (`_numeros()`) — arregla el caso real de la
     multa de $41.000/$41.070.
  3. **Nuevo**: 0.20 si además comparte 2+ palabras de CONTENIDO (no solo 1, para no confundir dos
     historias del mismo tema general) — mismo caso de la multa (comparten "placas"/"adulteradas"/"multas",
     sin nombre propio ni cifra exacta en uno de los títulos).
  4. **Nuevo, embeddings**: si AMBOS lados ya tienen un embedding calculado (por el trabajador, nunca en
     vivo) y coseno ≥ `EMBED_SIM_UMBRAL` (0.75) Y comparten nombre propio o cifra.
- **Umbral de embeddings, medido en vivo** (Ollama real, `nomic-embed-text`, esta PC, antes de que se
  cayera): coseno de los 4 pares reales de arriba dio **0.7651 / 0.8605 / 0.7683 / 0.8191**. Un par de
  control (dos notas sin relación) dio 0.6150/0.6377. **Hallazgo real importante**: la similitud de
  embeddings SOLA no alcanza para titulares cortos con formato de plantilla — el pronóstico del clima de
  Sevilla contra el de Guayaquil (mismo FORMATO, ciudades distintas, sin relación real) dio **0.7780**, casi
  tan alto como los duplicados reales, porque `nomic-embed-text` capta la ESTRUCTURA de la frase, no solo el
  contenido. Por eso el match por embeddings exige ADEMÁS compartir un nombre propio o una cifra (exactamente
  lo que pedía el enunciado original: "combinada con entidades en común") — con esa combinación, el par
  Sevilla/Guayaquil queda afuera (no comparten ningún nombre propio ni cifra) aunque su coseno sea alto.
- **Arquitectura de dos velocidades respetada**: el hilo rápido (`agrupar_con_memoria`, dentro de
  `run_fast`) NUNCA calcula un embedding nuevo, solo lee los que el trabajador ya dejó en el registro (mismo
  criterio que `ia_cache.json`/`contexto_cache.json`). El trabajador (`_embed_pendientes_registro()`, llamada
  nueva en `enrich_pass()`) calcula hasta `EMBED_MAX_NEW`=40 embeddings nuevos por pasada (uno por historia,
  no por fuente) y hace una **reconciliación**: dos entradas del registro (dentro de la ventana) que
  comparten nombre/cifra Y tienen coseno alto se fusionan (la más vieja absorbe a la más nueva, para no
  romper `fuentes[0]`, la clave estable de `saved.json`/`notas.json`).
- **BUG REAL propio, encontrado ESCRIBIENDO la prueba de "Actualización"**: comparar el titular nuevo contra
  el UNION acumulado de tokens de TODAS las fuentes de una entrada (en vez de solo contra el titular
  representante) diluye el Jaccard a medida que la historia suma medios — una tercera nota real sobre el
  mismo hecho puede quedar bajo el umbral solo porque el denominador creció con vocabulario de fuentes
  anteriores que no tienen que ver con la nota nueva. `_sim()`/`CLUSTER_THRESHOLD` se calibraron para
  comparar UN titular contra OTRO (como hace `cluster()`), no contra una unión creciente — arreglado
  comparando siempre contra `rep_titulo` (el título más nuevo), no contra la unión.
- **BUG REAL propio, encontrado VERIFICANDO EN VIVO** (reinicio real de `serve` con este mismo código): tres
  pronósticos reales del tiempo en Guayaquil de DÍAS DISTINTOS (21/23/24 de septiembre, medio "Busqueda:
  Guayaquil" vía Google News) terminaron en la MISMA entrada del registro — no es un bug de identidad (son
  3 notas legítimamente distintas, cada una del clima de un día distinto en Guayaquil, correctamente
  agrupadas por su plantilla compartida), es el mismo fenómeno de "boletín con plantilla" que ya se
  documenta como pendiente de precisión más abajo. Un bug real DISTINTO que sí se encontró y arregló en la
  misma verificación: Google News arma el link de cada artículo con un token que puede cambiar entre
  lecturas del MISMO artículo — como el registro ahora persiste entre pasadas (a diferencia de `cluster()`,
  que partía de cero cada vez), esto se acumulaba (una fuente del mismo medio+título apareciendo 3 veces en
  la misma historia). Arreglado con un chequeo adicional por (outlet, título normalizado) antes de sumar una
  fuente — mismo criterio que ya usa `dedup()` para lo mismo dentro de una sola pasada, extendido para que
  sobreviva entre pasadas. Verificado con un reinicio real posterior: 0 entradas con fuentes duplicadas
  (antes: 1).
- `_nombres_propios()`: umbral del detector de Title Case inglés subido de 0.5 a 0.7 (ver diagnóstico
  arriba) — arregla el caso Valbonesi sin romper el caso ya documentado (Spencer/Emanuel, Title Case inglés
  real, sigue dando 1.00 y excluyéndose).

**Dashboard**: `renderActualizaciones(h)` (nuevo, `dashboard_template.html`) muestra la lista de
actualizaciones dentro de la misma tarjeta (fecha+medio+título+link), en `cardHTML()` y `contrasteCardHTML()`,
justo después de `renderContexto()`.

**Pruebas** (`test_problema1_memoria.py`, 7 pruebas, sin golpear red salvo la de embeddings que se salta
sola si Ollama no responde): reproduce el caso real de la multa en DOS corridas separadas (`agrupar_con_memoria()`
llamado dos veces, cada vez con un solo artículo, simulando que el otro medio ya rotó fuera del feed) →
una sola tarjeta con 2 medios; una tercera nota con una reacción real (verbo "responde" + cifra nueva) →
aparece como Actualización, sigue siendo 1 tarjeta con 3 medios; un control negativo (dos notas sin
relación) → 2 tarjetas, no se fusionan a ciegas; el caso Valbonesi (nombres propios ya no se vacían); el
caso del link cambiante de Google News (fuentes no se duplican); y (marcada `skipUnless` sobre
`ia.embed_disponible()`, se saltó en la verificación final porque Ollama ya no estaba disponible en ese
momento, pero SÍ corrió con éxito antes en la sesión, con Ollama real) un parafraseo extremo (CERO palabras
de contenido en común, solo la cifra) que el hilo rápido correctamente NO une, y que `_embed_pendientes_registro()`
SÍ reconcilia una vez calculados los embeddings.

**Verificado con un reinicio real de `serve`** (parado, `historias_registro.json` borrado a propósito para
empezar limpio, levantado de nuevo): a los ~60s bindeó el puerto, `data.json` con 1071 historias, registro
con **182 entradas con 2+ fuentes** y **39 con al menos una Actualización** ya en la primera pasada real —
0 entradas con fuentes duplicadas (bug de arriba, confirmado arreglado).

**Pendiente real**: el fenómeno de "boletín con plantilla" (pronósticos del tiempo/tránsito de días o
ciudades DISTINTAS agrupados por compartir estructura de frase) no se resolvió de raíz esta pasada — se
mitigó indirectamente para el caso de lugar EXTRANJERO (Problema 2, el veto geográfico), pero notas
legítimamente de Ecuador con esa plantilla (ej. 3 pronósticos de Guayaquil de días distintos) pueden seguir
agrupándose entre sí. No se tocó `EVENTO_GENERICO` para esto por el riesgo real de romper clustering
legítimo de otras noticias que comparten esas mismas palabras con sentido real (ej. "lluvias" en una
inundación real). Revisar si hace falta separar por FECHA EXPLÍCITA mencionada en el titular (no solo la
fecha de publicación) si este caso sigue apareciendo seguido.

### Problema 2 — categorización geográfica errónea (Sevilla en Guayaquil)

**Diagnóstico real**: la nota "Pronóstico del clima en Sevilla este 25 de septiembre..." (Infobae) llegó
agrupada (por el mismo problema de clustering de plantillas del Problema 1, NO por su propio texto) junto
con fuentes reales de Guayaquil, entre ellas una de "El Universo (Guayaquil)" con `ciudad_feed="Guayaquil"`
(la señal DURA de sección editorial). Causa raíz confirmada en `build_stories()`: `ambito = "local" if
ciudad_feed else ambito_de(blob)` — la señal de `ciudad_feed` forzaba ambito local SIN CONDICIÓN, sin que
nada comparara el TEXTO de la nota de Sevilla contra nada. Revisando las 94 historias marcadas Guayaquil de
esa misma corrida se encontró un SEGUNDO caso real vivo, mismo patrón: **"Pico y Placa en Cali"** (Colombia,
restricción vehicular) agrupada con boletines reales de Quito/Guayaquil sobre lluvia y pico y placa —
"Cali" no coincidía con ningún término de `FOREIGN_TERMS`, así que ni siquiera un veto simple lo hubiera
detectado sin ampliar la lista.

**Arreglo — veto geográfico** (`extranjero_sin_ecuador(text)`, nuevo en `monitor.py`, `= is_foreign(text)
and not is_ecuador(text)`):
- Aplicado en `build_stories()`: `ciudad_feed` ya NO fuerza local si el texto del **representante** (la nota
  más nueva del grupo, la que realmente se muestra como titular/resumen) tiene veto — la regla de la sección
  del feed sigue aplicando solo cuando el texto es neutro, tal como se pidió.
  - **BUG REAL propio, encontrado escribiendo la prueba**: la primera versión evaluaba el veto sobre el BLOB
    combinado de TODAS las fuentes del grupo, no sobre el representante — como un cluster mal armado
    (Problema 1) siempre va a tener a otra fuente del grupo que SÍ es de Guayaquil, el veto sobre el blob
    entero nunca se disparaba, exactamente el bug que se quería arreglar. Corregido comparando contra
    `rep["title"] + " " + rep["summary"]` (lo mismo que ve Fernando en la tarjeta), consistente con el
    candado de la IA (`get_ia`/`_apply`), que YA comparaba contra `s["titular"]+s["resumen"]` (= el
    representante) desde antes.
- Aplicado también en el candado de la IA (`get_ia` → `_apply`): ni siquiera la IA puede marcar
  local/guayaquil con veto activo, y si el texto tiene veto pero la IA ni propuso "internacional", se fuerza
  igual (invariante de código, no depende de que la IA lo pida) — mismo criterio "candado en código, no solo
  en el prompt" del resto del proyecto.
- **`FOREIGN_TERMS` ampliado** con ciudades intermedias que faltaban (Cali, Medellín, Barranquilla,
  Cartagena, Guadalajara, Monterrey, São Paulo, Río de Janeiro, Montevideo, Asunción, La Paz, Caracas,
  Miami, Houston, Los Ángeles, Toronto, Sevilla, Barcelona, Valencia, y las capitales centroamericanas con
  nombre completo para evitar colisión con topónimos ecuatorianos reales, ej. "san jose de costa rica" en
  vez de "san jose" suelto, "santo domingo de guzman" en vez de "santo domingo" suelto — Ecuador YA tiene su
  propio "Santo Domingo de los Tsáchilas").
- **`is_junk()` descarta pronósticos del clima de fuera de Ecuador** (pedido explícito): `WEATHER_TERMS`
  (frases completas: "pronóstico del clima", "así estará el clima", etc., no palabras sueltas como
  "clima"/"tiempo" que colisionarían con cambio climático/clima político) + `is_foreign()` sin `is_ecuador()`
  → se descarta como ruido antes de entrar al tablero. Un pronóstico de una ciudad ecuatoriana (o sin ciudad
  reconocible) sigue pasando — verificado con prueba explícita que NO se descarta.

**Pruebas** (`test_problema2_veto_geografico.py`, 9 pruebas): el caso real de Sevilla (queda internacional);
Sevilla sola es basura (is_junk); un pronóstico de Guayaquil NO es basura; el caso real de Cali (queda
internacional); Putumayo (el candado de temas YA arreglado en Fase 2 sigue preservando la categoría
correcta cuando la IA propone una sin relación, sin vaciarla a "otros" — se re-confirmó, no se tocó esa
lógica); y 4 casos que NO deben romperse: 3 notas reales de Guayaquil sin mención explícita de la ciudad
(Ceibos Town Center, carrera de Solca, reservorio Vía a la Costa — el caso normal que `ciudad_feed` está
pensado para resolver) y una nota que menciona Ecuador Y un país extranjero a la vez (sigue local, el veto
exige que NO haya NINGUNA señal de Ecuador).

**Verificado con el reinicio real de `serve`** (mismo reinicio que Problema 1): de **202 historias
marcadas ámbito local** (Ecuador completo, no solo Guayaquil) en la corrida real, **0 disparan el veto
geográfico** — confirmado programáticamente contra el `data.json` real, no solo con las pruebas sintéticas.

### Problema 3 — Alertas tempranas (módulo nuevo: `alertas.py`)

**Investigación de viabilidad, hecha ANTES de programar, con pruebas reales**:
- **X/Twitter — NO implementado, por decisión explícita del proyecto** (nada de scraping ni cuenta logueada,
  ver "Decisiones ya tomadas"). Precio investigado (fuentes de terceros — la página oficial de precios de X,
  `developer.x.com`, devolvió HTTP 402 al intentar leerla en esta sesión, irónicamente): **ya no existe un
  plan Basic fijo** — desde 2026 el modelo es pago por uso, **$0.015 por post creado, $0.005 por post
  LEÍDO**, tope de 3 millones de lecturas/mes antes de pasar a Enterprise. El viejo plan Basic ($200/mes fijo)
  quedó descontinuado, migración forzada a pago por uso después de junio 2026. Fernando decide si vale la
  pena con este dato.
- **Bluesky**: confirmado en vivo (`api.bsky.app/xrpc/app.bsky.feed.searchPosts`, 2026-09-25, sin cuenta ni
  token) que SIGUE respondiendo público — mismo hallazgo que ya documentaba `social.py`
  (`public.api.bsky.app` sí empezó a pedir sesión, pero `api.bsky.app` -sin "public."- sigue abierto).
- **Telegram**: se probaron **19 nombres de canal candidatos** además de "alertaecuador" (ya conocido de
  antes) — nombres plausibles de instituciones/medios (ecu911ec, SGRecuador, Bomberos_Guayaquil,
  PoliciaEcuador, primicias_ec, INAMHIEcuador, IGEPN, etc.), probados en vivo contra `t.me/s/<canal>`.
  **0 de 19 resultaron reales** (todos redirigen al landing genérico, solo "alertaecuador" respondió 200).
  Confirma lo que ya documentaba el proyecto: adivinar nombres de canal no funciona, la tasa de acierto real
  medida en dos sesiones distintas es ~1/20-1/40. `MONITOR_TG_CANALES` sigue vacío por defecto — Fernando
  tiene que revisar sus propios canales seguidos y pasar nombres reales.
- **Fuentes oficiales con RSS real, confirmado en vivo (HTTP 200 + XML válido)**: **INAMHI**
  (`inamhi.gob.ec/feed/`, boletines reales), **Secretaría Nacional de Gestión de Riesgos**
  (`gestionderiesgos.gob.ec/feed/` — bloqueaba el User-Agent por defecto de `curl`/`urllib` sin cabecera de
  navegador con un `403`/reset de conexión; con un User-Agent de navegador real, 200 limpio, mismo criterio
  que ya usa el resto del proyecto con `UA`), **INOCAR** (`inocar.mil.ec/web/?feed=rss2` — la URL obvia
  `/feed/` da 404, hay que usar el parámetro `?feed=rss2` de WordPress). Las tres integradas en
  `alertas.py` (`FUENTES_OFICIALES_RSS`), con frecuencia propia (30-60 min, igual criterio que `oficial.py`
  — estas instituciones no publican cada minuto).
- **Instituto Geofísico (sismos) — investigado, NO integrado**: la página "Mapa Últimos Sismos"
  (`igepn.edu.ec/mapa-ultimos-sismos`) no expone una URL de API/JSON visible en el HTML estático que trae
  `curl`/`WebFetch` — probablemente carga los datos con JavaScript contra un endpoint que no aparece en el
  HTML inicial (necesitaría inspección de tráfico de red en un navegador real, no disponible en esta
  sesión). Pendiente real, no resuelto.
- **CNEL (cortes programados) — investigado, NO integrado**: HTTP 503 sostenido durante TODA la sesión
  (con y sin User-Agent de navegador, en la home y en `/feed/`) — no se pudo confirmar si tiene RSS/API en
  este momento, puede ser mantenimiento o un bloqueo. Pendiente real.
- **Google Trends (picos de búsqueda)**: NO enganchado esta pasada — `trends.py` ya existe y el enganche a
  `alertas.marcar_pico_busqueda()` (ya escrito, sin llamador todavía) es directo, pero se priorizó dejar 3
  fuentes reales funcionando de punta a punta antes de sumar una cuarta. Pendiente real.

**Diseño e implementación** (`alertas.py`, nuevo módulo standalone — solo stdlib + `social.py` para
Bluesky/Telegram, nunca importa `monitor.py`, mismo criterio que `oficial.py`/`declaraciones.py`):
- **Nunca se mezcla con el feed de Noticias** — sección propia en el dashboard (`#secAlertas`, botón "⚠
  Alertas tempranas" en `#mainnav`).
- **4 estados, orden creciente, NUNCA se degradan** (`ESTADO_ORDEN`): `sin_confirmar` (1 fuente) →
  `corroborado` (2+ fuentes independientes — deduplicadas por `(fuente, autor)`, un repost del mismo origen
  NO cuenta como fuente nueva — o 1 fuente social + 1 pico de búsqueda cuando Trends se enganche) →
  `confirmado_oficial` (cualquier señal marcada `oficial=True`, las 3 fuentes RSS de arriba) → `ya_en_medios`
  (flag aparte, no reemplaza al estado anterior: se activa cuando `vincular_con_prensa()` encuentra una
  historia real del feed con el mismo tipo+lugar).
- **Detección** (sin IA, determinista): `detectar_tipo()` por palabras clave (incendio, accidente,
  inundación, balacera, corte_luz, corte_agua, protesta, sismo) y `detectar_lugar()` contra `BARRIOS_GYE`
  (diccionario de ~24 sectores/ciudadelas/parroquias REALES de Guayaquil — Alborada, Sauces, Kennedy Norte,
  Urdesa, Mapasingue, Guasmo, Suburbio, Ceibos, Samanes, Garzota, Bastión Popular, Flor de Bastión, Isla
  Trinitaria, Pascuales, Mucho Lote, Febres Cordero, Durán, Samborondón, Vía a la Costa, 9 de Octubre,
  Puerto Lisa, Sergio Toral, Prosperina, Monte Sinaí — nombres públicos ya conocidos, mismo criterio que
  `CITIES["Guayaquil"]` en `monitor.py`, que ya lista varios).
- **"Ya en medios" + métrica obligatoria de adelanto**: `vincular_con_prensa(historias)` (llamada desde
  `procesar_alertas()`, barata, sin red — compara contra `stories` que YA está en memoria) enlaza una alerta
  con la primera historia de prensa real que coincida en tipo+lugar, guarda `historia_link`/`historia_titulo`
  y calcula `adelanto_min = (ya_en_medios_ts - primera_deteccion) / 60` — sin este dato no se sabe si esta
  capa anticipa de verdad o solo mete ruido (pedido explícito). `metricas_adelanto()` (nuevo, en
  `data.json["alertas_metricas"]`) resume n/promedio/mediana + los 10 casos más recientes, panel nuevo en
  Estadísticas (`renderAlertasMetricas()`).
- **Arquitectura de dos velocidades respetada**: `alertas.recolectar_senales()` (llamadas de red reales a
  Bluesky/Telegram/RSS oficiales) vive en `enrich_pass()` (hilo trabajador) — `vincular_con_prensa()` y el
  disparo de ntfy viven en `write_outputs()`/`procesar_alertas()` (hilo rápido), deterministas y sin red.
- **ntfy SOLO desde Corroborado hacia arriba** (pedido explícito, nunca por "Sin confirmar"): `movil.enviar()`
  se llama solo para `alertas.pendientes_de_aviso("corroborado")`, y `marcar_avisada()` evita reavisar dos
  veces por el mismo escalón (usa `conf_movil["avisos_activos"]`, el mismo interruptor general que ya usa
  el resto de `movil.py` — no hay un flag nuevo aparte para apagar SOLO esto, si Fernando lo quiere aparte es
  un ajuste chico).

**Dashboard**: `#secAlertas` (nueva sección, nunca mezclada con Noticias), toggle Todas/Corroborado o
más/Confirmado oficial, cada tarjeta con tipo+lugar+estado+señales (autor, texto, fuente, link) +
"📰 Ya en medios" con el adelanto en minutos cuando aplica. Badge en el botón de navegación
(`#alertasBadge`) que se actualiza en CADA poll, mismo criterio que "Última hora" (información sensible al
tiempo, no debe esperar a que el usuario deje de estar "ocupado" leyendo otra cosa).

**Pruebas** (`test_problema3_alertas.py`, 12 pruebas, con datos de fixture — sin golpear Bluesky/Telegram/
RSS reales, eso es cosa de `recolectar_senales()` que no se prueba en vivo esta pasada): los 3 casos
pedidos por Fernando — (1) un rumor de 1 sola fuente queda "Sin confirmar" y no genera pendiente de ntfy;
(2) un evento con 3 fuentes independientes llega a "Corroborado" y SÍ genera pendiente de ntfy (probado con
`movil.enviar` mockeado, sin red real, y confirmado que no se reavisa dos veces); (3) un evento que luego
cubre un medio se enlaza (`ya_en_medios=True`) y registra un `adelanto_min` positivo — más pruebas de
respaldo: repost del mismo origen no suma corroboración, fuente oficial sube directo a confirmado_oficial,
el estado nunca se degrada, detección de tipo/lugar, y que un texto sin tipo reconocido no crea nada.

**Verificado con el reinicio real de `serve`**: `alertas_estado`/`alertas_metricas` llegan bien a
`data.json` sin errores (`"activas: 0 (enlazadas a prensa esta pasada: 0)"` — honesto, el trabajador recién
arranca a recolectar). La sección `#secAlertas`/`renderActualizaciones` confirmadas presentes en el
`dashboard.html` servido de verdad por el servidor real (no solo en el archivo fuente).

### Verificación final común a los tres problemas

- **194 pruebas automatizadas pasando** (contadas de verdad con `unittest.TestLoader().countTestCases()`
  sobre los 27 archivos `test_*.py`, no una estimación — 3 archivos nuevos de hoy: `test_problema1_memoria.py`
  [7], `test_problema2_veto_geografico.py` [9], `test_problema3_alertas.py` [12], más las 166 que ya
  existían, todas re-corridas y en verde, incluida `test_fase4_buscador.py` [7 pruebas, la más lenta,
  ~97s] que golpea red real -no mockeada- para sus propias pruebas).
- **Reinicio real de `serve`**: se encontró (otra vez, mismo patrón ya documentado varias veces en este
  archivo) UNA instancia corriendo (alias de Windows Store + proceso real, el patrón ya conocido, no
  duplicada esta vez) — se detuvo limpio, se reinició con TODO el código de hoy. Bindeó el puerto en ~55-60s
  (más lento que el "<15s" típico de otras verificaciones, pero dentro de rango normal — el registro nuevo
  parte vacío la primera vez, sin overhead real de comparación).
- **Ollama se cayó a mitad de sesión**: estaba corriendo (con `nomic-embed-text`) al momento de medir los
  umbrales de embeddings reales (ver Problema 1), pero para cuando se corrió la verificación final ya no
  respondía (puerto 11434 sin proceso escuchando) — no se investigó la causa (no es parte de este pedido),
  simplemente se documenta el estado real: la prueba de reconciliación por embeddings se SALTÓ sola
  (`skipUnless`) en la corrida final, pero SÍ corrió con éxito antes en la misma sesión con Ollama real (ver
  Problema 1).

### Pendientes reales (los tres problemas)

1. **Clustering de "boletines con plantilla"** (Problema 1): pronósticos del tiempo/tránsito de la MISMA
   ciudad pero DÍAS distintos pueden seguir agrupándose entre sí (confirmado en la verificación real: 3
   pronósticos de Guayaquil de días distintos en una sola entrada). No es un bug de identidad (las 3 notas
   son reales y de Guayaquil), es una imprecisión de "misma historia" vs. "mismo género de nota" — no
   resuelto de raíz, ver la nota completa en Problema 1.
2. **Instituto Geofísico (sismos) y CNEL (cortes programados)**: investigados, sin URL de API/RSS
   funcional encontrada en esta sesión (ver Problema 3) — quedan fuera de `alertas.py` hasta que aparezca
   una vía real.
3. **Google Trends (picos de búsqueda) sin enganchar** a `alertas.marcar_pico_busqueda()` — la función ya
   existe, falta el llamador real.
4. **La calidad del match por embeddings en un caso real de "parafraseo extremo" se probó una vez en esta
   sesión (con Ollama real, antes de que se cayera)**, no se pudo re-confirmar en la verificación final por
   la caída de Ollama — revisar de nuevo con Ollama corriendo la próxima vez que se abra el proyecto.
5. **No se revisó visualmente en un navegador real** ninguna de las dos piezas de UI nuevas (Actualizaciones
   dentro de una tarjeta, la sección Alertas tempranas completa) — se verificó con `node --check` sobre el
   `<script>` servido de verdad y con los datos reales llegando bien a `data.json`, pero la experiencia
   visual (que las tarjetas de alerta se vean bien, que el badge se note) queda pendiente de que Fernando la
   mire en su navegador.
6. **`X/Twitter`**: precio investigado y reportado arriba (pago por uso, $0.005/lectura desde 2026) —
   decisión de implementarlo o no queda en manos de Fernando, no implementado por default.
7. **Telegram**: 0/19 canales candidatos nuevos resultaron reales (ver Problema 3) — sigue pendiente que
   Fernando revise sus propios canales seguidos y pase nombres reales, adivinar no funciona.

## Fase 9 (2026-09-25/26) — duplicados, IA desalineada, Pulso social con debate real, y base de X

Pedido en cuatro partes (A→B→C→D, orden obligatorio: el agrupamiento (A) es la base de todo lo
demás). Diagnóstico primero con datos reales de la corrida del 2026-09-25 (`data.json`,
`historias_registro.json`), después arreglos, después verificación con `serve` reiniciado de
verdad — mismo criterio de siempre.

### A — Agrupamiento: dos caras del mismo problema

**A1 — los embeddings de la Fase 8 nunca corrieron en producción, confirmado real.**
`historias_registro.json` tenía **2481 entradas, 0 con `embedding`** — la capa semántica que la
Fase 8 documentó como arreglo del parafraseo estaba apagada de hecho. Causa raíz confirmada:
`ia.embed_disponible()` guardaba `_embed_model_ok` en una global **para siempre** — si Ollama no
respondía en el primer chequeo del proceso (arranque en frío), quedaba en `False` hasta reiniciar
`serve` por completo, sin importar que Ollama levantara minutos después. Arreglado con
`EMBED_CHECK_TTL` (10 min): un `False` vencido se reintenta solo. Nuevo `ia.estado_embeddings()` +
`monitor.estado_embeddings_dashboard()` (cuenta real de cobertura, `_embeddings_cobertura()`)
expuestos en `data.json["estado_embeddings"]` y como una fuente más en el panel "Salud de los
datos" del dashboard (antes no había forma de notar el apagón sin mirar el JSON a mano).
`test_fase9_embeddings.py` (3 pruebas, `ia.modelos()` mockeado).

**A2/A3 — duplicados que debían unirse + fusiones erróneas que no debían pasar**, mismo mecanismo
de fondo en los dos sentidos: el matching por palabras/nombre propio no tenía suficientes señales
finas.
- **Siglas** (`monitor._siglas()`, nuevo): `_nombres_propios()` solo captaba palabras en Sentence/
  Title Case, nunca acrónimos (CJNG, ATM, INAMHI...) — justo la entidad puntual que unía varias
  notas del mismo hecho. Se suman siempre (incluso cuando el titular se descarta por parecer Title
  Case inglés), excluyendo genéricas (`_SIGLAS_GENERICAS`: EEUU, ONU, OTAN...).
- **Años vs. fechas explícitas**: `_numeros()` trataba "2026"/"1961" como cifra compartida — casi
  cualquier par de notas de una misma corrida menciona el año actual. Ahora se excluyen (`_es_anio`)
  y se extraen aparte con `fecha_mencionada()` (regex de "N de mes"), usada como **veto duro** de
  "boletín con plantilla": misma ciudad + fecha explícita distinta (o ciudad distinta), nunca es el
  mismo hecho, sin importar cuánto compartan en palabras/nombres — cierra el pendiente de la Fase 8.
- **Servicio básico** (`servicio_mencionado()`, nuevo): mismo veto para "cortes de luz" vs. "cortes
  de agua" (caso real: se fusionaban por compartir vocabulario de plantilla — "reportan"/"cortes"/
  "ciudadanos" — con Jaccard 0.33, por encima del umbral general).
- **`LUGARES_COMUNES`** (nuevo, solo en el registro persistente — `cluster()` intra-pasada se dejó
  intacto a propósito, ver abajo): "guayaquil"/"ecuador"/"quito"/etc. ya no cuentan como el ÚNICO
  nombre propio compartido (caso real: "Santa Elena: crimen de un taxista" se fusionaba con "Bus...
  cayó de un puente... en Santa Elena" — un lugar en común no prueba que sea el mismo hecho).
- **Google News como "un solo medio"**: "Busqueda: Guayaquil" aparecía como outlet con 167 fuentes
  reales adentro (El Universo, Metro Ecuador, El Telégrafo...) porque Google News junta
  "Titulo real - Medio" en el `<title>`. `parse_feed(..., google_news=True)` ahora separa el sufijo
  (`_separar_medio_google_news`) y usa el medio real como outlet — de paso, dedup() (outlet+título)
  fusiona automáticamente el mismo artículo llegado por RSS directo Y por Google News.
- **`is_junk()` + portadas/noticieros**: "Portada 25 septiembre 2026", "Noticias, jueves... | 24
  Horas" se descartan antes de llegar al agrupamiento (`_es_portada_o_noticiero`) — su vocabulario
  casi nulo los pegaba a cualquier cosa que ya estuviera en el cluster.
- **"Deriva por rep_titulo"** (el bug de fondo de las fusiones erróneas): `_match_registro`
  comparaba SOLO contra el titular representante (el más nuevo, que se desplaza con cada fuente
  nueva) — una cadena de coincidencias parciales podía alejarse del hecho original. Ahora se guarda
  `fundador_titulo`/`fundador_resumen` (inmutable, el primer artículo) y se compara contra los DOS
  anclajes: **mínimo** de las dos similitudes para la vía "palabras" (sin ninguna otra
  corroboración, la más propensa a encadenar), **máximo** para las vías asistidas
  (nombre/número/contenido, que ya tienen su propia corroboración específica) — usar mínimo también
  ahí rompía casos legítimos (una reacción que se parece más a la fuente fundadora que a la más
  reciente).
- Nueva vía **"palabras+contenido"** con umbral más bajo (`CLUSTER_THRESHOLD_CONTENIDO=0.15`, solo
  para esta vía): caso real "clínica de libros" (Expreso/Municipio) con Jaccard 0.18 pero 2 palabras
  específicas reales en común (`clinica`, `libros`).

`test_fase9_agrupamiento.py` (11 pruebas, con los titulares TEXTUALES reportados): los 4 pares que
debían unirse (CJNG/Samborondón vía sigla — requiere la reconciliación por embeddings del
trabajador, ver abajo —, feriado 9 de octubre, clínica de libros, jugador desaparecido) y los 6
casos que NO debían unirse (Santa Elena, cortes luz/agua, alcalde de Juchitán/Caso Blindado,
Trump-Xi/vetar periodistas, portadas, boletines de plantilla por ciudad/fecha distinta).

**Caso límite real, medido con Ollama real, NO resuelto**: "Pablo Emilio Ríos Maza fue
localizado..." vs. "Localizan a joven jugador del Deportivo Quito..." — CERO palabras/nombre/número
en común. Coseno de embeddings medido: **0.617** — MÁS BAJO que un par de control sin relación
("jugador" vs. "precio del dólar", 0.527-0.607) y muy por debajo del umbral (0.75). El modelo de
embeddings no conecta "Pablo Emilio Ríos Maza" con "jugador del Deportivo Quito" — haría falta una
base de conocimiento (qué jugador pertenece a qué equipo) que este proyecto no tiene. Documentado
como pendiente real, no un bug pendiente de arreglar con el enfoque actual.

**A4 — reconstrucción real del registro** (respaldado antes: `historias_registro.json.bak-fase9-
20260925_223241`, 4MB, conservado). Reconstruido desde el `fetch_cache.json` de la última corrida
real (sin golpear los 53 feeds de nuevo), con las reglas nuevas:

| métrica | antes (registro viejo) | después (1 pasada) |
|---|---|---|
| entradas totales | 2503 | 954 |
| entradas con 2+ fuentes | 506 | 237 |
| incoherencia (similitud fundador↔fuente más lejana < 0.08) | 39/506 (7.7%) | 14/237 (5.9%) |

(El total de entradas baja porque una sola pasada de `collect()` trae menos artículos que días de
acumulación — no es una pérdida de historial, es la base de partida; el registro vuelve a crecer
con cada pasada real de `serve`.) Con 10 pasadas de `_embed_pendientes_registro()` corridas después
(Ollama real, `nomic-embed-text`): **18 fusiones reales por parafraseo** confirmadas (400/954
entradas con embedding al momento de cerrar esta sesión, 514 pendientes — se completan solas con
`serve` corriendo). El caso Samborondón/CJNG específico quedó en 2 tarjetas (3+2 medios) al cierre
de esta sesión — la cobertura de embeddings todavía no había llegado a esas dos entradas puntuales
en el momento de medir; el mecanismo en sí está confirmado funcionando (ver arriba, coseno 0.785
para ese par exacto).

**Decisión explícita, no un olvido**: `cluster()`/`_mismo_hecho()` (agrupamiento SOLO intra-pasada)
se dejaron **intactos** — siguen usando sus propias pruebas (`test_cluster.py`,
`test_cluster_evento_generico.py`, todas siguen pasando). El pipeline real usa
`agrupar_con_memoria()` en su lugar desde la Fase 8; ahí es donde viven todos los arreglos de esta
fase. Restar `LUGARES_COMUNES` también en `cluster()` rompía el caso ya documentado de la inundación
de Guayaquil (el ÚNICO nombre propio compartido entre esos dos titulares reales era "Guayaquil", y
ese es justamente el caso correcto de unir) — la exclusión de lugares ubicuos solo tiene sentido
donde se compara contra un núcleo estable (el registro persistente), no en el enlace por máximo de
`cluster()`.

### B — La IA: el problema principal era A QUÉ TEXTO se engancha, no el modelo

**B1 — huella de contenido** (`monitor._huella_contenido()`, nuevo): `get_ia()`/`get_contexto()`/
`get_veredicto()` cachean por `fuentes[0].link` (clave estable a propósito, para que
`saved.json`/`notas.json` sigan apuntando a la misma historia) — pero calculaban el resultado UNA
sola vez, con el titular representante de ESE momento. Con la deriva de agrupamiento (A3) encima,
una historia que sumaba medios podía terminar mostrando un titular nuevo con una lectura/contexto/
veredicto que describía otro hecho por completo. Arreglo: cada entrada cacheada guarda una huella
(hash de titular+resumen representante+cantidad de fuentes); si no coincide con la actual, el hilo
trabajador la recalcula (compite por el mismo cupo de siempre, `IA_MAX_NEW`/`CONTEXTO_MAX_NEW`/
`VEREDICTO_MAX_NEW`) y el hilo rápido sigue mostrando lo viejo pero marcado
`ia_desactualizada`/`contexto_desactualizado`/`veredicto_desactualizado` — el dashboard muestra un
chip "⚠ desactualizada" en vez de presentar una lectura vieja como si fuera de hoy.
`test_fase9_huella.py` (4 pruebas, Ollama mockeado).

**B2 — cobertura: solo 623/2480 historias tenían lectura IA**, y el orden de "interés" a secas
dejaba competir notas internacionales de UN SOLO medio (medido: 744 fuentes de Infobae, 271 de
Semana) contra lo local por el mismo cupo fijo. `_prioridad_cupo_ia()` (nuevo, compartida por
`get_ia`/`get_contexto`/`get_veredicto`): local primero, ruido internacional de 1 medio al final del
cupo — nunca cambia el orden real de "stories" que ve el dashboard, solo en qué orden se GASTA el
cupo de la pasada.

**B3 — `evaluar_ia.py`** (nuevo, script standalone): `python evaluar_ia.py generar` arma
`evaluacion_ia.csv` con 40 historias reales (30 locales, 10 internacionales) y lo que el programa
ya calculó (categoría por palabras clave puras vs. por IA, ámbito por palabras clave vs. por IA,
Lectura editorial). Fernando llena a mano 3 columnas (`categoria_correcta`, `ambito_correcto`,
`lectura_correcta` sí/no) y corre `python evaluar_ia.py evaluar` para una precisión real —
palabras clave vs. IA, y qué % de Lecturas de verdad describen la nota. **No reemplaza el
diagnóstico de B1**: si la mayoría de "lectura_correcta=no" resulta ser el mismo patrón de huella
desactualizada, el problema real seguía siendo B1, no el modelo — el script lo señala si la
precisión de Lectura sale baja.

### C — Pulso social: de "posts sueltos por tema" a debate real por historia

Diagnóstico confirmado: `get_social()` consulta por TEMA ABSTRACTO ("Ambiente", "Asamblea/Leyes") —
Bluesky/Mastodon devuelven la conversación GLOBAL de esa palabra (Armenia/Venezuela/Delcy Rodríguez
bajo "Asamblea/Leyes"), sin ningún hilo real, solo publicaciones sueltas. `get_social()`/
`SOCIAL_CACHE` **no se tocaron** — `renderGap()` (Oportunidades) sigue usando esa data por tema
para el cálculo de brecha (Decisiones ya tomadas). Se agregó una pieza NUEVA y paralela:

**`monitor.get_social_historias()`** (nuevo, `social_historias_cache.json`): ancla la escucha a las
`SOCIAL_HIST_MAX` (def. 6) historias LOCALES más importantes (Guayaquil primero, después Ecuador),
buscando por sus ENTIDADES puntuales (`_social_query_historia()`: nombres propios/siglas del
titular + ciudad, reusa las mismas funciones de la Parte A) — nunca por el nombre de la categoría.
**Filtro de pertenencia** (`_post_pertenece_historia()`): un post solo cuenta si menciona una
entidad de la historia, la ciudad de la historia, o tiene señal clara de Ecuador — lo que no cumple
eso se descarta y queda CONTADO (`n_descartados`), nunca oculto en silencio. **Posturas con citas
reales** (`ia.clasificar_posturas()`, tarea CHICA y verificable a propósito — clasificar, no
resumir): a_favor/en_contra/duda/denuncia, cada grupo citando los IDs exactos de los posts que la
sostienen; cualquier postura sin IDs reales se descarta en CÓDIGO (`monitor.py` vuelve a filtrar
contra los IDs que de verdad existen en esa pasada, no confía solo en el candado del prompt).
**Hilo principal**: el post con más `comentarios_n`/`comentarios` (dato que `social.py` ya traía,
no un mecanismo nuevo). `test_fase9_social_historias.py` (5 pruebas, `social.recolectar`/
`ia.clasificar_posturas` mockeados): ancla por entidad no por categoría, filtro de pertenencia
descarta lo ajeno, postura con ID inventado se descarta, modo_lectura nunca toca la red, hilo
principal elige el post con más respuestas.

**Alertas dentro de Pulso social** (Problema C2): `#secAlertas` dejó de ser una pestaña propia —
es ahora el PRIMER bloque de `#secSocial` (mismo HTML/JS de `alertaCardHTML`/`renderAlertas()`, sin
tocar `alertas.py`), y el badge (`#alertasBadge`) se movió al botón de nav "Pulso social". El panel
"Por tema (resumen agregado)" (el `get_social()` de siempre) queda como segunda pieza, debajo del
nuevo "Debate real — por historia".

**No implementado esta fase, documentado como pendiente**: la curva de volumen por hora (el pedido
explícito decía "cuando haya X, la curva por hora" — sin X integrado a esta escucha todavía, se
difiere; ver Fase 9-D, X vive en un flujo aparte). El "resumen del hilo principal" es UN post con
sus respuestas ya guardadas por `social.py`, no una reconstrucción completa de un thread (esa
profundidad de dato no está disponible en Bluesky/Reddit/YouTube tal como los trae `social.py` hoy).

### D — Base de X: reemplazada por Apify a mitad de esta sesión

**Cambio de plan real, a mitad de trabajo**: se había empezado D con la API oficial de X (Bearer
Token pagado, $0.005/lectura) — Fernando decidió en cambio probar **X vía Apify** durante UN MES
(un actor de terceros que hace scraping SIN cuenta logueada), más barato para una prueba
($0.00025/tweet vs. $0.005/lectura). El código de la API oficial se descartó (nunca llegó a
conectarse a `monitor.py`/`alertas.py`) y `xapi.py` se reescribió para el backend de Apify —
misma arquitectura de PROVEEDOR (`xapi.py` expone las mismas funciones hacia los llamadores; el
backend "oficial" queda de `BACKEND` un STUB no implementado, por si algún día se retoma esa vía).

**Riesgo real, registrado a propósito** (actualiza "Decisiones ya tomadas"): esto NO es un acceso
autorizado por X — puede dejar de funcionar sin aviso si X bloquea al actor, y cualquier dato que
termine publicado debe verificarse contra el tweet original antes de citarlo como un hecho. Sigue
prohibido usar una cuenta propia logueada o scrapear X directamente desde este programa.

**Verificado en vivo por Fernando el 2026-09-26** (no en esta sesión, con su propia cuenta):
actor `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`, $0.00025/tweet (plan
FREE de Apify, $5 de crédito gratis/mes), entrada `{"searchTerms":["Guayaquil lluvias"],
"maxItems":20,"queryType":"Latest","lang":"es"}` devolvió 20 tweets reales en ~25s con los campos
documentados en el docstring de `xapi.py` (`id`,`text`,`createdAt`,`url`,`conversationId`,
`replyCount`,`author.userName`,`author.location`,`author.description`, etc.). Material
genuinamente útil confirmado: un aviso de @EmergenciasEc sobre lluvias con 25 respuestas (sirve
para alertas), un cruce político sobre las lluvias entre una candidata y la alcaldesa (sirve para
Pulso social), medios (Expreso/Extra/El Telégrafo) útiles para comparar quién publicó primero.

**`xapi.py` (reescrito)**:
- **Apagado por defecto**: sin `MONITOR_APIFY_TOKEN`/`x_config.json` (`{"apify_token":"..."}"`),
  `activo()` es `False` y ninguna función hace red. El token nunca se imprime, ni en `data.json`,
  ni en `last_error`, ni en ninguna URL logueada (`_error_http()` solo devuelve el código HTTP).
- **Presupuesto duro, día Y mes** (no "total" como el plan original de la API oficial — esto es
  una prueba de UN mes): `MONITOR_X_TOPE_DIA_USD` (0.16) y `MONITOR_X_TOPE_MES_USD` (4.50), dejan
  margen dentro de los $5 gratis de Apify. Antes de cada llamada se calcula el costo MÁXIMO
  (`maxItems × precio`) y, si se pasaría de cualquiera de los dos topes, no se hace la llamada —
  además, `maxTotalChargeUsd` viaja SIEMPRE en la llamada a Apify, para que la plataforma misma
  corte si el código se equivocara calculando.
- **Costo REAL, no solo estimado**: la corrida se dispara con el endpoint asíncrono
  (`POST /v2/acts/<actor>/runs?waitForFinish=120`, no el endpoint sync-get-dataset-items, que NO
  devuelve el `runId`) para poder consultar después `usageTotalUsd` en `GET /v2/actor-runs/<id>` —
  si ese campo no viene (best-effort, no verificado en vivo por esta sesión con un token real), se
  usa el costo ESTIMADO en su lugar, nunca se pierde el registro del gasto.
- **Modo simulación** (`MONITOR_X_SIMULAR=1`, o `xapi.simular()`): arma las consultas reales a
  partir de las historias actuales y proyecta costo por día y por mes — CERO llamadas de red, sin
  necesitar token siquiera.
- **Capas** (peor caso ≈ 630 tweets/día ≈ $0.16/día, confirmado con `simular()`):
  **Historias** (6 locales top, 25 tweets c/u, 2×/día, búsqueda por entidades — reusa
  `_social_query_historia()` de la Parte C); **Debate** (1×/día, respuestas al tweet con más
  `replyCount` de las 3 historias con más volumen, vía `conversation_id:`, con **respaldo**
  automático al actor `apidojo/tweet-scraper` si el operador no trae nada con el principal —
  **no verificado en vivo** si el operador funciona con el actor principal, queda como pendiente
  real); **Alertas Guayaquil** (1×/hora, términos compuestos tipo+"Guayaquil" — NO términos
  sueltos, para no arriesgar que el actor trate cada uno como búsqueda independiente y traiga
  "incendio" de cualquier país —, dedup por ID ya visto en `x_cache.json`).
- **Clasificación de autor** (`clasificar_autor()`): persona/medio/institución/político —
  `social.es_cuenta_medio()` + lista editable de cuentas institucionales conocidas
  (`CUENTAS_INSTITUCION`) + palabras de cargo en la bio.
- **Integrado a `alertas.py`** como fuente `"x"` (`_recolectar_x()`, llamada desde
  `recolectar_senales()`): **sin** un filtro de pertenencia aparte — `registrar_senal()` YA exige
  que el texto mencione un tipo+lugar reconocido (`detectar_tipo`/`detectar_lugar`), más específico
  que mirar `author.location` (que además descartaría alertas reales de perfiles sin ese campo
  lleno). La corroboración se deduplica por `(fuente, autor)` con el mismo mecanismo ya existente
  (`_recomputar_estado`), sin cambios ahí. `fecha_iso()` convierte el formato clásico de X
  ("Sat Sep 26...") a ISO, que es lo que `registrar_senal()` espera.
- **Integrado a `monitor.py`**: `xapi.pasada()` corre en `enrich_pass` (hilo trabajador, nunca
  `run_fast`), reusando las mismas historias/entidades de Pulso social (Parte C) y los mismos
  `TIPO_KEYWORDS`/`BARRIOS_GYE` de `alertas.py`. `estado_x` (gasto hoy/mes, restante, activo/no)
  expuesto en `data.json` vía `xapi.estado_dashboard()` — nunca el token. Panel nuevo "Prueba X
  (Apify)" en Estadísticas (gasto real, tope, restante).
- `test_fase9_xapi.py` (15 pruebas, sin red real — fixtures con la forma REAL verificada por
  Fernando): sin token queda apagado (2 variantes: env var y `x_config.json`), el token nunca
  aparece en `estado_dashboard()`/`last_error`, la simulación no hace red (3 pruebas, incluida
  `pasada()` completa), el tope diario corta antes de llamar, un 402 queda reportado sin cobro, un
  costo real reportado por Apify se registra tal cual (y se usa el estimado si Apify no lo da), un
  ID repetido no se procesa dos veces, un tweet de @EmergenciasEc sobre inundaciones en Guayaquil
  crea una alerta real, un tweet de medio se clasifica "medio" (no cuenta como voz ciudadana), una
  cuenta institucional conocida se clasifica "institución".

**Verificado en vivo con el token real de Fernando** (cargado en `x_config.json` al cierre de esta
sesión): `xapi.buscar_historia("Guayaquil", max_items=20)` devolvió **20 tweets reales** (autores
reales, texto real, `createdAt` real) en unos segundos — confirma el flujo completo (token →
corrida asíncrona → dataset → parseo) funcionando de punta a punta.

**Hallazgo real, no esperado**: el costo reportado por Apify para esta corrida fue **`usageTotalUsd:
0`** (inspeccionado el run crudo vía `GET /v2/actor-runs/<id>`: `chargedEventCounts` sí registra 20
eventos "tweet", pero `accountedChargedEventCounts` da 0 y `eventUsage.tweet.eventTotalUsd` da 0,
con `platformUsageBillingModel: "DEVELOPER"`). Osea: **la corrida fue real y gratis** — no un error
de mi código (usa el valor que Apify reporta, nunca inventa uno): `_registrar_gasto()` no anotó
nada porque no hubo nada que cobrar (`if monto <= 0: return`, ya en el código). Posible explicación,
NO confirmada: este actor puede tener resultados de cortesía/un umbral antes de empezar a cobrar de
verdad contra los $5 de crédito mensual. **Recomendación real para Fernando**: revisar
`estado_x`/el panel "Prueba X" en los próximos días de uso normal — si el gasto sigue en $0 después
de varias corridas reales, es una buena noticia (la prueba de un mes podría no gastar nada); si en
algún momento empieza a subir, ahí se confirma que el "gratis" de hoy era un umbral inicial, no la
tarifa real. No se probó todavía si el operador `conversation_id:` funciona con el actor principal
(la capa "Debate" no se disparó en esta verificación puntual, solo "Historias") — confirmar con la
primera corrida real completa del trabajador.

**`xapi.simular()` corrido de verdad contra las historias reales de Guayaquil de HOY** (con `serve`
reiniciado, sin necesitar token): de las 6 historias top elegidas por `_historias_top_social()`,
**3 de 6 eran pronósticos del clima/fenómeno de El Niño** (el pendiente ya documentado de A3,
"boletín con plantilla" — esas notas siguen contando como historias separadas y de alto ranking).
Esto es relevante para X: sin una prioridad que las baje, una parte real del presupuesto diario de
Apify se gastaría en boletines de clima en vez de en historias de más valor periodístico —
**pendiente real, no resuelto**: `_historias_top_social()`/la selección de historias para X no
filtra por "es un boletín de plantilla" todavía. Costo proyectado real de esta corrida: **$0.1575/
día** (dentro del tope diario de $0.16) pero **$4.725/mes** proyectando 30 días seguidos al tope
diario — **por encima** del tope mensual de $4.50. No es un bug (`_cabe_en_presupuesto()` ya
revisa los dos topes antes de cada llamada real, así que el mensual se auto-limita solo, cortando
los últimos 1-2 días de un mes de 30 si se gasta el diario completo todos los días), pero es una
tensión real entre los dos valores por defecto que vale la pena que Fernando sepa: si quiere
consistencia perfecta día a día durante los 30 días completos, `MONITOR_X_TOPE_DIA_USD` debería
bajar a `4.50/30 ≈ 0.15` en vez de `0.16`.

### Verificación final de esta sesión

- **Suite de pruebas**: 5 archivos nuevos de esta fase (`test_fase9_agrupamiento.py` [11],
  `test_fase9_embeddings.py` [3], `test_fase9_huella.py` [4], `test_fase9_social_historias.py` [5],
  `test_fase9_xapi.py` [15] — 38 pruebas nuevas en total) sumados a los ya existentes — **232
  pruebas en total, corrida completa en verde** (contado de verdad con `unittest discover`, no
  estimado; incluye `test_cluster.py`/`test_cluster_evento_generico.py` sin cambios de
  comportamiento, confirmando que `cluster()` intra-pasada sigue intacto).
- **Reconstrucción real del registro** (ver Parte A4): backup guardado, antes/después medido con
  datos reales, 18 fusiones por parafraseo confirmadas con Ollama real corriendo.
- **`estado_embeddings`**: confirmado pasando de "0 con embedding" (oculto) a expuesto en
  `data.json` y en el panel "Salud de los datos", con reintento automático si Ollama no responde al
  arranque.
- **Reinicio real de `serve` con TODO el código de la Fase 9 junto (A+B+C+D)**: confirmado sin
  ninguna instancia duplicada corriendo antes de arrancar. Bindeó el puerto casi al instante (el
  registro ya venía reconstruido de la Parte A4). Confirmado por HTTP real contra el servidor
  real (no solo el archivo en disco):
  - `estado_embeddings`: **"ok (nomic-embed-text) -- 422/1004 historias con embedding"** — subiendo
    solo (era 400/954 al cierre de la Parte A), confirma que el trabajador lo sigue completando
    de fondo sin que nadie lo empuje a mano.
  - `salud_fuentes` incluye la fila nueva "Embeddings (agrupamiento)" con `ok: true` y el mismo
    detalle de arriba — visible en el panel "Salud de los datos" del dashboard.
  - `estado_x`: `{"activo": false, "estado": "desactivado: falta token de Apify (...)", "gasto_hoy":
    0.0, "gasto_mes": 0.0, "tope_dia": 0.16, "tope_mes": 4.5}` — honesto, sin inventar actividad,
    tal como se diseñó.
  - `estado_ia`/`estado_contexto`/`estado_veredicto`/`estado_declaraciones` mostrando cachés reales
    ya acumulados (193/1001, 62/1001, 73/1001, 2/1001 respectivamente) — el trabajador seguía
    activo y procesando de fondo (confirmado con `ollama ps`: `monitor-critico` cargado en VRAM en
    el momento de la medición).
  - `estado_social_historias`/`social_historias` **no llegaron a poblarse dentro de la ventana de
    esta verificación** (~4 minutos de espera activa): el trabajador todavía estaba ocupado con el
    backlog de interpretaciones pesadas (`monitor-critico`, ~100s cada una) de pasadas anteriores
    cuando se cerró la sesión — `get_social_historias()` corre DESPUÉS de esos pasos en
    `enrich_pass`, así que no alcanzó a llegar en el tiempo medido. El mecanismo en sí ya está
    probado de punta a punta con `ia`/`social` mockeados (`test_fase9_social_historias.py`, 5
    pruebas) — falta la confirmación EN VIVO con datos reales, que va a aparecer sola en cuanto el
    trabajador llegue a esa parte de una pasada (unos minutos más de `serve` corriendo).
  - `xapi.simular()` corrido contra las 6 historias reales de Guayaquil de esa misma corrida (ver
    el hallazgo real más abajo, en la sección D) — sin necesitar token.

### Pendientes reales de la Fase 9

1. El caso límite "jugador desaparecido" (A3) no se resuelve ni con embeddings — medido, no
   arreglado; haría falta una base de conocimiento externa que este proyecto no tiene.
2. Samborondón/CJNG (A4) quedó en 2 tarjetas al cierre de esta sesión — se resuelve solo cuando la
   reconciliación por embeddings del trabajador llegue a esas entradas (`serve` corriendo un rato).
3. El "boletín con plantilla" por ciudad/fecha (A3) cierra el pendiente de la Fase 8 para ESE
   patrón puntual, pero no es un mecanismo general — un boletín nuevo con otra plantilla (no clima/
   feriado/servicio básico) puede seguir necesitando su propio veto si aparece.
4. B3 (`evaluar_ia.py`) generó el CSV de muestra en esta sesión pero **Fernando todavía no lo llenó
   a mano** — la precisión real de palabras clave/IA/Lectura queda pendiente de su evaluación.
5. C: sin curva de volumen por hora (depende de X, Parte D); "hilo principal" es un post con sus
   respuestas ya guardadas, no una reconstrucción completa de thread.
6. D: no verificado si el operador `conversation_id:` funciona con el actor principal (asume que
   sí, con respaldo automático si no) — confirmar con la primera llamada real. El campo
   `usageTotalUsd` de la API de Apify tampoco se confirmó en vivo (asume ese nombre según la
   documentación pública de Apify, no un tweet de prueba real de esta sesión).
7. `social_historias`/`estado_social_historias` no llegaron a poblarse EN VIVO dentro de la ventana
   de verificación de esta sesión (el trabajador seguía con backlog de interpretaciones pesadas) —
   confirmar en `data.json` en cuanto `serve` lleve más tiempo corriendo.
8. La selección de "historias top" para X (y, en menor medida, para Pulso social) no filtra
   boletines de plantilla (clima/fenómeno de El Niño) — 3 de las 6 historias elegidas en la
   simulación real de hoy eran justamente eso (ver hallazgo real en la Parte D).

**Primera acción real que le toca a Fernando**: crear una cuenta en Apify (si no tiene una),
entrar a **Settings → API & Integrations**, copiar su **Personal API token**, y guardarlo en
`x_config.json` (nunca en el código). Comando para crear ese archivo (reemplazar el texto entre
comillas por el token real antes de correrlo):

```powershell
'{"apify_token": "PEGA_AQUI_TU_TOKEN_DE_APIFY"}' | Set-Content -Encoding utf8 x_config.json
```

Con eso ya alcanza — `xapi.py` lo lee solo, no hace falta reiniciar nada más que `serve`.

## Fase 10 (2026-09-26) — migración de la IA a la nube (Gemini): transporte conectado + panel de gasto

**Esta sección reemplaza lo que dicen arriba "Requisitos en la PC" y la descripción de `ia.py` sobre Ollama.**
Motivo (Fernando): los modelos locales (qwen2.5:3b, monitor-critico, nomic-embed-text) colapsaban el
hardware, tumbaban el servidor y corrompían pasadas de `enrich_pass`. Se pasa a Gemini en la nube.

**Nota de proceso**: esta sección se escribió originalmente a mitad de la migración (cuando el
transporte todavía eran funciones que devolvían `None`) y quedó DESACTUALIZADA sin que nadie la
volviera a tocar — el código real (`ia.py`) avanzó dos etapas más (transporte conectado de verdad)
en la misma sesión, sin documentarlo. Mismo patrón de "código real por delante del documento" que ya
pasó varias veces en este proyecto (ver `ia.interpretar()`/`_temas_por_relevancia()`/`/api/nota` en
secciones anteriores) — la diferencia es que acá el documento se quedó ATRÁS, no que el código nunca
se conectara. Reescrita hoy con el estado verificado de verdad contra el código y una corrida real de
`serve`.

### Estado real (transporte conectado, verificado en vivo)

- `ia.py` ya no tiene nada de Ollama (sin `localhost:11434`, `HOST`, `IA_CTX`, `PREFER`, `CHAT_MODEL`,
  `modelos()`, `_post`, `_post_stream`). Las tres funciones de transporte (`ia._generar()`,
  `ia._generar_stream()`, `ia.embed()`) hablan de verdad con la API REST de Gemini
  (`generativelanguage.googleapis.com/v1beta`), sin el SDK `google-generativeai` (sin soporte desde el
  30-11-2025) — todo con `urllib`, misma regla de oro del proyecto. Prompts, candados en código y
  firmas públicas de cada función pública **no cambiaron** (`monitor.py`/`agente.py`/`casos.py`/
  `declaraciones.py` llaman exactamente lo mismo que llamaban con Ollama).
- **Perfiles** (reemplazan a los "modelos" de Ollama): `ia.PERFIL_RAPIDO` (triaje/extracción por lotes:
  `analizar`, `extraer_entidades`, `contextualizar`, `veredicto_contraste`, `clasificar_posturas`,
  `extraer_declaracion`, `traducir_titular`, `coincide_dominio`, sugerencias de casos, chat "rápido") →
  default `gemini-3.8-flash`. `ia.PERFIL_PROFUNDO` (`interpretar`, `comparar_declaraciones`, chat
  "profundo", respuesta final del Asistente y del chat de casos) → default `gemini-3.1-pro-preview`
  (en PREVIEW; si deja de existir o da 404 sostenido, `_resolver_modelo()` cae solo al perfil rápido).
  El parámetro `forzado` que siguen aceptando varias funciones es solo compatibilidad con los
  llamadores existentes: ya no elige un modelo de Ollama, se ignora.
- **Clave**: `GEMINI_API_KEY` en `.env` (raíz), leída con stdlib (`_cargar_env`, sin `python-dotenv`,
  no pisa variables ya definidas). Va SIEMPRE en el header `x-goog-api-key` (nunca en la URL) y NUNCA
  se imprime, ni en `last_error`, ni en `data.json`, ni en ningún mensaje de error (`_error_http`
  limpia cualquier URL antes de usarla en un mensaje). Verificado leyendo el código y confirmando que
  `estado_ia_nube`/`estado()`/`last_error` en una corrida real nunca traen la clave, solo texto
  descriptivo.
- **Presupuesto duro, real, medido desde `usageMetadata`** (nunca estimado a ciegas): `ia_gasto.json`
  (gasto por día/mes + historial de las últimas 300 llamadas) y `ia_nube_estado.json` (catálogo de
  modelos confirmados + pausas por 429/cuota agotada, TTL 1h). Topes por variable de entorno
  (`MONITOR_IA_TOPE_DIA_USD`, def. $1.00; `MONITOR_IA_TOPE_MES_USD`, def. $20.00 — **sin override en
  el `.env` de esta PC hoy**, quedan en el default; si Fernando quería un tope más chico como $0.20/día
  hace falta agregar `MONITOR_IA_TOPE_DIA_USD=0.20` al `.env`, todavía no está puesto).
  `_cabe_en_presupuesto()` corta ANTES de llamar si el costo máximo posible se pasaría de cualquiera de
  los dos topes. Precios verificados en vivo el 2026-09-26 en la página oficial de precios de Gemini
  (`PRECIO_RAPIDO_INPUT/OUTPUT`, `PRECIO_PROFUNDO_INPUT/OUTPUT`, `PRECIO_EMBED_INPUT` — este último
  estimado a falta de que `gemini-embedding-001` figure en la página actual de precios).
- `agente.py`: ciclo de herramientas → `ia._generar_json` (perfil rápido); respuesta final →
  `ia._generar_stream` (perfil profundo). `_responder_final_stream` conserva `modelo_fn`/`num_ctx`/
  `forzado_final` solo por compatibilidad con `monitor.py` (se ignoran).
- `monitor.py`, dos cambios quirúrgicos: (1) `get_declaraciones` chequea `ia.disponible()` antes del
  lote — sin eso, con la IA caída, cada nota quedaba en `_procesadas` sin declaración para siempre. (2)
  `_social_model()` devuelve `None` y `get_social` salta el OSINT sin marcar `osint_error` (si lo
  marcara, `SOCIAL_OSINT_RETRY_TTL` re-consultaría redes cada 20 min en vez de 6 h, gastando cuota de
  YouTube). `social.py` NO se tocó (pieza protegida); su `analizar_osint` todavía apunta a Ollama, pero
  ya nadie la llama.
- **Piezas protegidas, sin cambios**: `xapi.py`, `social.py`, `alertas.py`, `gdelt.py`, `sercop.py`,
  `feeds.py` (y `redes.py`/`tiktok.py`, que orquestan X/TikTok). Ninguna importa `ia`.
- **Hilo rápido**: `run_fast` solo lee cachés de IA (`modo_lectura=True`); la única fuga hacia Ollama era
  `construir_salud_fuentes` → `ia.embed_disponible()` (hasta 8 s de timeout); ahora es inmediato.
- **Embeddings — ojo acá**: los vectores viejos de nomic-embed-text en `historias_registro.json` y
  `casos/*/index.sqlite3` NO son comparables con los de `gemini-embedding-001` (dimensiones/espacio
  distintos). Descartarlos o marcarlos por modelo antes de mezclar. Documentos subidos a un caso
  mientras no haya embeddings quedan sin vector (no se pierden, pero hay que reindexarlos). No
  investigado a fondo esta pasada si `historias_registro.json` ya tiene una mezcla de los dos.
- `Modelfile.critico` (definición del modelo `monitor-critico` de Ollama) se **borró** hoy — ya no lo
  usa nada desde que Ollama se retiró por completo.

### Parte C (2026-09-26) — panel de gasto de Gemini en el dashboard

Faltaba exponer el gasto real: `ia.py` ya calculaba todo (`estado_gasto()`, `estado()`,
`backend_listo()`) pero `monitor.py` nunca lo volcaba a `data.json`, y el dashboard no tenía panel.
Delegado a Codex CLI (`codex exec`, ver flujo de delegación más abajo) con instrucciones exactas
(snippets reales de `ia.py`/`monitor.py`/`dashboard_template.html`) para minimizar el riesgo de que
inventara una forma distinta.

- `monitor.py` (`write_outputs`): nueva clave `data.json["estado_ia_nube"]` = `{"activo":
  ia.backend_listo(), "estado": ia.estado(), **ia.estado_gasto()}` (o el default seguro si `ia is
  None`) — junto a `estado_ia`/`estado_embeddings`, mismo patrón que `estado_redes` (Fase 9, Parte D).
- `dashboard_template.html`: panel nuevo "IA en la nube (Gemini) — gasto real" en Estadísticas, junto
  al de "Prueba X (Apify)", con la función `renderEstadoIA()` (mismo patrón visual que
  `renderXPrueba()`: 4 tarjetas — gastado hoy/tope, gastado mes/tope, restante hoy, restante mes — más
  una línea de estado en texto). Nunca muestra la clave, solo lo que `estado_ia_nube` expone.
- **Bug real encontrado de paso, NO corregido esta pasada** (fuera del pedido puntual, queda para que
  Fernando decida): el panel de "Prueba X (Apify)" que YA EXISTÍA está roto — `monitor.py` guarda el
  estado bajo la clave `data.json["estado_redes"]`, pero `dashboard_template.html` lee
  `DATA.estado_x` (nunca existe esa clave) — el panel de X siempre muestra "sin datos" sin importar
  el gasto real. Se evitó a propósito repetir el mismo error con el panel nuevo de Gemini (mismo
  nombre `estado_ia_nube` en las dos puntas, confirmado con `curl` contra el servidor real). Arreglo
  de una línea si se quiere corregir (cambiar `DATA.estado_x` por `DATA.estado_redes` en
  `dashboard_template.html`, o renombrar la clave en `monitor.py`) — no se tocó porque no era parte de
  esta tarea.
- **Verificado en vivo, servidor real** (`python monitor.py serve`, sin otra instancia corriendo,
  puerto 8000 arriba en ~60s): `curl http://127.0.0.1:8000/data.json` trajo
  `estado_ia_nube: {"activo": true, "estado": "ok (nube: gemini-3.8-flash /
  gemini-3.1-pro-preview) -- gasto hoy $0.0003", "gasto_hoy": 0.00026, "gasto_mes": 0.20083,
  "tope_dia": 1.0, "tope_mes": 20.0, "restante_hoy": 0.99974, "restante_mes": 19.79918}` — dato real,
  no simulado (el gasto ya venía acumulado de la migración de hoy). `curl` contra `dashboard.html`
  confirmó el panel/función servidos de verdad (`grep` positivo de `estadoIaNube`/`renderEstadoIA`).
  **No verificado**: cómo se ve el panel en un navegador real (esta sesión no tiene esa herramienta) —
  la estructura HTML/JS se confirmó con `node --check` sobre el `<script>` servido y con los datos
  reales llegando bien, pero la parte visual queda pendiente de que Fernando la mire.
- Suite de pruebas completa corrida tras el cambio: **256 pruebas, 241 en verde** — los 15 errores son
  los mismos y ya conocidos de `test_fase9_xapi.py` (buscan `xapi.GASTO_PATH`, que se movió a
  `redes.py` en la Fase 9 Parte D3; no relacionados con este cambio, no introducidos hoy).
- **Calidad editorial de `interpretar()` con la API real** (Gemini Pro, perfil profundo) — revisada
  sobre 5 lecturas YA generadas por el trabajador en esta corrida real (no una llamada de prueba
  aislada, para no gastar presupuesto de más): 4 de 5 mostraron lectura editorial genuina, no
  paráfrasis (ej. sobre el portafolio del Biess: "¿Quiénes son los verdaderos beneficiarios de este
  incremento en inversiones y créditos?"; sobre las lluvias de fin de septiembre: conecta con la crisis
  de las hidroeléctricas del austro, un ángulo real). La 5ta lectura parecía un caso grave de
  alucinación (hablaba de lavado de activos y criptomonedas sobre una nota de un boxeador) — investigado
  y NO es un problema de Gemini: es una historia mal agrupada por el clustering (dos notas de medios
  distintos, sin relación real, fusionadas por error) que el propio mecanismo de huella de contenido
  (Fase 9) ya había detectado y marcado `ia_desactualizada: true` — el sistema de seguridad ya
  construido funcionó como se diseñó, mostrando el dato viejo pero avisando que está vencido, en vez de
  presentarlo como si fuera confiable. Pendiente real: por qué esas dos notas se agruparon (bug de
  clustering, no de esta fase) — no investigado a fondo esta pasada.
- **Hallazgo aparte, no corregido**: hay dos carpetas `backups_20260923_205120/` y
  `backups_20260924_221812/` en la raíz del proyecto con copias completas de código de sesiones
  anteriores (de antes de la migración a Gemini) — quedan ahí sin tocar; si ya no hacen falta,
  confirmar con Fernando antes de borrarlas (podrían ser un respaldo intencional).

### Flujo de delegación a Codex CLI (adoptado en esta sesión, 2026-09-26)

Regla de Fernando: para cambios de código, escribir el requerimiento + contexto real en
`tarea_codex.md`, invocar `codex exec --skip-git-repo-check -s workspace-write "Lee tarea_codex.md y
guarda el resultado en <archivo de salida>"` (permiso `Bash(codex exec:*)` ya agregado a
`.claude/settings.local.json` de esta sesión), leer y REVISAR el resultado (nunca aplicarlo a ciegas:
mismo criterio de siempre en este proyecto — probar antes de integrar), aplicarlo a los archivos
reales, y borrar los archivos puente. Para una tarea que toca más de un archivo (como el panel de
gasto de arriba), el archivo de salida es un único `.md` con un bloque de código por archivo target,
en vez de forzar un solo nombre de archivo con una sola extensión.

## Fase 11 (2026-09-28) — el proyecto se llama "Spike": empaquetado real, limpieza, ranking y retrieval del Asistente

Cuatro pedidos de Fernando, con el mismo flujo de delegación a Codex de la sección de arriba para los
tres cambios de código (`compilar.bat`, `monitor.py`, `dashboard_template.html`, `herramientas.py`) —
`tarea_codex.md` con el contexto real ya diagnosticado y los fragmentos EXACTOS a reemplazar,
`codex exec` guardó `respuesta_codex.md`, se revisó a mano cada bloque antes de aplicarlo con Edit a
los archivos reales, y los dos archivos puente se borraron al cerrar.

- **`logo.ico` generado con stdlib puro, sin Pillow**: `logo.png` (500x542, RGB truecolor 8-bit, sin
  interlace — confirmado leyendo el IHDR a mano) se convirtió con un script chico
  (`png_to_ico.py`, corrido desde el scratchpad de la sesión, no queda en el repo) que decodifica el
  PNG (zlib + des-filtrado de los 5 tipos de filtro de PNG), lo reescala con un filtro de caja (box
  filter, promedio de bloques — nunca agranda, solo reduce) a los 6 tamaños estándar de ícono de
  Windows (256/128/64/48/32/16), lo centra sobre un lienzo cuadrado transparente, y arma un `.ico`
  multi-resolución válido (PNG-in-ICO, formato soportado desde Windows Vista). Se prefirió esto a
  `pip install Pillow` para no romper la regla de oro del proyecto (única excepción ya pre-autorizada:
  `pypdf`) — confirmado que no había Pillow instalado en esta PC antes de decidir el camino stdlib.
  `logo.ico` quedó en la raíz del proyecto (72958 bytes, 6 resoluciones, verificado leyendo su propio
  directorio ICO de vuelta).

- **Bug real en `compilar.bat`, diagnóstico inicial y corrección REAL (probada compilando de
  verdad, no solo leyendo el .bat)**: la línea `    --standalone ^ --include-package=webview` tenía el
  `^` de continuación de línea de cmd.exe A MITAD de la línea (no al final absoluto) —
  `compilar_log.txt` de una compilación anterior (de una versión previa del .bat) lo confirma: las
  `Nuitka-Options:` reales usadas ese día NUNCA incluían `--include-package=webview`. El primer
  intento de arreglo fue separar esa línea en dos líneas propias (cada una con su `^` final) para que
  `--include-package=webview` SÍ se pasara — pero al compilar de verdad con eso, Nuitka **fallo real**:
  `FATAL: pywebview: Conflict between user and plugin decision for module
  'webview.platforms.android'`. Causa real: Nuitka YA detecta e incluye pywebview solo (análisis
  estático del `import webview` en `monitor.py`, sin necesitar ninguna bandera) — de hecho el build
  ANTERIOR (antes de tocar nada, con el caret roto de siempre) ya traía la carpeta `webview/` completa
  en el standalone sin esa bandera, confirmado revisando `dist_compilado/monitor.dist/webview/` de una
  compilación vieja. Forzar `--include-package=webview` de más choca con la decisión propia del
  plugin de Nuitka sobre el submódulo Android (irrelevante en Windows) y hace fallar la compilación
  entera. **Arreglo final, verificado con una compilación real completa**: sacar esa bandera del todo
  (queda un comentario `REM` en `compilar.bat` explicando por qué no se agrega, para que nadie la
  vuelva a sumar "para estar seguros" en el futuro) — Nuitka sigue incluyendo `webview/` completo solo
  (confirmado en el log real: "Nuitka-Plugins:dll-files: Found 4 files DLLs from webview installation"
  + los `.js`/`.jar` de pywebview listados uno por uno). Es decir: **el `--include-package=webview`
  faltante NUNCA fue el problema real** — el síntoma original ("no funciona por sí solo") sigue sin una
  causa funcional confirmada más allá de la falta de ícono/nombre/consola limpia (ver abajo), que sí
  eran reales y ya estaban mal.
  Además, en el mismo cambio: se agregó `--windows-icon-from-ico=logo.ico` (ícono nativo del .exe,
  confirmado en el log: "Nuitka-Postprocessing: Adding 6 icon(s) from icon file 'logo.ico'"),
  `--output-filename=Spike.exe` (el ejecutable final ya no se llama `monitor.exe`, confirmado:
  "Successfully created '...\dist_compilado\monitor.dist\Spike.exe'"), y se cambió
  `--windows-console-mode=force` por `--windows-console-mode=attach` (modo recomendado de Nuitka para
  una app de ventana nativa con consola opcional: con doble clic desde el Explorador NO aparece
  ninguna consola negra de más, la ventana de pywebview se abre directo; si se corre desde una
  terminal ya abierta, sí se adjunta a esa consola para poder ver los `print()` de diagnóstico).
  `monitor.py` NO se renombró (ver la nota de nombre de proyecto arriba) — la carpeta standalone que
  genera Nuitka sigue llamándose `dist_compilado\monitor.dist\`, pero el ejecutable adentro ya es
  `Spike.exe` (26.7 MB, carpeta completa 46 MB).
  **Compilación real corrida de punta a punta en esta sesión** (no solo el script arreglado sin
  probar): primer intento con `--include-package=webview` FALLÓ de verdad (el error de arriba,
  confirmado en `compilar_log.txt` y en `nuitka-crash-report.xml`, que se borró después de
  diagnosticarlo); segundo intento sin esa bandera **terminó bien**, `Spike.exe` existe en
  `dist_compilado\monitor.dist\Spike.exe`. Nota de proceso real (no un bug del proyecto): la primera
  forma de invocar la compilación desde esta sesión (`cmd /c compilar.bat` vía PowerShell) fallaba con
  "'compilar.bat' is not recognized" de forma consistente aunque el archivo SÍ estaba ahí (confirmado
  con `cmd /c dir compilar.bat`); invocar el .bat directo (`& ".\compilar.bat"`) sí funcionó — quedó
  sin resolver del todo POR QUÉ `cmd /c <nombre>.bat` fallaba especificamente en este entorno, pero no
  es un problema del programa en sí, solo de cómo se lo invocó esa vez.
  **Pendiente real, no verificado en esta pasada**: el propio `Spike.exe` no se llegó a EJECUTAR con
  doble clic en esta sesión (solo se compiló) — falta que Fernando lo pruebe en su PC. El `.env` real
  quedó excluido del build a propósito (mismo criterio documentado siempre en el script); copiar el
  `.env` propio junto a `Spike.exe` es un paso manual de Fernando (el propio programa se negó a copiar
  la clave automáticamente por seguridad — un clasificador del entorno bloqueó esa acción puntual por
  "posible fuga de credencial", correctamente).

- **Limpieza (solo lo pedido explícitamente, nada más)**: borrados `dist_compilado\monitor.build\`
  (caché de compilación de Nuitka, **293 MB** — medido antes de borrar), la carpeta `handoff_ux\`
  (11 MB) y `__pycache__\` (chico). Tamaño total del proyecto: **440 MB → 136 MB**. Deliberadamente
  NO se tocó nada más, aunque se encontraron otros candidatos pesados durante el diagnóstico
  (`handoff_ux.zip`, las carpetas `backups_2026...` ya anotadas como pendiente de confirmar con
  Fernando en la sección de arriba, y los `.bak` de `historias_registro.json`) — el pedido fue
  específico a esos tres elementos y el resto son datos/respaldos, no caché, así que quedan para que
  Fernando decida aparte.

- **Ranking: bono de "alto impacto" para sucesos graves locales** (`monitor._bono_impacto`,
  `monitor.TEMAS_ALTO_IMPACTO = {"Crimen/Violencia", "Narcotrafico"}`): el cálculo de `s["interes"]`
  (duplicado en `run_once`/`run_fast`, ver `_peso_outlets`) no tenía ninguna señal de GRAVEDAD del
  hecho — solo premiaba cuánta cobertura YA había juntado una historia (medios, artículos, demanda,
  recencia). Caso real confirmado en `data.json` en vivo el mismo día: "Una mujer fue baleada tras
  retirar USD 2.000 de una entidad bancaria en el centro de Guayaquil" (ambito local, ciudad Guayaquil,
  tema Crimen/Violencia, un solo medio en los primeros minutos) rankeaba muy por debajo de coberturas
  internacionales de puro volumen (una nota sobre Irán con `interes` > 1100 por tener muchísimos más
  medios/artículos) en el listado global mezclado de Noticias — que es justo la vista por defecto.
  Arreglo: bono FIJO de 150 puntos que solo aplica a historias de ámbito LOCAL con tema
  `Crimen/Violencia` o `Narcotrafico` (deliberadamente no "Carceles"/"Policia/Militar", que suelen ser
  notas institucionales de rutina, no un hecho grave puntual) — bono fijo y no un multiplicador a
  propósito, para no forzar que una nota local de un solo medio SIEMPRE supere a una cobertura
  internacional masiva (eso sería mentir el orden, no priorizar), solo acercarla al tope. Se guarda
  además `s["alto_impacto"]` (booleano) para que el dashboard pueda marcarla visualmente aparte del
  puntaje — `cardHTML()` (`dashboard_template.html`) ahora muestra una etiqueta roja
  "🔴 Alto impacto" en la fila de tags de la tarjeta cuando aplica, visible aunque el bono de puntos no
  alcance a superar una historia internacional gigante.

- **Asistente: bug real de "retrieval" (por qué no encontraba la nota de la mujer baleada)** —
  confirmado que la nota SÍ estaba en `data.json` (no era un problema de datos ni de que el Asistente
  leyera mal el archivo); el bug estaba en el MATCH de texto libre. `herramientas.buscar_historias`/
  `buscar_guardadas`/`buscar_notas` (los tres, código idéntico duplicado) filtraban por `q` con una
  SUBCADENA LITERAL completa (`q.lower() in blob`) — exige que la frase exacta que arma el modelo
  aparezca tal cual, continua, dentro de titular+resumen. En la práctica esto casi nunca pasa: el
  modelo nunca reproduce el texto exacto de la nota, y en el caso real la nota dice "baleada" mientras
  Fernando preguntó por el "asesinato" — ni una sola palabra en común entre esa palabra clave y el
  titular real. Tampoco había ninguna normalización de tildes (a diferencia de TODO el resto del
  proyecto, que usa `norm()`/`strip_accents` en cualquier comparación de texto — `herramientas.py` es
  standalone a propósito, ver su propio docstring, y no importaba esa función). Arreglado con
  `herramientas._coincide_texto_libre()` (más `_norm_q()`/`_tokens_q()`, versión liviana local del
  mismo patrón que ya usan `alertas.py`/`oficial.py`/`declaraciones.py` para no crear un import
  circular con `monitor.py`): match por PALABRAS significativas (≥4 letras, sin tildes) — con 1-2
  palabras útiles en la consulta alcanza 1 coincidencia, con 3 o más se exige al menos la mitad; sin
  ninguna palabra útil (ej. solo stopwords) cae de respaldo a la subcadena literal de siempre, para no
  romper una consulta corta y exacta que ya funcionaba. Aplicado en las tres funciones.

- **Prueba nueva, reproduce el caso real de punta a punta** (`test_fase11_impacto_retrieval.py`, 9
  pruebas): el bono de impacto (una nota local de un solo medio con tema Crimen/Violencia supera a una
  nota trivial de más medios; una nota internacional del mismo tema NO recibe el bono) y el retrieval
  (la consulta parafraseada real de Fernando — "asesinato de una mujer en el centro de Guayaquil tras
  retirar efectivo" — SÍ encuentra la nota real que dice "baleada"; una consulta sin ninguna relación
  no trae nada; `buscar_guardadas`/`buscar_notas` usan el mismo match). Suite completa corrida después:
  **265 pruebas, 250 en verde** — los 15 errores son los mismos y ya documentados de
  `test_fase9_xapi.py` (buscan `xapi.GASTO_PATH`, movido a `redes.py` en la Fase 9 Parte D3, no
  relacionado con esta pasada).

### Pendientes reales de la Fase 11

1. **`Spike.exe` se compiló de verdad en esta sesión y quedó en
   `dist_compilado\monitor.dist\Spike.exe`** — pero no se probó con doble clic todavía (falta que
   Fernando copie su `.env` real ahí y lo abra). Ver el detalle completo (incluido el bug real del
   `--include-package=webview` que rompía la compilación) más arriba. `dist_compilado\monitor.build\`
   (caché intermedia de Nuitka, se regenera con cada compilación) se volvió a borrar después de esta
   corrida exitosa — no hace falta para EJECUTAR `Spike.exe`, solo la vuelve a crear Nuitka si se
   compila de nuevo (recompilar desde cero sin esa caché tarda más, pero no es un problema, ver
   Limpieza más arriba).
2. `handoff_ux.zip`, las carpetas `backups_2026...` y los `.bak` de `historias_registro.json` siguen
   sin borrar (no eran parte del pedido) — pendiente de que Fernando confirme si hacen falta.
3. El bono de 150 puntos es un valor fijo elegido por criterio, no medido contra docenas de casos
   reales — si en el uso diario un suceso grave sigue sin destacar lo suficiente (o, al revés, empieza
   a inflar temas de seguridad menores por encima de coberturas que sí importan más), el valor es la
   palanca obvia para ajustar.

## Fase 12 (2026-09-28) — Pulso social desfasado + UI del chat (scroll cortado y sin selección de texto)

Dos pedidos de Fernando, mismo flujo de delegación a Codex de siempre — `tarea_codex.md` con el
diagnóstico real ya confirmado, `codex exec` guardó `respuesta_codex.md`, revisado a mano antes de
aplicarlo con Edit, archivos puente borrados al cerrar.

- **Pulso social desfasado — causa real confirmada leyendo el código, no supuesta**: `worker_loop`
  llama a `enrich_pass()` en loop continuo (cada ~20s, `MONITOR_WORKER_PAUSA`, o antes si hay backlog),
  y `enrich_pass()` llama a `get_social()`/`get_social_historias()` en CADA pasada — el único freno
  real era el TTL interno de cada función, y `SOCIAL_TTL`/`SOCIAL_HIST_TTL` estaban en **6 HORAS** por
  defecto. El trabajador reintentaba cada 20s de verdad, pero el chequeo de TTL descartaba casi todos
  esos intentos durante 6 horas seguidas — el panel literalmente no traía un dato nuevo hasta que
  pasaran 6h desde la última actualización. El polling del cliente (cada 20s contra `data.json`, desde
  la Fase 0) ya era rápido; el cuello de botella era 100% backend. Arreglado: `SOCIAL_TTL` bajado a
  **10 minutos** (`get_social`, panel "Pulso social por tema" — no llama a ningún LLM,
  `_social_model()` devuelve `None` desde la migración a Gemini, así que bajar el TTL no agrega costo
  de API, solo más tráfico a redes públicas gratuitas/best-effort) y `SOCIAL_HIST_TTL` bajado a
  **20 minutos** (`get_social_historias`, panel "Debate real — por historia" — más conservador porque
  esta función SÍ llama a Gemini vía `ia.clasificar_posturas` por cada historia top, y el proyecto ya
  trackea gasto real con topes diarios/mensuales, Fase 10). Los dos siguen siendo overrideables por
  `MONITOR_SOCIAL_TTL`/`MONITOR_SOCIAL_HIST_TTL` (segundos), sin cambiar la firma de ninguna función.

- **Chat del Asistente: dos bugs distintos, con causas reales distintas** (el pedido asumía que los
  dos vivían en CSS; investigado a fondo, solo uno lo era):
  - **No hacía scroll con respuestas largas (SÍ era CSS)**: `.chatwidget` es
    `display:flex;flex-direction:column;max-height:min(480px,...);overflow:hidden`, y adentro
    `.chatlog` (compartido por los 3 chats del proyecto: por-item `#chatLog`, Asistente general
    `#asistenteLog`, chat de un caso `#casoChatLog`) es un hijo flex con `flex:1;overflow-y:auto`.
    Bug real de CSS clásico: un hijo flex con `flex:1` dentro de un `flex-direction:column` NO se
    encoge por debajo de la altura de su contenido sin `min-height:0` explícito — con una respuesta
    larga, `.chatlog` crecía más allá del `max-height` del padre y `.chatwidget{overflow:hidden}`
    RECORTABA el texto en vez de que `.chatlog` scrolleara solo. Arreglado agregando `min-height:0` (y
    sacando el `min-height:120px` que tenía antes, que contradecía el arreglo) — el bug solo se
    manifestaba en el widget flotante por-item (el único de los tres con un ancestro flex-column de
    altura fija; `#asistenteLog`/`#casoChatLog` son bloques simples con su propio `max-height`, sin
    este problema), pero el fix va en la clase compartida `.chatlog` porque no tiene costo en los otros
    dos contextos.
  - **No se podía seleccionar texto (NO era CSS — se buscó "user-select" en TODO
    `dashboard_template.html`, con y sin prefijos, y no existía NINGUNA regla de ese tipo)**: la causa
    real está en `monitor.py` — la ventana nativa se crea con
    `webview.create_window("Monitor de noticias - Ecuador", url)`, sin el parámetro `text_select=True`.
    **pywebview deshabilita la selección de texto por defecto en TODA la ventana**, no solo el chat, a
    menos que se pida explícitamente ese parámetro. Cuando Fernando usa `Spike.exe` (o
    `python monitor.py` sin argumentos, que abre la misma ventana nativa vía pywebview), esto explica
    "es imposible seleccionar... con el mouse" en TODA la app — en un navegador normal
    (`python monitor.py serve` + Chrome/Edge) la selección ya funcionaba bien, por eso nunca hubo un
    bug de CSS que corregir ahí. Arreglado agregando `text_select=True` a esa única llamada. Además, a
    pedido explícito de Fernando, se agregó una regla CSS de refuerzo
    (`user-select:text;-webkit-user-select:text;` en `.chatmsg`) — no era necesaria para el bug real,
    pero deja el comportamiento consistente sin importar el contexto (ventana nativa o navegador) si
    algún día se usa en un contexto más restrictivo.

- **Prueba nueva** (`test_fase12_social_chat.py`, 6 pruebas): `SOCIAL_TTL`/`SOCIAL_HIST_TTL` por debajo
  de 15/30 minutos (nunca 6h) y ninguno en cero; `webview.create_window` pide `text_select=True`
  (chequeo de texto fuente, no hay forma de probar una ventana nativa en una suite de `unittest`);
  `.chatlog` tiene `min-height:0`; `.chatmsg` tiene `user-select:text`/`-webkit-user-select:text`.
  **Bug propio encontrado escribiendo la prueba**: una primera versión de la prueba buscaba que NO
  existiera el string `"user-select:none"` en el archivo — pero mi propio comentario explicativo del
  cambio (línea que dice textualmente `no había ninguna regla "user-select:none"...`) hacía que la
  prueba fallara contra sí misma (falso positivo, no un bug real del CSS). Se sacó esa prueba, las
  otras tres del mismo test class no dependen de texto libre ambiguo.
  Suite completa corrida después: **265 pruebas + las 6 nuevas de este archivo = 271, 256 en verde** —
  los 15 errores restantes son los mismos y ya documentados de `test_fase9_xapi.py` (no relacionados
  con esta pasada).

### Pendientes reales de la Fase 12

1. **No verificado en vivo** (ni con `serve` real ni con `Spike.exe`) — los cambios se probaron con la
   suite automatizada y lectura de código, pero falta que Fernando confirme en su propia sesión: que
   el panel de Pulso social muestre temas distintos en corridas de ~10-20 min en vez de quedarse fijo
   horas, que una respuesta larga del chat haga scroll en vez de cortarse, y que pueda seleccionar/
   copiar texto del chat en la ventana nativa.
2. **`Spike.exe` (Fase 11) no se recompiló con este cambio** — el `text_select=True` de
   `webview.create_window` solo tiene efecto en una compilación nueva (o corriendo
   `python monitor.py`/`INICIAR.bat` directo, que sí toma el cambio de inmediato porque lee
   `monitor.py` fuente). Si Fernando quiere que el `.exe` ya compilado tenga la selección de texto
   arreglada, hay que correr `compilar.bat` de nuevo.
3. Si 10/20 minutos de TTL sigue sintiéndose lento para Pulso social en el uso real, la palanca son las
   mismas variables de entorno (`MONITOR_SOCIAL_TTL`/`MONITOR_SOCIAL_HIST_TTL`, en segundos) — bajarlas
   más para `SOCIAL_TTL` es barato (sin costo de API); bajar `SOCIAL_HIST_TTL` más agresivo sí sube el
   gasto real de Gemini, vale la pena mirar `ia_gasto.json`/el panel de Estadísticas antes de tocarlo.


## Fase 13 (2026-09-28/29) — Contextualización real de historias (antecedentes/actores/qué es nuevo/qué falta saber)

Pedido de Fernando en 3 rondas: primero un prompt (v1) que asumía un estado del proyecto ya
desactualizado (Gemini "apagado", embeddings "nunca corrieron") — se verificó contra el código real,
se reportó la discrepancia y **no se tocó nada** hasta confirmar. La v2 partió del estado real
confirmado y pidió diagnosticar primero (Paso 1, sin tocar código) y corregir después (Paso 2) solo
lo que el diagnóstico mostrara como faltante — no lo ya resuelto. A mitad de la Fase 13, Fernando
pidió pasar el resto de los cambios de código al flujo de Codex (`tarea_codex.md` → `codex exec` →
`respuesta_codex.md`) en vez de edición directa — los bugs encontrados **verificando en vivo con la
API real de Gemini** (ver más abajo) se corrigieron así.

### Paso 1 — Diagnóstico real (sin tocar código)

Leyendo el código (no de memoria) se confirmaron 5 causas reales de por qué el contexto no servía
para alguien sin seguimiento previo de la noticia:

1. **`_construir_contexto()` nunca leía `historias_registro.json`** (el registro rico de la Fase 9,
   con embeddings/actores/fechas) — solo usaba Wikipedia + GDELT + `entities.json` (un log liviano
   aparte). "Antecedentes" reales del propio monitor eran imposibles de mostrar porque el material
   nunca se los daba al modelo.
2. **La salida era una sola oración libre** (`_PROMPT_CONTEXTO`, máx. 45 palabras, `{"contexto":
   "..."}`) sin estructura ni citas verificables — no había nada que validar en código porque no
   había ids.
3. **`_construir_contexto()` nunca recibía los contratos SERCOP** que la propia historia ya tenía
   colgados (`s["contratos"]`), aunque ya estaban calculados.
4. **La entidad "principal"** (la que ancla GDELT/antecedentes) a veces terminaba siendo un MEDIO DE
   PRENSA ("Teleamazonas") o un LUGAR ("Durán", "el Aeropuerto José Joaquín de Olmedo") en vez de un
   actor real — 3 de 6 casos reales revisados a mano.
5. **Bug real de persistencia, encontrado leyendo el código** (no era lo que se había reportado antes
   como "el registro se reconstruye al reiniciar" — eso resultó ser impreciso): `_guardar_registro()`
   y `_cargar_registro()` nunca serializaban ni restauraban `embedding_modelo`/`embedding_multi_modelo`
   — se escribían en memoria (`_embed_pendientes_registro()`) pero se perdían en cada recarga desde
   disco (que pasa en CADA pasada, no solo al reiniciar el proceso). Confirmado con el archivo real:
   cobertura de embeddings trabada en **exactamente 40/981** (= `EMBED_MAX_NEW`) — las mismas 40
   entradas más viejas recalculándose sin necesidad en cada pasada, las genuinamente nuevas sin turno
   nunca.

Retención confirmada: `REGISTRO_MAX_HORAS = CLUSTER_MAX_HORAS` (72h, sin distinción local/
internacional).

### Paso 2 — Correcciones (solo lo que el Paso 1 confirmó como faltante)

- **Persistencia real** (`monitor.py`, `_cargar_registro`/`_guardar_registro`): se agregaron
  `embedding_modelo`/`embedding_multi_modelo` a la serialización y a la reconstrucción — cambio de
  formato retrocompatible (campo nuevo, entradas viejas caen a `None` vía `.get()`, nunca rompe nada
  existente). Verificado en vivo, antes/después de un reinicio real: cobertura de embeddings pasó de
  **40 fijos** a **177 y creciendo** en la misma sesión, sin quedar nunca trabada.
- **Retención de 90 días para lo local** (`REGISTRO_DIAS_LOCAL`, env `MONITOR_REGISTRO_DIAS_LOCAL`,
  def. 90): nueva función `_es_local_entry(e)` (deriva ámbito de `ciudad`/texto del titular, mismo
  criterio que `is_ecuador()`) y el paso de purga de `_fusionar_en_registro()` ahora usa un corte
  distinto para local (90 días) vs. internacional (`MAX_AGE_DAYS`, 3 días, sin cambios — pedido
  explícito de no tocarlo). El dashboard no cambia: `build_stories()` sigue descartando de la vista
  todo lo más viejo que `MAX_AGE_DAYS`, la retención extra solo alimenta antecedentes. Tamaño del
  registro informado en cada corrida verbose (`_tam_registro_mb()`, nueva línea de log en
  `run_once`/`run_fast`) — medido en vivo: 9.54 MB con 1205 entradas.
- **Filtro de "lugar o medio"** (`_es_lugar_o_medio()`, `_PATRON_LUGAR_O_MEDIO`): descarta un
  candidato a actor/principal si su nombre coincide con un outlet conocido de `feeds.py` o con
  `social.es_cuenta_medio()`, o si su extracto YA VERIFICADO de Wikipedia lo describe como lugar/medio
  ("es un/una ciudad/urbe/provincia/país/aeropuerto/canal de televisión/..."). Aplicado antes de
  gastar Wikipedia (sobre los candidatos crudos) y después (sobre el extracto verificado). Ampliado en
  vivo con un caso real no previsto: "Colombia" (país) no lo agarraba el patrón original hasta sumar
  "país"/"nación"/"república" a la lista de tipos de lugar.
- **Módulo nuevo `contexto.py`** (standalone, no importa `monitor.py`, mismo criterio que
  `oficial.py`/`declaraciones.py`/`alertas.py`): prompt de 4 bloques + `limitaciones`, validación de
  citas **en código** (`_validar()`) contra el set real de ids del material entregado — cualquier
  afirmación sin id válido se descarta antes de guardar, se cuenta en `descartadas`. `actores` valida
  contra su propio campo `apariciones` (no `fuentes`, por pedido explícito del esquema). Sin material,
  ni siquiera llama a la IA. `MAX_TOKENS` subido de 900 a **2500** tras un bug real encontrado
  verificando en vivo con la API real de Gemini: con 900, el perfil PROFUNDO
  (`gemini-3.1-pro-preview`, con razonamiento interno) devolvía una respuesta cortada a los **59
  caracteres** (JSON inválido, `last_error: "respuesta sin JSON valido"`) — gastaba el presupuesto
  "pensando" antes de escribir el JSON visible, mismo patrón ya documentado antes en este proyecto
  para otras llamadas al perfil profundo, pero esta tarea es más compleja (4 bloques anidados) y
  necesitaba más margen.
- **Material del contexto** (`_material_contexto()`, nuevo, en `monitor.py`): junta lo que ya existía
  (otros medios del mismo grupo, bios verificadas de Wikipedia, co-menciones/titulares de GDELT) MÁS
  lo nuevo: antecedentes del registro (`_antecedentes_registro()`) y apariciones de actores
  (`_apariciones_actor_registro()`) y contratos SERCOP ya colgados de la historia. Cada pieza recibe
  un id corto (`M1`, `W2`, `R3`, `A4`, `S5`) que viaja también al dashboard (`h.contexto.material`)
  para poder mostrar la cita como link clickeable.
  - **Bug real encontrado verificando en vivo** (caso real "la esposa de alias Fito"): la primera
    versión de `_antecedentes_registro()` comparaba contra la UNIÓN de nombres de TODAS las fuentes ya
    fusionadas de la historia — con 4 medios cubriendo el mismo hecho (uno citando a un funcionario,
    otro a Noboa opinando), ese conjunto junta nombres tangenciales. Exigir compartir solo UNO de esos
    nombres trajo antecedentes sin relación real: una nota de México sobre una ley, una marcha en
    Bogotá, hasta una nota sobre una película de Marvel — todas coincidían por "Noboa"/"Colombia",
    nombres demasiado genéricos. Arreglado en dos capas: (1) el set de comparación sale del titular
    **fundador** (el primer artículo, inmutable — mismo ancla de la Fase 9 contra la "deriva"), no de
    la unión que crece con cada fuente nueva; (2) se exige 2+ nombres en común cuando el fundador
    tiene 2 o más disponibles (1 solo alcanza si no hay más remedio).
  - **Segundo bug relacionado, encontrado en la misma verificación**: el bloque de "apariciones de
    actor" iteraba sobre TODOS los nombres crudos del registro (`_canon_set(propio.get("nombres"))`,
    extracción mecánica por mayúscula, sin verificar) — traía la misma clase de ruido ("colombia
    también aparece en: Avengers Doomsched..."). Arreglado acotando esa iteración a los nombres de las
    entidades que YA pasaron por extracción de IA + el filtro de lugar/medio (`verificadas` +
    `candidatos`), nunca el set crudo completo. **Pendiente real, no cerrado del todo**: nombres de
    instituciones genéricas (ej. "IESS") siguen pudiendo generar antecedentes tangenciales (noticias
    administrativas no causalmente relacionadas) cuando la propia IA los extrae como candidato — en la
    prueba real esto no generó ninguna cita inventada (el modelo no forzó una conexión falsa, solo
    describió los hechos con su cita real), pero vale la pena revisar si se repite seguido.
- **Caché reemplazado por hash del conjunto de fuentes** (`_hash_fuentes()`, nuevo): `get_contexto()`
  ya no decide "desactualizado" por `_huella_contenido()` (cantidad de fuentes, la que siguen usando
  `get_ia`/`get_veredicto`, sin cambios ahí) sino por un hash de los links reales de `s["fuentes"]` —
  una fuente que se reemplaza sin cambiar el total también dispara recálculo. La clave del diccionario
  sigue siendo `story_key(s)` (mismo criterio estable de siempre, no se tocó).
  - **Bug propio encontrado verificando en vivo, corregido antes de restart**: una entrada de caché de
    ANTES de este cambio (formato viejo, sin `antecedentes`) nunca tenía `_fuentes_hash` para comparar
    — el chequeo de "está vencida" daba siempre `False` y la entrada se quedaba en formato viejo para
    siempre. Arreglado: `"antecedentes" not in entry` también cuenta como desactualizada, así el
    trabajador migra sola cada historia del top local la primera vez que le toca cupo.
- **Automático solo para el top local** (`CONTEXTO_TOP`, env `MONITOR_CONTEXTO_TOP`, def. 10):
  `get_contexto()` ahora filtra a `es_local` y ordena por `interes` antes de aplicar el cupo por
  pasada (`CONTEXTO_MAX_NEW`, sin cambios, def. 8) — antes procesaba cualquier ámbito, con local solo
  como prioridad de orden. El resto se calcula **bajo demanda**.
- **`GET /api/contexto?id=<clave>`** (nuevo, `monitor.py`, `_do_GET_contexto`): calcula el contexto de
  una historia puntual en el momento (la clave es la misma `story_key`/`storyKey()` de siempre), sirve
  del caché si ya está fresco, y si no llama a `_construir_contexto()` en el momento y lo persiste.
  Verificado en vivo con `curl` real contra el servidor real corriendo: `{"ok": true, "recalculado":
  true, "contexto": {...}}` con 2 antecedentes, 8 actores, 3 novedades y 2 preguntas abiertas reales
  para la historia de "la esposa de alias Fito" — y confirmado que el resultado quedó persistido en
  `contexto_cache.json` y apareció en la siguiente publicación de `data.json`.
- **Dashboard** (`dashboard_template.html`): `renderContexto(h)` reescrita — panel `<details>`
  desplegable con los 4 bloques, cada afirmación con sus fuentes como chips clicables
  (`fuenteChip()`/`fuentesHTML()`, resuelven contra `h.contexto.material`), "Sin antecedentes en el
  registro"/"Sin actores identificados"/etc. cuando el bloque viene vacío, y un mensaje explícito
  ("Contexto: no disponible...") en vez de un "analizando…" perpetuo cuando `DATA.estado_contexto`
  indica que la IA está apagada. Las entradas de caché de formato viejo (sin recalcular todavía) caen
  a un fallback visual simple, sin romper la tarjeta. `abrirDetalleHistoria()` dispara
  `cargarContextoBajoDemanda()` automáticamente si la historia abierta no tiene contexto y la IA está
  disponible — pide `/api/contexto?id=` y reemplaza el panel del modal cuando llega, sin bloquear el
  resto de la UI. En Oportunidades, bloque nuevo "Preguntas abiertas — oportunidad de reportaje"
  (`renderGap()`): las `que_falta_saber` de las historias locales con contexto ya calculado, ordenadas
  por `interes`, hasta 12 — el bloque de brecha por tema existente no se tocó.
- **`herramientas.py`** (`detalle_historia`): expone los 4 bloques nuevos (`antecedentes`, `actores`,
  `que_es_nuevo`, `que_falta_saber`, `limitaciones_contexto`) para que el Asistente los pueda citar
  igual que cualquier otro dato ya verificado.

### Verificación en vivo (con la clave real de Gemini, no simulada)

Se probaron end-to-end, con la API real, las **3 mismas historias locales del Paso 1**:

1. **"¿Qué le espera en Ecuador a la esposa de alias 'Fito'...?"** — antes: sin antecedentes, "principal"
   a veces mal resuelto. Después: 2 antecedentes reales (bio de Fito + una nota real anterior sobre un
   reclamo de terreno de la esposa, citada con su link real), 7 actores identificados correctamente
   (incluida Inda Peñarrieta, Daniel Noboa, el ministro John Reimberg) con roles y citas reales, 2
   novedades, 2 preguntas abiertas genuinas, 0 descartadas.
2. **"Mujer fue baleada tras retirar USD 2.000 en el centro de Guayaquil"** — antes: *"De acuerdo con
   reportes de medios como Expreso, Extra y Primicias, el asalto con balacera ocurrió en el centro de
   Guayaquil el 28 de septiembre"* (circular, no agrega nada al titular). Después: antecedentes vacío
   honesto (correctamente NO forzó una conexión falsa con una nota de inundaciones que compartía
   "Guayaquil"), y sobre todo **una pregunta de reportaje real y filosa**: *"¿De qué entidad bancaria
   específica retiró el dinero y hubo filtración de información desde el interior? — Es clave para
   investigar si operó una banda de 'sacapintas' en complicidad con personal del banco o guardias de
   seguridad."* — exactamente el tipo de ángulo que pedía el criterio de calidad original.
3. **"Cámara captó el secuestro de una nutricionista del IESS al salir de su casa en Durán"** — antes:
   *"Durán es una urbe de la provincia de Guayas, ubicada frente a Guayaquil..."* (geografía genérica,
   "Durán" mal resuelto como "principal"). Después: "principal" correctamente resuelto a "IESS" (una
   institución real mencionada en la nota, no un lugar), 2 preguntas abiertas relevantes sobre el
   paradero de la víctima y la posible relación con su trabajo — con el pendiente ya anotado arriba de
   que los antecedentes de "IESS" son tangenciales (cambios administrativos reales pero no
   necesariamente relacionados con el secuestro).

`/api/contexto?id=` confirmado funcionando contra el servidor real corriendo (no un mock): la llamada
recalculó, guardó en caché, y el resultado apareció en la siguiente lectura de `data.json`.
`dashboard.html` servido en vivo por el servidor real confirmado con las funciones nuevas presentes
(`cargarContextoBajoDemanda`/`contexto-panel`/`renderContexto`).

### Verificación final — tabla

| Cambio | Archivos | Prueba que lo demuestra | Estado |
|---|---|---|---|
| Persistencia `embedding_modelo` | `monitor.py` | `test_fase11_contexto.py::TestPersistenciaEmbeddingModelo` + verificado en vivo (40→177 entradas con embedding en una sesión) | Hecho, verificado en vivo |
| Retención 90d local / 3d internacional | `monitor.py` | `test_fase11_contexto.py::TestRetencionLocalVsInternacional` | Hecho, probado (no verificado con 90 días reales transcurridos, por razones obvias de tiempo) |
| Filtro lugar/medio (`_es_lugar_o_medio`) | `monitor.py` | `test_fase11_contexto.py::TestFiltroLugarOMedio` (5 pruebas, incluye Teleamazonas/Durán/aeropuerto reales) | Hecho, verificado en vivo |
| Módulo `contexto.py` (4 bloques + validación de citas) | `contexto.py` (nuevo) | `test_fase11_contexto.py::TestContextoValidacion` (8 pruebas) + verificado en vivo con Gemini real (3 historias) | Hecho, verificado en vivo |
| Material con registro + SERCOP + actores | `monitor.py` (`_material_contexto`, `_antecedentes_registro`, `_apariciones_actor_registro`) | `test_fase11_contexto.py::TestAntecedentesYActoresDelRegistro` (5 pruebas) + verificado en vivo | Hecho, verificado en vivo (con el pendiente de "IESS" anotado) |
| Caché por hash de fuentes | `monitor.py` (`_hash_fuentes`, `get_contexto`) | `test_fase11_contexto.py::TestHashFuentes` + `TestGetContextoTopLocal` (incluye el bug de formato viejo) | Hecho, verificado en vivo |
| Top 10 local automático + `/api/contexto` bajo demanda | `monitor.py` | `TestGetContextoTopLocal::test_solo_procesa_top_n_locales_ignora_internacionales` + `curl` real contra el servidor real | Hecho, verificado en vivo |
| Dashboard (panel 4 bloques + Preguntas abiertas) | `dashboard_template.html` | `node --check` sobre el script servido en vivo + confirmado que el dashboard.html real contiene las funciones nuevas | Hecho, verificado que se sirve; NO verificado visualmente en un navegador (esta sesión no tiene esa herramienta) |
| Asistente expone los 4 bloques | `herramientas.py` | `test_herramientas.py` (sin regresión) | Hecho sin prueba dedicada nueva (expone campos ya validados por `contexto.py`) |

Suite completa: **300 pruebas** (29 nuevas de `test_fase11_contexto.py`), solo fallan las mismas 15
de `test_fase9_xapi.py` (no relacionadas, documentadas desde antes).

### Pendientes reales

1. Nombres de instituciones genéricas (ej. "IESS") todavía pueden generar antecedentes tangenciales
   cuando la IA los extrae como candidato de la propia nota — no generó ninguna cita inventada en las
   pruebas reales, pero no está cerrado con un filtro dedicado (a diferencia de outlets/lugares, que
   sí lo tienen).
2. No se verificó visualmente en un navegador real el panel nuevo ni el bloque "Preguntas abiertas"
   (sí se confirmó que el HTML/JS se sirve correctamente y es sintácticamente válido).
3. La retención de 90 días para lo local es nueva — no hay todavía un caso real con una historia de
   semanas de antigüedad sirviendo de antecedente (el registro recién empieza a acumular con la
   retención larga desde este cambio).
4. `Spike.exe` (compilado en la Fase 11 original) no se recompiló con estos cambios — sigue
   corriendo desde `python monitor.py` fuente en esta sesión.

## Fase 14 (2026-09-28/29) — Sección Guayaquil limpia y historias sin mezclas

Dos errores que Fernando veía a diario: la sección Guayaquil acogía notas que no eran de Guayaquil
(hechos de otras ciudades o de medios extranjeros mezclados por error de agrupamiento), y tarjetas
que mezclaban 2+ noticias distintas bajo un solo titular. Trabajado en el orden pedido: Paso 1
(diagnóstico con datos reales, sin tocar código), Paso 2 (corrección), en curso Paso 3
(verificación) — Paso 4 (botón "Reportar error") queda pendiente para una próxima sesión.

### Paso 1 — Diagnóstico (30 casos reales, `pruebas/casos_geo_agrupamiento.json`)

Se armó un fixture de regresión PERMANENTE con 15 casos de error reales (capturados de una corrida
en vivo, con titulares/medios/feed de origen reales) y 15 casos correctos (incluidos varios "casos
límite" que un arreglo ingenuo podría romper, ej. comunicados del Municipio de Guayaquil sin mención
textual de la ciudad — ahí `ciudad_feed` DEBE seguir ganando). Cinco causas reales, ordenadas por
cuántos casos explican:

1. **Dateline de agencia leído como ubicación del hecho** (ej. "Guayaquil (Ecuador), 28 sep
   (EFE).-" al inicio de un despacho sobre un nombramiento NACIONAL) — `detect_city()` lo tomaba
   como evidencia real del lugar del hecho.
2. **Enumeración de ciudades sin `_es_enumeracion_ciudades()`** (nunca existía un equivalente al ya
   resuelto `_es_enumeracion_paises()`) — "¿qué cambia para los aeropuertos de Quito, Guayaquil y
   Cuenca?" tomaba la primera ciudad mencionada como si fuera LA ciudad del hecho.
3. **Mezcla por vocabulario genérico** (la causa MÁS FRECUENTE, ~9 de 15 casos): palabras
   demasiado comunes ("menores", "casos", "parque lineal", "operativo") uniendo hechos sin
   relación real; compartir la MISMA organización o el MISMO país en momentos distintos tampoco es
   compartir el mismo hecho (ej. "Renuncia presidenta de la Cámara de Industrias" fusionada con una
   declaración institucional previa de la misma Cámara, semanas antes).
4. **Veto de extranjero solo contra el representante**, nunca contra fuentes YA fusionadas de
   grupos internacionales — una nota de Argentina sobre EE.UU. se colaba dentro de una historia real
   de lluvias en Guayaquil.
5. **Cantones de Guayas fuera de `CITIES`** (Pedro Carbo) — sin entrada propia, `detect_city()`
   nunca podía distinguirlos de Guayaquil.

### Paso 2 — Correcciones (todas verificadas en vivo con la API real de Gemini, no simuladas)

**Deterministas (sin IA), aplicadas primero:**
- `GUAYAQUIL_AREA`/`_area_de()`: `CITIES` se reestructuró con **Samborondón, Durán y Daule como
  entradas propias** (antes plegadas dentro de "Guayaquil"), y `_area_de()` las agrupa recién
  DESPUÉS de detectarlas por separado — permite distinguir "Samborondón" de "Guayaquil" como
  ciudades DISTINTAS para propósitos de discrepancia (ver más abajo) sin perder el agrupamiento de
  área metropolitana para el resto del dashboard.
- `_es_enumeracion_ciudades()` (nuevo, mismo patrón que `_es_enumeracion_paises`): 3+ ciudades
  reconocidas en el mismo texto → ninguna cuenta como LA ciudad del hecho.
- `_quitar_dateline()` (nuevo, regex de dateline de agencia EFE/AFP/Reuters/AP): se aplica ANTES de
  `detect_city()`/`_es_enumeracion_ciudades()` en `build_stories()`, en `_match_registro()` (veto de
  extranjero contra CADA fuente ya fusionada, no solo el representante), y en el candado de
  geografía de la IA (`get_ia`/`_apply`) — **bug real encontrado verificando en vivo, corregido en
  una segunda ronda**: el candado de la IA (que corre DESPUÉS de `build_stories()`, leyendo
  `geo` desde `ia_cache.json`) volvía a pisar el `ciudad=""` correcto con su propio
  `detect_city()` sin limpiar el dateline ni chequear enumeración — mismo bug, segundo lugar
  distinto del código, mismo arreglo aplicado ahí también.
- `_ciudad_de_fuente()`/`_ciudad_por_mayoria()` (nuevos): la ciudad de una historia ahora sale de la
  MAYORÍA de sus fuentes (no de una sola, ni del texto crudo sin filtrar) — `ciudad_feed` sigue
  ganando como señal DURA por fuente individual, pero ya no se acepta a ciegas si el texto del
  representante contradice claramente.
- `PALABRAS_GENERICAS_CONTENIDO` (nuevo, junto a `EVENTO_GENERICO`/`LUGARES_COMUNES`): "menores",
  "casos", "parque", "lineal" excluidos del solape de palabras/nombre propio SOLO en el registro
  persistente (no en `cluster()` intra-pasada, que se deja intacto a propósito).

**Verificación de coherencia (con IA, nueva — `ia.verificar_coherencia()` + 
`monitor._coherencia_pendientes_registro()`/`_dividir_entrada_registro()`):** revisa historias YA
formadas con 3+ fuentes, acotado a `MONITOR_COHERENCIA_MAX` (def. 8) por pasada del trabajador,
cacheado por hash de fuentes (`_hash_fuentes`) — si el modelo detecta 2+ hechos distintos, divide la
entrada del registro en grupos, validando EN CÓDIGO que cada fuente caiga en exactamente un grupo
(si el JSON del modelo es inválido o no cubre todas las fuentes, no se divide, se cachea igual para
no reintentar cada pasada). El grupo que contiene la fuente FUNDADORA conserva el `eid` original
(no rompe la clave estable de `saved.json`/`notas.json`).
- **Probado en vivo con Gemini real, 3 casos representativos del fixture**: el caso más grave
  (Juegos Nacionales de Menores + basura + tosferina, 3 hechos en una tarjeta) se dividió
  correctamente en 3 grupos exactos; un caso legítimo de 4 fuentes reales sobre el mismo asalto
  (Sacapintas) correctamente NO se dividió; el caso más sutil (misma organización, Cámara de
  Industrias, dos episodios distintos) se dividió correctamente en 2 grupos.
- **BUG REAL propio, encontrado verificando en vivo**: `ia.verificar_coherencia()` recortaba el
  listado de fuentes a las primeras 12 (`fuentes[:12]`) para armar el prompt, pero
  `monitor.py` validaba el resultado contra el TOTAL real de fuentes (`len(fuentes)`) — para
  historias con más de 12 fuentes (2 casos reales del fixture, mezclas internacionales con 13 y 20
  fuentes), el modelo nunca veía las fuentes 12+, así que sus grupos JAMÁS podían cubrir el rango
  completo y la validación fallaba SIEMPRE, quedando cacheadas como "revisadas, no se puede
  dividir" para siempre aunque la mezcla fuera real. Confirmado en el registro real: 7 entradas
  con más de 12 fuentes, las 7 ya marcadas sin ninguna división. Arreglado subiendo el límite a 40
  (mismo tope que ya usa `clasificar_posturas` para una lista de posts) — se limpió a mano el
  `coherencia_hash` de esas 7 entradas puntuales (backup guardado,
  `historias_registro.json.bak-fase14-geoevid-<timestamp>`) para que se re-evalúen con el código
  corregido en las próximas pasadas del trabajador.

**Clasificación con evidencia (con IA, nueva — `ia.clasificar_geo_evidencia()` +
`monitor.get_geo_evidencia()`):** para historias donde las fuentes fusionadas mencionan ciudades
DISTINTAS (`s["ciudad_discrepancia"]`, calculado en `build_stories()` sobre las ciudades ya
normalizadas por área metropolitana — evita marcar como "discrepancia" el caso trivial de
Durán/Samborondón vs. Guayaquil, que son la misma área), se le pide al perfil rápido de Gemini una
decisión citando una frase LITERAL del titular/resumen. `_validar_frase_evidencia()` en CÓDIGO
exige que esa frase exista de verdad (normalizada, sin tildes/mayúsculas) en el texto real — si la
IA inventó o parafraseó, el resultado se descarta y no se usa para corregir nada. Cuando el
resultado es válido: si `es_guayaquil=False` y la historia estaba marcada Guayaquil, se limpia
`s["ciudad"]`; si `es_guayaquil=True` y no tenía ciudad, se completa a "Guayaquil". Acotado a
`MONITOR_GEO_EVIDENCIA_MAX` (def. 8) por pasada, cacheado por `story_key()`.
- **Probado en vivo con Gemini real**: los dos casos ambiguos del fixture (dateline de la ministra,
  enumeración de la Ley de Aviación Civil) devuelven correctamente `ciudad_del_hecho: null,
  es_guayaquil: false` — el modelo no se deja engañar por el mismo material que sí engañaba al
  `detect_city()` crudo.
- Dashboard: el tag de ciudad en `cardHTML()` muestra la frase de evidencia como `title` (tooltip)
  cuando hay una válida — **bug real de Codex, encontrado revisando su propio cambio**: la primera
  versión abría el atributo `title="..."` sin cerrar la comilla, rompiendo el HTML de la tarjeta
  (el navegador se "comía" el resto de la etiqueta como si fuera parte del valor del atributo) —
  corregido agregando la comilla de cierre faltante.

### Paso 3 — Verificación (en curso, estado real a la fecha de cierre de esta sesión)

**Fixture antes/después** (30 casos, comparados contra el registro real en producción):
- **Los 3 casos de "error_ubicacion"**: los 3 se comportan correctamente en el servidor real
  (`ciudad=""` para los dos casos ambiguos, `ciudad="Guayaquil"` preservado para el caso frágil de
  Municipio de Guayaquil con menciones de otras ciudades en el texto).
- **Los 12 casos de "error_mezcla"**: **1 de 12 confirmado dividido en el registro real**
  ("Emiratos Árabes Unidos e Israel confirman reunión..." separado correctamente de "U.N. Releases
  New List of Companies...", exacto a `grupos_correctos` del fixture) — los otros 11 siguen
  fusionados en una sola entrada, TODAVÍA no procesados por el mecanismo de coherencia. Esto es
  esperado, no un fallo: el mecanismo revisa como máximo 8 entradas nuevas por pasada del
  trabajador, sobre un total de 146 entradas candidatas (3+ fuentes) en el registro real — divide
  el trabajo en muchas pasadas a propósito, para nunca reprocesar en lote (pedido explícito del
  usuario). El mecanismo en sí está confirmado funcionando (los 3 casos probados directamente con
  Gemini real dieron resultados correctos, más esta división real observada en producción) — falta
  tiempo de `serve` corriendo para que le toque el turno al resto del backlog.
- **Los 15 casos "correcto"**: los 15 siguen siendo una sola entrada del registro, sin ninguna
  regresión (0 divisiones erróneas).
- Suite completa: **300 pruebas, solo los 15 fallos ya conocidos y no relacionados** de
  `test_fase9_xapi.py` (busca `xapi.GASTO_PATH`, movido a `redes.py` en la Fase 9) — corrida 4 veces
  en esta sesión, una por cada ronda de cambios, siempre el mismo resultado.

**Historias de Guayaquil con `frase_evidencia`**: en el momento de escribir esto, **0 historias**
tienen `ciudad_discrepancia=True` en el snapshot real del feed — el disparador del clasificador de
evidencia (fuentes que genuinamente mencionan ciudades DISTINTAS, ya normalizadas por área
metropolitana) es honesto y no se fuerza a producir actividad artificial; en esta sesión el feed
real no trajo ningún caso de discrepancia real todavía. El mecanismo está probado y funcionando
(2/2 casos de prueba con Gemini real, ver arriba) — falta que aparezca un caso real en producción
para reportar la lista pedida ("todas las historias de Guayaquil con frase_evidencia, cuántas
excluidas").

**Gasto de IA de esta sesión** (Fase 14 completa, las 3 rondas de cambios + verificación manual):
gasto diario subió de aproximadamente $0.61 a **$0.70 de $1.00** (tope diario) durante el trabajo de
esta fase — incluye las llamadas de prueba manuales (5-6 llamadas directas a
`ia.verificar_coherencia`/`ia.clasificar_geo_evidencia`) más lo que el trabajador ya procesó en
producción real (22 entradas revisadas por coherencia al cierre). El costo por llamada de estas dos
funciones nuevas es bajo (perfil rápido, `max_tokens` 200-500) — el gasto principal de la sesión
sigue viniendo del resto del pipeline (interpretación editorial con el perfil profundo, mucho más
caro por llamada).

**Confirmado en el dashboard renderizado**: `data.json` real expone `ciudad_discrepancia` en el
100% de las historias (1334/1334 en la corrida real) y `geo_evidencia` cuando corresponde; el
`<script>` de `dashboard_template.html` servido por el servidor real pasa `node --check` sin
errores tras el arreglo del atributo `title`. No se revisó visualmente en un navegador real (esta
sesión no tiene esa herramienta).

### Pendientes reales de la Fase 14

1. **11 de los 12 casos de mezcla del fixture siguen sin dividir** al cierre de esta sesión — el
   mecanismo está confirmado funcionando, solo falta que `serve` siga corriendo el tiempo suficiente
   para que le toque el turno a cada entrada (acotado a 8/pasada sobre 146 candidatas).
2. **0 casos reales de `ciudad_discrepancia`/`frase_evidencia` observados en producción todavía** —
   el disparador es honesto (requiere discrepancia real entre fuentes), no se pudo forzar ni
   simular con datos sintéticos dentro del alcance de esta verificación.
3. **Paso 4 (botón "Reportar error" en cada tarjeta, guardando en
   `pruebas/casos_reportados.json`) no implementado todavía** — queda para la próxima sesión.
4. El gasto de Gemini llegó a 70% del tope diario durante esta sesión — si se retoma la Fase 14 el
   mismo día, vale la pena revisar `estado_ia_nube` antes de correr más verificaciones manuales que
   gasten presupuesto.
5. No se revisó visualmente en un navegador real el tooltip de evidencia ni ningún otro cambio
   visual de esta fase.

## Fase 16 (2026-09-29) — orden de carpetas + exe sin consola + esqueleto de carga

(Nota de numeración: esta sección se escribió originalmente como "Fase 15" y se renombró a Fase 16
al descubrir que "Fase 15" ya estaba tomada por el motor de señales/`senales.py`, en curso en
paralelo — ver `COORDINACION.md` y el pedido de Fernando de la sesión siguiente. Sin relación de
contenido entre ambas, pura coincidencia de numerar dos sesiones distintas el mismo día.)

Pedido de Fernando: ordenar la carpeta de trabajo y dejar visible solo el ejecutable para abrir
el programa, sin pantalla negra de cmd, y con un esqueleto de carga por si la primera pasada
tarda.

### Reorganización de carpetas

- **`codigo_fuente/`** (nueva, oculta con `attrib +h` — sigue ahí, solo no aparece en el
  Explorador con la vista por defecto): contiene TODO lo que antes vivía suelto en la raíz —
  `monitor.py` y el resto de los `.py`, los `test_*.py`, `casos/`, `pruebas/`, todos los
  `*.json` de datos/caches reales (`data.json`, `historias_registro.json`, `.env`, etc.),
  `dashboard_template.html`/`dashboard.html`, `logo.png`/`logo.ico`, los `.bat`/`.command`, y
  ahora también **el propio `Spike.exe` con todas sus DLL/pyd** (ver más abajo, "por qué el exe
  quedó ahí adentro y no en `dist_compilado/`"). `CLAUDE.md` y `AGENTS.md` (más `.claude/`)
  se quedaron en la raíz real a propósito — son los archivos que Claude Code/Codex leen
  automáticamente por convención de carpeta, moverlos habría cortado esa continuidad — pero
  también se marcaron ocultos (`attrib +h`) para que no aparezcan a simple vista; con "mostrar
  archivos ocultos" en el Explorador siguen ahí, sin tocar.
- **`codigo_fuente/archivo_historico/`**: las 8 carpetas `backups_2026...`, `handoff_ux.zip`,
  `compilar_log.txt`, `serve_log.txt`, los `PROMPT_fase9*.md`, `respuesta_codex.md`,
  `tarea_codex.md`, los tres `historias_registro.json.bak-*` y la carpeta `Claude outputs/` —
  nada se borró (Fernando eligió "archivar, no borrar"), solo se sacaron de la vista principal.
- **Por qué el exe quedó DENTRO de `codigo_fuente/` y no en una carpeta propia más prolija**:
  `monitor.py` resuelve `HERE = os.path.dirname(os.path.abspath(__file__))` y a partir de ahí
  arma las rutas de `data.json`/`.env`/todos los caches — tanto en el script interpretado como
  en el `.exe` compilado (Nuitka resuelve `__file__` a la carpeta donde vive el binario). Fernando
  eligió explícitamente "que el exe use los datos reales acumulados" en vez de arrancar vacío —
  para que eso sea posible, `Spike.exe` (y las ~40 DLL/`.pyd` que trae) tienen que vivir en la
  MISMA carpeta que `data.json`/`historias_registro.json`/`.env`, no en una subcarpeta aparte
  (`dist_compilado/monitor.dist/`, como quedaba antes de esta fase, hubiera arrancado siempre
  vacío). `compilar.bat` ahora copia el standalone completo desde `dist_compilado\monitor.dist\`
  hacia la carpeta actual al terminar de compilar (`xcopy /y /e /i` + `rmdir`), así que una
  recompilación futura vuelve a dejarlo bien ubicado solo, sin un paso manual.
- **Acceso directo `Spike.lnk` en la raíz real**: apunta a `codigo_fuente\Spike.exe`, con
  "Iniciar en" = `codigo_fuente\` (así Windows lo abre con esa carpeta como referencia, aunque
  `monitor.py`/Nuitka de todos modos resuelven todo por `__file__`, no por el directorio de
  trabajo) e ícono `logo.ico`. Es el ÚNICO archivo visible en la raíz con la vista normal del
  Explorador.

### Ventana nativa sin consola + esqueleto de carga (Fase 16, `monitor.py`)

- **La pantalla negra de cmd NO la causaba `Spike.exe`**: `--windows-console-mode=attach`
  (ya configurado desde la Fase 11) hace que el `.exe` NUNCA asigne una consola cuando se abre
  con doble clic — confirmado en esta sesión con `Get-CimInstance Win32_Process`: `Spike.exe`
  corriendo sin ningún `cmd.exe`/`conhost.exe` como hijo. La consola negra que Fernando veía
  venía de `INICIAR.bat` (un `.bat` SIEMPRE abre una consola al ejecutarse, sin importar qué
  llame adentro) — con el acceso directo nuevo, `INICIAR.bat` ya no es el punto de entrada de
  uso diario (sigue existiendo, es una herramienta de desarrollo).
- **BUG REAL de fondo, encontrado leyendo `serve()` para agregar el esqueleto**: la ventana
  nativa (`webview.create_window(...)` + `webview.start()`) se creaba DESPUÉS de
  `run_fast(verbose=True)` (la primera pasada del feed, ~53 RSS + agrupamiento contra el
  registro) — es decir, el usuario no veía NADA (ni consola, ni ventana) hasta que esa primera
  pasada terminaba. Documentado como "no debería tardar" (~10s en mediciones viejas de la Fase 0
  con un registro mucho más chico), pero **medido en vivo hoy con el registro real actual
  (63MB, `historias_registro.json`) la primera pasada tardó varios minutos** (se dejó correr
  15+ minutos con CPU subiendo sin parar antes de cortarla a mano) — el registro creció mucho
  desde que se midió por última vez (Fase 0), y el costo de comparar cada artículo nuevo contra
  miles de entradas ya acumuladas (Fase 9, `agrupar_con_memoria`) ya no es instantáneo. Esto
  confirma que el pedido de un esqueleto no era un capricho: sin él, doble clic en el `.exe` se
  siente literalmente como que "no pasó nada" durante varios minutos.
- **Arreglo — ventana YA, con esqueleto inline, mientras el backend arranca en un hilo aparte**:
  `serve()` se reordenó (sin tocar la lógica de `run_fast`/el resto del pipeline, solo CUÁNDO se
  llama) para que `webview.create_window("Spike", html=_ESQUELETO_HTML, text_select=True)` sea
  case si lo PRIMERO que hace, usando el parámetro `html=` de pywebview (contenido inline, no
  depende de que el servidor HTTP ya esté arriba). `_ESQUELETO_HTML`/`_ERROR_HTML` (nuevas,
  arriba de `serve()` en `monitor.py`) son páginas propias con el mismo esquema de colores
  claro/oscuro de `dashboard_template.html`, spinner + tarjetas "shimmer". Todo el trabajo
  pesado (primera pasada del feed, bind del puerto, arrancar los hilos de fondo) se movió a
  `_arrancar_backend()`, que corre en un hilo de fondo; cuando termina, `window.load_url(...)`
  navega la MISMA ventana del esqueleto al dashboard real — nunca se abre una ventana nueva. Si
  `_arrancar_backend()` falla de verdad (ej. sin internet la primera vez), la ventana muestra
  `_ERROR_HTML` con el mensaje real en vez de quedarse trabada en el esqueleto para siempre. Se
  conservó el mismo respaldo de siempre (navegador + consola) para cuando no hay `pywebview`
  instalado o la ventana nativa no se pudo crear.
- **Verificado en vivo, dos corridas reales**:
  1. Con `MONITOR_SAMPLE=1` (sin red): el ciclo completo (ventana con esqueleto → backend →
     `dashboard.html`/`data.json` generados → navegación a la URL real) se completó en pocos
     segundos, confirmado con los archivos generados y el proceso (`Spike`, sin hijos
     `cmd`/`conhost`, solo el `msedgewebview2.exe` normal del motor de renderizado).
  2. Con los datos reales (`.env` real, `historias_registro.json` de 63MB): confirmado que la
     ventana abre al instante (título "Spike", `Responding: True` todo el tiempo) y sin ninguna
     consola — pero la primera pasada NO terminó en los 15+ minutos que se la dejó correr (ver
     el bug de rendimiento de arriba). Se cortó el proceso a mano para no dejarlo corriendo sin
     supervisión; se confirmó que `data.json`/`historias_registro.json` quedaron intactos y con
     JSON válido (la corrida no alcanzó a escribir nada, no hubo corrupción de datos).
- `test_fase12_social_chat.py` actualizado (el texto exacto de `create_window` cambió: ahora es
  `webview.create_window("Spike", html=_ESQUELETO_HTML, text_select=True)` en vez de pasar la URL
  directo) — sigue confirmando que `text_select=True` viaja en esa misma llamada. Suite completa
  vuelta a correr desde `codigo_fuente/`: 322 pruebas, mismos 15 errores ya conocidos y no
  relacionados de `test_fase9_xapi.py` (busca `xapi.GASTO_PATH`, movido en la Fase 9).

### Pendientes reales de la Fase 16

1. **La primera pasada del feed contra el registro real (63MB) es lenta de verdad — no
   solucionado, solo confirmado y ahora bien comunicado con el esqueleto**: en esta sesión no
   terminó en 15+ minutos. Vale la pena una sesión aparte para perfilar `agrupar_con_memoria()`/
   la reconciliación de embeddings contra un registro de este tamaño (probablemente necesita un
   índice más barato que comparar cada artículo nuevo contra todas las entradas de las últimas
   72h/90 días, que ya deben ser miles). Mientras tanto: la primera vez que Fernando abra
   `Spike.exe` en la carpeta real, esperar que tarde varios minutos (el esqueleto se queda
   visible todo ese tiempo, no se congela ni se cierra solo).
2. **No se recompiló de nuevo después de este hallazgo** — el `.exe` actual YA incluye el
   arreglo del esqueleto (se compiló después de escribirlo), solo no se pudo confirmar en vivo
   que la transición al dashboard real ocurre con el registro de 63MB completo (sí se confirmó
   con datos de muestra, sin red).
3. **`codigo_fuente/dist_compilado/monitor.build/`** (caché de compilación de Nuitka) se dejó
   como quedó — sigue ahí para acelerar la próxima recompilación; no afecta a `Spike.exe` ni a
   los datos.
4. Si Fernando algún día quiere clonar/copiar esta carpeta a otra PC, tiene que copiar
   `codigo_fuente/` ENTERA (el exe no sirve solo) y no `Spike.lnk` solo (el acceso directo
   tiene una ruta absoluta a esta PC).

## Fase 17 (2026-09-29) — el `.exe` tardaba muchísimo (o nunca terminaba): causa real y arreglo

Pedido de Fernando: encontrar con evidencia por qué el `.exe` cargaba las noticias muchísimo más
lento que antes, y dejarlo al menos tan rápido como `python monitor.py serve`. Trabajo en conjunto
con Codex (`codex exec`, delegado por Claude), siguiendo la misma disciplina de `COORDINACION.md`
que la Fase 15 (señales): un archivo, un dueño a la vez, ningún paso cerrado sin revisión de Codex
anotada. Ver `COORDINACION.md` (sección "Frente B") para la bitácora completa paso a paso.

### Diagnóstico (Paso 1) — no era un problema de empaquetado

Se instrumentó `monitor.py` con un log de tiempos por etapa nuevo, `arranque.log` (junto al
programa, porque el `.exe` con `--windows-console-mode=attach` no tiene consola visible — un
`print()` durante el arranque no lo ve nadie): `_log_arranque()`/`_medir_etapa()`, aplicados a
`collect()` (tiempo total + feeds más lentos/con error), cada sub-paso de `enrich_pass()`, y los
hitos de `serve()`/`_arrancar_backend()` (ventana creada, puerto bindeado, primera pasada
terminada, primera respuesta HTTP real). También loguea si el proceso es "exe compilado" o "python
interpretado" y qué `HERE` está usando (la hipótesis más común de ".exe lento" — que use una
carpeta distinta a la del `.py` — se confirma o descarta al instante con esa sola línea).

Con esa instrumentación, se corrió la MISMA actualización dos veces contra los datos reales
(`historias_registro.json`, 1485 entradas / 63MB) — una con `python monitor.py serve`, otra con
`Spike.exe` recién compilado con la misma instrumentación. **Las dos mostraron EXACTAMENTE el
mismo patrón**: `collect()` (54 feeds RSS en paralelo) termina en ~5-10s, y después las dos quedan
colgadas en la MISMA etapa (`agrupar_con_memoria()` → `_fusionar_en_registro()` →
`_match_registro()`) — sin ninguna diferencia atribuible al empaquetado. Se cortaron a mano
después de 15+ minutos sin terminar cada una, sin dañar el registro real (confirmado JSON válido y
sin modificar en los dos casos).

**Causa exacta, encontrada con `cProfile` sobre una copia de SOLO LECTURA del registro real**
(nunca se tocó el archivo real durante el diagnóstico): `_match_registro()` recalculaba
`extranjero_sin_ecuador(articulo_nuevo)` en CADA una de las ~1300 vueltas del `for eid, e in
registro.items():` (una por cada entrada candidata dentro de la ventana de 72h), pese a que ese
valor depende SOLO del artículo nuevo, nunca de la entrada del registro contra la que se compara
en esa vuelta — una recomputación 100% redundante, ~1300 veces por artículo cuando alcanzaba con 1.
Perfilando 40 artículos reales (9 genuinamente nuevos): **58.09 de 61.85 segundos (93.9%) se
fueron en `extranjero_sin_ecuador`/`is_foreign`/`is_ecuador`/`geo_hit`/`norm`**, con **1 795 076
llamadas a `geo_hit()`** solo para esos 9 artículos — cada una normalizando texto y armando un
patrón de regex nuevo con `re.escape()`, para un catálogo de términos (`EC_TERMS`/
`FOREIGN_TERMS`, ~38 y ~44 términos) que NUNCA cambia en tiempo de ejecución.

**Por qué se puso tan lento justo ahora**: la causa de código es vieja, pero antes pasaba
inadvertida porque el registro era chico. La Fase 13 extendió la retención de historias LOCALES de
3 a 90 días (`REGISTRO_DIAS_LOCAL`) — el registro real creció a 1485 entradas/63MB (~30x más que
antes de esa fase). La ventana de MATCHING (`REGISTRO_MAX_HORAS`, 72h) no cambió, pero con un
registro más grande hay más candidatos dentro de esa ventana en momentos de actividad alta, y el
costo de esta función escala con esa cantidad.

**Hipótesis típicas de ".exe empaquetado", confirmadas o descartadas con evidencia real** (no con
suposición): rutas de datos en carpeta temporal de extracción — descartada (`--standalone`, no
`--onefile`; `HERE` resuelve a una carpeta real y persistente, confirmado con el `.exe` usando el
registro/caches reales de 63MB, no arrancando vacío); `multiprocessing` sin `freeze_support()` —
descartada (`grep -rn "multiprocessing"` en todo el proyecto: cero resultados, solo se usa
`ThreadPoolExecutor`); llamadas de red sin timeout — descartada (revisados todos los
`urlopen`/`op.open` del proyecto, todos con timeout explícito 8-220s); certificados SSL —
descartada (`collect()`, la única etapa con HTTPS real, tardó igual en `.py` que en `.exe`,
4.87-5.37s vs 4.97s); carga bloqueante del dashboard — ya resuelta en la Fase 16 (esqueleto), pero
exponía el problema real de arriba (ni la primera pasada sola terminaba en un tiempo razonable);
choque con el ciclo de señales de la Fase 15 (Frente A) — no aplicaba, `monitor.py` todavía no
importa/llama a `senales.py` en ningún lado; empaquetado en un solo archivo + antivirus — descartada
(`--standalone`, no hay un único archivo autoextraíble).

**Bloqueante aparte, encontrado y arreglado para poder recompilar durante este mismo diagnóstico**:
compilar con `codigo_fuente/` como carpeta de trabajo (porque ahí vive el standalone YA compilado
de la Fase 16, con sus `.pyd`/`.dll`, puestos ahí a propósito para que el `.exe` comparta datos con
el `.py`) hacía que Nuitka cargara por error el `_ctypes.pyd` LOCAL en vez del real del sistema
(porque `python -m nuitka` pone el directorio de trabajo actual primero en `sys.path`), y concluyera
que la carpeta entera "es parte de la librería estándar" — rechazando compilar `monitor.py` con
`Error, 'monitor.py' is in the standard library...`. Confirmado con
`nuitka.importing.StandardLibrary.isStandardLibraryPath()` (da `True` compilando desde
`codigo_fuente`, `False` desde una carpeta vacía). Arreglado en `compilar.bat`: ahora compila
SIEMPRE desde una carpeta de trabajo vacía y descartable (`dist_compilado\_build_cwd\`), con todas
las rutas de entrada/salida absolutas — el resultado final (dónde queda `Spike.exe`) no cambió.

### Arreglos aplicados (Paso 2, los tres revisados por Codex)

1. **`a_extranjero` sacado del loop** (`_match_registro`): se calcula UNA vez por artículo, antes
   del `for`, en vez de una vez por cada entrada candidata. Cambio matemáticamente equivalente
   (el valor no depende de la entrada), cero riesgo de cambiar qué se considera "la misma historia".
2. **`EC_TERMS`/`FOREIGN_TERMS` precompilados** (`_EC_TERMS_RE`/`_FOREIGN_TERMS_RE`, diccionarios
   `{termino: patron_compilado}` armados una vez al cargar el módulo, confirmado por grep que son
   listas fijas — nunca se les hace `.append`/`+=`): `is_ecuador`/`is_foreign`/
   `_es_enumeracion_paises` usan estos patrones en vez de rearmarlos en cada llamada. `geo_hit()`
   en sí no se tocó (sigue igual para ciudades/nombres/alias dinámicos).
3. **Cache por entrada dentro de una misma pasada** (`cache_entry`, parámetro opcional nuevo de
   `_match_registro`, creado una vez en `_fusionar_en_registro` y compartido entre todas sus
   llamadas de esa pasada): `extranjero_sin_ecuador`/tokens del representante/tokens del fundador
   de una entrada del registro no dependen de qué artículo nuevo se esté evaluando — con varios
   artículos nuevos comparados contra las MISMAS entradas en una sola pasada, se recalculaban una
   vez por cada PAR (artículo × entrada) cuando alcanza con una vez por entrada.
   **Bug real encontrado por Codex antes de cerrar este arreglo** (nunca llegó a producción): la
   primera versión de la huella de cache concatenaba `rep_titulo + " " + rep_resumen` en un solo
   string — dos pares (título, resumen) DISTINTOS pueden concatenar al mismo string si el "corte"
   entre ambos cae en otro lugar (ej. `título="Rescate playa Guayaquil"`+`resumen="hoy"` concatena
   igual que `título="Rescate"`+`resumen="playa Guayaquil hoy"`), dejando pasar un `tok_rep` VIEJO
   como si siguiera válido. Arreglado usando una TUPLA de los campos originales como huella (nunca
   colisiona), en vez de un string armado. `test_fase17_arranque.py` (3 pruebas): reproduce el caso
   exacto que encontró Codex (confirmado que el test FALLA con la versión vieja del código y PASA
   con la corregida, verificado a mano revirtiendo la línea antes de restaurarla), un control de
   que el cache sigue sirviendo cuando de verdad no hay cambios, y un caso de equivalencia
   end-to-end con una entidad extranjera real.

**Medido con el mismo método en cada paso** (`cProfile` sobre una copia de solo lectura del
registro real, nunca se tocó el archivo real):

| | Antes | Con arreglos 1+2 | Con arreglos 1+2+3 (final) |
|---|---|---|---|
| Artículos evaluados / nuevos | 40 / 9 | 40 / 10 | 300 / 153 |
| Tiempo real bajo profiling | 61.85s | 9.62s | **3.33s** |
| Llamadas a `extranjero_sin_ecuador` | 23 268 | 12 954 | 1 706 |
| Llamadas a `geo_hit`/`re.search` | 1 795 076 | 977 790 | 189 358 |
| Proyección a los ~1744 artículos reales | ~2700s (45 min) | ~419s (7 min) | **~19.4s (0.3 min)** |

### Mejora adicional — carga progresiva (salió de medir el resultado del Paso 2)

Con los arreglos de arriba, la corrida real completa (feeds + agrupamiento + IA en modo lectura +
`write_outputs`) bajó a 31-48 segundos — un cambio de "nunca termina" a "menos de un minuto", pero
todavía por encima de la meta de Fernando ("noticias visibles en menos de 10 segundos"). La razón:
el enlazado de puerto + arranque del servidor HTTP vivía DENTRO de `_arrancar_backend()` (después
de la primera pasada del feed), así que la ventana nunca podía mostrar nada real hasta que esa
pasada terminara — ni siquiera si YA había un `dashboard.html` bueno de la corrida anterior.

**Arreglo**: el enlazado de puerto + arranque del servidor HTTP se movió AL PRINCIPIO de `serve()`,
antes de la primera pasada del feed (bindear un socket es prácticamente instantáneo, nunca depende
de red/IA). Si ya existe un `dashboard.html` de una corrida anterior (el caso normal, salvo la
primerísima vez que se usa el programa), la ventana se abre mostrando ESE dato real de inmediato —
ni siquiera el esqueleto de la Fase 16 — mientras la pasada nueva corre de fondo; cuando termina, el
propio `dashboard_template.html` (que YA sabía refrescarse solo con el poll periódico de `data.json`
y mostrar "Actualizado hace...", sin ningún cambio de frontend necesario) se actualiza solo. Si NO
hay `dashboard.html` previo (primera vez real), se sigue mostrando el esqueleto de la Fase 16 sin
cambios ahí.

**Medido en vivo, servidor real, con el `.exe` recompilado final**: `puerto bindeado` →
`primera respuesta HTTP (GET /dashboard.html)` en **1.45 segundos** (una corrida) y **0.33
segundos** medido con `curl` directo (otra corrida) desde el arranque del proceso — muy por debajo
de la meta de 10s. La pasada de fondo siguió corriendo normal (30.96s esa misma corrida) y el
dashboard ya visible se refrescó solo al terminar, sin que el usuario tuviera que esperar nada.

### Verificación final (Paso 3)

- **`test_arranque_tiempos.py`** (escrito por Codex, mide con reloj monotónico tiempo hasta
  noticias visibles y tiempo hasta la corrida completa, en `.py` y en `.exe`, contra los MISMOS
  datos reales): corrida real, `.py` → 54.6s hasta la corrida completa, `.exe` → 38.6s — las dos
  terminan solas, sin colgarse. (El campo "hasta noticias visibles" del script dio `null` para el
  `.exe` por una carrera de milisegundos propia del script de prueba entre el marcador de log y el
  arranque del servidor -- no un problema del programa: el servidor real respondió en <1.5s, ver
  la medición directa de la carga progresiva arriba.)
- **Feed que no responde**: simulado en aislamiento (URL no enrutable, `10.255.255.1`):
  `_fetch_feed()` cortó exactamente a los 8s (`MONITOR_FEED_TIMEOUT`) sin lanzar excepción, y con
  `collect()` en paralelo (`ThreadPoolExecutor`) un feed colgado nunca frena a los demás —
  confirmado también con datos reales (el feed "Wambra" devolvió HTTP 429 en TODAS las corridas de
  hoy sin afectar el tiempo total de `collect()`, siempre 5-10s con 54 feeds).
- **Tope de gasto de IA**: confirmado en vivo bajo condiciones reales, no simuladas -- el
  presupuesto diario de Gemini ($1.00) se agotó de verdad durante esta sesión por las corridas
  reales del propio diagnóstico. Ya funcionaba bien desde la Fase 10 (`_cabe_en_presupuesto()`,
  `data.json["estado_ia_nube"]`); confirmado que ninguna llamada a `get_ia`/`get_contexto`/etc. se
  colgó esperando presupuesto, todas devolvieron rápido y sin gastar más.
- **Reutilización de cachés entre arranques**: no se hicieron 3 corridas completas adicionales a
  propósito (presupuesto diario ya agotado por las pruebas de este mismo diagnóstico) -- verificado
  en cambio con la evidencia ya acumulada de las 4+ corridas reales de hoy: la etapa `get_ia` de
  `run_fast()` (modo lectura, solo lee `ia_cache.json`) se mantuvo consistentemente rápida
  (0.15-0.46s) en todas, sin crecer con el tamaño del caché -- si estuviera reprocesando de cero en
  cada arranque, ese tiempo habría crecido.
- **Suite de pruebas**: 325 pruebas (322 + 3 nuevas de `test_fase17_arranque.py`). Al cierre de
  esta sesión aparecen 18 fallos: los 15 de siempre (`test_fase9_xapi.py`, no relacionados, buscan
  `xapi.GASTO_PATH` movido en la Fase 9) MÁS 3 nuevos (`test_cjng_samborondon_via_embedding`,
  `test_trump_xi_en_dos_idiomas_se_unen`, `test_parafraseo_extremo_se_reconcilia_recien_con_
  embeddings_del_trabajador`) causados por el presupuesto de Gemini agotado por las pruebas de HOY
  MISMO (confirmado: `ia.embed()` devuelve `None` con `last_error: "presupuesto agotado"`) -- estas
  3 pruebas usan `@unittest.skipUnless(ia.embed_disponible(), ...)`, pero `embed_disponible()` solo
  confirma que el modelo está configurado, no que quede presupuesto para llamarlo (hueco real desde
  la migración a Gemini de la Fase 10, no introducido en esta Fase 17). No se tocó `ia.py` ni el
  skip de estas pruebas (fuera de alcance de este arreglo) -- deberían volver a pasar solas cuando
  el presupuesto diario se resetee.
- Recompilado `Spike.exe` dos veces durante esta fase (una tras los arreglos del Paso 2, otra tras
  la carga progresiva) -- la segunda es la que queda en `codigo_fuente/Spike.exe` al cierre.

### Pendientes reales de la Fase 17

1. Las 3 pruebas de embeddings fallan hoy por presupuesto agotado (ver arriba) -- revisar mañana
   (o subiendo `MONITOR_IA_TOPE_DIA_USD` a propósito, decisión de Fernando) que vuelvan a pasar.
2. El hueco de `ia.embed_disponible()` (no distingue "modelo configurado" de "queda presupuesto")
   es una mejora real para una próxima sesión -- no se tocó en esta Fase por estar fuera del
   alcance pedido (arreglo del `.exe` lento, no del sistema de presupuesto).
3. `test_arranque_tiempos.py` (de Codex) tiene una carrera de milisegundos propia en la detección
   de "noticias visibles" para el modo `.exe` -- no afecta la medición real (confirmada por otra
   vía, `curl` directo), pero valdría la pena que Codex la ajuste si se va a seguir usando este
   script en el futuro (ej. reintentar el chequeo HTTP una vez más después de ver el marcador de
   log, antes de darlo por perdido).
4. La ganancia de "carga progresiva" solo aplica desde la SEGUNDA vez que se abre el programa en
   una carpeta (necesita un `dashboard.html` previo) -- la primerísima vez sigue viendo el
   esqueleto de la Fase 16 hasta que la primera pasada real termine (ahora en 30-50s en vez de
   45+ minutos, pero no instantáneo, porque genuinamente no hay nada que mostrar todavía).

## Fase 18 (2026-09-29) — Pulso social reorganizado por red social

Pedido de Fernando: "ordena las categorías del pulso social por red social. Y de cada red social
sacar el que están diciendo" — confirmado con él que el orden pedido es RED primero (Bluesky/
YouTube/Reddit/Mastodon/Telegram como secciones propias), TEMA segundo adentro de cada red, con
las publicaciones reales — no un resumen nuevo generado por IA (esa opción se le ofreció aparte y
la descartó).

**`renderSocial()` (`dashboard_template.html`) reescrita**: antes agrupaba PRIMERO por tema (con
el desglose por fuente adentro, como conteos); ahora agrupa PRIMERO por red social, y dentro de
cada red lista los temas de los que habla esa red, con las publicaciones reales de esa combinación
red+tema (ordenadas por cuántas publicaciones aporta esa red a cada tema). Mismo dato de siempre
(`DATA.social[tema].top`, cada post ya traía `.fuente`) — el cambio es de armado/orden en el
frontend, sin tocar nada del backend (`social.py`/`monitor.py`/`get_social`). El toggle de ámbito
(Todos/Ecuador/Guayaquil/Mundo) se sigue aplicando igual, filtrando los temas ANTES de repartirlos
por red. Simplificación deliberada (aprobada explícitamente por Fernando antes de escribir el
código, viendo una previsualización): esta vista ya no muestra el sentimiento/polarización/resumen
OSINT ni la separación "gente vs. medios" en bloques separados (se reemplazó por un chip chico
"medio" junto al autor) — el dato de OSINT sigue calculándose y viviendo en `DATA.social[tema]`
igual que antes, solo no se renderiza en este panel reorganizado; si hace falta más adelante, se
puede agregar en otro lado sin tocar el cálculo.

**BUG REAL encontrado reescribiendo esta función (no introducido en esta fase, ya existía)**:
`fuenteChip` estaba definida DOS VECES en `dashboard_template.html` con firmas distintas —
`fuenteChip(f)` (Parte A, insignia de color por red: "Bluesky"/"YouTube"/...) y, más abajo,
`fuenteChip(material, id)` (Fase 11, cita de una pieza de material verificado del contexto). Por
hoisting de funciones en JavaScript, la declaración que queda vigente en TODO el archivo es la
ÚLTIMA — la de `material/id` — así que las 6 llamadas de un solo argumento (`fuenteChip("bluesky")`,
etc.) en realidad invocaban la otra función con `material="bluesky"`, `id=undefined`; como
`"bluesky"[undefined]` es `undefined`, esa función devolvía `""` siempre. Resultado real: las
insignias de red coloreadas en Pulso social (por tema, por publicación, en "Debate real — por
historia") y en el Buscador en vivo (panel "🗣 Lo que dice la gente") venían rindiendo VACÍAS todo
este tiempo, sin ningún error visible en consola (JavaScript no avisa de una colisión de nombres de
función, solo se queda con la última). Arreglado renombrando la insignia de red a `fuenteBadge(f)`
y actualizando sus 6 usos (`fuenteChip(material, id)`, la de citas, quedó intacta con su único uso).

**Verificado sin abrir un navegador** (esta sesión no tiene esa herramienta): `node --check` sobre
el script embebido en `dashboard_template.html` Y sobre el `dashboard.html` real ya generado con
datos reales — sintaxis válida en los dos. Además, se armó un arnés en Node.js aparte que carga
SOLO las funciones involucradas (`CATCOLOR`/`THEME_CAT`/`themeColor`/`esc`/`FUENTE_INFO`/
`fuenteBadge`/`renderSocial`) con un `DATA.social` real sacado de `data.json` (20 temas reales) y
un DOM mínimo simulado (`$`, `.innerHTML`, `.textContent`), y se llamó a `renderSocial()` de
verdad: sin excepciones, la salida quedó agrupada por red (confirmado con los 3 casos reales de la
corrida: Bluesky con 10 temas/16 publicaciones, YouTube, Mastodon), las insignias de red salieron
con color y texto reales (confirma el arreglo del bug de arriba), y el filtro de ámbito se probó
con los 4 valores reales (sin filtro: 40943 caracteres de HTML; "ecuador": 1983 caracteres, solo el
único tema real marcado Ecuador en esa corrida; "internacional": mensaje honesto de "sin temas en
este ámbito" porque ningún tema de esa corrida real tenía ese ámbito; "guayaquil": 39489
caracteres, los 19 temas restantes). **Nota de proceso**: la primera versión de esta verificación
dio un falso positivo (el filtro de ámbito parecía no funcionar) por una limitación del propio
arnés de prueba (usar `eval()` en dos llamadas separadas crea bindings de `let` distintos para
`socialAmb`) — no un bug del código real; se confirmó reescribiendo el arnés para que todo corra en
un solo `eval()`, y ahí el filtro funcionó correctamente en los cuatro casos.

Se regeneró `dashboard.html` con datos reales (`python monitor.py once`, sin `MONITOR_SAMPLE`) y se
recompiló `Spike.exe` con la plantilla nueva embebida. Suite de pruebas de Python completa
(325 pruebas): sin cambios respecto a antes de esta fase (mismos 18 fallos ya documentados en la
Fase 17 — 15 de `test_fase9_xapi.py` + 3 de presupuesto de Gemini agotado — ninguno relacionado con
este cambio, que es puro frontend).

### Pendientes reales de la Fase 18

1. No se revisó visualmente en un navegador real (esta sesión no tiene esa herramienta) — la
   verificación fue por sintaxis + un arnés de Node.js que simula el DOM mínimo necesario, no una
   captura de pantalla real.
2. El sentimiento/polarización/resumen OSINT por tema (que SÍ se sigue calculando) no tiene hoy
   ningún lugar donde mostrarse en el dashboard — quedó fuera de este panel a pedido explícito de
   Fernando; si más adelante lo quiere de vuelta, hay que decidir dónde encaja (¿una pestaña aparte
   por tema? ¿un resumen por red, la opción que se descartó esta vez?).
3. El bug de `fuenteChip` duplicada llevaba un tiempo sin detectarse (no se investigó desde cuándo
   exactamente). Revisado con `grep` si hay MÁS funciones `function NOMBRE` repetidas en todo
   `dashboard_template.html` tras este arreglo: ninguna — era la única colisión.

### Segunda vuelta de la Fase 18 (mismo día) — por qué Fernando seguía sin ver el cambio, y "página interminable"

Fernando reportó dos veces seguidas que el cambio de la Fase 18 no se veía. Causas reales,
confirmadas una por una (no adivinadas):

1. **`Spike.exe` estaba corriendo cuando se intentó recompilar** — Windows bloquea un `.exe` en
   uso, `xcopy` falló con "Sharing violation" al copiar el build nuevo, pero `compilar.bat` corría
   el `rmdir` de todos modos SIN chequear si el copiado había funcionado — el build nuevo recién
   compilado se borraba igual, sin ningún aviso, dejando el `.exe` VIEJO (el que seguía corriendo)
   intacto. Arreglado: `compilar.bat` ahora revisa el resultado de `xcopy` antes de borrar
   `dist_compilado\monitor.dist` — si falla, avisa explícitamente "cerrá Spike.exe" y NO borra el
   build nuevo (queda a salvo ahí para el siguiente intento).
2. **Cache del navegador embebido (WebView2)**: investigado a fondo el código de `pywebview` —
   con `private_mode=True` (el default, nunca cambiado en este proyecto), cada arranque de
   `Spike.exe` usa una carpeta de caché TEMPORAL nueva (`tempfile.TemporaryDirectory()`), así que
   esto en particular NO explicaba el problema (se pensó que sí en la ronda anterior, quedó
   descartado con evidencia real leyendo el código de `webview/platforms/winforms.py`). Aun así, se
   dejó el arreglo de `Cache-Control: no-cache` en el servidor (`Quiet.end_headers()`,
   `monitor.py`) porque SÍ protege el caso real de correr `python monitor.py serve` y abrirlo en un
   navegador normal (Chrome/Edge), que sí persiste caché entre sesiones.
3. **BUG REAL, la causa de fondo**: al reescribir `renderSocial()` para agrupar por red, nunca se
   actualizó el `<h2>`/párrafo de descripción ESTÁTICOS que están arriba del panel en el HTML
   (`dashboard_template.html`) — seguían diciendo "Por tema (resumen agregado)" y describiendo
   sentimiento/polarización/"gente vs. medios" en bloques separados, cosas que ya no se calculan
   en esta vista. Aunque el contenido de ABAJO sí estaba agrupado por red, el título y la
   descripción seguían describiendo el diseño viejo — probablemente por eso no se percibía como un
   cambio real. Corregido: título ahora dice "Por red social", descripción actualizada.
4. **"Página interminable"**: el panel nuevo no tenía ningún límite -- listaba TODOS los temas del
   catálogo (hasta 20) dentro de cada red, uno debajo del otro. Arreglado con el mismo patrón ya
   usado en Contraste (`CONTRASTE_PAGE`/`contrasteExpandido`): `SOCIAL_PAGE=5` temas visibles por
   red antes de un botón "Ver mas (N tema(s) mas)" por red (`socialExpandido`, independiente por
   red). Medido con datos reales (arnés de Node.js): el HTML del panel bajó de 41178 a 16645
   caracteres con el tope puesto, y expandir una red con el botón la vuelve a mostrar completa sin
   afectar a las demás.
5. Se le pidió a Fernando explícitamente "no uses emojis de ahora en adelante" — se quitaron los
   ~45 emojis que quedaban en `dashboard_template.html` (insignias, botones, títulos, etiquetas de
   tipo de alerta, etc.), reemplazados por texto plano o quitados donde eran solo decorativos. Se
   dejaron sin tocar los emojis que puedan aparecer DENTRO del texto citado de una publicación real
   de redes sociales (no es contenido nuestro, no corresponde editarlo). Guardado como preferencia
   permanente en la memoria del asistente (no volver a usar emojis en este proyecto).

Verificado en vivo con el `.exe` recompilado (una vez que Fernando lo cerró): `curl` directo contra
el servidor real confirmó el header `Cache-Control: no-cache`, el texto "Por red social" en la
página servida, y ningún proceso `cmd`/`conhost` colgando del `.exe` (sigue sin consola). Suite de
pruebas: sin cambios (325 pruebas, mismos 18 fallos ya documentados, ninguno nuevo).

### Tercera vuelta de la Fase 18 (mismo día) — BUG GRAVE: ni siquiera las Noticias aparecían

Fernando: "acabo de entrar y no solo el problema no esta solucionado, sino que ahora tampoco salen
las noticias del feed." — la sección Noticias, que nunca se había tocado en esta fase, apareció
completamente vacía. Causa real, propia, introducida en el mismo paso donde se quitaron los emojis
(punto 5 de la segunda vuelta, arriba) — **no detectada por `node --check` ni por el arnés de Node
anterior**, los dos métodos de verificación usados hasta ese momento:

- Al quitar el emoji del ícono del menú móvil (`📊`/`🧭`), se borró la línea que declaraba
  `const ico = p==="asistente" ? "..." : "...", lbl = ...;` dejando solo `const lbl = ...;` — pero
  UNA línea más abajo seguía existiendo `$("#mobileMenuIco").textContent = ico;`, que ahora
  referenciaba una variable que ya no existía. Esto lanza `ReferenceError: ico is not defined`
  DENTRO de `showProducto(p)`, función que se llama de forma SÍNCRONA en el nivel superior del
  script (`showProducto(productoFromHash());`, cerca de la línea 3322) — un error ahí corta la
  ejecución del resto del `<script>` completo, incluyendo la llamada a `hydrate(); renderAll();`
  (~línea 3394) que puebla `#list` con las noticias. Resultado: página en blanco en Noticias, sin
  ningún error visible para Fernando (solo en la consola del navegador, que él no tiene forma de
  ver).
- **Por qué los métodos de verificación anteriores no lo agarraron**: `node --check` solo valida
  SINTAXIS (que el JavaScript esté bien formado), nunca lo EJECUTA — una referencia a una variable
  inexistente es válida sintácticamente, revienta recién en tiempo de ejecución. El arnés de Node.js
  usado en la Fase 18 (segunda vuelta) solo cargaba y ejecutaba las funciones de `renderSocial()`
  en aislamiento, nunca el script completo de punta a punta como lo hace un navegador real.
- **Arreglo del método de verificación** (para no repetir esta clase de bug): se instaló `jsdom`
  (`npm install jsdom` en una carpeta de trabajo, herramienta de Node.js que sí ejecuta una página
  HTML completa con su DOM, como un navegador headless) y se armó una prueba que carga el
  `dashboard.html` REAL (generado con datos reales), lo ejecuta de punta a punta, y hace click
  programático en cada botón de navegación principal (Noticias/Última hora/Pulso
  social/Estadísticas/Oportunidades/Contraste/Guardadas/Buscar) más los botones de
  Dashboard/Asistente/sidebar/menú móvil — así se agarra cualquier excepción de ejecución en
  cualquier punto de la página, no solo en la función que se tocó. Confirmado con esta prueba: la
  página fallaba exactamente como describía Fernando (`#list` con 0 caracteres); con el arreglo
  aplicado, cero errores en las 12 interacciones probadas y `#list` con contenido real (>50000
  caracteres).
- **Arreglo real**: se borró la línea `$("#mobileMenuIco").textContent = ico;` (el elemento
  `#mobileMenuIco` tampoco existe más en el HTML, se había quitado en el mismo pase de emojis).
- **Nota de transparencia, proceso propio**: mientras se diagnosticaba este bug se corrió
  `python monitor.py once` para regenerar un `dashboard.html` de prueba MIENTRAS el `Spike.exe` de
  Fernando seguía corriendo en vivo — algo que este mismo documento ya advierte no hacer (ver
  "Bug real propio" de la sesión del 2026-09-23, segunda tanda). Se verificó con `json.load()`
  inmediato que `data.json`/`historias_registro.json` no quedaron corruptos (la escritura atómica
  del proyecto protege contra esto; en el peor caso es "gana la última escritura", sin daño real) y
  se copió el resultado a una carpeta aparte para las pruebas de aquí en más, sin volver a tocar los
  archivos reales del proyecto mientras `Spike.exe` seguía activo.

**Verificado con el `.exe` recompilado y corrido de verdad** (no solo con datos generados por
`python`, la corrida real del binario): se lanzó `Spike.exe` recién compilado, se esperó a que
bindeara el puerto (confirmado en `arranque.log`), y se hizo `curl` directo contra
`http://127.0.0.1:8000/dashboard.html` servido por ESE proceso — confirmado sin `mobileMenuIco`,
con "Por red social" y `SOCIAL_PAGE = 5` presentes, con el header `Cache-Control: no-cache`. Se
revisó además que los únicos emojis que sobreviven en la página servida están dentro de texto
CITADO textual de publicaciones reales de redes sociales (Bluesky/Mastodon/X/YouTube, ej. "🎉🎉🎉" en
un comentario real de YouTube) — nunca en textos propios de la interfaz, consistente con la decisión
ya documentada de no alterar contenido citado de terceros. Suite de pruebas de Python completa:
325 pruebas, mismos 18 fallos ya documentados (15 de `test_fase9_xapi.py` + 3 de presupuesto de
Gemini agotado ese día), ninguno nuevo.

**Lección para cualquier cambio futuro de `dashboard_template.html`**: `node --check` (sintaxis) y
un arnés que prueba una función aislada NO alcanzan para confirmar que un cambio no rompió nada —
hace falta ejecutar la página COMPLETA (con `jsdom` o equivalente) y recorrer al menos la
navegación principal antes de dar un cambio de frontend por probado, sobre todo si el cambio toca
código que corre en el nivel superior del script (fuera de una función que se llama bajo demanda).

## Fase 19 (2026-09-29) — Pulso social sin orden: alertas por encima del selector, sin "carpeta" por red

Cuarto reclamo seguido sobre Pulso social. Fernando: "la pagina del pulso social es eterna y
tiene una cosa sobre otra, no tiene un orden y una forma de 'poner en carpeta' cada cosa, por
ejemplo no se que saco el programa de twitter, que saco de youtube, que saco de tal, etc, y
adicional, todas las alertas de sucesos de twitter estan por encima de la selección para
identificar cosas de Ecuador, internacionales y Guayaquil." Dos problemas reales, confirmados
leyendo el HTML/JS existente (no adivinados):

1. **El toggle de ámbito (`#socialseg`, Ecuador/Guayaquil/Internacional) vivía al FINAL de la
   página**, justo antes del panel "Por red social" — y solo controlaba ESE panel. El bloque
   "Alertas de la gente" (que desde la Fase 9-D incluye señales de X/Twitter) vivía al PRINCIPIO,
   con su PROPIO toggle sin relación (nivel de corroboración: Todas/Corroborado/Confirmado
   oficial) — nunca respetaba ningún filtro de ámbito. Literal: las alertas de Twitter estaban
   "por encima" del selector, tal como reportó Fernando.
2. **Ningún panel de Pulso social tenía un filtro por RED** — "Alertas de la gente" mezclaba
   señales de Bluesky/Telegram/X/fuentes oficiales en el mismo texto plano (sin insignia de color
   ni forma de aislar una red), y "Debate real — por historia" tampoco distinguía. Solo "Por red
   social" (Fase 18) ya agrupaba por red, pero era el TERCER bloque de la página — para llegar
   ahí había que pasar por Alertas (sin límite de cantidad, "página eterna") y Debate real.

### Arreglo

**Dos toggles nuevos, compartidos por TODA la página**, movidos al principio de `#secSocial`
(antes de "Alertas de la gente"):
- **Ámbito** (`#socialseg`, ya existía pero solo para "Por red social" — ahora controla las TRES
  piezas): Todos/Ecuador/Guayaquil/Internacional.
- **Red** (`#socialFuenteSeg`, nuevo — el pedido explícito de "poner en carpeta"): Todas las
  redes/Bluesky/YouTube/Reddit/Mastodon/Telegram/X (Twitter)/Fuentes oficiales.

**Alertas de la gente** (`alertas.py` no se tocó, es puro frontend): las alertas nunca tienen
ámbito "Internacional" por diseño (son sucesos locales, ver `alertas.BARRIOS_GYE`/
`detectar_lugar`) — se deriva en JS (`alertaAmbito(a) = a.lugar ? "guayaquil" : "ecuador"`) sin
necesitar tocar el backend; con "Internacional" seleccionado, las alertas se ocultan con un
mensaje honesto en vez de mostrarlas igual. El filtro de red compara contra `senal.fuente`
("bluesky"/"telegram"/"x") o `senal.oficial` para "Fuentes oficiales". Cada señal dentro de una
tarjeta ahora usa `fuenteBadge()` (la misma insignia de color de "Por red social") en vez de texto
plano, así se ve de un vistazo de qué red vino. Se agregó paginación (`ALERTAS_PAGE=8` + "Ver
más", mismo patrón que el resto del proyecto) — antes no tenía ningún límite.

**Debate real — por historia**: `monitor.get_social_historias()` (`monitor.py`) calculaba
`ambito` (`"guayaquil"` si `s["ciudad"]=="Guayaquil"`, si no `"ecuador"`) pero nunca lo guardaba
en la entrada cacheada — se agregó `"ambito": ambito` a las dos ramas del diccionario de salida
(historia sin posts y con posts). Entradas del caché de ANTES de este cambio no tienen el campo
todavía (`undefined` en el frontend) — el filtro las excluye cuando hay un ámbito activo distinto
de "Todos" hasta que el trabajador las recalcule solas (mismo patrón de migración gradual ya usado
varias veces en este proyecto, ej. `interp_v` de la Fase 22/9). Con una red seleccionada, se
filtran las citas de cada postura y el hilo principal (X/fuentes oficiales nunca alimentan este
panel — se avisa explícito en vez de mostrarlo vacío sin explicación).

**Por red social** (Fase 18): con una red elegida, ahora muestra SOLO el bloque de esa red en vez
de las 5 apiladas (antes ya tenía su propio "Ver más" por red, pero todas quedaban visibles a la
vez) — reduce aún más la "página interminable". X/oficial muestran el mismo aviso honesto que en
Debate real (nunca alimentan este panel).

**Verificado con datos reales, no simulados** (splice de `dashboard_template.html` nuevo +
`data.json` real en un archivo de prueba aislado, cargado con `jsdom` — método adoptado tras el
bug del `ico` de la Fase 18, ver la lección de arriba): con el filtro de red en "X (Twitter)", las
43 alertas reales de esa corrida se mantuvieron TODAS visibles (confirmado por separado con
Python: **43 de 43 alertas tenían al menos una señal de X, 0 de Bluesky/Telegram/oficial** en el
momento de la prueba) — la respuesta honesta a la pregunta real de Fernando ("¿qué sacó el
programa de Twitter?") es, hoy, "todo lo que hay en Alertas". Con "Bluesky"/"Telegram"/"Oficial"
seleccionados, el panel de Alertas quedó vacío (0 tarjetas) — correcto, no un bug, confirmado
contra los datos reales. El filtro de ámbito "Internacional" ocultó las alertas (por diseño) y
mostró "Debate real"/"Por red social" con su aviso honesto (0 temas de ámbito Mundo en esa
corrida real). Paginación de Alertas confirmada: 8 tarjetas visibles → 43 tras "Ver más", sin
errores.

**BUG PROPIO en el primer intento de filtro de ámbito** (encontrado antes de aplicar el cambio,
no llegó a producción): la primera versión de la condición de ámbito para Alertas usaba un
ternario anidado sin paréntesis (`!socialAmb || socialAmb==="internacional" ?
socialAmb==="internacional"?false:true : alertaAmbito(a)===socialAmb`) — funcionaba por la
precedencia real de operadores en JS, pero era ilegible y frágil para tocar despues. Se extrajo a
una función nombrada (`alertaPasaAmbito`) con un comentario explicando los tres casos, antes de
integrarla al filtro real.

**Verificación del `.exe` recompilado — hallazgo real, no resuelto del todo**: al relanzar
`Spike.exe` para la verificación final, la primera corrida se quedó colgada en
`cluster: agrupando N articulos contra el registro persistente...` varios minutos, y el
`arranque.log` (que se trunca una vez por PROCESO) apareció con una `=== arranque ===` COMPLETAMENTE
NUEVA unos 6 minutos después, sin que nadie relanzara el programa a mano — consistente con que el
PRIMER proceso murió en silencio (sin ninguna línea de error, ni en `arranque.log` ni en el stdout
capturado) y algo lanzó una SEGUNDA instancia que sí completó una pasada entera (27s) antes de
morir tambien, sin error visible, unos segundos después de `INICIO redes_pasada`. Se relanzó una
TERCERA vez y se vigiló minuto a minuto con un monitor de proceso: esa instancia sí sobrevivió
mucho más allá del punto exacto donde la segunda había muerto (completó una vuelta ENTERA del
trabajador -- `embed_pendientes_registro` hasta `get_social_historias` -- y volvió a arrancar el
ciclo rápido de nuevo), lo que descarta que el código nuevo de esta fase sea la causa. **No se
identificó la causa raíz de por qué las dos primeras instancias murieron sin dejar rastro de
error** -- candidatos sin confirmar: presión de memoria en esta sesión de verificación (se venían
corriendo varias pruebas de Node/Python pesadas en paralelo justo antes), o un artefacto propio de
lanzar el `.exe` desde una terminal automatizada en vez de con doble clic real. `data.json`/
`historias_registro.json` se confirmaron con JSON válido después de las muertes (sin corrupción,
la escritura atómica del proyecto protegió como siempre). **Si a Fernando le pasa lo mismo
(Spike.exe se cierra solo sin aviso, sobre todo la primera vez que lo abre después de no usarlo un
tiempo largo), es la primera pista a revisar la próxima sesión** — no se pudo reproducir con
certeza ni confirmar si es un problema real del programa o exclusivo de este entorno de prueba.

Suite de pruebas de Python completa tras el cambio: 325 pruebas, mismos 18 fallos ya documentados
(15 de `test_fase9_xapi.py` + 3 de presupuesto de Gemini agotado), ninguno nuevo. `Spike.exe`
recompilado con el cambio.

### Pendientes reales de la Fase 19

1. **Muerte silenciosa de las dos primeras instancias del `.exe` durante esta verificación** (ver
   arriba) — no reproducida con certeza, no confirmada como bug real del programa ni descartada
   del todo. Si vuelve a pasar, revisar el Administrador de tareas de Windows por un posible cierre
   por memoria, y si hay forma de capturar un volcado/traza del momento exacto en que el proceso
   desaparece (hoy `arranque.log` no registra nada si el proceso muere sin excepción Python
   capturada, ej. un `SIGKILL`/OOM del sistema operativo).
2. Entradas viejas de `social_historias_cache.json` (de antes de este cambio) no tienen el campo
   `ambito` todavía -- se completan solas cuando el trabajador las recalcule (TTL normal), no hace
   falta ninguna acción manual.
3. No se revisó visualmente en un navegador real (esta sesión no tiene esa herramienta) -- toda la
   verificación fue con `jsdom` contra datos reales (ver arriba), que confirma comportamiento y
   ausencia de errores mas no la apariencia visual de los dos toggles nuevos.
