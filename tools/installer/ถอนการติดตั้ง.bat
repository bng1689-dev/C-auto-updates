@echo off
chcp 65001 >nul
title CRIMES AUTO - Uninstall
cd /d "%TEMP%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall.ps1" %*
if errorlevel 1 (
  echo.
  echo [X] Uninstall failed - see messages above
  pause
)
