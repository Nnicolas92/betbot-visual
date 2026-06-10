@echo off
title BETBOT SCANNER v3.0
echo ============================================================
echo  BETBOT SCANNER v3.0 - Surebets automaticos
echo  Betwarrior + Bookmaker.eu
echo ============================================================
echo.
echo  Leyendo credenciales de .env...
echo  Corriendo scanner cada 30 segundos...
echo  Ctrl+C para detener
echo.
python arb_scanner.py
pause
