@echo off
title INSTALADOR BETBOT v3.0
echo ============================================================
echo  INSTALADOR COMPLETO BETBOT v3.0
echo ============================================================
echo.
echo PASO 1: Descargando Python 3.11...
curl -L -o python_installer.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
if errorlevel 1 (
    echo.
    echo ERROR al descargar Python. Hacelo manualmente:
    echo   1. Ir a https://www.python.org/downloads/
    echo   2. Descargar Python 3.11
    echo   3. Instalar CON el tick en ADD PYTHON TO PATH
    pause
    exit
)
echo.
echo PASO 2: Instalando Python silencioso...
python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
timeout /t 25 /nobreak > nul
echo.
echo PASO 3: Verificando Python...
python --version
if errorlevel 1 (
    echo ERROR: Python no encontrado. Reinicia CMD e intenta de nuevo.
    pause
    exit
)
echo.
echo PASO 4: Instalando dependencias...
pip install playwright python-dotenv opencv-python
echo.
echo PASO 5: Descargando navegador Chromium...
python -m playwright install chromium
echo.
mkdir sesiones 2>nul
mkdir screenshots 2>nul
echo.
echo ============================================================
echo  INSTALACION COMPLETA!
echo.
echo  PROXIMOS PASOS:
echo  1. Copia .env.example a .env
echo  2. Abre .env con Bloc de Notas y completa tus datos
echo  3. Corre SCANNER.bat
echo ============================================================
pause
