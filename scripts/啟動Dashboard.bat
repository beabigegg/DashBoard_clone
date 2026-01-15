@echo off
setlocal EnableDelayedExpansion

echo ========================================
echo  MES Dashboard Portal
echo ========================================
echo.

set "ROOT=%~dp0.."

REM Check for python.exe in different locations (standard venv or conda)
if exist "%ROOT%\venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%\venv\Scripts\python.exe"
) else if exist "%ROOT%\venv\python.exe" (
    set "PYTHON=%ROOT%\venv\python.exe"
) else (
    echo [ERROR] Virtual environment not found
    echo Please run initialization script first
    echo.
    pause
    exit /b 1
)

echo Starting server...
echo URL: http://localhost:5000
echo Press Ctrl+C to stop
echo.
echo ========================================
echo.

"%PYTHON%" "%ROOT%\apps\portal.py"

echo.
echo ========================================
echo Server stopped
pause
