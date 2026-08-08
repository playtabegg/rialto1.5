@echo off
setlocal

:: ============================================================
::  Rialto - Game Disc Builder : debug launcher
::  Same environment as launch_rialto.bat, but runs Rialto with
::  a console attached so errors are visible.
:: ============================================================

echo [DEBUG] Starting Rialto in debug mode...

set "RIALTO_DIR=%~dp0"
set "RIALTO_DIR=%RIALTO_DIR:~0,-1%"
cd /d "%RIALTO_DIR%"

:: Legacy bundled environment on the dev machine (not in the repo)
if exist "%RIALTO_DIR%\python39\" (
    set "VENV_DIR=%RIALTO_DIR%\python39\venv"
    set "PY_BOOTSTRAP=python"
    if exist "%RIALTO_DIR%\python39\python.exe" set "PY_BOOTSTRAP=%RIALTO_DIR%\python39\python.exe"
    goto :have_python
)

set "VENV_DIR=%RIALTO_DIR%\venv"
set "PY_BOOTSTRAP=python"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Python was not found on your PATH.
    echo.
    echo   Rialto needs Python 3.9 or newer ^(64-bit^). 3.9 - 3.12 is the tested range.
    echo   Download it from: https://www.python.org/downloads/
    echo   Tick "Add python.exe to PATH" in the installer, then
    echo   open a new window and run this file again.
    echo.
    pause
    exit /b 1
)

:have_python

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [DEBUG] No virtual environment yet - creating "%VENV_DIR%"...
    "%PY_BOOTSTRAP%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo [ERROR] Could not create the virtual environment.
        echo.
        pause
        exit /b 1
    )
    if exist "%VENV_DIR%\rialto_deps_ok.txt" del /q "%VENV_DIR%\rialto_deps_ok.txt"
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo.
    echo [ERROR] "%VENV_DIR%\Scripts\python.exe" is missing.
    echo   Delete the "venv" folder and run launch_rialto.bat again.
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_DIR%\rialto_deps_ok.txt" (
    echo [DEBUG] Installing dependencies into the virtual environment...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%RIALTO_DIR%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo [ERROR] Installing the dependencies failed.
        echo   Check your internet connection, then try again. If a package
        echo   refuses to build, install Python 3.12, delete "venv", and retry.
        echo.
        pause
        exit /b 1
    )
    echo ok > "%VENV_DIR%\rialto_deps_ok.txt"
)

echo [DEBUG] Python: "%VENV_DIR%\Scripts\python.exe"
echo [DEBUG] Running Rialto with console output...
echo.

"%VENV_DIR%\Scripts\python.exe" "%RIALTO_DIR%\Rialto.pyw"

echo.
echo [DEBUG] Script ended. Check for errors above.
pause
endlocal
