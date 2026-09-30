# Fase 9, parte D3: X + TikTok con $5 al mes, noticias iguales en inglés y español, y que los datos se VEAN en el dashboard

Este prompt **reemplaza a `PROMPT_fase9_D2_conectar_x.md`**. Si D2 ya se aplicó, parte de lo que quedó hecho. Si no, todo lo de D2 va incluido acá. Hay tres pedidos de Fernando.

---

## 1. Condición de cierre: los datos tienen que verse en el dashboard

Fernando activó el token de Apify y no vio nada. Desde Cowork se revisó `data.json` (04:31 UTC del 26-09) y se encontró esto:
- `estado_x` activo, pero con gasto $0. Todavía no había corrido ninguna llamada, porque la capa X esperaba detrás del backlog de IA del trabajador.
- `xapi.tweets_de_historia()` no tiene llamador. `get_social_historias()` solo usa `social.recolectar()`.
- Los tweets de `buscar_alertas_gye()` solo se cuentan (`r["alertas"] = len(items)`) y nunca llegan a `alertas.py`.
- El panel "Prueba X" solo muestra el gasto.

Es el patrón repetido n.º 6 del proyecto: algo documentado como hecho que nadie conectó. Por eso, **esta fase no se da por terminada hasta cumplir todo esto, verificado en vivo**:
1. `serve` reiniciado y **una pasada real** de X y de TikTok, lanzada con el botón "Actualizar redes ahora" (ver 2.5).
2. En el `data.json` real: tweets y comentarios de TikTok dentro de `social_historias` de al menos 2 historias locales, cada uno con `fuente: "x"` o `"tiktok"`, además del gasto real en `x_gasto.json` (renómbralo `redes_gasto.json` si lo unificas).
3. **Comprobación de que se renderiza**, no solo de que está en el JSON. Toma el `dashboard.html` que sirve `serve`, ejecuta las funciones de render de Pulso social contra ese `data.json` (con node + un DOM mínimo, o con Playwright/Chromium si está disponible en la PC) y confirma que el HTML resultante contiene el texto de al menos un tweet y de un comentario de TikTok. Si no se puede automatizar, dilo explícitamente y pídele a Fernando una captura. **No declares "listo" sin esta prueba.**
4. Al final, dile a Fernando en una sola línea dónde mirar: sección, bloque y qué va a ver.

---

## 2. X + TikTok (Instagram queda fuera): sacarle el máximo a los $5 al mes

### 2.1 Actores y precios (verificados en Apify el 2026-09-26, plan FREE)
- **X**: `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`, **$0.00025 por tweet**. Ya probado en vivo: 20 tweets reales. El respaldo es `apidojo/tweet-scraper` ($0.0004 por tweet, acepta `conversationIds`).
- **TikTok**:
  - `clockworks/tiktok-scraper`: **$0.0037 por video** + **$0.001 por inicio de actor**. Input: `searchQueries`, `resultsPerPage`, `searchSection`. Los add-ons de filtro de fecha y de país cuestan $0.0013 extra por resultado: **no los uses** y filtra la fecha en local con la fecha del video.
  - `clockworks/tiktok-comments-scraper`: **$0.00125 por comentario**. Input: `postURLs`, `commentsPerPost`, `maxRepliesPerComment`.
- **Instagram fuera.** Si quedó algún rastro en el código o en CLAUDE.md, elimínalo. Solo X y TikTok.

### 2.2 Presupuesto con ritmo, no frecuencias fijas
El objetivo es **gastar cerca de los $5 al mes sin pasarse nunca**, en vez de dejar crédito sin usar:
- Tope mensual duro: **$4.70** (deja $0.30 de margen para cobros de plataforma o de inicio que no se hayan previsto). `MONITOR_REDES_TOPE_MES_USD`.
- **Ritmo diario dinámico**: `presupuesto_hoy = restante_mes / días_que_quedan_del_mes`. Lo que no se gasta un día pasa al siguiente, y si un día se gasta de más, los siguientes se ajustan solos.
- Reparto inicial: **X 65 % / TikTok 35 %**. Si una de las dos redes da error o no encuentra nada útil durante 2 días, su parte pasa a la otra. El reparto va visible en el panel.
- Antes de cada llamada se calcula su costo máximo, **incluido el cobro de inicio del actor**. Si no entra en el presupuesto de hoy, la llamada se salta y el panel lo dice. Después de cada corrida se registra el **costo real** del run (confirma en vivo el nombre del campo en la API de Apify; hoy está asumido).

### 2.3 Prioridad (dónde rinde más cada centavo)
Cuando el presupuesto del día no alcanza para todo, se sigue este orden:
1. **Alertas Guayaquil por X**: cada hora, hasta 10 tweets, con `since_id` o descarte por `id` ya visto. Es lo más barato y lo más sensible al tiempo. Cada tweet nuevo **entra a `alertas.py`** con la misma función que usan Bluesky/Telegram, como fuente `"x"`, deduplicado por autor.
2. **Tweets por historia**: las 6 historias locales top, **sin boletines de plantilla** (clima, El Niño, feriados, servicios; en la simulación real salieron 3 de 6), 25 tweets cada una, `Latest`, `lang: es`. Solo se vuelve a consultar una historia si es nueva o si sumó fuentes desde la última consulta: no se paga dos veces por lo mismo.
3. **Debate en X**: las respuestas (`conversation_id:`) del tweet con más respuestas de las 3 historias con más volumen. Confirma en la primera llamada real si el operador funciona; si no, usa el respaldo con `conversationIds`.
4. **TikTok, una vez al día**: para las 2 historias locales top, busca videos con las entidades de la historia + "Guayaquil" o "Ecuador" (3 videos por historia) y quédate con los de los últimos 7 días. Después baja **20 comentarios** del video con más comentarios de cada historia. Ahí está el debate de la gente, porque los comentarios valen más que los videos. No vuelvas a bajar comentarios de un video si su conteo de comentarios no creció.
- Cuenta de referencia al ritmo base (~$0.157/día): X ≈ 320 tweets/día ≈ $0.08; TikTok ≈ 6 videos ($0.022) + 40 comentarios ($0.05) + 4 inicios ($0.004) ≈ $0.076. Total ≈ $0.156/día. Al principio el gasto de TikTok queda por encima del 35 % del reparto; que el ritmo lo reajuste con los datos reales. **Verifica con la simulación** y ajusta los tamaños para que el ritmo real quede cerca del presupuesto diario sin pasarse.

### 2.4 Integración
- **Pulso social**: por historia, tweets + respuestas + videos y comentarios de TikTok, junto a lo que ya había (YouTube, etc.), con el mismo formato de post (`fuente`, `autor`, `texto`, `url`, `likes`, `fecha`, `tipo`). Pasan por el filtro de pertenencia a Ecuador, por la clasificación persona/medio/institución/político y por las posturas con citas. El **hilo principal** es el tweet o video con sus respuestas. La **curva de volumen por hora** sale de las fechas de los tweets. Cada post lleva un distintivo visible de su red (X / TikTok / YouTube).
- **La capa de redes no espera a la IA**: corre en un hilo liviano propio, o al inicio de cada pasada sin depender de nada, apenas hay token y después según el ritmo. Lo mismo vale para la recolección de `get_social_historias`.

### 2.5 Panel "Prueba de redes" (Estadísticas) + botón
- Botón **"Actualizar redes ahora"**: dispara una pasada respetando el presupuesto (endpoint local, mismo criterio de autorización que el resto).
- Muestra: gasto de hoy / del mes / restante, presupuesto de hoy según el ritmo, reparto X/TikTok, última y próxima corrida por capa, tweets, videos y comentarios en caché, y el último error real.
- Métricas de la prueba: % de historias top con 10 o más posts de personas de Ecuador (por red), alertas originadas o corroboradas por X y su adelanto en minutos sobre la prensa, proporción de personas/medios/instituciones/políticos por red y costo por historia con debate útil. Con esto Fernando decide al final del mes qué red vale la pena.

### 2.6 Pruebas (fixtures, sin red)
Tienen que cubrir:
- El ritmo reparte bien y nunca pasa el tope mensual.
- El cobro de inicio de actor entra en el cálculo.
- Un día sin gasto aumenta el presupuesto del siguiente.
- Una red con fallas cede su parte.
- Un boletín de clima no se elige.
- Un tweet de alerta llega a `alertas.py`.
- Los tweets y los comentarios de TikTok aparecen en `social_historias` con su `fuente`.
- No se baja dos veces un video sin comentarios nuevos.
- El token nunca aparece en logs ni en `data.json`.

---

## 3. La misma noticia en inglés y en español tiene que ser UNA historia con marco global

**Problema** (confirmado en el `data.json` real del 26-09): la cumbre Trump–Xi en Washington aparece como historias separadas por idioma. En inglés: "Trump-Xi summit: Four key takeaways...", "5 takeaways from Trump's summit with Xi", "What Donald Trump and Xi Jinping revealed in the body language...". En español: "Trump y Xi Jinping exhiben unidad al cierre de la visita de Estado a EE.UU.". Pasa lo mismo con otros hechos internacionales. El agrupamiento compara palabras, así que dos idiomas nunca se juntan, y `nomic-embed-text` está entrenado sobre todo en inglés, con poca capacidad para comparar entre idiomas.

**Qué hacer:**
1. **Embeddings multilingües.** Prueba con Ollama un modelo multilingüe de embeddings: `bge-m3` (~1.2 GB) o `paraphrase-multilingual` (~560 MB). Primero **mide** con pares reales del registro: los de Trump–Xi como deben-unirse, y como no-deben-unirse otros pares que comparten "Donald Trump" pero son hechos distintos (el data.json tiene varios). Compara con `nomic-embed-text` y elige el umbral con esos datos. Ten en cuenta la VRAM de 4 GB: los embeddings se calculan en el trabajador y no pueden competir con el modelo de lectura al mismo tiempo. Si el modelo multilingüe no mejora de verdad los pares medidos, dilo y no lo cambies.
2. **Regla de unión entre idiomas**: coseno multilingüe alto **y** al menos una entidad en común (nombre propio o sigla, normalizados sin tildes y con equivalencias básicas: EE.UU./US/USA, ONU/UN, Xi Jinping/Xi), dentro de la ventana de 72 h. Con una entidad genérica suelta ("Trump", "Estados Unidos") no alcanza: hace falta una segunda entidad o un coseno muy alto, porque "Trump" aparece en decenas de hechos distintos al día.
3. **Marco global de la tarjeta**: cuando una historia tiene fuentes en más de un idioma:
   - Titular en español, neutral, que describa el hecho común. Primero se busca entre los titulares en español; si solo hay titulares en inglés, lo redacta la IA y se marca como "titular traducido".
   - Distintivo "Cobertura global · ES + EN" y el número de medios por idioma.
   - Las fuentes se listan agrupadas por idioma (Español / English), todas con su enlace, para que Fernando vea los dos ángulos.
   - Si la IA hace la lectura, recibe fuentes de los dos idiomas y lo sabe. Aplica la huella de la parte B: si la historia sumó el otro idioma, la lectura se rehace.
4. Esto aplica a lo **internacional**. Para lo local de Ecuador, casi todo en español, no cambies el comportamiento más allá de lo que ya hace la parte A.
5. **Pruebas** con los titulares reales de arriba (deben unirse y no deben unirse) y el antes y después sobre el registro real: cuántas historias internacionales quedaron con fuentes en dos idiomas y cuántas uniones falsas aparecieron. Revisa a mano una muestra de 10 uniones entre idiomas y reporta cuántas están bien.

---

## Cierre
Documenta todo en CLAUDE.md como "Fase 9, parte D3", con sus pendientes reales. Actualiza "Decisiones ya tomadas" con este texto: "Redes vía Apify: solo X y TikTok, prueba de un mes con $5; Instagram descartado". Termina con la línea para Fernando que pide la sección 1.4.
