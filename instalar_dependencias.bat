@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Instalador de dependencias - ticketera-pos
echo ============================================
echo.

REM Preferir el py launcher (evita el stub de la Microsoft Store, que deja
REM win32ui roto). Solo si no existe se usa "python".
set "PYCMD=py -3"
%PYCMD% --version >nul 2>&1
if errorlevel 1 set "PYCMD=python"
%PYCMD% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo Descargalo desde https://www.python.org/downloads/
    echo y marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
echo Interprete: %PYCMD%

echo [1/3] Actualizando pip...
%PYCMD% -m pip install --upgrade pip

echo [2/3] Instalando dependencias desde requirements.txt...
%PYCMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo [3/3] Configurando pywin32 (copia las DLLs que necesita win32ui)...
for /f "delims=" %%P in ('%PYCMD% -c "import os,sys;print(os.path.dirname(sys.executable))"') do set "PYDIR=%%P"
if exist "%PYDIR%\Scripts\pywin32_postinstall.py" %PYCMD% "%PYDIR%\Scripts\pywin32_postinstall.py" -install

echo Verificando win32ui...
%PYCMD% -c "import win32print, win32ui, flask, flask_cors, qrcode, PIL" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Las dependencias no quedaron operativas (win32ui).
    echo Si persiste, instala "Microsoft Visual C++ 2015-2022 Redistributable (x64)".
    pause
    exit /b 1
)

echo.
echo [OK] Instalacion completada. El entorno esta listo.
echo Ejecuta iniciar_impresion.bat para levantar el servicio de impresion.
pause
