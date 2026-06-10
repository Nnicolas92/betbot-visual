@echo off
echo Actualizando Playwright y descargando Chromium 127+...
py -m pip install playwright --upgrade --quiet
py -m playwright install chromium
py -m pip install playwright-stealth --quiet
echo.
echo Listo. Ahora corre CORRER.bat
pause
