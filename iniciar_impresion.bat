@echo off
cd /d "%~dp0"
echo Servicio de impresion ticketera-pos (http://127.0.0.1:5000)
echo No cierres esta ventana mientras el punto de venta este operando.

REM Preferir el py launcher: evita el stub de la Microsoft Store, que
REM rompe "import win32ui" (ImportError: DLL load failed). Solo si no
REM existe el launcher se cae a "python".
py -3 --version >nul 2>&1
if not errorlevel 1 (
    py -3 impresion-pos.py
) else (
    python impresion-pos.py
)
pause
