@echo off
setlocal
title PCB Assembly - Setup and Run
pushd "%~dp0"
if errorlevel 1 goto folder_error

if not exist "main.py" goto files_missing
if not exist "requirements.txt" goto files_missing
if not exist "requirements.lock.txt" goto files_missing

echo.
echo [1/5] Checking Python virtual environment...
if exist ".venv\Scripts\python.exe" goto check_venv

py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if not errorlevel 1 goto create_with_py

python -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if not errorlevel 1 goto create_with_python

if not exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" goto python_missing
"%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if errorlevel 1 goto python_missing
"%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv ".venv"
if errorlevel 1 goto venv_error
goto check_venv

:create_with_py
py -3.12 -m venv ".venv"
if errorlevel 1 goto venv_error
goto check_venv

:create_with_python
python -m venv ".venv"
if errorlevel 1 goto venv_error

:check_venv
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if errorlevel 1 goto incompatible_venv

echo.
echo [2/5] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto venv_error

echo.
echo [3/5] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto install_error

echo.
echo [4/5] Installing project requirements...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 goto install_error

echo.
echo [5/5] Starting the dashboard...
echo Open http://127.0.0.1:8002 in your browser.
echo Keep this window open. Press Ctrl+C to stop the server.
echo If port 8002 is already occupied, stop the previous server first.
echo.
".venv\Scripts\python.exe" "main.py" --host 127.0.0.1 --port 8002
if errorlevel 1 goto server_error
popd
endlocal
exit /b 0

:files_missing
echo ERROR: Keep this BAT file beside main.py, requirements.txt and requirements.lock.txt.
goto failed

:python_missing
echo ERROR: Python 3.12 was not found.
echo Install Python 3.12, enable the Python launcher or Add Python to PATH,
echo then close this window and run this file again.
goto failed

:incompatible_venv
echo ERROR: The existing .venv is unavailable or does not use Python 3.12.
echo Rename that .venv folder to keep a backup, then run this file again.
goto failed

:venv_error
echo ERROR: Could not create or activate the virtual environment.
goto failed

:install_error
echo ERROR: Installation failed. Check your internet connection and the error above.
goto failed

:server_error
echo ERROR: The server stopped. Review the message above.
goto failed

:folder_error
echo ERROR: Could not open the project folder.
pause
endlocal
exit /b 1

:failed
echo.
pause
popd
endlocal
exit /b 1

