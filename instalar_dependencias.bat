@echo off
echo 🚀 Instalando dependencias necesarias para la impresión...

:: Reinstalar pywin32
echo 🔹 Instalando pywin32...
pip install --force-reinstall pywin32

:: Instalar qrcode con soporte para PIL
echo 🔹 Instalando qrcode...
pip install qrcode[pil]

:: Instalar Flask
echo 🔹 Instalando Flask...
pip install flask

:: Instalar Flask-CORS
echo 🔹 Instalando Flask-CORS...
pip install flask-cors

echo ✅ Instalación completada. ¡Tu entorno está listo!
pause
