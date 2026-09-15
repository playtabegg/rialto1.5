@echo off
setlocal
:: Rialto 1.5 portable launcher.
:: You usually don't need this file: double-click Rialto.pyw instead
:: (Rialto installs its own dependencies on first run), then use
:: File > Put Rialto on the Desktop inside the app to launch it like a normal app.
cd /d "%~dp0"

:: cmd looks in the current directory before it looks at PATH, and the current
:: directory is now the Rialto folder - the same folder people unpack downloads
:: into. A python.exe sitting there would be run in preference to the real one,
:: so say so rather than run it.
if exist "%~dp0python.exe" goto :local_python
if exist "%~dp0pythonw.exe" goto :local_python
goto :no_local_python
:local_python
echo.
echo [ERROR] There is a python.exe in the Rialto folder.
echo   Windows would run that one instead of your installed Python.
echo   Move or delete it, then run this file again.
echo.
pause
exit /b 1
:no_local_python

:: `where python` is not enough on its own. A clean Windows 10/11 ships an
:: App Execution Alias at %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe;
:: `where` finds it and reports success, but it is only a Store placeholder
:: that cannot run anything. Actually running Python is the reliable test.
python -c "import sys" >nul 2>nul
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
    echo   If you just saw a message about the Microsoft Store, or about
    echo   "App execution aliases", that placeholder is all you have -
    echo   install the real Python from the link above.
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0Rialto.pyw" (
    echo.
    echo [ERROR] Rialto.pyw was not found next to this launcher.
    echo   Run this file from inside the Rialto folder.
    echo.
    pause
    exit /b 1
)

:: Ask the Python we just proved works where its own pythonw.exe is, rather
:: than trusting whatever `pythonw` happens to resolve to on PATH - that name
:: has the same Store-placeholder problem. pythonw.exe launches Rialto with no
:: console window; if this Python somehow has none, fall back to python.exe so
:: the launch is noisy rather than silent.
set "RIALTO_PYW="
for /f "usebackq delims=" %%P in (`python -c "import os,sys;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"`) do set "RIALTO_PYW=%%P"

if defined RIALTO_PYW if exist "%RIALTO_PYW%" (
    start "" "%RIALTO_PYW%" "%~dp0Rialto.pyw"
    endlocal
    exit /b 0
)

echo [Launch] pythonw.exe is missing - starting Rialto with a console window.
start "" python "%~dp0Rialto.pyw"
endlocal
exit /b 0
