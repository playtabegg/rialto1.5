@echo off
powershell -Command "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force"

:: Get the directory where this batch file lives
set "RIALTO_DIR=%~dp0"
set "RIALTO_DIR=%RIALTO_DIR:~0,-1%"

:: Change to Python 3.9 environment directory
cd /d "%RIALTO_DIR%\python39"

:: Optional cleanup of old temp folders in site-packages
echo [Cleanup] Cleaning up any old temp folders...
for /d %%G in ("venv\Lib\site-packages\~*") do rd /s /q "%%G"
for %%F in ("venv\Lib\site-packages\*.tmp") do del /q "%%F"

:: Create virtual environment if not found
if not exist venv (
    echo [Setup] No virtual environment found. Creating now...
    python.exe -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Upgrade pip
echo [Update] Upgrading pip...
venv\Scripts\python.exe -m pip install --upgrade pip

:: Install all required packages from requirements.txt
echo [Install] Installing/updating all dependencies...
venv\Scripts\python.exe -m pip install -r "%RIALTO_DIR%\requirements.txt"

:: Launch Rialto from project root
cd /d "%RIALTO_DIR%"
echo [Launch] Launching Rialto...
start "" "%RIALTO_DIR%\python39\venv\Scripts\pythonw.exe" "%RIALTO_DIR%\Rialto.pyw"

exit
