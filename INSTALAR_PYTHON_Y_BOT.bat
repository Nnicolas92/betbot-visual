@echo off
echo ========================================
echo  PASO 1: Descargando Python 3.11...
echo ========================================
curl -L -o python_installer.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
echo.
echo ========================================
echo  PASO 2: Instalando Python...
echo ========================================
python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
echo.
echo Esperando instalacion...
timeout /t 30 /nobreak
echo.
echo ========================================
echo  PASO 3: Verificando...
echo ========================================
python --version
pip --version
echo.
echo ========================================
echo  PASO 4: Instalando dependencias del bot
echo ========================================
pip install playwright python-dotenv opencv-python
python -m playwright install chromium
echo.
mkdir sesiones 2>nul
mkdir screenshots 2>nul
echo.
echo ========================================
echo  LISTO! Ahora corra: GRABAR_BETWARRIOR.bat
echo ========================================
pause
