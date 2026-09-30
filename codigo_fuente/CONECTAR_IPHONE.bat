@echo off
REM Doble clic: muestra como conectar el iPhone y manda un aviso de prueba.
cd /d "%~dp0"
REM Mismo arreglo que INICIAR.bat (2026-09-23): un solo interprete elegido de
REM antemano, nunca "python ... || py ..." (ese patron podia disparar los dos
REM en algunos casos raros del alias de Windows Store).
where python >nul 2>&1
if %errorlevel%==0 (
    python monitor.py movil
) else (
    py monitor.py movil
)
echo.
pause
