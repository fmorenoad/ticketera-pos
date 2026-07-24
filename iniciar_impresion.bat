@echo off
cd /d "%~dp0"
echo Servicio de impresion ticketera-pos (http://127.0.0.1:5000)
echo No cierres esta ventana mientras el punto de venta este operando.

python --version >nul 2>&1
if not errorlevel 1 (
    python impresion-pos.py
) else (
    py -3 impresion-pos.py
)
pause
