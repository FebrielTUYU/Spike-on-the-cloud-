@echo off
REM Doble clic en este archivo para arrancar el Monitor en tiempo real.
REM Abre el dashboard en el navegador y se actualiza solo. Deja la ventana abierta.
cd /d "%~dp0"

REM BUG REAL encontrado 2026-09-23 (arreglado): antes esta linea era
REM   python monitor.py serve || py monitor.py serve
REM "||" en un .bat significa "si el primer comando termina con error, corre
REM el segundo". El problema es que "python monitor.py serve" queda corriendo
REM INDEFINIDAMENTE (es el servidor) -- no deberia "terminar" nunca por si
REM solo. Pero en esta PC "python" es el alias de Windows Store, que a veces
REM devuelve un codigo de error al arrancar aunque SI haya lanzado el programa
REM real de fondo -- eso disparaba el "||" y arrancaba una SEGUNDA instancia
REM completa por encima de la primera (las dos escribiendo data.json/
REM dashboard.html a la vez). Confirmado en vivo: encontradas y detenidas dos
REM instancias corriendo juntas, tres veces en una sola sesion. Arreglado
REM eligiendo UN SOLO interprete de antemano (nunca los dos a la vez).
where python >nul 2>&1
if %errorlevel%==0 (
    set PYCMD=python
) else (
    set PYCMD=py
)

REM Ademas, chequeo de seguridad: si el puerto 8000 ya esta contestando, el
REM Monitor casi seguro YA esta corriendo en otra ventana -- no lo dupliques,
REM solo abri el dashboard que ya esta en vivo.
for /f %%i in ('powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',8000); 'True' } catch { 'False' }"') do set YA_CORRIENDO=%%i
if /i "%YA_CORRIENDO%"=="True" (
    echo El Monitor ya esta corriendo en esta compu. Abriendo el dashboard...
    start "" "http://localhost:8000/dashboard.html"
    pause
    exit /b
)

echo Iniciando el Monitor de noticias... (para detener, cierra esta ventana)
%PYCMD% monitor.py serve
echo.
echo El Monitor se detuvo. Revisa el mensaje de arriba si fue por un error.
pause
