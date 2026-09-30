# Monitor de noticias — Ecuador (v1, fase 1)

Programa local que lee las noticias de **política** y **economía** de varios
medios ecuatorianos, agrupa la misma historia contada por distintos medios,
la etiqueta por temas (palabras clave) y arma un **dashboard** que ordena las
historias por **prominencia editorial**.

No necesita internet para instalarse ni librerías extra: **solo Python 3**.

## Requisitos

- Python 3 (cualquier versión reciente). Nada más. Sin `pip install`.

## Cómo correr

**La forma fácil (sin escribir código): doble clic.**

- Windows: doble clic en **`INICIAR.bat`**
- Mac: doble clic en **`iniciar.command`** (la 1ª vez: clic derecho → Abrir)

Eso arranca el Monitor en tiempo real: abre el dashboard en tu navegador y se
**actualiza solo cada 15 minutos**. Deja la ventana abierta; para detenerlo,
ciérrala. Requiere tener Python insterlado (python.org, marca "Add to PATH").

Si prefieres la terminal, es lo mismo que:

    python3 monitor.py serve            (puerto/min: serve 8001 10)

**Corrida única** (genera el dashboard una vez y termina):

    python3 monitor.py

Para probar sin internet (datos de ejemplo), antepón `MONITOR_SAMPLE=1`:

    MONITOR_SAMPLE=1 python3 monitor.py        (en Windows: set MONITOR_SAMPLE=1)

## Diferenciar Ecuador vs mundo, y por tema

Arriba hay dos controles: las **pestañas** de categoría (Portada / Política /
Economía / Seguridad / Sociedad / General) y el **segmento** Todos / Ecuador /
Internacional. Se cruzan: p. ej. "Seguridad + Ecuador" = crimen nacional;
"Economía + Internacional" = economía del mundo. Cada tarjeta marca su ámbito
(Ecuador / Mundo), que se decide por el **tema de la nota**, no por el medio:
un diario ecuatoriano que cubre a Trump cae en Mundo, no en Ecuador.

## Gráficas de interés

El panel "Interés por tema" cruza dos señales por tema:

- **vol** = volumen de cobertura (cuántas historias lo tocan). Interés
  *editorial*: lo que los medios publican. La línea es su evolución.
- **busq** = **demanda** en Google Trends (índice 0–100, geo Ecuador). Lo que
  la gente *busca*. Se guarda en caché y se consulta como mucho cada 3 horas.

Cuando un tema tiene **mucha búsqueda y poca cobertura**, la historia se marca
con la etiqueta roja **Brecha**: interés desatendido, buen candidato a
investigar. El historial se guarda en `history.json`.

### De dónde sale el interés (Google Trends + Wikipedia)

El programa intenta primero **Google Trends** (búsquedas, geo Ecuador). Trends
es no oficial y a veces devuelve `429` (bloqueo). Cuando falla, cae
automáticamente a **Wikipedia** (vistas de artículos): una fuente oficial,
gratis y que **no se bloquea**, así siempre tienes una señal de interés real.
En la sección Estadísticas se indica qué fuente se usó en la corrida.

- Trends: índice relativo 0–100. Wikipedia: vistas normalizadas a 0–100.
  No son lo mismo que "cuánto busca la gente" exacto, pero sí un proxy real.
- Términos por tema: `TREND_TERMS` (Google) y `WIKI_TERMS` (artículo de
  Wikipedia) en `feeds.py`. Edítalos si un tema no refleja la búsqueda real.
- País de Trends: `MONITOR_TREND_GEO=CO ...` (vacío = mundo).
- Apagar Trends (usar solo Wikipedia): `MONITOR_NO_TRENDS=1 ...`.

### Cobertura y tono de prensa (GDELT)

Aparte del interés de la gente, el programa mide la **cobertura mediática** y el
**tono** con GDELT (gratis, sin clave, no se bloquea): escanea miles de medios,
no solo tus feeds. En la sección Estadísticas verás, por tema, el volumen de
cobertura y si es mayormente positiva (verde) o negativa (rojo). El tono también
aparece en Oportunidades. Es el eje "cuánto y cómo lo cubre la prensa", distinto
del "cuánto lo busca la gente".

- Solo prensa de Ecuador: `MONITOR_GDELT_PAIS=ecuador python3 monitor.py`
  (vacío = toda la prensa en español del mundo).
- Apagar GDELT: `MONITOR_NO_GDELT=1 ...`.

### Agente de IA local (Ollama)

Si tienes **Ollama** corriendo, el programa lo usa para *entender* las noticias:
reclasifica por significado (ej. una declaración política sobre hospitales la
manda a Sociedad/salud, no a Política), decide Ecuador vs mundo por el sentido, y
escribe una **interpretación** de por qué importa cada nota (aparece como "IA ·"
en la tarjeta). Todo local y gratis; no sale nada a la nube.

Optimizado para tu PC: solo analiza las historias top que aún no vio y **cachea**
cada una (`ia_cache.json`), así la primera corrida es más lenta y las siguientes
son rápidas. Usa un modelo pequeño.

- Requiere Ollama y un modelo chico. Si no tienes uno: `ollama pull llama3.2:3b`.
- Elegir modelo: `MONITOR_IA_MODEL=qwen2.5:3b python3 monitor.py`.
- Cuántas notas nuevas por corrida: `MONITOR_IA_MAX=25` (sube/baja según tu PC).
- Apagar la IA (volver a solo palabras clave): `MONITOR_NO_IA=1 python3 monitor.py`.

Si Ollama está apagado, el monitor sigue igual con la clasificación por palabras.

### Contraste con documentación oficial (SERCOP)

En las tarjetas de noticias de Ecuador que tocan gasto u obra pública (contratos,
municipio, hospital, carretera, etc.) aparece un desplegable **"Contraste oficial:
N contrato(s) SERCOP"**: contratos públicos reales de Contrataciones Abiertas
(OCDS) relacionados con el tema. Son **pistas para verificar**, no una afirmación
de que la nota trate de esos contratos — tú confirmas. Gratis, sin clave.

- Apagar SERCOP: `MONITOR_NO_SERCOP=1 python3 monitor.py`.

### Dos secciones

Arriba hay dos pestañas grandes: **Noticias** (el feed ordenado por interés,
con imágenes) y **Estadísticas** (KPIs, distribución por categoría y las
gráficas de búsqueda vs cobertura por tema, con el interruptor Más buscado /
Brecha). Clic en un tema de las gráficas te lleva a sus noticias.

## Qué significa lo que ves

- **Prominencia editorial**: cuántos medios levantaron la historia (señal
  principal), cuántas notas y qué tan reciente. Mide lo que los *editores*
  creen importante, no la audiencia. Es la señal que sí se puede calcular sin
  pedirle permiso a nadie y no la inflan los bots.
- **Temas**: las palabras clave que hicieron match. Se editan en `feeds.py`.
- **Demanda del público** (Google Trends): aparece vacía a propósito. Es la
  fase 1.5 (ver abajo).

## Cómo agregar o quitar medios

Todo está en `feeds.py`. Cada línea es un medio + sección + URL del feed.
El único VERIFICADO es El Universo; los demás son candidatos. Al correr, mira
el "Reporte de feeds": borra los que digan `HTTP 404` u otro error y deja los
que traigan items. Para que la prominencia tenga sentido necesitas **varios
medios** funcionando (así se cruza la misma historia entre ellos).

## Que arranque solo al prender la PC (Windows)

Para que arranque solo al encender la PC (y ya no toques nada nunca):
Win+R → escribe `shell:startup` → Enter → arrastra ahí un **acceso directo**
de `INICIAR.bat` (clic derecho en INICIAR.bat → Enviar a → Escritorio, y mueve
ese acceso directo a la carpeta que se abrió). Listo: cada vez que prendas la
PC, el monitor arranca y el dashboard queda al día sin que hagas nada.

## Lo que falta (siguientes fases)

- **Fase 1.5 — Demanda (Google Trends)**: HECHO (ver arriba). La *brecha*
  (mucha búsqueda + poca cobertura) ya se marca en las tarjetas.
- **Fase 2 — Descubrimiento (SERCOP)**: otro programa, sobre la API abierta
  de Contrataciones Abiertas (OCDS, gratis y sin clave). Ahí se buscan
  anomalías y documentos obligatorios faltantes. Es un proyecto mayor.

## Límites honestos de la v1

- El agrupamiento usa parecido de titulares (no entiende el texto): junta bien
  la misma historia, pero puede fallar en casos raros. Ajusta el umbral en
  `cluster(threshold=0.30)` si ves grupos de más o de menos.
- Esto **no descubre** temas ocultos: te muestra lo que ya está publicado y
  qué tan difundido está. El descubrimiento real es la fase 2.

## Avisos en el iPhone y ver el dashboard desde el celular

El Monitor puede mandarte una **notificación al iPhone** cuando hay un gran cambio,
y puedes **abrir el dashboard en el celular**. Todo sigue corriendo en tu PC: si la
PC está apagada o dormida, no hay avisos ni dashboard.

**Conectar el iPhone (una sola vez):**

1. En el iPhone, instala la app **ntfy** (App Store, gratis, sin cuenta).
2. En la PC, doble clic en **`CONECTAR_IPHONE.bat`**. Te muestra un *tema* (un nombre
   largo tipo `monitor-ec-3f9a…`) y manda un aviso de prueba.
3. En la app ntfy: toca **+**, escribe ese tema tal cual, y acepta las notificaciones.
   Vuelve a hacer doble clic en `CONECTAR_IPHONE.bat`: debe llegarte "Prueba del Monitor".

**Qué te avisa** (cada cosa una sola vez, máx. 3 avisos por pasada, nada de 23:00 a 7:00):

- **Historia fuerte**: una historia de Ecuador que ya cubren 2+ medios (y "sigue
  creciendo" si suma 2 medios más).
- **Pico de tema**: en las últimas 6 h salieron el doble de historias de un tema que
  lo normal. "Lo normal" se aprende solo: necesita ~12 horas de Monitor encendido.
- **Brecha**: un tema que la gente busca y casi nadie cubre (candidato a reportaje).

Los umbrales se cambian en **`movil.json`** (se crea solo). Para apagar los avisos:
`"avisos_activos": false`.

**Ver el dashboard en el celular:** al arrancar con `INICIAR.bat`, la ventana muestra
un enlace "Desde el celular". Tocar cualquier aviso también lo abre.

- **En casa**: el iPhone tiene que estar en el mismo WiFi que la PC. La primera vez,
  Windows pregunta si deja a Python usar la red: marca **Redes privadas** y acepta.
  Si no carga, revisa que tu WiFi esté como red *Privada* en Windows.
- **Fuera de casa**: instala **Tailscale** (gratis) en la PC y en el iPhone, con la
  misma cuenta. El Monitor detecta solo la dirección de Tailscale (empieza con 100.)
  y los avisos usan esa.
- Tip: en Safari, **Compartir → Agregar a pantalla de inicio** y queda como una app.

**Seguridad:** cualquier aparato que no sea tu PC necesita la **clave** de
`movil.json` (va incluida en el enlace; después queda recordada) y solo puede ver el
dashboard, nunca los otros archivos. No compartas `movil.json` ni el tema de ntfy:
quien tenga el tema puede leer tus avisos. Para que el Monitor vuelva a ser solo
local: `"acceso_red": false`.
