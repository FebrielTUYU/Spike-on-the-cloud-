# PROMPT Fase 10 — Fases 3 y 4: conectar Gemini (reemplazo de Ollama)

Lee primero la sección **"Fase 10 (2026-09-26)"** al final de `CLAUDE.md`. Resumen: Ollama ya se retiró del proyecto. `ia.py` quedó con el transporte vacío: `ia._generar()`, `ia._generar_stream()` y `ia.embed()` devuelven `None`, `ia.backend_listo()` devuelve `False`. Los prompts, los candados en código y las firmas públicas no cambiaron. Tu trabajo es conectar esas funciones a Gemini y reactivar todo lo que dependía de la IA.

Trabaja en este orden: 0 → A → B → C → D → E. Termina cada parte y verifícala antes de pasar a la siguiente. Háblame en español y dame una acción concreta a la vez (ver "Con quién hablas" en CLAUDE.md).

---

## 0. Antes de tocar nada

1. **Revisa que no haya otra sesión editando la carpeta.** El 26-09, mientras se hacía la purga de Ollama, otra sesión estaba implementando la D3 (`monitor.py`, `redes.py`, `tiktok.py`). Revisa el estado de `PROMPT_fase9_D3.md`. Si la D3 quedó a medias, dímelo antes de seguir. No mezcles las dos cosas.
2. **Revisa que `.env` exista en la raíz y que `GEMINI_API_KEY` tenga valor.** No imprimas la clave: solo di "presente" o "falta". Si falta, detente y dame este comando para crearlo (yo pego la clave después del `=`):
   ```powershell
   'GEMINI_API_KEY=' | Set-Content -Encoding utf8 .env
   ```
3. **Corre la suite completa y anota la línea base.** Debería dar 235 pruebas, con 15 errores ya conocidos en `test_fase9_xapi.py`.

## Reglas de esta fase

- **SDK: NO uses `google-generativeai`.** Quedó sin soporte el 30-11-2025. Usa la API REST de Gemini con `urllib` (librería estándar). Así se mantiene la regla de oro y no hace falta ningún `pip`. Si en algún punto crees que el SDK nuevo (`google-genai`) es necesario, pregúntame antes de instalarlo.
- **La clave va en el header `x-goog-api-key`, nunca en la URL.** Tampoco en logs, en `last_error`, en `data.json` ni en mensajes de error. Si un error HTTP trae la URL, límpiala antes de guardarla.
- **Modelos, configurables por variable de entorno** (se pueden poner en `.env`):
  - `MONITOR_GEMINI_RAPIDO` = `gemini-3.8-flash` (perfil rápido: triaje y extracción)
  - `MONITOR_GEMINI_PROFUNDO` = `gemini-3.1-pro-preview` (perfil profundo)
  - `MONITOR_GEMINI_EMBED` = `gemini-embedding-001`
  - Al arrancar, confírmalos contra la lista real de modelos de la API (`GET /v1beta/models`), una vez y con caché. Si alguno no existe, dilo en el estado. No inventes otro nombre de modelo. Ojo: el Pro está en **preview** y puede cambiar o desaparecer. Si falla con 404, el perfil profundo cae al rápido y el estado lo dice.
- **Todas las llamadas nuevas a la IA van solo en el hilo trabajador (`enrich_pass`)** o en las rutas on-demand del servidor. **`run_fast` nunca llama a la red de la IA.** Esto ya se cumple hoy; verifica que siga así.
- **Presupuesto duro, mismo patrón que `xapi.py`/`redes.py`.**
  - Lee el precio actual en https://ai.google.dev/gemini-api/docs/pricing. No lo supongas.
  - Registra el gasto real de cada llamada a partir de `usageMetadata` (tokens de entrada y salida) en `ia_gasto.json`.
  - Pon topes con `MONITOR_IA_TOPE_DIA_USD` y `MONITOR_IA_TOPE_MES_USD`. Si una llamada se pasaría del tope, no se hace.
  - Si la cuenta está en el nivel gratis (costo 0), igual respeta los límites de peticiones.
  - Expón el gasto en `data.json["estado_ia_nube"]` y muéstralo en el panel "Salud de los datos".
- **Límite de peticiones (429).**
  - Reintenta con espera creciente, máximo 2 veces, respetando `Retry-After` si viene.
  - Después de eso, pausa ese perfil unos minutos y anota el motivo en el estado.
  - Nunca dejes que una ráfaga de 429 frene toda la pasada del trabajador.
  - No fijes cifras de cuota de memoria: mídelas con respuestas reales.

## A. Transporte en `ia.py`

Implementa las funciones de transporte sin cambiar ningún prompt ni ningún candado:

1. **`_generar(prompt, sistema, mensajes, json_mode, perfil, temperatura, max_tokens, timeout)`**
   - Usa `generateContent`.
   - `sistema` va en `systemInstruction`.
   - `mensajes` se traduce a `contents` con roles `user`/`model`.
   - `json_mode=True` usa `generationConfig.responseMimeType = "application/json"`.
   - Devuelve el texto, o `None` con `last_error` legible (código HTTP y motivo, sin la clave).
   - Si la respuesta viene bloqueada por filtros de seguridad (`finishReason` SAFETY u otro), devuelve `None` con ese motivo. Las noticias de crimen o narcotráfico pueden disparar filtros: mide cuántas notas reales pasan esto y dímelo.
2. **`_generar_stream(...)`**
   - Usa `streamGenerateContent?alt=sse` y lee las líneas `data:` con `urllib`.
   - Llama a `on_delta` por cada pedazo.
   - Un `on_delta` que falla nunca corta la generación.
3. **`embed(texto, modelo)`**
   - Usa `embedContent` con `gemini-embedding-001`.
   - Devuelve la lista de floats, o `None`.
   - Si es fácil, agrega un `embed_lote()` con `batchEmbedContents` para el trabajador.
4. **`backend_listo()`, `disponible()`, `embed_disponible()` y `estado()`**
   - Deben reflejar la realidad: clave presente + modelo confirmado + no pausado por 429.
   - Sin red en cada llamada: usa caché con TTL corto.
5. **Pruebas nuevas** (`test_fase10_gemini.py`), sin red real, con `urllib` mockeado:
   - arma bien el payload JSON y el de streaming;
   - la clave nunca aparece en `last_error` ni en el estado;
   - un 429 reintenta y después pausa;
   - un bloqueo de seguridad devuelve `None`;
   - el tope de gasto corta antes de llamar;
   - un modelo inexistente queda reportado.

   Después haz **una prueba en vivo mínima** con la clave real: una llamada de cada perfil y un embedding. Dime el tiempo y el costo reales.

## B. Embeddings: migración sin mezclar espacios

Los vectores que hay hoy en `historias_registro.json` y en `casos/*/index.sqlite3` son de nomic-embed-text. **No son comparables con los de Gemini** (otra dimensión y otro espacio).

1. **Guarda con cada vector el modelo que lo generó** (`embedding_modelo`). La comparación coseno solo compara vectores del **mismo** modelo y la **misma** longitud. Agrega ese candado en código.
2. **Descarta los vectores viejos de nomic.**
   - Primero haz un respaldo con fecha de `historias_registro.json`.
   - Deja que `_embed_pendientes_registro()` los recalcule, con el cupo por pasada de siempre.
3. **Recalibra `EMBED_SIM_UMBRAL` con datos reales.** El 0.75 se midió con nomic y no vale para otro modelo. Usa los pares reales documentados en CLAUDE.md:
   - la multa de $41.000/$41.070;
   - Valbonesi/ALMA;
   - CJNG/Samborondón;
   - Trump–Xi ES/EN;
   - el control negativo: clima de Sevilla vs. clima de Guayaquil, que con nomic dio 0.778.

   Dame la tabla de cosenos y el umbral elegido, con su porqué. Mantén la exigencia de nombre propio o cifra compartida además del coseno.
4. **Multilingüe (D3).** `gemini-embedding-001` es multilingüe, así que puede reemplazar a la vez a nomic y a bge-m3 (`EMBED_MODEL_MULTILINGUE`). Verifícalo con los pares ES/EN reales antes de asumirlo.
5. **Casos.**
   - Reindexa los fragmentos sin vector o con vector de otro modelo. Reusa el progreso visible de `docs_estado.json`.
   - **Antes de mandar a la nube los documentos de un caso, pregúntame.** Son material mío de reportaje (fuentes incluidas), y Google puede usar ese contenido si la cuenta está en el nivel gratis. Implementa un interruptor `MONITOR_CASOS_NUBE` y deja el valor por defecto que yo elija cuando te responda.

## C. Reactivar el pipeline del trabajador (perfil rápido)

Con el transporte andando, ya se reactivan solas estas funciones, porque `ia.disponible()` da True:

- `get_ia`
- `get_contexto`
- `get_veredicto`
- `get_declaraciones`
- `get_social_historias` (posturas)
- `extraer_entidades_chat`
- sugerencias de casos

Verifica cada una con **historias reales**, no con muestra:

1. Revisa los cupos por pasada (`IA_MAX_NEW`, `IA_INTERP_MAX`, `CONTEXTO_MAX_NEW`, etc.). Estaban bajos por el hardware local. Súbelos solo si el presupuesto y los 429 lo permiten, y dime cuánto cuesta por día cada cupo nuevo.
2. **OSINT del Pulso social.**
   - Agrega `ia.analizar_osint(posts)` con **el mismo prompt** que `social._OSINT_PROMPT` (cópialo, no lo cambies) y perfil rápido.
   - Haz que `monitor.get_social` lo use en vez de `social.analizar_osint`. Devuelve `_social_model()` a algo útil o elimina esa función.
   - **No modifiques `social.py`**: su recolección es una pieza protegida.
   - Cuida que `osint_error` no baje el TTL a 20 min de forma permanente, porque gasta cuota de YouTube.
3. **La huella de contenido (Fase 9, B1) sigue valiendo.** Las entradas marcadas desactualizadas deben recalcularse primero. Así se aprovecha la migración para corregir las lecturas IA que quedaron de otra noticia.

## D. Perfil profundo: lectura editorial, Asistente, chat y casos

Todas estas funciones ya piden el perfil profundo:

- `interpretar()`
- `comparar_declaraciones()`
- `chat_stream(modo="profundo")`
- `agente._responder_final_stream()` (Asistente, "Leer con el Asistente" y chat de casos)

Mide en vivo y reporta:

1. **Latencia real por función.** Antes era de 100 a 175 s con monitor-critico. Mide el tiempo hasta el primer token y el tiempo total.
2. **Calidad, antes/después.** Usa los mismos casos documentados en CLAUDE.md: el subsidio al diésel en Lectura IA, "Alias Fito" en el chat (debe verificar, nunca inventar) y la pregunta "¿Qué ángulo de reportaje me recomendarías esta semana?" en el Asistente.
3. **Las 10 preguntas del Asistente** (lista en CLAUDE.md, Bloque 2) que nunca se corrieron completas en vivo. Córrelas ahora y dame el resultado resumido de cada una: si citó bien, si inventó algo, cuánto tardó.
4. **Si el Pro preview da muchos 429 o cuesta demasiado,** propónme qué funciones mover a Flash, con los datos. No lo decidas solo.

## E. Limpieza y cierre

1. **Pruebas.**
   - Arregla `test_fase9_xapi.py`: el gasto se movió a `redes.py` en la D3 y la prueba no se actualizó.
   - Actualiza las pruebas que todavía mencionan Ollama.
   - La suite completa debe quedar en verde.
2. **Documentación.**
   - En `CLAUDE.md`, reemplaza "Requisitos en la PC" (ya no hace falta Ollama; ahora hacen falta `.env` y la clave) y la descripción de `ia.py`.
   - Agrega una excepción explícita a la regla de oro **solo si** terminaste usando un SDK.
   - En `LEEME.md`, explica cómo sacar la clave en Google AI Studio y dónde ponerla.
3. **`Modelfile.critico` queda obsoleto.** Pregúntame antes de borrarlo. Dime además si conviene desinstalar Ollama de la PC (se abre solo al iniciar Windows).
4. **Condición de cierre (obligatoria).** Haz un reinicio real de `python monitor.py serve`, con una sola instancia corriendo, y verifica en `data.json` real y **en el dashboard renderizado** que:
   - `estado_ia`, `estado_contexto`, `estado_veredicto` y `estado_declaraciones` avanzan (+N nuevas);
   - las tarjetas muestran Lectura IA, contexto y veredicto de la noticia correcta;
   - el Pulso social tiene lectura OSINT y posturas;
   - `estado_embeddings` muestra la cobertura subiendo con el modelo nuevo;
   - el panel de gasto muestra el gasto real del día;
   - el servidor aguanta al menos 1 hora sin caerse. Ese era el problema original: repórtalo con la RAM y CPU observadas.

   Nada de "documentado como hecho" sin esta verificación. En este proyecto ese patrón ya pasó siete veces.

**Entregable final**: una tabla por función con estado (ok/falla), latencia real, costo por día estimado a partir de lo medido, y la lista de lo que quedó pendiente con el motivo.
