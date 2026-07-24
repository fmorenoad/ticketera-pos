@echo off
setlocal
cd /d "%~dp0"
title Instalador Ticketera POS

echo =================================================
echo    Instalador del punto de impresion - Ticketera
echo =================================================
echo.

:: ---------- 1) Python ----------
call :buscar_python
if defined PYTHON (
    echo [1/3] Python encontrado.
    goto :dependencias
)

echo [1/3] Python no esta instalado. Instalando automaticamente...
where winget >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Este Windows no tiene winget para instalar Python solo.
    echo         Instala Python manualmente desde:
    echo         https://www.python.org/downloads/
    echo         IMPORTANTE: marcar "Add Python to PATH" al instalar,
    echo         y luego vuelve a ejecutar este instalador.
    pause
    exit /b 1
)

winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements

:: La sesion actual no ve el PATH nuevo: agregar rutas tipicas
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"

call :buscar_python
if not defined PYTHON (
    echo.
    echo [AVISO] Python quedo instalado pero esta ventana aun no lo ve.
    echo         Cierra esta ventana y ejecuta instalar.bat OTRA VEZ.
    pause
    exit /b 1
)
echo        Python instalado correctamente.

:: ---------- 2) Dependencias ----------
:dependencias
echo [2/3] Verificando dependencias...
%PYTHON% -c "import flask, flask_cors, qrcode, win32print, win32ui, PIL" >nul 2>&1
if not errorlevel 1 (
    echo        Dependencias OK.
    goto :listo
)

echo        Instalando dependencias (puede tardar unos minutos)...
%PYTHON% -m pip install --upgrade pip
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias. Revisa la conexion a internet.
    pause
    exit /b 1
)

%PYTHON% -c "import flask, flask_cors, qrcode, win32print, win32ui, PIL" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Las dependencias no quedaron operativas. Contacta a soporte.
    pause
    exit /b 1
)

:: ---------- 3) Listo ----------
:listo
echo [3/3] Verificacion completa.
echo.
echo =================================================
echo    YA ESTA TODO LISTO. Abriendo el kiosko...
echo =================================================
if not exist impresora.txt (
    echo.
    echo [RECUERDA] Aun no existe impresora.txt: se usara la impresora
    echo            predeterminada de Windows. Para fijar la termica,
    echo            crea impresora.txt con su nombre exacto.
)
timeout /t 3 /nobreak >nul
start "" "%~dp0abrir_kiosko.bat"
exit /b 0

:: ---------- Funciones ----------
:buscar_python
set "PYTHON="
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python"
    goto :eof
)
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"
goto :eof
