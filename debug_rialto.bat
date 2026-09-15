@echo off
:: Rialto 1.5 debug launcher.
:: Same as launch_rialto.bat, but keeps a console attached so errors
:: are visible. Rialto installs its own dependencies on first run.
cd /d "%~dp0"

:: cmd looks in the current directory before PATH, so a python.exe dropped into
:: the Rialto folder would win over the real one. Same guard as launch_rialto.
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
    echo   Install Python 3.9+ from https://www.python.org/downloads/
    echo   and tick "Add python.exe to PATH" during setup, then open a
    echo   new window and run this file again.
    echo.
    echo   If you just saw a message about the Microsoft Store, or about
    echo   "App execution aliases", that placeholder is all you have -
    echo   install the real Python from the link above.
    echo.
    pause
    exit /b 1
)

echo [DEBUG] Running Rialto with console output...
echo.

python "%~dp0Rialto.pyw"

echo.
echo [DEBUG] Script ended. Check for errors above.
pause
