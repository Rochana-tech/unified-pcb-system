@echo off
cd /d "%~dp0frontend"
echo Layer 1 UI starting at http://localhost:5173
python -m http.server 5173
