@echo off
title La Loncheria - Servidor
color 0A
cd /d "%~dp0"

echo.
echo  ============================================
echo    La Loncheria - Iniciando servidor...
echo  ============================================
echo.
echo  Direccion: http://127.0.0.1:5000
echo  Para detener: cierra esta ventana o Ctrl+C
echo.

:: Intentar con "python", si falla con "py"
python --version >nul 2>&1
if %errorlevel% == 0 (
    python app.py
) else (
    py --version >nul 2>&1
    if %errorlevel% == 0 (
        py app.py
    ) else (
        echo  ERROR: Python no encontrado en el sistema.
        echo  Instala Python desde https://python.org
    )
)

echo.
echo  El servidor se detuvo.
pause
