# Fase 18 — Spike: arreglar la base antes de sumar funciones

**Para:** Claude Code (implementa) + Codex (escribe las pruebas desde esta especificación, ANTES de ver el código de Claude, y revisa).
**Contexto:** Spike ya corre como `.exe`. Fernando hizo el chequeo final y reportó fallos en redes, noticias, estadísticas, oportunidades, contraste y Consulta general. Desde Cowork se revisó el código y el `data.json` real (corrida 2026-09-30 00:08 UTC). Todo lo que está abajo sale de esa revisión, con los números medidos. **No es una lista de ideas: son fallas confirmadas, con su causa.**

**Regla de esta fase (la de siempre, que se sigue rompiendo):** nada se da por hecho hasta verificarlo de punta a punta sobre el `data.json` real Y en el dashboard renderizado, **y después de recompilar el .exe con `compilar.bat`** (Fernando prueba el .exe, no el .py). En el CLAUDE.md, cada paso va con el número medido antes/después.

---

## Diagnóstico medido (resumen)

| Síntoma que vio Fernando | Causa encontrada |
|---|---|
| Se mezclan noticias distintas en una misma historia | Los embeddings **nunca se guardan**: 190 llamadas a `gemini-embedding-001` hoy, pero `0/1711` entradas con vector. El agrupamiento sigue siendo solo por palabras. |
| Una noticia ya cubierta aparece como nueva | Fragmentación: las lluvias de Guayaquil del 29-sep están en **~10 tarjetas separadas**. Además, `rep_titulo` se reemplaza por el título de la nota más nueva, así que una historia vieja sube con otro titular. |
| Guayaquil mezclado con otras ciudades | La historia hereda "Guayaquil" si UNA de sus fuentes lo es. Casos reales: "Cartagena, sin agua por 40 horas" (fundida con cortes de agua de Guayaquil), "Fuerza Regida en la CDMX" (fundida con un show en Samborondón por "fechas y precios"), "116 personas… República Dominicana", "La Libertad, Santa Elena", "JPEC… Cotopaxi", IVA nacional. |
| No recoge noticias al instante | El ciclo corre cada ~90 s (bien), pero **los RSS llegan tarde**: mediana de atraso El Universo 405 min, El Universo Guayaquil 427, El Diario 666, Expreso 125. (Ojo: la medición está inflada por los reinicios; ver Paso 7.) |
| Internacionales sin marco relevante | 1303 de 1563 historias son internacionales. Infobae y Semana entran con su feed GENERAL (conciertos, Cartagena, CDMX), no el de mundo. |
| Ya no identifica oportunidades | `senales.py` (Fase 15) **nunca se importa en `monitor.py`**. No existe `senales_estado.json`. Además, IA solo en 87/1563 historias y contexto en 34/1563, y las "Preguntas abiertas" dependen del contexto. |
| Contraste sin descubrimiento real | 1333 `sin_datos`, 212 `pendiente`, 18 `coincide`. Y `coincide` significa "otro medio dice lo mismo" (medio contra medio), justo lo que no se busca. |
| Estadísticas no reflejan Guayaquil | Interés de búsqueda = Wikipedia en español (global, no Guayaquil), de hace 25 h. GDELT de hace 6 días (429). Aun así una nota local sale con "demanda 100". |
| Redes: Mastodon trae el País Vasco en Guayaquil | El Pulso por TEMA busca en Mastodon por hashtag global ("asamblea" y otros) y el filtro solo descarta si el post nombra otro país. Los 20 temas muestran posts de España, Chile, Venezuela y Eslovaquia etiquetados como "guayaquil". |
| Redes sin fecha / cosas de ayer | Mastodon guarda solo `YYYY-MM-DD`, sin hora. Una alerta de X del **18-sep** (vehículo incendiado en La Atarazana) quedó enlazada a una nota del **29-sep** (incendio de vivienda en el sur). |
| X no mostró las inundaciones de La Atarazana | (1) Las alertas buscan `"corte_luz Guayaquil"` y `"corte_agua Guayaquil"` con guion bajo (no matchean nada) y `"inundacion"` sin tilde. (2) Son 8 términos que se reparten **10 tweets por hora**, ~1 por término. (3) La capa por historia corre cada 12 h y arma consultas como `"hasta Guayaquil"`, `"ataque Guayaquil"` o `"fuerte Guayaquil"` (toma como nombre propio la primera palabra del titular). (4) `_es_boletin_plantilla` saca de X toda historia con servicio mencionado (cortes de agua, etc.): justo lo comunitario. |
| Consulta general: "no tengo datos" sobre noticias comunitarias de Guayaquil | `herramientas.buscar_historias` no tiene filtro por ciudad, y con `q="noticia comunitaria Guayaquil"` exige 2 de 3 palabras ("comunitaria" casi nunca aparece). Había 121 historias de Guayaquil, entre ellas las inundaciones. |

---

## Orden de trabajo

Van primero los P0: sin ellos, lo demás se construye sobre datos rotos.

### P0-1. Carrera de escritura en `historias_registro.json` (embeddings perdidos)
- **Causa:** `run_fast` (cada ~90 s: `_cargar_registro` → `_fusionar_en_registro` ~10 s → `_guardar_registro`) y el trabajador (`_embed_pendientes_registro`, `_embed_multilingue_…`, `coherencia_…`) cargan y guardan el mismo archivo sin lock. Gana el último que escribe y borra lo del otro.
- **Arreglo:** un `threading.Lock` de módulo para cargar, modificar y guardar el registro. El trabajador NO tiene que retener el lock mientras llama a Gemini: calcula los vectores afuera y después, adentro del lock, **recarga el registro y aplica solo sus campos** (`embedding`, `embedding_modelo`, fusiones) sobre la versión fresca. Revisar a mano todo `_guardar_registro(` (líneas ~1921, 2024, 2165, 2291 y `agrupar_con_memoria`).
- **Aceptación:** después de 3 pasadas del trabajador, `estado_embeddings` sube en cada pasada (ej. 0 → 40 → 80 → 120) y no vuelve a 0 tras un `run_fast`. Prueba de Codex: dos hilos simulados, uno que agrega artículos y otro que agrega embeddings; al final están las dos cosas.

### P0-2. Agrupamiento: ni fundir cosas distintas ni partir un mismo evento
1. **Titular de la historia = el del artículo fundador** (o el de la fuente local con más medios), no el del más nuevo. Lo nuevo va en `actualizaciones` con su hora. Así una historia vieja no se disfraza de nueva.
2. **Veto de lugar extranjero:** si el título de un artículo nombra una ciudad o país extranjero (Cartagena, CDMX, República Dominicana…, reusar `is_foreign`) y la entrada del registro es local (o al revés), no se fusionan, aunque `ciudad` esté vacía.
3. **Veto de plantilla:** frases genéricas ("fechas y precios", "corte de agua", "ataque armado", "¿a qué hora…?", "lista completa de zonas") no pueden ser el único puente entre dos notas. Hace falta además entidad o lugar compartido.
4. **Evento en curso (arregla la fragmentación):** si hay ≥3 historias del mismo lugar con el mismo tipo de hecho (lluvia/inundación, corte, balacera, protesta) en ≤6 h, se agrupan bajo una historia madre (ej. "Lluvias en Guayaquil — 29 sep") con sub-actualizaciones por sector. Con embeddings (P0-1) funcionando, usar coseno más la regla de lugar.
5. **Marca "nueva" vs "actualización":** cada tarjeta dice "Nueva" solo si la historia se creó en esta ventana. Si solo se sumó una fuente: "Actualización · vista por primera vez hace X h".
- **Aceptación con los casos reales:** Cartagena, Fuerza Regida/CDMX, Rep. Dominicana y La Libertad **no** pueden quedar en historias de Guayaquil. Las ~10 tarjetas de lluvias en Guayaquil del 29-sep quedan en 1 historia madre (o ≤2). Codex arma los fixtures con esos titulares exactos (están en `data.json` y en `historias_registro.json`).

### P0-3. Qué es "Guayaquil"
- Una historia es de Guayaquil si **la mayoría de sus fuentes** son de Guayaquil (por texto o por sección de feed) **y el titular elegido no nombra otra ciudad o provincia**. Si hay mezcla, la marca pasa a la ciudad mayoritaria o a "Ecuador".
- Noticia nacional (IVA del feriado, ley de menores, caso Fito) → ámbito Ecuador, sin ciudad, aunque la haya publicado la sección Guayaquil de un diario.
- Samborondón y Durán: etiqueta propia ("Samborondón", "Durán") y el filtro "Guayaquil" las incluye como **Gran Guayaquil**, con chip visible. (Si Fernando prefiere separarlas, es un solo flag.)
- **Aceptación:** de las 121 historias de Guayaquil actuales, ninguna con otra ciudad o país en el titular sin mencionar Guayaquil ni un cantón del Gran Guayaquil.

### P0-4. Conectar `senales.py` (Fase 15), que nunca se enchufó
- Importar el módulo, arrancar el hilo `ciclo_senales` en `serve()` como dice COORDINACION.md, escribir `senales` en `data.json` y renderizarlas en Oportunidades, arriba de todo.
- Las señales tienen que servir para **todo Ecuador**, no solo Guayaquil (hoy `_es_guayaquil` filtra todo). Guayaquil va primero, pero Fernando reportó que "ya no identifica oportunidades en Ecuador".
- **Aceptación:** existe `senales_estado.json`, `data.json["senales"]` tiene ≥1 señal en una corrida normal y se ve en el .exe.

### P1-5. Redes X (Apify): que encuentre lo que pasa ahora
1. **Términos de alerta:** construirlos desde las palabras de `TIPO_KEYWORDS` con tilde (`"inundación"`, `"anegado"`, `"corte de luz"`, `"sin agua"`…), nunca desde la clave (`corte_luz`). Una sola consulta con `OR` + `Guayaquil` + **`since:` de las últimas 2 h** (verificar en vivo que el actor respeta el operador; si no, filtrar por `createdAt` al recibir).
2. **Capa de cuentas hiperlocales:** una consulta `from:` con cuentas que informan en tiempo real (ATM, ECU 911, Bomberos Guayaquil, Municipio, Interagua/EMAPAG, CNEL, Prefectura, Secretaría de Riesgos, INAMHI y reporteros locales; Fernando completa la lista en un JSON editable). Es más barata y trae más señal que buscar palabras sueltas.
3. **Búsqueda reactiva por evento en curso:** cuando P0-2 detecta un evento en curso en Guayaquil, lanzar al instante (sin esperar 12 h) una consulta X con los barrios de las notas + palabras del tipo de hecho. Ejemplo: `(inundación OR anegado OR lluvia) (Atarazana OR "Av. de las Américas" OR Samanes) since:…`.
4. **Consulta por historia:** no usar como entidad la primera palabra del titular ("Hasta", "Ataque", "Fuerte"). Solo nombres propios reales, siglas o barrios. Sin entidad buena → no gastar.
5. **`_es_boletin_plantilla`:** excluir solo pronósticos del clima y portadas. **Inundaciones, cortes y afectaciones no son plantilla**: son lo comunitario.
6. **Presupuesto:** priorizar evento en curso > alertas > cuentas hiperlocales > historias > debate. TikTok, que lleva 2 "malos días", queda en pausa automática.
- **Aceptación:** reproducir con el caso del 29-sep (lluvias, Av. de las Américas, norte): la capa de alertas o la reactiva trae tweets de esa tarde con fecha y hora, y aparecen en la historia madre.

### P1-6. Alertas: nada viejo, nada mal enlazado
- Descartar al recibir cualquier señal con más de 24 h.
- Enlazar alerta ↔ historia solo si la diferencia de hora es ≤12 h **y** el lugar es compatible. (El caso Atarazana 18-sep ↔ vivienda del sur 29-sep tiene que fallar.)
- **Aceptación:** prueba con ese caso exacto.

### P1-7. Pulso social: solo gente de aquí, siempre con hora
- Para ámbito local o Guayaquil, un post cuenta **solo si tiene señal positiva** (menciona Ecuador, Guayaquil, un barrio o una entidad de la historia, o el autor se ubica en Ecuador). Ya no alcanza con "no nombra otro país".
- **Mastodon fuera de los ámbitos locales** (no hay comunidad ecuatoriana ahí; los 20 temas de hoy son ruido extranjero). Puede quedar para Internacionales.
- Cada post guarda `created_at` completo (ISO con hora) y el dashboard muestra "hace X min/h" y la hora local de Guayaquil. En el Pulso local no se muestran posts de más de 48 h.
- Si un tema no tiene nada local: "Sin conversación local detectada". Nunca rellenar con posts de afuera.
- **Aceptación:** en `data.json["social"]`, 0 posts sin señal ecuatoriana en ámbitos local o guayaquil. Todos con hora.

### P1-8. Velocidad real de los feeds
- **Medir bien:** la latencia se calcula solo sobre artículos que aparecieron con el feed ya sondeado antes (no en la primera lectura tras un arranque, que infla los números).
- **Fuentes más rápidas:** probar desde la PC de Fernando los *news sitemaps* (`sitemap-news` / `news-sitemap.xml`) de El Universo, Expreso, Extra, Primicias y Ecuavisa. Primicias y Ecuavisa hoy están muertos por RSS y un sitemap podría revivirlos. Usar los que respondan como fuente de "último minuto" junto al RSS. Documentar en feeds.py cuáles funcionan y cuáles no.
- **Aceptación:** mediana de latencia real < 20 min en los medios con sitemap.

### P1-9. Internacionales con marco
- Infobae y Semana: cambiar a sus feeds de mundo/internacional (o filtrar su feed general). Nada de espectáculos ni noticias locales de otros países.
- Triaje con Gemini (perfil rápido, en lote) para lo internacional: quedan solo historias con **relevancia global o para Ecuador/la región**, y cada una trae una línea de "por qué importa" (marco). Tope de historias internacionales publicadas (ej. 150) por relevancia.
- **Aceptación:** 0 historias internacionales de farándula o conciertos. Las internacionales del top tienen su línea de marco.

### P2-10. Cobertura de IA y contexto
- Hoy: IA en 87/1563 y contexto en 34/1563. El gasto de Gemini de hoy va en $0.12 de $1 diario: sobra margen.
- Prioridad del trabajador: Guayaquil → Ecuador → top internacional. Subir `CONTEXTO_MAX_NEW` para lo local.
- **Aceptación:** ≥80 % de las historias de Guayaquil y ≥50 % de las de Ecuador con IA y contexto después de 2 pasadas.

### P2-11. Contraste rediseñado: documento oficial primero, hallazgo o nada
Criterio de Fernando: *si es gubernamental, se contrasta con documentación oficial; si son declaraciones, ahí sí se chequea con medios.*
1. **Clasificar la afirmación** (Gemini, perfil rápido): (a) **acto oficial** (ley, decreto, contrato, cifra oficial, corte programado, obra); (b) **declaración** de un actor; (c) **hecho** (crimen, accidente, clima).
2. **(a) Acto oficial → documento primario:** Registro Oficial, Asamblea, SERCOP, Presidencia (decretos), INEC y BCE. Para servicios locales: Municipio, ECU 911, Interagua/EMAPAG, CNEL, ATM. Resultado: "Documento encontrado: [enlace]" o "No se encontró el documento oficial" (esto último ya es un dato: se anuncia algo que no está publicado).
3. **(b) Declaración → otros medios + declaraciones previas del mismo actor** (`declaraciones.json`). Aquí va el valor: ¿dijo algo distinto antes?
4. **(c) Hecho → cifras entre medios:** muertos, montos, horas, lugares. Si difieren, es hallazgo.
5. **Estados nuevos:** `hallazgo` (discrepancia con cita verificable de las dos partes), `documento_oficial` (hay respaldo primario), `corroborado_medios` (el viejo "coincide", visualmente secundario), `sin_hallazgo`. **Nunca** mostrar "coincide" como si fuera un descubrimiento.
- **Aceptación:** la ley de menores (penas de hasta 26 años) enlaza a Asamblea o Registro Oficial, o dice explícitamente que no se encontró. Al menos 1 `hallazgo` real en una corrida, con las dos citas.

### P2-12. Estadísticas honestas
- Cada número muestra su fuente, su **alcance geográfico real** y su antigüedad. Wikipedia = hispanohablantes del mundo, **no Guayaquil**. No se usa como "demanda" de una historia local: ahí va "sin dato local".
- Dato de más de 6 h → marcado como viejo. Dato de más de 48 h → no se grafica.
- **Decisión para Fernando (no implementar sin su OK):** medir búsquedas reales de Guayas con Google Trends `geo=EC-G` vía Apify (con costo, dentro o fuera de los $5).

### P2-13. Consulta general que sí responde
- `buscar_historias`: agregar `ciudad` y `barrio`. Si `q` no trae nada, el agente reintenta sin `q` filtrando por ciudad y tema (`Cultura/Comunidad`, servicios, lluvias, seguridad barrial).
- Con embeddings funcionando (P0-1): búsqueda semántica sobre titular + resumen.
- **Aceptación con la pregunta exacta de la captura:** *"En el caso que queramos medir una noticia comunitaria en Guayaquil para realizarla en los próximos días, ¿qué idea podríamos trabajar?"* Tiene que responder con historias reales del feed (inundaciones del 29-sep por sector, cortes de agua en el norte, Mucho Lote, taxirrutas de estudiantes…), citándolas, y proponer ángulos. Si responde "no tengo datos", la prueba falla.

---

## Fase 18-B (solo si Fernando lo aprueba): "movimiento real de la ciudad"
No implementar sin su OK. Opciones medidas por costo y señal:
- **Lluvia en tiempo real (gratis, sin clave):** precipitación por hora de Guayaquil con Open-Meteo. Si pasa de un umbral, dispara la búsqueda reactiva de X del P1-5 y una alerta "posibles anegaciones".
- **Mareas (INOCAR):** marea alta + lluvia = riesgo de inundación. Es un cruce que la prensa hace tarde.
- **Cuentas hiperlocales en X** (P1-5.2): ya son la mejor aproximación sin ir al campo.
- **Waze for Cities:** datos de tráfico e incidentes en vivo, pero exige convenio (pensado para municipios y medios). Viable solo si Spike se vuelve producto para un diario.
- **Tips ciudadanos:** un bot de Telegram o WhatsApp donde lectores o fuentes mandan reportes. Es la ventaja real que ningún scraper da.

---

## Cierre
- Codex escribe primero `test_fase18_*.py` desde esta especificación (fixtures con los titulares reales citados arriba). Claude implementa. Codex revisa.
- Recompilar con `compilar.bat` y probar en el .exe.
- En CLAUDE.md y COORDINACION.md: tabla antes/después con los números de la sección "Diagnóstico medido".
