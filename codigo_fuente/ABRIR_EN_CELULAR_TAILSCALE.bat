@echo off
REM Doble clic: deja el dashboard disponible en el iPhone fuera de casa (via Tailscale).
cd /d "%~dp0"
REM Mismo arreglo que INICIAR.bat (2026-09-23): un solo interprete elegido de
REM antemano, nunca "python ... || py ..." (ese patron podia disparar los dos
REM en algunos casos raros del alias de Windows Store).
where python >nul 2>&1
if %errorlevel%==0 (
    python -c "import movil; movil.activar_tailscale()"
) else (
    py -c "import movil; movil.activar_tailscale()"
)
echo.
pause
