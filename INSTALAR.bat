@echo off
echo ========================================
echo  BETBOT v2.0 - INSTALADOR
echo ========================================
echo.
echo [1/3] Instalando dependencias Python...
pip install playwright python-dotenv opencv-python
echo.
echo [2/3] Instalando navegador Chromium...
python -m playwright install chromium
echo.
echo [3/3] Creando carpetas...
mkdir sesiones 2>nul
mkdir screenshots 2>nul
echo.
echo INSTALACION COMPLETA!
echo Siguiente: GRABAR_BETWARRIOR.bat
pause
