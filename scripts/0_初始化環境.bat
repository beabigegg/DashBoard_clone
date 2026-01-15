@echo off
setlocal EnableDelayedExpansion

echo ========================================
echo  Initialize MES Dashboard Environment
echo ========================================
echo.

set "ROOT=%~dp0.."

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    echo Please install Python 3.11+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Checking virtual environment...
if exist "%ROOT%\venv\Scripts\python.exe" (
    echo [OK] Virtual environment exists
) else (
    echo Creating virtual environment...
    python -m venv "%ROOT%\venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

echo.
echo [2/3] Installing dependencies...
"%ROOT%\venv\Scripts\pip.exe" install -r "%ROOT%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [3/3] Verifying packages...
"%ROOT%\venv\Scripts\python.exe" -c "import oracledb; print('[OK] oracledb installed')"
"%ROOT%\venv\Scripts\python.exe" -c "import flask; print('[OK] Flask installed')"
"%ROOT%\venv\Scripts\python.exe" -c "import pandas; print('[OK] Pandas installed')"

echo.
echo ========================================
echo  Initialization Complete!
echo ========================================
echo.
echo Run "scripts\啟動Dashboard.bat" to start server
echo.
pause
