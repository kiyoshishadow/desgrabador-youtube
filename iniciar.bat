@echo off
chcp 65001 >nul
title Desgrabador de YouTube
cd /d "%~dp0"

echo ==========================================
echo   Desgrabador de YouTube
echo ==========================================
echo.

REM Verificar que Python este instalado
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro Python en el sistema.
    echo.
    echo Descargalo desde: https://www.python.org/downloads/
    echo Y al instalarlo, marca la opcion "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/3] Verificando dependencias...
python -c "import flask, flask_cors, yt_dlp" >nul 2>nul
if errorlevel 1 (
    echo [2/3] Instalando dependencias, puede tardar unos segundos...
    pip install flask flask-cors yt-dlp
    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudieron instalar las dependencias.
        pause
        exit /b 1
    )
) else (
    echo [2/3] Dependencias ya instaladas.
)

echo [3/3] Iniciando el servidor...
echo.
echo Servidor disponible en: http://127.0.0.1:5000
echo Se abrira el navegador automaticamente.
echo Presiona Ctrl+C en esta ventana para detener el servidor.
echo.

start "" http://127.0.0.1:5000
python youtubesubs_app.py

pause
