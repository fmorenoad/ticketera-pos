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

echo        Configurando pywin32 (copia las DLLs que necesita win32ui)...
for /f "delims=" %%P in ('%PYTHON% -c "import os,sys;print(os.path.dirname(sys.executable))"') do set "PYDIR=%%P"
if exist "%PYDIR%\Scripts\pywin32_postinstall.py" %PYTHON% "%PYDIR%\Scripts\pywin32_postinstall.py" -install

%PYTHON% -c "import flask, flask_cors, qrcode, win32print, win32ui, PIL" >nul 2>&1
if not errorlevel 1 goto :listo

echo        win32ui aun no carga: falta el runtime de Visual C++. Instalandolo...
call :instalar_vcredist

echo        Reintentando win32ui...
%PYTHON% -c "import win32print, win32ui" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] win32ui sigue sin cargar tras instalar el runtime de Visual C++.
    echo         Reinicia el equipo y ejecuta instalar.bat otra vez.
    pause
    exit /b 1
)
echo        win32ui OK tras instalar el runtime.

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
REM Preferir el py launcher: evita el stub de la Microsoft Store, que
REM deja "import win32ui" roto (ImportError: DLL load failed).
set "PYTHON="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
    goto :eof
)
python --version >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
goto :eof

:instalar_vcredist
REM Descarga e instala el Microsoft Visual C++ 2015-2022 Redistributable (x64),
REM que aporta las DLLs (vcruntime140 / mfc140u) de las que depende win32ui.
set "VCEXE=%TEMP%\vc_redist.x64.exe"
echo        Descargando Visual C++ Redistributable (x64)...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%VCEXE%' -UseBasicParsing" 2>nul
if not exist "%VCEXE%" (
    echo [ERROR] No se pudo descargar el runtime de Visual C++. Revisa la conexion a internet.
    goto :eof
)
echo        Instalando (silencioso; puede pedir permisos de administrador)...
"%VCEXE%" /install /quiet /norestart
del /q "%VCEXE%" >nul 2>&1
goto :eof
