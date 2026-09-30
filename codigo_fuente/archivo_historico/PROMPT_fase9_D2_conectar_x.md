# Fase 9, parte D2: los tweets de X se recolectan pero no llegan al dashboard

Fernando activó el token de Apify (`x_config.json`, 04:26 UTC del 2026-09-26) y abrió el dashboard, pero no ve ningún dato de X. Desde Cowork se revisaron `data.json` (generado 04:31 UTC), `xapi.py`, `monitor.py` y `dashboard_template.html`. Esto es lo que se encontró. **Reprodúcelo primero** y avisa si algo no coincide.

## Diagnóstico
1. **X todavía no hizo ninguna llamada.** `estado_x` = `activo: True, gasto_hoy: 0.0` y no existen `x_cache.json` ni `x_gasto.json`. El token apareció a mitad de una pasada del trabajador y el trabajador sigue con backlog de IA (`estado_ia` = 193/1007), así que la capa X espera a la siguiente pasada. Esto es menor, pero Fernando no tiene cómo saberlo.
2. **Aunque X corra, los tweets no se muestran en ningún lado (el mismo patrón de "hecho pero sin conectar", otra vez):**
   - `xapi.pasada()` guarda los tweets por historia en `x_cache.json` (`guardar_tweets_historia`), pero **`get_social_historias()` no los lee**: solo usa `social.recolectar()` (YouTube/Mastodon/Bluesky). `xapi.tweets_de_historia()` no tiene ningún llamador en `monitor.py`.
   - `respuestas_de()` (el debate) baja respuestas que tampoco llegan al Pulso social.
   - `buscar_alertas_gye()` devuelve tweets nuevos, pero `pasada()` solo **los cuenta** (`r["alertas"] = len(items)`) y **nunca se los pasa a `alertas.py`**. Las alertas siguen alimentándose solo de Bluesky/Telegram/RSS, y el texto del bloque "Alertas de la gente" ni menciona X.
   - El panel "Prueba X" solo muestra el gasto. Ninguna de las métricas pedidas en la parte D (historias con 10 o más tweets de personas, alertas por X y su adelanto, proporción de personas frente a medios) está conectada.
3. `social_historias` sigue en "sin datos aun", por el mismo backlog del trabajador (pendiente 7 de la Fase 9).

## Arreglos
1. **Conectar X al Pulso social.** En `get_social_historias()`, por cada historia, suma `xapi.tweets_de_historia(link)` y sus respuestas como posts con `fuente: "x"`, con el mismo formato que el resto (`autor`, `texto`, `url`, `likes`, `reposts`, `fecha`, `tipo`). Pasan por el filtro de pertenencia y la clasificación persona/medio/institución/político, entran en las posturas con citas y, si hay respuestas, forman el **hilo principal** (tweet original y sus respuestas). Con `createdAt` agrega la **curva de volumen por hora** que quedó pendiente (pendiente 5).
2. **Conectar X a las alertas.** Cada tweet nuevo de `buscar_alertas_gye()` entra a `alertas.py` con la misma función de entrada que usan Bluesky/Telegram, como fuente `"x"`, deduplicada por `author.userName`. Actualiza el texto del bloque "Alertas de la gente" para que nombre a X.
3. **Que X no dependa del backlog de IA.** La capa X es barata y rápida, así que tiene que correr apenas aparece el token y después según su propia frecuencia, aunque el trabajador esté ocupado con interpretaciones pesadas. Puede ser un hilo liviano propio o un chequeo al inicio de cada pasada que no espere a nada. Lo mismo para `get_social_historias`: su recolección no puede quedar detrás de la IA.
4. **Botón "Actualizar X ahora"** en el panel "Prueba X" (endpoint local, mismo criterio de autorización que el resto). Fuerza una pasada respetando los topes y así Fernando puede probar sin esperar.
5. **Panel "Prueba X" con estado honesto.** Muestra la última corrida (hora y resultado por capa), la próxima corrida programada, cuántos tweets hay en caché y el último error real. Agrega las métricas de la parte D: % de historias top con 10 o más tweets de personas, alertas originadas o corroboradas por X con su adelanto en minutos, proporción de personas / medios / instituciones / políticos y costo por historia con debate útil.
6. **Selección de historias para X** (pendiente 8): excluye los boletines de plantilla (clima, El Niño, feriados, servicios) de las 6 historias top. En la simulación real, 3 de 6 eran boletines y eso gasta crédito en conversación que no es debate.
7. **Verificar en vivo lo que quedó asumido** (pendiente 6): confirma con la primera llamada real si `conversation_id:` funciona con el actor principal y cuál es el campo real del costo del run en la API de Apify. Documenta lo que salga.

## Pruebas y verificación
- Pruebas con fixtures (forma real del tweet, ya documentada en `xapi.py`): un tweet guardado para una historia aparece en `social_historias` de esa historia con `fuente: "x"`; un tweet de `buscar_alertas_gye` crea o corrobora una alerta; un boletín de clima no entra en la selección para X; el botón respeta el tope diario.
- Verificación real: `serve` reiniciado, **una pasada real de X** y, sobre el `data.json` real, `x_gasto.json` con gasto registrado, tweets visibles en `social_historias` de al menos una historia, el estado de alertas con la fuente X y el panel "Prueba X" con datos. Muéstrale a Fernando los números.
- Documenta todo en CLAUDE.md como "Fase 9, parte D2", con sus pendientes reales.

Al final, dile a Fernando una sola cosa: en qué sección del dashboard (Pulso social o Estadísticas → Prueba X) va a ver los tweets.
