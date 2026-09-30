# Coordinación — dos frentes activos

## Frente B (nuevo, 2026-09-29): el `.exe` tarda muchísimo en cargar o no termina

**Quién es quién**: Claude hace diagnóstico + arreglos; Codex (vía `codex exec`) escribe la
prueba de arranque con tiempos del Paso 3 y revisa cada cambio antes de cerrarlo. Un archivo,
un dueño a la vez — ver la tabla de abajo.

| Archivo | Dueño | Estado | Nota |
|---|---|---|---|
| `monitor.py` | Claude (tomado) | en curso | instrumentación de tiempos por etapa (Paso 1), después arreglos (Paso 2) |
| `test_arranque_tiempos.py` (nuevo) | **Codex** | por crear | prueba de arranque que mide tiempos .py vs .exe, Paso 3 — Claude NO edita este archivo |
| `COORDINACION.md` (esta sección) | Claude | libre tras cada edición | |
| `CLAUDE.md` | Claude (al cierre) | libre | Paso 3.6 |

**Estado de los pasos (Frente B)**:
- [x] Paso 1 — Diagnóstico con tiempos reales (sin cambiar lógica) — revisado por Codex, ver `respuesta_codex.md`
- [x] Paso 2 — Arreglos — revisado por Codex (encontró un bug real en el cache antes de cerrar, ver abajo), arreglado y con prueba dedicada
- [x] Paso 3 — Verificación — completa, ver tabla final y hallazgos en CLAUDE.md (Fase 17)

**Reglas de este frente**: no tocar `.env`; no borrar runtime (copiar antes de dejar de usar);
respetar topes de gasto de IA/redes; no romper el Frente A (ciclo de señales/notificaciones, ver
abajo); parar y preguntar antes de borrar datos, reprocesar >50 historias en lote, o cambiar la
herramienta de empaquetado (Nuitka).

### Bitácora del Frente B

### ✅ Paso 1 — Diagnóstico con tiempos reales (Claude)

**Instrumentación agregada** (`monitor.py`, sin cambiar ninguna lógica existente): `_log_arranque()`
(escribe a `arranque.log`, junto al programa, con timestamp — se trunca una vez por proceso y
después queda en modo append; es la única forma de ver algo cuando corre el `.exe`, que no tiene
consola) + `_medir_etapa()` (context manager chico para INICIO/FIN/duración de un bloque). Se
instrumentó: `collect()` (tiempo total + los 5 feeds más lentos + cualquiera con error/timeout),
cada sub-paso de `enrich_pass()` (embeddings, multilingüe, coherencia, señales, redes, IA,
geo-evidencia, contexto, factcheck, veredicto, declaraciones, social, social-por-historia), y los
hitos de arranque de `serve()`/`_arrancar_backend()` (ventana creada, primera pasada terminada,
puerto bindeado, primera respuesta HTTP real, navegación del esqueleto al dashboard real). También
loguea, en la primera línea, si el proceso es "exe compilado" o "python interpretado" y qué `HERE`
está usando — la hipótesis #1 más común de ".exe lento" es que use una carpeta distinta a la del
`.py`, y esto lo confirma o descarta al instante.

**CAUSA CONFIRMADA (dominante, ~94% del tiempo medido) — algorítmica, NO de empaquetado:**
`_match_registro()` (llamada desde `_fusionar_en_registro()`, dentro de `agrupar_con_memoria()`,
que reemplaza a `cluster()` en el pipeline real desde la Fase 9) recalcula
`extranjero_sin_ecuador(articulo_nuevo)` en **CADA iteración** del registro completo (hasta ~1300
entradas por artículo, dentro de la ventana de 72h) — pese a que ese valor depende SOLO del
artículo nuevo, nunca de la entrada del registro contra la que se compara en esa vuelta del loop.
Es una recomputación 100% redundante: se hace ~1300 veces por artículo cuando alcanza con 1.

Medido con `cProfile` sobre una copia de solo lectura del registro real (nunca se tocó el archivo
real, ver más abajo): perfilando 40 artículos reales recién bajados (de los cuales solo 9 eran
genuinamente nuevos — el resto ya estaban registrados y se descartan barato), `_fusionar_en_registro`
tardó **61.85s** (con el overhead propio de profiling), de los cuales:
- `extranjero_sin_ecuador` + lo que llama debajo (`is_foreign`/`is_ecuador`/`geo_hit`/`norm`/
  `strip_accents`): **58.09s = 93.9% del tiempo total**, con **1 795 076 llamadas a `geo_hit()`**
  (cada una hace `norm()` + construye un regex con `re.escape()` + `re.search()`) solo para esos 9
  artículos.
- El resto (tokens, similitud, sets) es marginal en comparación.

**Extrapolación real, no estimada**: a este ritmo (9 artículos nuevos ⇒ 61.85s bajo profiling), los
~1746 artículos que trae `collect()` en una pasada completa (de los cuales una fracción similar,
~22%, sería genuinamente nueva ⇒ ~390 artículos) proyectan **~2700s (45 minutos) bajo profiling** —
consistente con lo observado en vivo SIN profiling: se dejó correr tanto `python monitor.py serve`
como `Spike.exe` (recién compilado, con la misma instrumentación) contra los datos reales, y
**los dos se quedaron colgados en la MISMA etapa exacta** (justo después de que `collect()` termina
en ~5s, antes de cualquier otro log) durante 15+ minutos, sin ninguna diferencia perceptible entre
ambos — se cortaron a mano sin haber terminado, sin dañar `historias_registro.json` (confirmado
JSON válido y sin tocar en los dos casos, `ts` de modificación sin cambios).

**Por qué se puso tan lento AHORA**: la causa de fondo (la recomputación redundante) es vieja, pero
antes pasaba inadvertida porque el registro era chico. La Fase 13 extendió la retención de
historias LOCALES de 3 a 90 días (`REGISTRO_DIAS_LOCAL`) — el registro real hoy tiene **1485
entradas / 63MB** (antes de esa fase habría sido ~30x más chico). El costo de esta función escala
con el tamaño del registro dentro de la ventana de 72h (que NO cambió, sigue en 72h) — no con la
retención en sí, pero un registro más grande en general trae más candidatos dentro de esa ventana
en momentos de mucha actividad.

**Hallazgo aparte, bloqueaba poder recompilar el `.exe` para esta misma prueba (arreglado, ver
Bitácora de arreglos más abajo)**: compilar con `codigo_fuente/` como carpeta de trabajo (porque
ahí vive el standalone YA compilado de una vez anterior, con sus `.pyd`/`.dll`, puestos ahí a
propósito en la Fase 16 para que el `.exe` comparta datos con el `.py`) hacía que Nuitka cargara por
error el `_ctypes.pyd` LOCAL en vez del real del sistema, y concluyera que la carpeta entera "es
parte de la librería estándar" — rechazando compilar `monitor.py` con
`Error, 'monitor.py' is in the standard library...`. Confirmado con
`nuitka.importing.StandardLibrary.isStandardLibraryPath()` (da `True` compilando desde
`codigo_fuente`, `False` desde una carpeta vacía). Arreglado en `compilar.bat` (ver más abajo) —
esto es un problema de la HERRAMIENTA DE COMPILACIÓN/carpetas, no de por qué el programa anda
lento, pero había que resolverlo para poder generar un `.exe` fresco con la instrumentación y
probarlo en las mismas condiciones que el `.py`.

**Hipótesis de la lista original, confirmadas o descartadas con evidencia real:**

| # | Hipótesis | Veredicto | Evidencia |
|---|---|---|---|
| 1 | Rutas de datos en carpeta temporal de extracción | **Descartada** | Se usa `--standalone` (no `--onefile`); `HERE` resuelve a una carpeta real y persistente (`codigo_fuente`, confirmado por el propio `arranque.log` del `.exe`: `HERE=C:\Users\elped\DOWNLO~1\DASHBO~1\CODIGO~1`, forma corta de la misma ruta real); el `.exe` usó el registro/caches reales de 63MB, no arrancó vacío. |
| 2 | `multiprocessing` sin `freeze_support()` | **Descartada** | `grep -rn "multiprocessing"` en todo el proyecto: cero resultados. Solo se usa `ThreadPoolExecutor` (hilos, no procesos). |
| 3 | Llamadas de red sin timeout | **Descartada** (no es la causa de esto) | Revisados todos los `urlopen`/`op.open` del proyecto (monitor/ia/social/trends/wiki/gdelt/sercop/factcheck/oficial/xapi/alertas/movil): todos tienen timeout explícito (8–220s según el caso). |
| 4 | Certificados SSL en el ejecutable | **Descartada** | `collect()` (única etapa que hace HTTPS real en esta pasada) tardó prácticamente igual en `.py` (4.87–5.37s) y en `.exe` (4.97s) — si hubiera un problema de certificados en el build, se vería como demoras/reintentos justo ahí, y no los hay. |
| 5 | Carga bloqueante (dashboard espera a que todo termine) | **Ya resuelta en la Fase 16** (esqueleto de carga), pero expone el problema real de arriba: con el registro actual, ni la primera pasada sola termina en un tiempo razonable, así que el esqueleto queda visible mucho más de lo esperado. | Ver Fase 16 en CLAUDE.md. |
| 6 | Choque con el ciclo de señales (Frente A) | **No aplica todavía** | `grep -n "senales" monitor.py`: cero resultados — la integración de Frente A a `monitor.py`/`serve()` todavía no se hizo (sigue en Paso 1 de ese frente), así que hoy no hay ningún choque posible. Ver Pendientes. |
| 7 | Empaquetado onefile + antivirus escaneando en cada arranque | **Descartada** | `compilar.bat` usa `--standalone`, nunca `--onefile` — no hay un único archivo que se autoextraiga; es una carpeta de ~47MB con el exe + DLLs sueltos, igual que `python.exe` + su instalación. |

**Verificado en vivo, dos corridas reales con los MISMOS datos** (no simulado): `python monitor.py
serve` y `Spike.exe` (recompilado con la instrumentación de este paso) contra el registro real de
63MB — ambos con `collect()` en ~5s y después colgados en la misma etapa, sin ninguna diferencia
achacable al empaquetado. `arranque.log` de cada corrida guardado como evidencia (se pisan entre sí
si corren a la vez en la misma carpeta — mismo archivo, ver Pendientes).

**Revisión de Codex**: pendiente — se pide a continuación, antes de tocar `_match_registro()`
(Paso 2).

### ✅ Paso 2 — Arreglos aplicados (Claude)

Codex revisó el diagnóstico y el primer arreglo propuesto (`respuesta_codex.md`): confirmó que
`a_extranjero` no depende de `e` y que sacarlo del loop es "seguro y matemáticamente equivalente",
y que precompilar los patrones de `EC_TERMS`/`FOREIGN_TERMS` es seguro siempre que sean listas fijas
(confirmado por grep: nunca se les hace `.append`/`+=` en ningún lado). Con ese visto bueno, se
aplicaron los dos arreglos propuestos MÁS uno adicional (cache por entrada) que salió de medir el
resultado real después del primero — Codex todavía no vio este tercero, ver más abajo.

1. **`a_extranjero` sacado del loop** (`_match_registro`): se calcula UNA vez por artículo, antes
   del `for eid, e in registro.items():`, en vez de una vez por cada entrada candidata.
2. **`EC_TERMS`/`FOREIGN_TERMS` precompilados** (`_EC_TERMS_RE`/`_FOREIGN_TERMS_RE`, diccionarios
   `{termino: patron_compilado}` armados una vez al cargar el módulo): `is_ecuador`/`is_foreign`/
   `_es_enumeracion_paises` usan estos patrones en vez de llamar a `geo_hit()` (que normalizaba y
   armaba el patrón de nuevo en cada llamada) para estos dos catálogos fijos. `geo_hit()` en sí NO
   se tocó — sigue igual para sus otros usos (ciudades/nombres/alias dinámicos).
3. **Cache por entrada dentro de una misma pasada** (`cache_entry`, nuevo parámetro opcional de
   `_match_registro`, creado una vez en `_fusionar_en_registro` y compartido entre todas las
   llamadas de esa pasada): `extranjero_sin_ecuador(entrada)`/`tokens(rep_titulo)`/
   `tokens(fundador_titulo)` de una entrada del registro NO dependen de qué artículo nuevo se esté
   evaluando — con varios artículos nuevos comparados contra las MISMAS entradas en una sola
   pasada (el caso real), se recalculaban una vez por cada par (artículo × entrada) cuando alcanza
   con una vez por entrada. Se invalida solo: la clave de cache incluye el texto exacto de
   `rep_titulo+rep_resumen` de esa entrada, así que si la entrada suma una fuente más nueva a mitad
   de la misma pasada (cambia su representante), el siguiente artículo que la compare recalcula en
   vez de usar el valor viejo.

**Medido con el mismo método del Paso 1** (`cProfile` sobre una copia de solo lectura del registro
real, nunca se tocó el archivo real):

| | Antes (Paso 1) | Después de arreglo 1+2 | Después de arreglo 1+2+3 (cache) |
|---|---|---|---|
| Artículos evaluados | 40 (9 nuevos) | 40 (10 nuevos) | 300 (153 nuevos) |
| Tiempo real (`_fusionar_en_registro`, bajo profiling) | 61.85s | 9.62s | **3.33s** |
| Llamadas a `extranjero_sin_ecuador` | 23 268 | 12 954 | 1 706 |
| Llamadas a `geo_hit`/`re.search` | 1 795 076 | 977 790 | 189 358 |
| Proyección lineal a los ~1744 artículos reales de esa corrida | ~2700s (45 min) | ~419s (7 min) | **~19.4s (0.3 min)** |

**Verificado sin romper nada**: suite completa (322 pruebas) corrida después de cada arreglo — los
mismos 15 errores ya conocidos y no relacionados de `test_fase9_xapi.py`, cero regresiones nuevas.
Las pruebas existentes que ejercitan `is_ecuador`/`is_foreign`/`extranjero_sin_ecuador`/
`_match_registro` con casos reales (`test_geo_enumeracion.py`, `test_fase2_candado_ia.py`,
`test_problema2_veto_geografico.py`, `test_fase9_agrupamiento.py`, `test_fase9_multilingue.py`,
entre otras) siguen pasando exactamente igual — evidencia de que el resultado de estas funciones no
cambió, solo cuánto tardan en darlo.

**Revisión de Codex sobre el arreglo 3 (cache) — BUG REAL encontrado antes de cerrar**: Codex marcó
que la huella de cache original (`rep_titulo + " " + rep_resumen`, un string concatenado) podía
COLISIONAR entre dos estados distintos de la misma entrada -- ej. `rep_titulo="Rescate playa
Guayaquil"` + `rep_resumen="hoy"` concatena exactamente igual que `rep_titulo="Rescate"` +
`rep_resumen="playa Guayaquil hoy"` (la palabra "playa" cambia de lado, el string combinado da
igual) -- con eso, un `tok_rep` viejo podía quedar cacheado como si siguiera válido después de que
la entrada sumara una fuente nueva a mitad de la misma pasada. Nunca llegó a producción (se
encontró en la revisión, antes de dar el arreglo por cerrado). **Arreglado**: la huella ahora es una
TUPLA de los campos originales (`(rep_titulo, rep_resumen, fundador_titulo)`), que nunca colisiona
entre pares distintos, en vez de un string armado. `test_fase17_arranque.py` (3 pruebas nuevas):
reproduce el caso exacto que reportó Codex (confirmado que el test FALLA con la version vieja del
código y PASA con la corregida — se verificó manualmente revirtiendo la línea antes de restaurarla),
más un control de que el cache sigue sirviendo cuando de verdad no hay cambios, más un caso de
equivalencia end-to-end de `_match_registro` con una entidad extranjera. Suite completa: **325
pruebas** (3 nuevas), mismos 15 errores ya conocidos y no relacionados de `test_fase9_xapi.py`.

**Paso 2 cerrado.**

**Hallazgo aparte durante la verificación final (NO es una regresión de este arreglo)**: la suite
completa corrida al final de esta sesión mostró 3 fallos NUEVOS además de los 15 ya conocidos
(`test_cjng_samborondon_via_embedding`, `test_trump_xi_en_dos_idiomas_se_unen`,
`test_parafraseo_extremo_se_reconcilia_recien_con_embeddings_del_trabajador` — las tres sobre
reconciliación por EMBEDDINGS, un código que este arreglo no tocó en absoluto). Causa real
confirmada: `ia.embed('prueba')` devolvió `None` con `last_error: "presupuesto agotado: tope
diario de IA (1.0000 + 0.0000 > 1.00 USD)"` — el propio trabajo de esta sesión (correr `python
monitor.py serve`/`Spike.exe` varias veces con datos e IA reales para medir tiempos de verdad)
agotó el presupuesto diario de Gemini ($1.00/día). Estas 3 pruebas usan
`@unittest.skipUnless(ia.embed_disponible(), ...)`, pero `embed_disponible()` solo confirma que el
MODELO está configurado/alcanzable, no que quede presupuesto para llamarlo -- un hueco real que ya
existía desde la migración a Gemini (Fase 10), no algo introducido en este Frente. Confirmado que
la suite estaba limpia (322 pruebas, solo los 15 de siempre) ANTES de las corridas reales extensas
de este mismo Paso 1/3 -- no se tocó `ia.py`/el skip de estas pruebas (fuera de alcance de este
frente); deberían volver a pasar solas cuando el presupuesto diario se resetee.

### ✅ Paso 3 — Verificación (Claude, con la prueba de arranque que escribió Codex)

- **Recompilado `Spike.exe`** con los tres arreglos del Paso 2 (compilar.bat, ya con su propio
  arreglo de carpeta de trabajo, siguió funcionando sin problemas en esta recompilación).
- **`test_arranque_tiempos.py`** (escrito por Codex): corrido contra `python monitor.py serve` y
  `Spike.exe`, mismos datos reales. Resultado real: `.py` → 54.6s hasta la corrida completa; `.exe`
  → 38.6s. El campo "segundos hasta noticias visibles" del script dio `null` para el `.exe` por una
  carrera de milisegundos entre el marcador de log y el arranque del hilo del servidor (propia del
  script de prueba, no un problema del programa — el servidor real respondió en <1.5s, ver el punto
  de "carga progresiva" más abajo). Ambas corridas terminaron solas, sin colgarse, muy por debajo de
  los "nunca termina"/"45 minutos" de antes del arreglo.
- **Mejora adicional aplicada tras medir esto** (no estaba en el arreglo original, salió de ver que
  38-55s seguía sin cumplir la meta de "<10s hasta ver noticias"): **carga progresiva real**. Antes
  de esta mejora, el enlazado de puerto pasaba DENTRO de `_arrancar_backend()` (en el hilo de
  fondo), así que la ventana (esqueleto o real) nunca podía mostrar nada hasta que esa función
  terminara. Se movió el enlazado de puerto + arranque del servidor HTTP AL PRINCIPIO de `serve()`,
  antes de la primera pasada del feed (bindear un socket es prácticamente instantáneo, nunca
  depende de red/IA). Con eso: si YA existe un `dashboard.html` de una corrida anterior (el caso
  normal, salvo la primerísima vez), la ventana se abre mostrando ESE dato real de inmediato —
  nunca el esqueleto — mientras la pasada nueva corre de fondo; cuando termina, el propio
  `dashboard_template.html` (que YA sabía refrescarse solo con el poll periódico de `data.json`,
  sin ningún cambio de frontend necesario) se actualiza solo. Si NO hay dashboard previo (primera
  vez real), se sigue mostrando el esqueleto de la Fase 16, sin cambios ahí.
  **Medido en vivo, servidor real**: `[12:58:33.134] serve: puerto bindeado` →
  `[12:58:34.587] servidor: primera respuesta HTTP (GET /dashboard.html)` — **1.45 segundos** desde
  el arranque del proceso hasta que la ventana ya tenía noticias reales en pantalla, muy por debajo
  de la meta de 10s. La pasada de fondo siguió corriendo normal y terminó a los 48.3s, momento en el
  que el dashboard ya visible se refrescó solo con los datos nuevos.
- **3 arranques seguidos / reutilización de cachés**: no se hicieron 3 corridas reales completas
  adicionales a propósito (el presupuesto diario de Gemini ya estaba prácticamente agotado por las
  pruebas de este mismo Paso 1/3, ver el hallazgo de la suite más abajo) — se verificó en cambio con
  evidencia ya acumulada de TODAS las corridas reales de hoy: la etapa `get_ia` de `run_fast()`
  (que en modo lectura solo LEE `ia_cache.json`, nunca llama a Gemini) se mantuvo consistentemente
  rápida (0.45-0.46s) en cada una de las 4+ corridas reales de esta sesión — si estuviera
  reprocesando de cero en cada arranque en vez de reusar el caché, ese tiempo habría crecido con el
  tamaño del caché, no se habría mantenido plano.
- **Feed que no responde**: simulado en aislamiento con una URL que nunca contesta
  (`10.255.255.1`, dirección no enrutable): `_fetch_feed()` cortó exactamente a los 8s
  (`MONITOR_FEED_TIMEOUT`), devolvió `status="URLError"` sin lanzar excepción. Con `collect()`
  corriendo los feeds en paralelo (`ThreadPoolExecutor`), un feed colgado nunca frena a los demás —
  confirmado también con datos reales: "Wambra" devolvió `HTTP 429` en TODAS las corridas de hoy sin
  afectar el tiempo total de `collect()` (siempre 5-10s con 54 feeds).
- **Tope de gasto de IA alcanzado**: confirmado en vivo (no simulado) — el presupuesto diario
  ($1.00) se agotó de verdad durante esta sesión por las corridas reales del propio diagnóstico.
  Ya funcionaba bien desde la Fase 10 (`_cabe_en_presupuesto()`, `data.json["estado_ia_nube"]`,
  panel del dashboard) y esta sesión lo confirmó bajo condiciones reales: TODAS las llamadas a
  `get_ia`/`get_contexto`/etc. en las corridas de hoy (con el presupuesto ya en el límite) siguieron
  devolviendo rápido (nunca se colgaron esperando), simplemente sin gastar más.
- **Suite completa**: 325 pruebas (322 + las 3 nuevas de este Frente). Al cierre de esta sesión
  aparecen 15 + 3 = 18 fallos — los 15 de siempre (`test_fase9_xapi.py`, no relacionados) MÁS 3
  nuevos causados por el presupuesto de Gemini agotado por las propias pruebas de hoy (ver el
  hallazgo detallado arriba, en la bitácora del Paso 2) — NO por este arreglo. Deberían volver a
  pasar solas cuando el presupuesto diario se resetee.

### 🔧 Arreglo de herramienta (no es el Paso 2, es un bloqueante aparte): `compilar.bat`

Compilar con `codigo_fuente/` como directorio de trabajo actual rompía la compilación (ver
diagnóstico arriba). Arreglado: `compilar.bat` ahora compila SIEMPRE desde una carpeta de trabajo
vacía y descartable (`dist_compilado\_build_cwd\`), con todas las rutas de entrada/salida
absolutas — el resultado final (dónde queda `Spike.exe`) no cambió en nada, solo desde dónde se
invoca Nuitka. Verificado con una recompilación real completa, exitosa.

---

# Frente A — Fase 15 — Motor de señales

Archivo vivo: leer antes de cada paso, actualizar al terminar cada uno. Regla dura: **un archivo,
un dueño a la vez** — antes de editar, anotarlo acá como tomado; liberarlo al terminar.

## Quién es quién
- **Claude**: implementa `senales.py` y la integración en `monitor.py`. Diagnóstico del Paso 1.
- **Codex** (vía `codex exec`, delegado por Claude en esta sesión — Codex CLI 0.157.1 disponible):
  pruebas independientes de `senales.py` a partir de la especificación del prompt de Fernando (NO
  del código de Claude), revisión de los cambios antes de cerrar cada paso.

## Archivos: quién los tiene tomados ahora mismo

| Archivo | Dueño | Estado | Nota |
|---|---|---|---|
| `COORDINACION.md` | Claude | libre tras cada edición | este archivo |
| `senales.py` (nuevo) | Claude | por crear | Paso 2 |
| `monitor.py` | Claude | (avisar antes de editar) | integración de señales, wiring de `enrich_pass`/`serve` |
| `movil.py` | Claude | (avisar antes de editar) | ntfy sin tope diario, prioridad, resumen 3x/día |
| `dashboard_template.html` | Claude | (avisar antes de editar) | Paso 6, sección Oportunidades rediseñada |
| `test_fase15_senales.py` (nuevo) | **Codex** (tomado, en curso) | por crear | pruebas independientes de `senales.py` desde la especificación — Claude NO edita este archivo |
| `CLAUDE.md` | Claude (al cierre) | libre | Paso 7 |

## Estado de los pasos

- [ ] Paso 1 — Diagnóstico (Claude, sin cambiar código)
- [ ] Paso 2 — `senales.py` (Claude implementa, Codex prueba desde spec)
- [ ] Paso 3 — Frecuencia (`MONITOR_SENALES_MIN`)
- [ ] Paso 4 — Notificaciones (ntfy sin tope, prioridad, resumen)
- [ ] Paso 5 — Pulso social como dato, no señal propia
- [ ] Paso 6 — Sección Oportunidades rediseñada
- [ ] Paso 7 — Verificación final + CLAUDE.md

## Bitácora (entradas más nuevas arriba)

### ✅ Paso 1 — Diagnóstico (Claude, sin cambiar código)

**1. Notificaciones hoy — causa real de "llegan pocas", con datos reales de `movil_estado.json`/`alertas.json`:**

- `movil.procesar()` corre en CADA pasada de `run_fast` (cada `MONITOR_FEED_MIN`, hoy 1 min) — la
  frecuencia NO es el problema.
- **Causa real, confirmada con datos**: `movil_estado.json` tiene 290 historias marcadas (cap 300).
  Agrupando por ráfagas (candidatos detectados dentro de una misma pasada), hay 102 pasadas
  distintas con actividad, pero **6 de esas pasadas generaron 174 de las 290 marcas** (ráfagas de
  67, 48, 31, 11, 10 y 7 candidatos en una sola pasada — probablemente reinicios del servidor o
  eventos reales grandes). `max_por_corrida=3` significa que de una ráfaga de 67 candidatos, solo
  **3 llegan con detalle completo** y el resto se comprime en UN solo push "Y 64 cambios más" con
  apenas 8 títulos visibles — y los 64 quedan marcados como "ya avisados" para siempre, sin volver a
  surgir. Es decir: el sistema SÍ detecta mucho, pero el celular de Fernando recibe como máximo 4
  push por ráfaga sin importar cuántas historias reales haya. Fuera de las ráfagas, la cadencia real
  es más baja de lo que parece (185 marcas en 48h, pero la mayoría concentradas en esas 6 ráfagas).
- `avisos_nota_nueva` (notas de 1 sola fuente, recién salidas) está **apagado por defecto** en el
  `movil.json` real — nunca se activó. `min_medios=2` sigue excluyendo a casi toda nota hiperlocal
  con 1 solo medio (limitación ya documentada).
- Picos de tema y brechas: `movil_estado.json["temas"]` tiene 22 entradas, pero la mayoría con más de
  79-150 horas de antigüedad (solo 2 recientes) — confirma que `factor_pico=2.0`+`pico_min=4` y el
  enfriamiento de 48h para brechas los hacen genuinamente raros, no un bug.
- **Alertas tempranas (`alertas.json`) SÍ empujan por ntfy correctamente**: de 39 alertas registradas,
  8 llegaron a `corroborado` y las 8 tienen `avisado_hasta="corroborado"` (confirmado enviadas) — este
  camino funciona bien, pero es angosto por diseño (solo incendio/accidente/balacera/corte/protesta
  detectados en Bluesky/Telegram/RSS oficiales de Guayaquil).
- **Horas de silencio (23-7) están ENCENDIDAS por defecto** en el `movil.json` real — compuesto con el
  problema de ráfagas, lo que se detecta de noche se apila para la mañana en un solo lote.

**2. Inventario de Estadísticas/Oportunidades — qué permite decidir y qué es decoración:**

| Elemento | De dónde sale | ¿Habilita una decisión? |
|---|---|---|
| KPIs (`#statskpi`) | conteos simples | No — conteo puro |
| Distribución por categoría (`#dist`) | `seccion` de cada historia | No — descriptivo |
| `renderInterp` (lista de frases) | mezcla de conteos + 1 brecha de tema | Parcial — la línea de brecha sí, el resto es resumen |
| `renderPies` (torta GDELT) | GDELT o volumen propio | No — mercado de cobertura, descriptivo |
| `renderEvolCat` | `history.json` | No — tendencia en el tiempo, descriptivo |
| `renderCharts` (sparks demanda/cobertura) | Trends + cobertura por TEMA | Parcial — el tag "Brecha" sugiere reportaje, pero a nivel de tema abstracto, no historia concreta |
| `renderGdelt` | nota complementaria de cuántos temas respondió GDELT | No — salud de fuente |
| `renderLatenciaFeeds` | `latencia_cache.json` | No — salud técnica de feeds |
| `renderAlertasMetricas` | `alertas.metricas_adelanto()` | No — mide si el sistema de alertas anticipa a la prensa, no es una decisión editorial |
| `renderXPrueba` | gasto de Apify | No — presupuesto |
| `renderEstadoIA` | gasto de Gemini | No — presupuesto |
| **Oportunidades — Preguntas abiertas** (Fase 11) | `contexto.que_falta_saber` por historia | **Sí** — pregunta concreta + por qué importa, ya por historia |
| **Oportunidades — Brecha interés vs cobertura** | Trends+redes por TEMA | Parcial — dice "tema desatendido" pero no baja a una historia ni dice qué hacer primero |
| **Oportunidades — Incompletas** | honestidad de datos faltantes | No — es un aviso de "no sé", no una oportunidad |
| **Oportunidades — Temas poco cubiertos** | conteo de cobertura por tema | Parcial — señala un vacío genérico, sin `primer_paso` ni certeza |

**Marcados para "Otros datos" (Paso 6, sin borrar):** KPIs, distribución por categoría, `renderPies`,
`renderEvolCat`, `renderGdelt`, `renderLatenciaFeeds`, `renderAlertasMetricas`, `renderXPrueba`,
`renderEstadoIA` — todos informativos/de salud del sistema, ninguno propone una acción concreta.
`renderCharts` y el bloque "Temas poco cubiertos"/"Brecha por tema" quedan REEMPLAZADOS en la
práctica por las señales de la Fase 15 (más concretas, por historia) pero no se borran del código —
pasan al bloque colapsado también, ya que sin bajar a historia concreta no cumplen el criterio nuevo.

**3. Arquitectura de frecuencia — qué hace falta para 15 min sin tocar redes ni la corrida completa:**

- `run_fast` YA corre cada `MONITOR_FEED_MIN` (hoy 1 min) leyendo solo caches (nunca red) — la
  frecuencia base ya es más rápida que los 15 min pedidos.
- `enrich_pass` (el trabajador) es el único que toca red/IA, y ya está desacoplado de `run_fast`.
- **Diseño elegido**: un ciclo nuevo y separado, `senales.ciclo_senales()`, llamado desde un hilo propio
  en `serve()` (mismo patrón que `worker_loop`), pausado por `MONITOR_SENALES_MIN*60` segundos entre
  vueltas (def. 15 min = 900s). Lee `stories` desde el último `data.json` publicado (mismo patrón que
  `_cargar_ultimas_historias()`), lee `historias_registro.json`/`entities.json`/`alertas.json`/
  `saved.json` de solo lectura (nunca red), y solo llama a Gemini (perfil rápido) para las DOS piezas
  que lo requieren explícitamente: el veredicto de "¿hubo desenlace?" (tipo 4) y `primer_paso` de cada
  señal nueva — acotado a `MONITOR_SENALES_IA_MAX` por vuelta (mismo patrón que `CONTEXTO_MAX_NEW`),
  para que el gasto de IA sea predecible y nunca dependa de cuántas señales se detecten. Nunca llama a
  `redes.py`/`xapi.py`/`tiktok.py`/`social.py` — el pulso social se LEE de lo que `get_social`/
  `get_social_historias` ya calcularon (Paso 5).

**Revisión de Codex**: pendiente — se le pide a continuación que arme `test_fase15_senales.py` a
partir de esta especificación (no del código que Claude va a escribir), en paralelo al Paso 2.

