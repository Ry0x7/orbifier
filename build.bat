@echo off
rem Builds dist\orbifier.exe with PyInstaller using orbifier.spec.
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

echo Installing PyInstaller ...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check pyinstaller || goto :fail

echo Building ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm orbifier.spec || goto :fail

if not exist "dist\orbifier.exe" (
    echo [ERROR] Build finished but dist\orbifier.exe was not found.
    goto :fail
)

echo.
echo Build complete: %CD%\dist\orbifier.exe
exit /b 0

:fail
echo.
echo [ERROR] Build failed.
pause
exit /b 1
