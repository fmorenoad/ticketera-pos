@echo off
REM Levantar el servicio de impresion (misma carpeta que este script)
start "" "%~dp0iniciar_impresion.bat"

REM Esperar a que el servicio arranque
timeout /t 2 /nobreak >nul

REM Abrir Chrome en modo kiosko
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --disable-translate "https://ticketera.iwan.cl"
) else (
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --kiosk --disable-translate "https://ticketera.iwan.cl"
)
