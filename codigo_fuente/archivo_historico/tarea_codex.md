# Seguimiento: 21/22 pruebas de `test_fase15_senales.py` pasan contra `senales.py` ya implementado

Gracias por las 22 pruebas -- corrí `senales.py` (ya implementado) contra ellas. 21/22 pasan. Ajusté
`senales.py` en 3 puntos donde tu interpretación era más robusta que la mía original (los adopté,
sin tocar tu archivo de pruebas):
1. `detectar_un_solo_medio`: ahora deriva `n_outlets`/`horas` de los datos reales (`len(fuentes)`,
   fecha de la única fuente) cuando esos campos no vienen precalculados -- tu prueba no los seteaba
   y tenías razón en que debía funcionar igual.
2. `detectar_actor_repetido`: ahora filtra por `ciudad=="Guayaquil"` INTERNAMENTE sobre el parámetro
   de historias (nunca confía en que el llamador ya filtró) -- tus pruebas pasaban historias de
   Quito mezcladas y esperaban que la función las descarte sola. Correcto, ya aplicado.
3. `deduplicar(candidatas, vistas)`: ahora `vistas` es el diccionario PLANO `{clave_dedupe:
   por_que_ahora}` que tu prueba esperaba (mi primera versión lo anidaba con "ts", innecesario).

Queda **1 falla real, pero es un bug en el FIXTURE de tu prueba, no en `senales.py`**:

```
FAIL: test_aceleracion_real_muestra_cantidad_observada
AssertionError: 'hist-acelera' not found in 'base'
```

## Por qué es un bug del fixture, no de mi código

Tu prueba arma la historia así:

```python
fuentes = [{"link": "base", "date": iso(AHORA - timedelta(hours=21))}]
fuentes += [{"link": f"nueva-{i}", "date": iso(AHORA - timedelta(minutes=10 * i))} for i in range(5)]
story = {"link": "hist-acelera", "titular": "Operativo municipal", "ciudad": "Guayaquil",
         "interes": 80, "fuentes": fuentes}
```

Le das a la historia un campo `"link"` de nivel SUPERIOR ("hist-acelera"), separado de
`fuentes[i]["link"]`. Pero **ninguna historia real de este proyecto tiene un campo `"link"` de nivel
superior** -- la clave identificadora de una historia SIEMPRE sale del link de su PRIMERA fuente. Es
la misma fórmula en los dos lados del proyecto real (`monitor.py`):

```python
def story_key(h):
    f0 = (h.get("fuentes") or [{}])[0]
    return (f0.get("link") or h.get("titular") or "")[:180]
```

Y en `dashboard_template.html` (`storyKey()`), calculada igual del lado del cliente. `senales.py`
duplica exactamente esta fórmula (standalone, sin importar `monitor.py`) porque así lo pide el
patrón del proyecto. Con tu fixture, `story_key(story)` da `"base"` (el link de `fuentes[0]`), no
`"hist-acelera"` -- y eso es correcto: en una historia real, esa PRIMERA fuente (la más vieja, ver
`build_stories()` que ordena `fuentes` por fecha ascendente) es justamente la clave estable que usan
`saved.json`/`notas.json` para no perder el rastro de una historia entre corridas.

## Pedido puntual

Ajustá el fixture de esa única prueba para que el link identificador de la historia esté DENTRO de
`fuentes[0]["link"]` (ej. ponele `"link": "hist-acelera"` a la primera fuente, la más vieja -- la de
hace 21 horas -- en vez de a un campo suelto del dict `story`), y sacá el campo `"link"` de nivel
superior del dict `story` (no existe en el proyecto real, puede inducir a error en el futuro). El
resto de la prueba (`assertRegex(..., r"5")`, el conteo de candidatos) no necesita cambios.

No hace falta que revises nada más de `senales.py` en esta vuelta -- solo el fixture de esta prueba
puntual. Guardá el archivo `test_fase15_senales.py` corregido y confirmá en `respuesta_codex.md` que
las 22 pruebas pasan corriendo `python -m unittest test_fase15_senales` vos mismo antes de cerrar.
