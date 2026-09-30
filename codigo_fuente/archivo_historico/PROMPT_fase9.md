# Fase 9: duplicados, IA desalineada, Pulso social con debate real y base de X

Contexto: Fernando reporta cuatro cosas. (1) Siguen entrando noticias repetidas desde otro medio. (2) Las IA "no funcionan para cada distinción" y no operan bien. (3) Las alertas tienen que ser parte del Pulso social, y el Pulso social no muestra debate ni conversación real de la gente. (4) Va a pagar la API de X para una prueba, así que hay que dejar la base lista.

Antes de escribir código, desde Cowork se revisaron `data.json`, `historias_registro.json` y `social` de la corrida del 2026-09-25 (02:54 UTC). Esto es lo que se encontró. **Reprodúcelo tú primero con los archivos reales**: si algo no coincide, dilo antes de arreglar.

Orden de trabajo obligatorio: **A → B → C → D**. Todo lo que se hace después depende de que el agrupamiento esté sano: la IA, el Pulso social y X se anclan a historias. Si las historias están mal armadas, todo lo de abajo hereda el error.

---

## A. Agrupamiento: el problema tiene dos caras, no solo duplicados

### A1. Los embeddings de la Fase 8 nunca corrieron en producción
- En `historias_registro.json` hay **2481 entradas y 0 con `embedding`**. La capa semántica que la Fase 8 documentó como arreglo del parafraseo está apagada de hecho (es otra vez el patrón de "documentado como hecho, sin conectar").
- La causa probable está en `ia.embed_disponible()`: guarda `_embed_model_ok` en una global **para siempre**. Si Ollama no respondía en el primer chequeo (arranque en frío, timeout de 8 s en `modelos()`), queda en `False` hasta reiniciar el proceso. Confírmalo y verifica también que `nomic-embed-text` esté instalado (`ollama list`).
- Arreglo: que el chequeo expire (reintentar cada ~10 min si dio False) y exponer `estado_embeddings` en `data.json`, visible en el dashboard como el resto de los `estado_*`. Así un hueco nunca vuelve a quedar invisible.

### A2. Duplicados reales que siguen separados (subagrupamiento)
Son pares de historias locales de la misma corrida que quedaron en tarjetas distintas:
- Operativo CJNG en Samborondón/Mocolí: **4–5 tarjetas** ("Presunto cabecilla... capturados en Samborondón", "Tropas estadounidenses y Policía Nacional ejecutan allanamientos en Samborondón", "Operativo entre Ecuador y EEUU deja más de 30 detenidos vinculados a cártel mexicano", "La presunta red societaria... operativo en Mocolí", "¿Qué se sabe de los detenidos con el CJNG en Samborondón...").
- "¿El 9 de octubre es feriado nacional?..." frente a "¿Habrá feriado el 9 de octubre de 2026?...".
- "Los libros rotos tienen una salida: una clínica..." (Expreso) frente a "La Biblioteca Municipal abrió una clínica para rescatar libros..." (Municipio).
- "Pablo Emilio Ríos Maza fue localizado..." frente a "Localizan a joven jugador del Deportivo Quito que estaba desaparecido...".
- Avión C-5M Galaxy en Guayaquil (2 tarjetas), precio del huevo (2), "¿Vuelven los apagones?" frente a "El Ejecutivo aplica seis medidas para evitar los apagones" (y 2 más), Multicomercio (2), Noboa en la ONU contra el crimen transnacional (2), trata en la Kennedy (3).

Causas concretas encontradas en el código:
- `_nombres_propios()` usa `[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{3,}`, así que **no capta siglas**: CJNG, ATM, CTE, BDE, DAC, INAMHI, CNEL quedan fuera. Muchas veces la sigla es justo la entidad que comparten dos notas. Agrega las siglas de 3 o más mayúsculas y excluye las genéricas (EEUU, EE. UU., ONU, etc.).
- Un "9" o un "26" nunca cuentan como cifra, porque `_numeros()` exige 3 o más dígitos. Las fechas explícitas del titular ("9 de octubre", "26 de septiembre") son señal de *mismo hecho*, pero también de *distinto día* (ver A3). Trátalas como un campo `fecha_mencionada` aparte, no como cifra.
- **Google News se cuenta como un medio**: "Busqueda: Guayaquil" aparece como outlet (167 fuentes), cuando detrás hay medios reales. El título lo dice ("... - El Universo", "- Metro Ecuador", "- eltelegrafo.com.ec", "- Perú 21"). Pasa, por ejemplo, con el caso Durán/CTE: 5 medios reales cuentan como 1. Hay que extraer el medio real del sufijo (o del `<source>` del item RSS), usarlo como `outlet` y **quitar el sufijo del título** antes de tokenizar. Hoy el sufijo ("- extra.ec", "- teleamazonas") mete tokens basura en `_sim`. Si el mismo artículo llega por RSS directo y por Google News, es la misma fuente (dedup por medio real + título limpio).

### A3. Historias que se fusionan mal (sobreagrupamiento por deriva): esto Fernando no lo vio, pero es igual de grave
Hay entradas del registro que mezclan hechos sin relación. Estos son reales, de la misma corrida:
- "Guayaquil enfrenta el septiembre más lluvioso..." + "Noticias, jueves 24 de septiembre del 2026 | 24 Horas" + "Portada 25 septiembre 2026" (El Norte) + "Últimas noticias | 25 septiembre 2026 - Mediodía" (Euronews). La tarjeta muestra lluvias y la **lectura IA habla de ONGs en Ceuta**.
- "Santa Elena: lo que se conoce del crimen de un taxista..." junto a "Bus con trabajadores cayó de un puente en la vía a la Costa".
- "Usuarios reportan cortes de luz en el norte de Guayaquil" junto a "Ciudadanos en Durán reportan cortes de agua".
- "4.04-meter Tides in Guayaquil Ports" junto a "Precio del dólar en casas de cambio...".
- "Juez impone prisión preventiva a Miguel Sánchez, alcalde de Juchitán (CJNG)" junto a "Caso Blindado: Fiscalía solicita prisión...".
- "Trump y Xi Jinping proclaman la armonía..." junto a "vetar a periodistas / Casa Blanca".

Causas:
1. **Deriva por `rep_titulo`**: `_match_registro` compara solo contra el titular representante, y ese titular **cambia al más nuevo** cada vez que entra una fuente. A se une con B, el representante pasa a ser B, C se une con B, y la historia se va desplazando de tema. Arreglo: una nota nueva tiene que parecerse al **núcleo** de la historia (por ejemplo, a la mayoría de sus fuentes, o al titular fundador más el representante), no solo al último titular.
2. **Años como "cifra compartida"**: "2026", "1961" y "1930" entran en `numeros`. Cualquier par que mencione el año comparte cifra, y con eso el umbral baja a 0.20. Hay que excluir años (19xx/20xx) y fechas.
3. **Lugares ubicuos como "nombre compartido"**: "guayaquil", "ecuador" y "quito" están en casi todas las notas locales. Compartirlos no prueba que sea el mismo hecho. No deben servir para bajar el umbral (igual que `EVENTO_GENERICO`, pero para las ciudades principales).
4. **Basura que entra al agrupamiento**: portadas y noticieros completos ("Portada 25 septiembre 2026", "Noticias, jueves... | 24 Horas", "Últimas noticias | ... Mediodía"). Van a `is_junk()`.
5. **Boletines con plantilla** (clima, feriado, precio del dólar, mareas): la regla es que la misma ciudad con **distinta fecha mencionada** nunca se une, y distinta ciudad tampoco. Esto cierra el pendiente 1 de la Fase 8.

### A4. Pruebas y reconstrucción
- Nuevo `test_fase9_agrupamiento.py` con **todos los pares de A2 como deben-unirse** y **todos los de A3 como no-deben-unirse**, usando los titulares textuales de arriba. Las pruebas viejas de clustering tienen que seguir pasando.
- Después, **reconstruye el registro una vez** con las reglas nuevas: respalda antes `historias_registro.json` y avísale a Fernando antes de tocarlo. Reporta el antes y el después sobre los datos reales: número de historias locales, entradas con 2 o más medios, cuántos pares de A2 quedaron unidos y cuántas entradas incoherentes quedan. Para medir la incoherencia, usa la similitud entre la fuente fundadora y la fuente más lejana de la entrada: desde Cowork se contaron **32 de 493** entradas multi-fuente con similitud menor a 0.08 entre esas dos.

---

## B. La IA: el problema principal no es el modelo, es a qué texto se engancha

Evidencia, sacada de 14 tarjetas locales con lectura IA: en al menos 6, **la lectura habla de otra noticia** (lluvias → Ceuta; cortes de luz → "presionar a manifestantes"; C-5M → operativo de Mocolí; marea → precio del dólar; Santa Elena → bus accidentado).

Causas:
1. **La clave de caché es `fuentes[0].link`**: el enlace de la nota más vieja, que es la clave estable. Pero `get_ia()` calcula la lectura **una sola vez**, con el titular que tenía la historia *en ese momento*. Cuando la historia suma fuentes y cambia el titular representante, la tarjeta muestra el titular nuevo con la lectura, los temas y la geografía viejos. Con la deriva de A3 encima, la lectura termina describiendo otra noticia. Lo mismo aplica a `get_contexto`, `get_veredicto` y `get_factcheck` (revísalos).
   - Arreglo: la clave sigue siendo estable (para `saved.json`/`notas.json`), pero cada resultado de IA guarda una **huella del contenido que analizó** (hash del titular representante + conjunto de fuentes). Si la huella cambia de forma significativa (cambió el representante o se sumaron medios), se recalcula. En la tarjeta, si la lectura es de una huella vieja, se marca "lectura desactualizada" hasta que el trabajador la rehaga.
2. **Cobertura**: solo 623 de 2480 historias tienen lectura IA. Prioriza lo local y lo que está arriba en el ranking, y deja sin IA el ruido internacional de 1 medio. Hoy hay 744 fuentes de Infobae y 271 de Semana (Colombia) compitiendo por la GPU.
3. **Medir antes de cambiar de modelo**. Arma `evaluar_ia.py`: toma 40 historias reales (30 locales), genera un archivo simple donde Fernando marca la categoría correcta, el ámbito correcto y si la lectura corresponde a la noticia (sí/no), y calcula la precisión de palabras clave, de IA y de la lectura. Solo con ese número se decide si hace falta otro modelo o si bastaba con arreglar el punto 1. Explícale a Fernando, en una línea, cómo llenar ese archivo.

---

## C. Pulso social: de "posts sueltos por tema" a debate por historia, con las alertas adentro

Diagnóstico del `social` actual: se consulta por **tema abstracto** ("Ambiente", "Asamblea/Leyes"), así que Mastodon y Bluesky devuelven ruido global. En "Asamblea/Leyes" salen Armenia, Venezuela y Delcy Rodríguez; en "Ambiente", manchas de petróleo en el mundo. Aun así, a "Ambiente" se le puso `ambito: guayaquil`. No hay respuestas ni hilos: son publicaciones aisladas, y por eso no se ve debate. El caché además tenía temas de hace 2 días. Lo único parecido a conversación real son los **comentarios de YouTube en canales ecuatorianos** (por ejemplo, los del canal de Jimmy Jairala).

Rediseño:
1. **Anclar a historias, no a temas.** El Pulso social se arma sobre las N historias locales más importantes (Guayaquil primero, después Ecuador). La consulta a cada red sale de las entidades de la historia (nombres, siglas, lugares específicos), no del nombre de la categoría.
2. **Filtro de pertenencia.** Un post solo entra si menciona una entidad de la historia o una señal de Ecuador. Lo que no cumple eso se descarta y queda contado ("descartados por no ser de Ecuador: N"), para que el hueco se vea.
3. **Mostrar el debate, no solo un resumen.** Por historia: volumen de conversación (cuando haya X, la curva por hora), **posturas** (a favor, en contra, duda/pregunta, denuncia/testimonio), cada una con cuántos posts tiene y 2–3 citas textuales con autor y enlace, y el **hilo principal** (post original y sus respuestas más relevantes). Hay que separar persona, medio, político e institución, que ya existe (`tipo`/`canal_tipo`).
   - La IA solo **clasifica la postura de cada post respecto a la historia**. Es una tarea chica y verificable, que un modelo de 3B hace mejor que un resumen general. Toda postura tiene que citar los IDs de los posts que la sostienen; lo que no tenga cita se descarta en código, no solo pidiéndolo en el prompt.
4. **Alertas dentro del Pulso social.** `#secAlertas` deja de ser una sección propia y pasa a ser el **primer bloque de Pulso social** ("Alertas de la gente"), con los mismos estados, la misma métrica de adelanto y el mismo ntfy desde Corroborado. El badge pasa al botón de Pulso social. No cambies la lógica de `alertas.py` más allá de lo necesario para sumar X como fuente (D).
   - Deja constancia honesta en el dashboard: hoy las alertas marcan "activas: 0" porque las fuentes oficiales RSS publican boletines institucionales (talleres, convenios), no alertas, y Bluesky casi no tiene contenido de Guayaquil. Con las fuentes gratis que hay, esta capa no tiene de qué alimentarse. X es la prueba de si eso cambia.

---

## D. Base de X (API oficial, pago por uso): decisión nueva de Fernando

Actualiza "Decisiones ya tomadas" en CLAUDE.md: **X está autorizado solo por la API oficial con Bearer Token pagado por Fernando.** Scraping y cuentas logueadas siguen prohibidos.

Precios oficiales verificados el 2026-09-25 en docs.x.com/x-api/getting-started/pricing: **$0.005 por post leído**, **$0.010 por usuario leído**, **Counts recent $0.005 por request**. El mismo recurso se cobra una sola vez por día UTC, y el tope es de 3 millones de lecturas al mes. Los créditos se compran por adelantado en el Developer Console. La búsqueda reciente cubre 7 días, trae hasta 100 posts por request y admite operadores como `lang:`, `-is:retweet` y `conversation_id:`.

Módulo nuevo `xapi.py` (solo stdlib, standalone, mismo patrón que `oficial.py`):
1. **Apagado por defecto.** Sin `MONITOR_X_BEARER` (variable de entorno o `x_config.json` fuera del código) no hace nada y reporta "desactivado". El token nunca va en el código, en `data.json` ni en logs.
2. **Presupuesto duro en código**: `MONITOR_X_TOPE_DIA_USD` (por defecto 1.50) y `MONITOR_X_TOPE_TOTAL_USD` (por defecto 10). `x_gasto.json` registra cada cobro estimado. Antes de cada request se calcula su costo máximo (`max_results` × precio) y, si se pasaría del tope, no se hace. Cuenta de forma conservadora, sin descontar la deduplicación de X. El gasto va visible en el dashboard: hoy, total, restante y costo por señal útil.
3. **Modo simulación** (`MONITOR_X_SIMULAR=1`): arma todas las consultas reales a partir de las historias actuales, las muestra y proyecta el costo diario, **sin red**. Es lo primero que se corre.
4. **Estrategia barata en capas:**
   - *Counts* (lo más barato): volumen por hora de las 6 historias locales principales, cada 4 h. Da la curva de conversación y detecta picos.
   - *Search* solo para las 3 historias con más volumen: hasta 20 posts, `lang:es -is:retweet`, cada 12 h, con `since_id` para no pagar dos veces lo mismo.
   - *Conversación*: una vez al día, para el post más respondido de cada una de esas historias, sus respuestas vía `conversation_id:` (hasta 25). Eso es el "debate".
   - *Alertas Guayaquil*: una consulta por hora con tipos de `alertas.py` (incendio, balacera, choque, inundación, sin luz/agua...) + Guayaquil/barrios de `BARRIOS_GYE`, `-is:retweet`, `since_id`, con tope de 60 posts al día. Entra a `alertas.py` como fuente `"x"`, y la corroboración se deduplica por autor como las demás.
   - Cuenta del peor caso con esos valores: counts 36 × $0.005 = $0.18; search 120 posts = $0.60; conversación 75 posts = $0.375; alertas 60 posts = $0.30. Total ≈ **$1.46/día**, dentro del tope de $1.50. Con $10 alcanza para una semana. Confírmalo con la simulación.
5. **Arquitectura de dos velocidades**: toda la red de X vive en el trabajador (`enrich_pass`), nunca en `run_fast`. Caché en `x_cache.json`. Los errores (401, 402 sin créditos, 429) se reportan en `estado_x` con el motivo real.
6. **Medición de la prueba**, que es para lo que Fernando paga. En Estadísticas, un panel "Prueba X" con: % de historias locales principales con 10 o más posts reales de Ecuador, n.º de alertas originadas o corroboradas por X y su adelanto en minutos sobre la prensa, costo por historia con debate útil, y cuánto del contenido es de personas frente a medios o políticos. Sin esto, la prueba no deja una respuesta.
7. Pruebas `test_fase9_xapi.py` con respuestas de X simuladas (fixtures): el tope diario corta, la simulación no hace red, `since_id` evita cobrar dos veces, sin token queda apagado, y un 402 queda reportado.

---

## Verificación final (como en fases anteriores, sin atajos)
- Todas las pruebas en verde, contadas de verdad.
- Reinicio real de `serve` y, sobre el `data.json` real: `estado_embeddings` con embeddings calculados, el antes y después de A4, cuántas lecturas IA se marcaron desactualizadas o se rehicieron, el Pulso social anclado a historias locales (nada de Armenia/Venezuela en ámbito Ecuador), las alertas dentro del Pulso social y X en simulación con su proyección de costo.
- Cierra con una sección en CLAUDE.md, "Fase 9", y sus pendientes reales.
- La primera acción que le pides a Fernando al final es una sola: crear la cuenta de desarrollador de X, fijar un límite de gasto en el Developer Console, cargar el crédito y pegar el Bearer Token donde indiques.
