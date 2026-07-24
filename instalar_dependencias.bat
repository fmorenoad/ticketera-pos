@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Instalador de dependencias - ticketera-pos
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo Descargalo desde https://www.python.org/downloads/
    echo y marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

echo [1/2] Actualizando pip...
python -m pip install --upgrade pip

echo [2/2] Instalando dependencias desde requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo.
echo [OK] Instalacion completada. El entorno esta listo.
echo Ejecuta iniciar_impresion.bat para levantar el servicio de impresion.
pause
