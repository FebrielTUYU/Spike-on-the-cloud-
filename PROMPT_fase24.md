# Fase 24: IA gratuita, recolección mucho más amplia y precisión (local, internacional, contraste)

Trabajas en Spike (`codigo_fuente\`) junto con Codex, con el flujo de siempre: tú diagnosticas, implementas y verificas, y Codex revisa cada cambio grande. No edites los archivos de estado en tiempo de ejecución (`data.json`, `*_cache.json`, `historias_registro.json`, `comunidad.json`…); solo léelos.

La interfaz de la Fase 23 quedó bien. Esta fase es sobre **cuánta información entra y qué tan precisa es**. Es un trabajo largo: hazlo por partes, en el orden de abajo, y cierra cada parte con números de antes y después medidos sobre datos reales.

---

## Diagnóstico de partida (medido en el `data.json` real del 2026-09-30 22:22 UTC)

Úsalo como línea base y como casos de prueba. Confirma cada cifra antes de tocar código.

**IA agotada.** `ia_gasto.json`: $1.00 el 29-sep y $1.00 el 30-sep (el tope diario). Como resultado:
- `ia` 201/571
- `contexto` 103/571
- `veredicto_ia` 0/571 (todas "pendiente")
- embeddings 736/2631 historias

Los embeddings **comparten el mismo tope** que la IA (`estado_embeddings` muestra "gasto hoy $1.0000"). Cuando se acaba el dinero, también deja de funcionar la unión de noticias en inglés y español. `ia_nube_estado.json` además registra pausas por HTTP 429. El historial de gasto no guarda **qué módulo** hizo cada llamada (solo "generar (rapido…)"), así que hoy no se sabe quién consume más.

**Comunidad y mapa.** El mapa tiene 25 puntos (16 noticias, 3 alertas, 6 comunidad) y hay 34 noticias de Guayaquil "sin sector reconocible". Comunidad tiene 35 publicaciones en 10 h (X 34, YouTube 1, Bluesky 0). Hay 0 cuentas comunitarias aprobadas.
- La consulta de X de Comunidad (`comunidad.consulta_x`) **exige la palabra "Guayaquil"** junto a los términos de queja, y la mayoría de las quejas reales no la escriben: nombran el barrio o etiquetan a la institución.
- YouTube trae 3 videos y 20 comentarios una vez por hora, cuando la cuota gratis es de 10 000 unidades/día (una búsqueda cuesta 100 y una página de comentarios cuesta 1). Se usa una fracción mínima.
- Hay 43 feeds RSS. De instituciones solo aparece el Municipio.

**Categorías.**
- 235 de 571 historias quedan en "general" y 128 no tienen temas.
- Caso real: "Retiro de poste permitirá renovar el sistema sanitario en la Av. Rodolfo Baquerizo Nazur" quedó con temas **Empleo, Salud**.
- Su gemela, "Poste de energía… provocó el retraso de las obras en La Alborada, según el Municipio", quedó en **Economía, Empleo, Petróleo/Energía**.

**Agrupamiento.** Esas dos notas son el **mismo hecho** y quedaron como dos historias separadas. En Internacional, "US Supreme Court lets Trump resume deportations to third countries" y "El Tribunal Supremo de EE. UU. permite a Trump reanudar las deportaciones" también están separadas. Pasa lo mismo con 3 historias distintas sobre encuestas Lula–Bolsonaro.

**Internacional.** 153 historias:
- Infobae aporta 67.
- Se cuelan deportes en inglés ("Cristiano Ronaldo misses Portugal training").
- Casos ecuatorianos marcados como internacionales ("Capturan a José Walther Manrique… caso Progen", "New Jerson cumplirá en libertad…").

**Contraste.** Estados: `corroborado_medios` 286, `sin_hallazgo` 276, `documento_oficial` 8, `hallazgo` 1.
- La nota del poste salió "corroborada: 3 medios cuentan lo mismo", pero uno de esos 3 "medios" es **el propio Municipio**, que es la parte interesada, y los otros dos repiten su versión. Es circular.
- La gemela salió "sin_hallazgo" porque solo se buscó en Asamblea, Registro Oficial, INEC, BCE y SERCOP. Nunca se buscó en CNEL, EMAPAG o Interagua, en los boletines del Municipio ni en el contrato de la obra.

**Redes.** El gasto de X del día fue de ~$0.13, con el tope mensual en $4.70. Por eso X no puede crecer mucho más sin subir el presupuesto: hay que sacarle más rendimiento a cada dólar.

---

## Parte 0: medición y conjunto de evaluación (antes de cambiar nada)

1. Agrega a `ia_gasto.json` el **módulo** que hizo cada llamada (triaje, contexto, veredicto, declaraciones, comunidad, embeddings, chat) y los tokens de entrada y salida. Muestra en el panel de gasto el reparto por módulo.
2. Arma `pruebas/evaluacion_fase24.csv` con **120 historias reales** del registro: 60 locales (al menos 30 de Guayaquil) y 60 internacionales. Incluye sí o sí los casos citados arriba. Columnas: titular, medios, categoría esperada, ámbito esperado (Guayaquil / resto de Ecuador / mundo), tipo esperado (acción / anuncio / declaración / dato; ver Parte C), ciudad esperada y el grupo con el que debería unirse.
   - Prellena lo que puedas y **deja a Fernando revisar y corregir** el CSV antes de usarlo para medir. Sin ese visto bueno no se reporta precisión.
3. `evaluar_fase24.py` calcula sobre ese CSV: exactitud de categoría, ámbito, tipo y ciudad, y pares mal unidos o mal separados. Esa es la medida de "más preciso" para toda la fase.

---

## Parte A: IA sin costo (primero, porque hoy el presupuesto bloquea todo lo demás)

Objetivo: que el trabajo de fondo **no gaste nada** y que el tope pagado de Gemini quede solo para lo que Fernando pide en persona.

**A1. Menos llamadas antes de cambiar de proveedor**
- Todo lo que se pueda resolver con reglas va sin IA: basura, deportes (también en inglés), ventana de tiempo, duplicados exactos, ciudad y barrio por diccionario, y verbos de atribución y tiempo verbal para la Parte C.
- **Por lotes:** triaje de 20 a 30 historias por llamada, con salida JSON por historia, en vez de una llamada por historia.
- **Caché por contenido:** hash del titular + resumen normalizados. Una historia que no cambió no se vuelve a procesar.
- **Prioridad:** el contexto y el veredicto solo corren para las historias que se muestran (top por sección, Guayaquil y lo que Fernando abre), no para las 571.

**A2. Enrutador que reparte el trabajo** (`ia_router.py`). Fernando no quiere que un solo proveedor cargue con todo. **Cada tarea tiene un proveedor titular distinto** y un respaldo, con cupo diario por proveedor (medido, no supuesto) y registro de quién respondió cada vez. Reparto inicial (ajústalo según lo que midas en la Parte 0):

| Tarea | Titular | Respaldo |
|---|---|---|
| Triaje por lotes (basura/útil, ámbito, ciudad) | Gemini gratis, flash-lite | Groq `gpt-oss-20b` |
| Categoría + acción/anuncio/declaración/dato (Parte C) | Gemini gratis, Gemma (`gemma-4-31b-it` o `gemma-4-26b-a4b-it`) | Cerebras |
| Contexto de las historias que se muestran | Groq `gpt-oss-120b` | Gemini gratis, flash |
| Extracción de afirmaciones y veredicto (Parte E) | Cerebras (`gpt-oss-120b` u otro disponible) | Groq `gpt-oss-120b` |
| Embeddings | Gemini gratis, `gemini-embedding` | modelo local (A3) |
| Chat, Asistente, documentos privados | **Gemini pagado** (como hoy) | ninguno gratis |

- **Groq:** el catálogo de producción de septiembre de 2026 gira en torno a `gpt-oss-120b` y `gpt-oss-20b`. Hay reportes de que los Llama pasaron a "solo por cotización". Confirma en `console.groq.com/docs/models` qué modelos están en el plan gratis antes de fijarlos. El límite que de verdad frena es el de tokens por minuto, así que el enrutador debe respetar RPM y TPM.
- **Gemini gratis:** en un **proyecto aparte, sin facturación**, con una clave distinta de la pagada. Los cupos dependen del proyecto: léelos de AI Studio o de las cabeceras de respuesta.
- **Gemma** no es otra API: son modelos abiertos de Google que se sirven por **la misma API de Gemini** (mismo endpoint `generateContent`, mismo tipo de clave; solo cambia el nombre del modelo). Ya aparecen en la lista de modelos que devuelve la clave de Fernando (`ia_nube_estado.json`: `gemma-4-26b-a4b-it`, `gemma-4-31b-it`). Confirma en AI Studio su cupo y su precio en cada proyecto antes de usarlos.
- **Groq:** Fernando ya tiene la clave. Pídele que la ponga en `.env` como `GROQ_API_KEY` y pruébala primero.
- **Cerebras:** su catálogo gratis cambia seguido; consúltalo en vivo.
- Si un proveedor se agota, su tarea pasa al respaldo; si el respaldo también se agota, la tarea espera. Nunca cae en el Gemini pagado.
- Prueba cada modelo contra el CSV de la Parte 0 y deja el mejor como titular de cada tarea. Si alguno rinde claramente peor que el Gemini actual en español, repórtalo con números.
- **Condición importante:** los planes gratuitos pueden usar lo que se les envía para entrenar. Las noticias públicas pueden ir por ahí. **Los documentos de casos, fuentes o notas privadas de Fernando nunca**: esos van solo por la clave pagada o no van.

**A3. Embeddings gratis y separados del tope:** usa el plan gratis de `gemini-embedding` en el proyecto sin facturación. Si no alcanza, prueba un modelo multilingüe local chico en ONNX (tipo `multilingual-e5-small`) que corra en CPU en su PC (Ryzen 3, 16 GB), pero solo si entra en el `.exe` sin inflar el arranque; mide el tiempo antes de decidir. Meta: el 100 % de las historias con embedding.

**A4. Estado visible:** en el panel de IA, cupo usado y restante por proveedor, cuál está respondiendo, y un aviso claro cuando todos los gratuitos están agotados. En ese caso **no se usa la clave pagada para el fondo**: se espera al día siguiente.

Fernando tiene que crear las cuentas y claves de Groq, Cerebras y el proyecto gratis de Gemini. Deja en `LEEME.md` los pasos exactos y los nombres de variable del `.env` (`GROQ_API_KEY`, `GEMINI_FREE_KEY`, `CEREBRAS_API_KEY`).

---

## Parte B: recolección local mucho más amplia (Guayaquil)

Meta medible: **multiplicar por 5 o más** las publicaciones de la gente de Guayaquil en Comunidad y los puntos del mapa, **sin bajar la precisión**. Se mide con la fracción de publicaciones que de verdad son de Guayaquil en una muestra de 50 revisada a mano.

**B1. X: más rendimiento por dólar (el presupuesto no cambia salvo que Fernando lo suba)**
- Deja de exigir "Guayaquil". Arma consultas por **barrio y sector** (`comunidad.BARRIOS`, en tandas con OR) y por **menciones a instituciones**: `to:` / `@` de alcaldiagye, Interagua_Ec, EmapagEP, CNEL_EP, ATMGuayaquil, ECU911_, BCBGuayaquil, PrefecturaGuayas. Las quejas suelen ir dirigidas a ellas.
- Excluye retuits y medios en la consulta (`-filter:retweets` si el actor lo respeta; verifícalo en vivo).
- Mide el **rendimiento** de cada consulta: quejas útiles de Guayaquil por cada $0.01. Cada semana se apagan las que rinden poco y se refuerzan las que rinden.
- El presupuesto mensual pasa a variable del `.env`, mostrada en el panel con la proyección del mes.
- Fase 23: el panel de cuentas sugeridas sigue con **0 aprobadas**. Asegúrate de que tenga candidatas reales para que Fernando las apruebe.

**B2. YouTube: usar la cuota gratis de verdad** (10 000 unidades/día)
- Toma los **videos recientes de los canales de medios de Guayaquil** (El Universo, Expreso, Extra, Ecuavisa, TC Televisión, Teleamazonas y otros que encuentres; verifica los ID de canal) y lee sus **comentarios**, que cuestan 1 unidad por página. Ahí comenta la gente del barrio.
- Suma búsquedas por barrio y problema (100 unidades cada una) dentro de un presupuesto de unidades diario visible en el panel.
- Frecuencia: comentarios cada 15–30 min. Los comentarios se filtran por su propia fecha, igual que hoy.

**B3. Fuentes gratis nuevas**
- **Google News RSS por búsqueda** (`news.google.com/rss/search?q=…&hl=es-419&gl=EC`): consultas por barrio, por institución y por problema + Guayaquil. Deduplica contra los feeds que ya existen.
- **Instituciones:** prueba `/feed`, sitemap o página de noticias de CNEL EP, EMAPAG, Interagua, ATM, Prefectura del Guayas, Gobernación, ECU 911, Bomberos de Guayaquil, Secretaría de Gestión de Riesgos e INAMHI. Solo agrega lo que responda en vivo y márcalo como **fuente institucional**: es la versión oficial, **no un medio** (ver Parte E).
- **Más medios locales** con feed que funcione (revisa cuáles faltan en `feeds.py`; los muertos quedan comentados, no se borran).
- **Canales públicos de Telegram** de noticias o alertas de Guayaquil, por la vista web pública `t.me/s/<canal>`. Revisa los términos antes, solo canales públicos, y si hay dudas lo dejas desactivado y lo anotas.
- Documenta cada fuente nueva en `salud_fuentes` con su estado.

**B3b. Funcionarios: tuits que Fernando reenvía a Spike (sin Apify, sin costo)**
Decisión de Fernando: él activa en su iPhone las notificaciones de X (la campanita) de los funcionarios que le interesan, empezando por **John Reimberg** (`@JohnReimberg`) y **@MinInteriorEc**. Cuando llega el tuit, lo manda a Spike. Así Spike ve el tuit en el mismo momento que él, antes que los medios (su regla de oro), y sin gastar presupuesto de X.

Lo que hay que construir:
1. **Punto de entrada** en el servidor de Spike, alcanzable desde el celular por el acceso que ya existe (Tailscale serve / `movil.py`, con la misma clave): recibe una URL de tuit (`x.com/…/status/…` o `twitter.com/…`).
2. **Atajo de iOS "Enviar a Spike"** que aparece en el menú Compartir de la app de X: toma la URL y la envía a ese punto de entrada. Deja en `LEEME.md` los pasos exactos para que Fernando lo arme en la app Atajos, con capturas o texto paso a paso. Deben ser **dos toques**: Compartir y "Enviar a Spike".
3. **Lectura del tuit sin Apify:** usa la **API oEmbed pública de X** (`publish.twitter.com/oembed?url=…`, documentada en docs.x.com, no requiere clave) para obtener el texto, el autor y la fecha. Si oEmbed falla (tuit borrado, cuenta protegida, cambio de X), el tuit se guarda igual con la URL, la hora de recepción y el texto que Fernando pegue a mano.
4. **Respaldo en el escritorio:** una caja "Pegar tuit" en el dashboard (enlace o texto) que hace lo mismo.
5. **Qué pasa con cada tuit recibido:**
   - Se registra en `declaraciones.json` a nombre del funcionario (`funcionarios.json`, editable: usuario, nombre, cargo, área, `activa`) y se clasifica con C1. Ejemplo real de esta semana: "Reimberg anuncia un golpe importante contra el crimen organizado" es un **anuncio**, no una acción. Cuando llegue la noticia del operativo, se enlaza con el anuncio y se marca como cumplido o pendiente.
   - Se busca la historia relacionada (embeddings y entidades) y se cuelga en su tarjeta como "Lo que dijo el funcionario". Si no hay historia, crea una historia "solo tuit" marcada como **primicia (aún sin prensa)**.
   - Sirve de insumo al Contraste (Parte E): se compara con los datos, con sus declaraciones anteriores y con otras fuentes.
   - Se mide el **adelanto**: minutos entre la hora del tuit y la primera nota de prensa que lo reporta. Usa Google News RSS por funcionario solo para detectar cuándo lo recoge la prensa.
6. Si un tuit llega desde una cuenta que no está en `funcionarios.json`, se acepta igual y Spike le ofrece a Fernando agregar esa cuenta.

Limitación honesta: Spike solo ve los tuits que Fernando le reenvía. Si no los manda, no entran. Ese es el costo de no pagar la consulta automática.

**B4. Ubicación (el mapa)**
- Hay 34 notas de Guayaquil sin sector. Amplía el diccionario con **avenidas, calles principales, puentes, mercados, hospitales, centros comerciales y cooperativas**, cada uno ligado a su sector. Hoy "Rodolfo Baquerizo Nazur" funcionó; hay que cubrir cientos de referencias así.
- Para lo que no resuelva el diccionario, usa geocodificación con **Nominatim de OpenStreetMap** limitada al área de Guayaquil. Respeta su política de uso: máximo 1 solicitud por segundo, User-Agent propio y caché permanente.
- Cada punto dice cómo se ubicó: por el barrio en el texto, por una calle o referencia, o por geocodificación. Lo que no se ubica se cuenta aparte, como ya se hace.
- **La ventana de 10 h (Fase 21)** es una causa directa de que haya pocos puntos. Mantenla como opción por defecto para "lo nuevo", pero agrega al mapa y a Comunidad un selector de **10 h / 24 h / 72 h**.

**B5. Pulso social: sacar Bluesky y Mastodon** (pedido de Fernando)
- Quítalos del Pulso social y del riel de redes.
- En Comunidad aportaron 0 publicaciones en la corrida medida: apágalos también ahí con variable del `.env`, sin borrar el código.
- El tiempo y la frecuencia liberados van a X, YouTube y a las fuentes de B3.

---

## Parte C: precisión (qué es cada cosa)

**C1. Acción, anuncio, declaración o dato.** Clasifica cada nota y, sobre todo, **cada afirmación principal** en:
- **acción:** algo que ya se ejecutó y es verificable (se retiró el poste, se firmó el contrato, se detuvo a X, se aprobó la ley)
- **anuncio o promesa:** algo que se hará ("permitirá renovar…", "se construirá…")
- **declaración o narrativa:** la versión, explicación, acusación u opinión de alguien ("según el Municipio, el poste provocó el retraso")
- **dato:** una cifra con fuente

Primero reglas (verbos de atribución como dijo, aseguró, según, denunció o acusó; tiempo futuro o condicional; verbos de hecho en pretérito) y después IA gratuita por lotes para los casos dudosos. La tarjeta muestra el tipo y **quién lo afirma**. El par del poste es el caso de prueba:
- "Retiro de poste" es una **acción**.
- "El poste provocó el retraso, según el Municipio" es una **declaración** del Municipio, que es parte interesada.

**C2. Categorías que sí correspondan.**
- Rehaz la taxonomía para lo que cubre Spike. Agrega, por ejemplo, **Obras y servicios públicos** (agua, luz, alcantarillado, vías), **Movilidad y tránsito**, **Riesgos y clima**, y separa **Economía** de **Empleo**.
- Clasifica con la IA gratuita por lotes, con la taxonomía y ejemplos en la instrucción. Las palabras clave quedan como respaldo.
- Una categoría solo se asigna si se puede justificar con el texto, y la tarjeta muestra la razón en una línea.
- Meta: menos del 10 % en "General" y exactitud medida con el CSV de la Parte 0.

**C3. Agrupamiento.**
- Dos notas del mismo hecho, del mismo lugar y del mismo par de días se unen aunque el titular cambie (el caso del poste) y aunque estén en otro idioma (el caso de la Corte Suprema). Para eso se usan los embeddings, que con la Parte A dejan de faltar.
- Pero **no** se unen notas distintas por compartir plantilla.
- Mide los pares mal unidos o mal separados con el CSV.

---

## Parte D: Internacional (recuperarla)

- **Ámbito por el tema, no por el medio:** si los actores, el lugar o el caso son ecuatorianos (Progen, New Jerson, entidades de Ecuador), la historia es de Ecuador aunque la publique Infobae o El Tiempo.
- **Filtro de utilidad por nota, no por medio.** Fernando **no** quiere quitar Infobae ni ningún otro feed. Quiere que Spike distinga lo útil de lo basura. Infobae es el caso de prueba porque aporta más notas (67 de 153) y mucha basura:
  - Señales sin IA: patrones de titular de relleno ("lo que sabemos", "¿por qué…?", "así fue", "esto dijo", curiosidades, virales, farándula, deportes, horóscopo, "cómo ver…"), notas sin hecho nuevo, refritos de otra nota del mismo medio en el mismo día y rutas de URL de secciones blandas.
  - Después, triaje por lotes con IA gratuita (A2): "¿aporta un hecho, dato o decisión con interés público? sí / no / dudoso", con una línea de motivo.
  - Una nota marcada como basura no se borra: queda oculta con un interruptor "ver descartadas" y su motivo, para poder auditarla.
  - Botones **Útil / Basura** en cada tarjeta. Las marcas de Fernando se guardan y alimentan las reglas y los ejemplos que se le dan a la IA. Mide la precisión del filtro contra esas marcas.
  - Reporta por medio qué porcentaje pasa el filtro. Infobae debería bajar mucho sin que se pierdan sus notas útiles: revisa 30 descartadas a mano y 30 aceptadas.
- **Volumen con criterio:**
  - Infobae y Semana, preferentemente con feed de mundo o internacional (el feed general se conserva, pero pasa por el filtro).
  - Tope por medio en la portada internacional.
  - Una historia internacional solo sube al top si la cubren 2 o más medios de países distintos o si tiene relación con Ecuador o la región.
- **Filtro de basura en inglés** (deportes, farándula, estilo de vida), igual que en español.
- **Unión bilingüe** funcionando (depende de A3 y C3) y una sola historia con "marco global" y fuentes en ambos idiomas, como se pidió antes.
- **Relevancia para Ecuador:** una línea de "por qué importa aquí" (comercio, migración, deuda, petróleo, seguridad regional), solo cuando la relación es real. Si no la hay, no se inventa.

---

## Parte E: Contraste que verifique afirmaciones, no titulares

El objetivo es que, frente a "la obra no avanzaba por un poste", Spike busque evidencia y diga qué tan respaldada está la afirmación, con enlaces, en vez de quedarse en "3 medios dicen lo mismo" o "no se encontró".

**E1. Extraer afirmaciones comprobables** de cada historia seleccionada: quién afirma, qué afirma, sobre qué obra, entidad o persona, dónde y cuándo. Sale de la Parte C1.

**E2. Buscar evidencia en el lugar correcto**, enrutando según la entidad:
- **Obra pública:** contrato en SERCOP/OCDS (contratista, monto, fecha de inicio, plazo, ampliaciones o modificaciones). En el caso real, el Municipio dijo que la obra empezó en marzo con 5 meses de plazo: ¿el contrato lo confirma? ¿Hay una ampliación registrada?
- **Servicios** (luz, agua): boletines y cuentas de CNEL EP, EMAPAG e Interagua. ¿CNEL confirma que el poste era suyo y cuándo lo retiró?
- **Municipio:** boletines anteriores en guayaquil.gob.ec. ¿Mencionó el poste antes o solo cuando ya había quejas?
- **La gente:** publicaciones de Comunidad del mismo sector y periodo. ¿Qué dicen los vecinos de La Alborada sobre el retraso y desde cuándo?
- **Historial propio:** `historias_registro.json`, para armar la línea de tiempo del tema.
- **Declaraciones previas** del mismo actor (`declaraciones.json`), para ver si se contradice.
- Para buscar en la web sin costo usa Google News RSS y búsquedas por sitio. Si el plan gratis de Gemini incluye búsqueda con Google en el proyecto sin facturación, pruébalo y mide su cupo.

**E3. Veredicto con evidencia, nunca sin ella:**
- **Respaldada:** un documento o una fuente independiente la confirma.
- **Contradicha:** un documento o una fuente independiente la contradice.
- **Parcial:** se confirma una parte.
- **Versión única:** solo la dice la parte interesada y los medios que la repiten.
- **Sin evidencia suficiente:** se dice qué falta y a quién consultar (por ejemplo: "pedir a CNEL la fecha de la solicitud de retiro del poste").

**Corrige la circularidad:** los medios que citan a la misma fuente **no** son corroboración independiente, y una fuente institucional (Municipio, CNEL…) **nunca** cuenta como "medio". Hoy `corroborado_medios` con 286 casos está inflado por esto.

**E4.** Cada veredicto muestra sus **citas con enlace** y la fecha del documento. Si la IA propone un veredicto sin cita, se descarta.

**E5.** Corre primero sobre Guayaquil y lo que Fernando abre, con la IA gratuita. Caso de aceptación obligatorio: el par del poste de La Alborada debe terminar unido en una sola historia, con la acción y la declaración separadas, y con un veredicto que cite al menos el contrato o proceso en SERCOP (o diga que no está) y la versión de CNEL o su ausencia.

---

## Verificación final (obligatoria)

1. Tabla de antes y después sobre datos reales:
   - gasto diario de la IA pagada (meta: ~$0 de fondo)
   - % de historias con triaje, contexto, veredicto y embedding
   - publicaciones de Comunidad en 10 h y en 24 h
   - puntos del mapa y notas sin sector
   - % en "General"
   - exactitud del CSV revisado por Fernando (categoría, ámbito, tipo, ciudad, agrupamiento)
   - composición de Internacional
   - reparto de estados del contraste
2. Pruebas `test_fase24_*.py` para cada parte.
3. Recompila el `.exe`, déjalo correr al menos 2 horas y mide ahí, no solo en las pruebas.
4. Registra la Fase 24 en `CLAUDE.md`: qué quedó conectado de verdad, qué quedó a medias y qué depende de Fernando (claves nuevas, aprobar cuentas, revisar el CSV, presupuesto de X).
