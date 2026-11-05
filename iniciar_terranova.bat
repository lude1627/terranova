@echo off
cd /d "%~dp0"
py -3 -m backend.main
if errorlevel 1 (
    echo.
    echo No se pudo iniciar Terranova. Verifica que Python 3 este instalado y disponible con el comando py.
    pause
)
