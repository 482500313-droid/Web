@echo off
title Deteniendo servidor...
color 0C
echo.
echo  ============================================
echo    La Loncheria - Deteniendo servidor...
echo  ============================================
echo.

taskkill /F /IM python.exe    /T >nul 2>&1
taskkill /F /IM python3.13.exe /T >nul 2>&1
taskkill /F /IM py.exe         /T >nul 2>&1

echo  Servidor detenido.
echo.
ping -n 3 127.0.0.1 >nul
