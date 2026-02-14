@echo off
echo [DEBUG] Starting Rialto Debug Mode...

:: Get the directory where this batch file lives
set "RIALTO_DIR=%~dp0"
set "RIALTO_DIR=%RIALTO_DIR:~0,-1%"

cd /d "%RIALTO_DIR%\python39"

if not exist venv (
    echo [ERROR] Virtual environment not found!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

cd /d "%RIALTO_DIR%"

echo [DEBUG] Running Rialto with console output...
echo.

REM Use python.exe instead of pythonw.exe to see errors
"%RIALTO_DIR%\python39\venv\Scripts\python.exe" "%RIALTO_DIR%\Rialto.pyw"

echo.
echo [DEBUG] Script ended. Check for errors above.
pause
