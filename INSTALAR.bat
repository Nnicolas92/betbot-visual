@echo off
echo ============================================
echo  BETBOT VISUAL - Instalacion automatica
echo ============================================
echo.
py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado.
    echo Descargalo de https://python.org/downloads
    echo IMPORTANTE: marcar "Add Python to PATH"
    pause
    exit /b 1
)
echo [1/3] Instalando librerias...
py -m pip install requests playwright colorama python-dotenv --quiet
if errorlevel 1 goto error
echo [2/3] Descargando Chromium ~150MB...
py -m playwright install chromium
if errorlevel 1 goto error
echo.
echo [3/3] Listo! Ahora doble click en CORRER.bat
echo ============================================
pause
exit /b 0
:error
echo ERROR. Revisa el mensaje arriba.
pause
