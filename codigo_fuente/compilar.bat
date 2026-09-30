@echo off
setlocal
set "PROYECTO=%~dp0"
if "%PROYECTO:~-1%"=="\" set "PROYECTO=%PROYECTO:~0,-1%"

python -m nuitka --version >nul 2>&1
if errorlevel 1 (
    echo Nuitka no esta instalado o no se puede ejecutar con Python.
    echo Instala Nuitka con: pip install nuitka
    exit /b 1
)

REM No se incluye casos/: contiene investigaciones reales y privadas del usuario.
REM No se incluyen *_cache.json: son caches locales que se regeneran y pueden contener datos privados.
REM No se incluyen data.json, history.json ni historias_registro.json: son datos generados de corridas reales.
REM No se incluye .env: contiene la clave real de Gemini del usuario y nunca debe distribuirse.
REM No se incluyen x_config.json ni movil.json: contienen configuracion personal.
REM No se incluyen saved.json, notas.json ni declaraciones.json: contienen contenido personal del usuario.

REM --include-package=webview NO se agrega a proposito: Nuitka ya detecta e
REM incluye pywebview solo (analisis estatico del import en monitor.py), y
REM forzarlo con esta bandera choca con la decision propia del plugin de
REM Nuitka sobre webview.platforms.android (error real visto al probar:
REM "Conflict between user and plugin decision for module
REM 'webview.platforms.android'", compilacion fallida). Confirmado que sin
REM esta bandera el standalone igual trae la carpeta webview/ completa.

REM BUG REAL encontrado (Fase 17, diagnostico de arranque lento): compilar
REM con ESTA carpeta (codigo_fuente) como directorio de trabajo rompe la
REM compilacion DESPUES de la primera vez. Motivo confirmado paso a paso:
REM "python -m nuitka" pone el directorio de trabajo actual primero en
REM sys.path; esta carpeta tambien tiene, desde el paso de copiado de mas
REM abajo, el standalone YA compilado de la vez anterior (Spike.exe +
REM _ctypes.pyd + python314.dll + demas .pyd/.dll, puestos aca a proposito
REM para que el .exe encuentre data.json/.env junto a el). Al arrancar
REM Nuitka, su propio "import _ctypes" interno encuentra primero el
REM _ctypes.pyd LOCAL (el copiado) en vez del real de la instalacion de
REM Python -- eso hace que Nuitka concluya, por error, que ESTA CARPETA
REM ENTERA es parte de la libreria estandar (porque contiene un .pyd que
REM "parece" de stdlib), y rechaza compilar monitor.py con: "Error,
REM 'monitor.py' is in the standard library, compiling files from there as
REM main files is not supported." Confirmado en vivo con
REM nuitka.importing.StandardLibrary.isStandardLibraryPath(): da True
REM compilando desde esta carpeta, False compilando desde una carpeta
REM vacia. Arreglo: compilar SIEMPRE desde una carpeta de trabajo vacia y
REM descartable (nunca desde esta carpeta) -- las rutas de entrada/salida
REM van absolutas, asi el resultado sigue siendo el mismo de siempre.
set "BUILD_CWD=%PROYECTO%\dist_compilado\_build_cwd"
if not exist "%BUILD_CWD%" mkdir "%BUILD_CWD%"
pushd "%BUILD_CWD%"

python -m nuitka ^
    --standalone ^
    --include-data-files="%PROYECTO%\dashboard_template.html"=dashboard_template.html ^
    --include-data-files="%PROYECTO%\logo.png"=logo.png ^
    --windows-icon-from-ico="%PROYECTO%\logo.ico" ^
    --output-filename=Spike.exe ^
    --output-dir="%PROYECTO%\dist_compilado" ^
    --assume-yes-for-downloads ^
    --windows-console-mode=attach ^
    "%PROYECTO%\monitor.py"

set ERR=%errorlevel%
popd

if %ERR% neq 0 (
    echo La compilacion fallo. Revisa los mensajes anteriores.
    exit /b 1
)

REM Spike.exe necesita vivir en la MISMA carpeta que data.json/.env/los
REM caches (busca todo relativo a su propia ubicacion, no a la carpeta
REM actual) -- por eso el standalone completo se copia de
REM dist_compilado\monitor.dist\ hacia esta misma carpeta (donde ya esta
REM monitor.py y todos los datos reales), en vez de quedar aislado dos
REM niveles mas abajo. Se sobreescriben dashboard_template.html/logo.png
REM (son copias identicas del mismo archivo fuente, no se pierde nada).
REM BUG REAL (Fase 18, encontrado en vivo): si Spike.exe esta corriendo en
REM este momento (Fernando lo tiene abierto), Windows bloquea ese archivo y
REM "xcopy" falla con "Sharing violation" -- pero como el script seguia de
REM largo sin chequear el resultado, el "rmdir" de la linea de abajo borraba
REM IGUAL el build nuevo recien compilado (en dist_compilado\monitor.dist),
REM dejando el .exe VIEJO (el que seguia corriendo) como si nada hubiera
REM pasado, y ademas perdiendo el build nuevo sin ningun aviso. Arreglado:
REM se revisa el resultado de xcopy ANTES de borrar nada.
echo Copiando el ejecutable junto a los datos reales...
xcopy /y /e /i "%PROYECTO%\dist_compilado\monitor.dist\*" "%PROYECTO%\"
if errorlevel 1 (
    echo.
    echo No se pudo copiar el ejecutable nuevo -- probablemente Spike.exe esta
    echo abierto ahora mismo. CERRA Spike.exe por completo y volve a correr
    echo compilar.bat -- el build nuevo quedo a salvo en
    echo dist_compilado\monitor.dist\Spike.exe, no se perdio nada.
    exit /b 1
)
rmdir /s /q "%PROYECTO%\dist_compilado\monitor.dist"

echo Compilacion terminada: Spike.exe (en esta misma carpeta)
echo ANTES DE CORRERLO POR PRIMERA VEZ EN UNA PC NUEVA, COPIA JUNTO AL EXE UN ARCHIVO .env PROPIO CON UNA CLAVE REAL DE GEMINI. NUNCA USES LA CLAVE DE FERNANDO.
echo El .exe no incluye ningun archivo .env a proposito (en esta carpeta ya hay uno real, no hace falta tocarlo).
exit /b 0
