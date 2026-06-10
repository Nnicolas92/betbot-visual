@echo off
echo ========================================
echo  BETBOT — Instalacion completa
echo ========================================
pip install playwright playwright-stealth colorama requests opencv-python
python -m playwright install chromium
echo.
echo Listo. Ahora:
echo  1. Copiá .env.example como .env
echo  2. Completá tus credenciales en .env
echo  3. Doble click en CORRER.bat
pause
