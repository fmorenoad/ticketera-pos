@echo off
cd /d "%~dp0"
echo Servicio de impresion ticketera-pos (http://127.0.0.1:5000)
echo Impresora en uso: la predeterminada de Windows.
echo No cierres esta ventana mientras el punto de venta este operando.
python impresion-pos.py
pause
