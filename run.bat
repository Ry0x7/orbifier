@echo off
rem Orbifier launcher: sets up a local .venv on first run, then starts the app.
rem   run.bat          open the GUI
rem   run.bat --cli    classic console menu
setlocal
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3 was not found. Install it from https://www.python.org/downloads/
    goto :fail
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    %PY% -m venv .venv || goto :fail
)

if not exist ".venv\.deps-installed" (
    echo Installing dependencies ...
    ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto :fail
    type nul > ".venv\.deps-installed"
)

".venv\Scripts\python.exe" orbifier.py %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [ERROR] Orbifier exited with an error.
pause
exit /b 1
