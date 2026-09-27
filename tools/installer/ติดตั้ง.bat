@echo off
chcp 65001 >nul
set "VER="
if exist "%~dp0app\VERSION" set /p VER=<"%~dp0app\VERSION"
if defined VER (title CRIMES AUTO - Install v%VER%) else (title CRIMES AUTO - Install)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" %*
if errorlevel 1 (
  echo.
  echo [X] Install failed - see messages above
  pause
)
