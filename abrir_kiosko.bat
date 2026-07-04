@echo off
REM Ejecutar un archivo antes de abrir el navegador
start "" "C:\ticketera-pos\iniciar_impresion.bat"
REM Esperar unos segundos para que el archivo se ejecute
timeout /t 2 /nobreak >nul
REM Abrir Chrome en modo kiosko
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --disable-translate "https://ticketera.iwan.cl"
