@echo off
title Layer 2A Simple UI
cd /d "%~dp0frontend"
echo.
echo ==========================================
echo   Layer 2A - ANN Fault Detection UI
echo ==========================================
echo.
echo Open: http://localhost:5174
echo Press Ctrl+C to stop the UI.
echo.
py -m http.server 5174
if errorlevel 1 python -m http.server 5174
pause
