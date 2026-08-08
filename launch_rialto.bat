@echo off
setlocal

:: ============================================================
::  Rialto - Game Disc Builder : launcher
::  Creates (once) a virtual environment next to this file,
::  installs the dependencies, then launches Rialto.
:: ============================================================

:: Directory this batch file lives in (no trailing backslash)
set "RIALTO_DIR=%~dp0"
set "RIALTO_DIR=%RIALTO_DIR:~0,-1%"
cd /d "%RIALTO_DIR%"

:: ------------------------------------------------------------
:: Legacy layout: a bundled python39\ folder on the dev machine.
:: This folder is NOT part of the repository, so clones skip it.
:: ------------------------------------------------------------
if exist "%RIALTO_DIR%\python39\" (
    echo [Setup] Using bundled Python environment in python39\
    set "VENV_DIR=%RIALTO_DIR%\python39\venv"
    set "PY_BOOTSTRAP=python"
    if exist "%RIALTO_DIR%\python39\python.exe" set "PY_BOOTSTRAP=%RIALTO_DIR%\python39\python.exe"
    pushd "%RIALTO_DIR%\python39"
    echo [Cleanup] Removing any old temp folders...
    for /d %%G in ("venv\Lib\site-packages\~*") do rd /s /q "%%G" 2>nul
    for %%F in ("venv\Lib\site-packages\*.tmp") do del /q "%%F" 2>nul
    popd
    goto :have_python
)

:: ------------------------------------------------------------
:: Normal layout (any clone): use the system Python.
:: ------------------------------------------------------------
set "VENV_DIR=%RIALTO_DIR%\venv"
set "PY_BOOTSTRAP=python"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Python was not found on your PATH.
    echo.
    echo   Rialto needs Python 3.9 or newer ^(64-bit^). 3.9 - 3.12 is the tested range.
    echo   Download it from: https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: on the first page of the installer, tick
    echo   "Add python.exe to PATH" before clicking Install.
    echo   Then close this window, open a NEW one, and run this file again.
    echo.
    pause
    exit /b 1
)

:have_python

:: ------------------------------------------------------------
:: Create the virtual environment if it isn't there yet
:: ------------------------------------------------------------
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [Setup] Creating virtual environment in "%VENV_DIR%"...
    "%PY_BOOTSTRAP%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo [ERROR] Could not create the virtual environment.
        echo   Check that your Python install includes the "venv" module,
        echo   and that you have write permission to this folder.
        echo.
        pause
        exit /b 1
    )
    :: Force a dependency install for the brand new environment
    if exist "%VENV_DIR%\rialto_deps_ok.txt" del /q "%VENV_DIR%\rialto_deps_ok.txt"
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo.
    echo [ERROR] The virtual environment looks incomplete:
    echo   "%VENV_DIR%\Scripts\python.exe" is missing.
    echo   Delete the "venv" folder and run this file again.
    echo.
    pause
    exit /b 1
)

:: ------------------------------------------------------------
:: Install dependencies only on first run (or if the marker is gone)
:: ------------------------------------------------------------
if not exist "%VENV_DIR%\rialto_deps_ok.txt" (
    echo [Setup] First run - installing dependencies. This takes a minute...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%RIALTO_DIR%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo [ERROR] Installing the dependencies failed.
        echo   Check your internet connection, then try again.
        echo   If a package refuses to build for your Python version,
        echo   install Python 3.12 ^(the newest tested release^),
        echo   delete the "venv" folder, and run this file again.
        echo.
        pause
        exit /b 1
    )
    echo ok > "%VENV_DIR%\rialto_deps_ok.txt"
    echo [Setup] Dependencies installed.
) else (
    echo [Setup] Dependencies already installed - skipping.
    echo         ^(Delete "%VENV_DIR%\rialto_deps_ok.txt" to reinstall.^)
)

:: ------------------------------------------------------------
:: Launch
:: ------------------------------------------------------------
if not exist "%RIALTO_DIR%\Rialto.pyw" (
    echo.
    echo [ERROR] Rialto.pyw was not found next to this launcher.
    echo   Run this file from inside the Rialto folder.
    echo.
    pause
    exit /b 1
)

:: pythonw.exe launches without a console window. If the environment somehow
:: has no pythonw.exe, fall back to python.exe rather than failing silently.
if exist "%VENV_DIR%\Scripts\pythonw.exe" (
    echo [Launch] Starting Rialto...
    start "" "%VENV_DIR%\Scripts\pythonw.exe" "%RIALTO_DIR%\Rialto.pyw"
) else (
    echo [Launch] pythonw.exe is missing - starting Rialto with a console window.
    start "" "%VENV_DIR%\Scripts\python.exe" "%RIALTO_DIR%\Rialto.pyw"
)

endlocal
exit /b 0
