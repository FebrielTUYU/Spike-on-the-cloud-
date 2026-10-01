# Fase 23 — Más voces de la comunidad + rediseño por sección (Estadísticas, Noticias, Pulso social, Asistente)

Trabajas en Spike (`codigo_fuente\`) junto con Codex, igual que en fases anteriores: tú diagnosticas, implementas y verificas, y le delegas a Codex la revisión de cada cambio grande (flujo descrito en CLAUDE.md, "Flujo de delegación a Codex CLI"). No toques los archivos de estado en tiempo de ejecución (`data.json`, `history.json`, `*_cache.json`, `historias_registro.json`, `comunidad.json`, etc.) salvo para leerlos.

Van cuatro imágenes de referencia en `referencias_fase23\` (Fernando también las adjunta en el chat):
1. `1_estadisticas.png`: dashboard de tarjetas con KPIs arriba y gráficos en cuadrícula
2. `2_noticias.png`: lista de menciones a la izquierda y lectura de la nota a la derecha (estilo Awario)
3. `3_pulso_social.png`: panel por red social con riel de redes y bloques por sección (estilo Porter)
4. `4_asistente.png`: pantalla de chat con saludo, accesos rápidos, sugerencias y caja de entrada abajo

Se toma la **estructura y el orden de la información**, no los colores ni los datos de ejemplo. La paleta sigue siendo la de Spike (verde + negro, Fase 22).

---

## Paso 0: poner al día la documentación (antes de tocar nada)

`CLAUDE.md` y `COORDINACION.md` se quedaron en la Fase 19, pero el código ya tiene las Fases 20, 20b, 21, 22, 22b y 22c (Comunidad Guayaquil, WhatsApp/Facebook, ventana de 10 h y EmergenciasEc, interfaz tipo Power BI, recarga por versión de plantilla, mapa de Guayaquil y lectura de la comunidad con IA). Escribe en CLAUDE.md una sección corta por fase: qué hace, en qué archivos está y qué quedó pendiente o sin verificar en vivo. Sácalo del código y de las pruebas `test_fase20*`, `test_fase21*` y `test_fase22*`, no de la memoria.

---

## Parte A: ampliar las cuentas comunitarias (acceder más fácil a las quejas de la gente)

Hoy `x_cuentas_locales.json` tiene casi solo cuentas **oficiales** (ECU 911, ATM, Bomberos, Interagua, etc.) más EmergenciasEc, y `facebook_fuentes.json` está vacío. Fernando quiere **cuentas de noticias comunitarias**: páginas o personas que publican lo que pasa en los barrios (reportes ciudadanos, denuncias vecinales, cuentas de sector tipo "Guayaquil Denuncia", grupos de barrio). Ahí se concentran las quejas.

1. **Descubrir candidatas con datos reales que ya tiene Spike**, sin inventar usuarios:
   - `redes.red_emergencias()`: usuarios que más interactúan con EmergenciasEc
   - autores de `comunidad.json` con varias quejas en Guayaquil en los últimos días
   - cuentas que aparecen mencionadas o retuiteadas en `x_cache.json` junto a términos de queja (`comunidad.TERMINOS_QUEJA`) y barrios
   Rankéalas por nº de quejas de Guayaquil distintas que aportaron. Descarta medios grandes e instituciones (`xapi.clasificar_autor`, `social.es_cuenta_medio`).
2. **Agregar un tipo nuevo `"comunitaria"`** en `x_cuentas_locales.json` (distinto de `oficial`), con `verificada` y `activa` como las demás. Una comunitaria **nunca** cuenta como fuente oficial en Alertas. Sus publicaciones entran a Comunidad como voz de la gente (hoy `es_persona()` puede descartarlas por el handle; revisa ese filtro para que una cuenta marcada `comunitaria` pase).
3. **Dejar la lista editable desde el dashboard**: un panel en Comunidad con "Cuentas sugeridas" (usuario, nº de quejas aportadas, ejemplo de post, botones Agregar/Descartar) y "Cuentas seguidas". Nada se agrega solo: Fernando aprueba cada una.
4. **Facebook**: el mismo panel debe permitir pegar URLs de páginas y grupos públicos de barrio, que se guardan en `facebook_fuentes.json`. No inventes URLs.
5. **Presupuesto**: las cuentas van en una sola consulta `from:A OR from:B …` por tanda (ya existe `xapi.consulta_cuentas`), así que agregar cuentas sube el costo por tweets devueltos, no por cuenta. Mide cuántos tweets/día agregan las comunitarias y muéstralo en el panel de gasto. El tope sigue en $4.70/mes; si se acerca, que las comunitarias bajen de frecuencia antes que EmergenciasEc y Alertas.

---

## Parte B: rediseño de la interfaz

Regla común para todas las secciones: **nada de datos de relleno**. Si Spike no tiene un dato que aparece en la imagen (seguidores, demografía, impresiones, alcance), ese bloque **no se dibuja**; no se simula ni se pone en cero. Cada gráfico lleva una línea de lectura en texto que diga qué significa ("La mayoría de quejas de hoy son de agua, concentradas en el Guasmo"). Si el gráfico no permite decir nada, se quita.

### B1. Estadísticas → imagen 1
Fernando dice que hoy "no dicen mucho". Rehacer `secStats`:
- **Fila de 4 KPI** arriba, cada uno con valor, variación contra el periodo anterior (+/−%) y una barrita de progreso: historias de hoy, quejas de la comunidad hoy, alertas activas y el tema que más creció.
- **Cuadrícula de tarjetas** debajo:
  - cobertura por categoría en el tiempo (área o línea, no 3D)
  - interés de búsqueda vs cobertura (con la brecha marcada)
  - actividad por hora del día (barras, como "Earnings per day")
  - 2 tarjetas tipo dona con porcentaje: Ecuador vs Mundo y Guayaquil vs resto del país
  - un calendario del mes con intensidad de noticias por día (clic en un día filtra Noticias)
- Nada de gráficos 3D ni decorativos: la imagen los tiene, pero no se copian.
- Usa las fuentes reales que ya existen (history.json, trends/wiki, GDELT si responde). Muestra la antigüedad del dato ("interés: hace 25 h") cuando sea viejo.

### B2. Noticias → imagen 2, más compacta
- **Dos columnas**: a la izquierda la lista de historias, a la derecha la historia seleccionada (título, medios, imagen, resumen, contexto, contraste, pulso social de esa historia, enlaces).
- Tarjetas de la lista **más pequeñas** que en la imagen, para que se distingan una de otra: título en 2 líneas máx., medio · ciudad · hora, un fragmento corto, nº de medios y un indicador de tono o de interés. Separación clara entre tarjetas (borde o fondo alterno).
- Arriba de la lista: iconos de filtro por fuente/red, buscar, orden (Relevantes/Recientes) y filtros existentes (ámbito, Guayaquil).
- En el celular, la lista ocupa toda la pantalla y la historia se abre encima con botón para volver.

### B3. Pulso social → imagen 3
- **Riel de redes** a la izquierda del contenido (X, TikTok, Bluesky, Mastodon, YouTube, Facebook, WhatsApp importado; solo las que tienen datos). Clic en una red muestra su panel.
- Bloques con encabezado tipo pestaña, como en la imagen:
  - **Conversación**: volumen de publicaciones por hora (barras) + top temas
  - **Participación**: interacciones (likes/RT/comentarios) si la red las trae, más la tabla "publicaciones con más interacción"
  - **Dónde**: mini mapa o lista de barrios de Guayaquil (reusar `mapa.py`) + tabla de barrios con más menciones
  - **Publicaciones**: tabla con autor, texto, red, hora, interacciones y un enlace
- Las alertas importantes siguen dentro del Pulso social (decisión anterior de Fernando), arriba del bloque de la red activa.
- Sin demografía ni "followers": no hay esos datos.

### B4. Resto de secciones (Resumen, Última hora, Comunidad, Oportunidades, Contraste, Guardadas, Buscar)
Aplicar **un solo sistema visual común**, el de las tarjetas de la imagen 1: tarjeta blanca con título chico en mayúsculas, KPI grandes, gráficos limpios y la misma separación y radios. No se rediseña la lógica, solo se unifica el aspecto para que todo Spike se vea como un producto.

### B5. Asistente → imagen 4
- Pantalla inicial: saludo ("Hola, Fernando" + "¿Qué investigamos hoy?"), 4 accesos rápidos en tarjetas (Buscar en noticias, Subir documentos, Redactar, Casos) y 3 sugerencias generadas con lo que está pasando ahora en Spike (ej.: "¿Qué dice la gente del corte de agua en el Guasmo?").
- Caja de entrada abajo con adjuntar, historial y selector de modelo (Gemini flash/pro).
- Riel vertical a la derecha con: Chat, Casos, Buscar, Documentos, Historial.
- Al empezar a chatear, el saludo desaparece y queda la conversación (sin perder el arreglo de scroll y selección de texto de la Fase 12).

---

## Verificación (obligatoria, de punta a punta)

Patrón repetido en este proyecto: funciones que se documentan como hechas y nunca se conectan. Por eso:
1. Pruebas nuevas `test_fase23_*.py` para la Parte A (descubrimiento de candidatas, tipo `comunitaria`, que no cuenten como oficiales y guardado del panel).
2. Correr Spike con el `data.json` real, recompilar el `.exe` con `compilar.bat` y abrirlo. Tomar capturas de las 5 vistas (Estadísticas, Noticias, Pulso social, una sección del resto y Asistente) en escritorio y en ancho de celular, y compararlas con las imágenes de referencia.
3. Confirmar en esas capturas que ningún bloque muestra datos inventados o vacíos disfrazados.
4. Entregar una tabla final con "pedido de Fernando → qué se hizo → cómo se verificó → qué quedó pendiente", y registrar la Fase 23 en CLAUDE.md.
