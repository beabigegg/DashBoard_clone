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

set "PYTHONPATH=%ROOT%\src"
set "WAITRESS=%ROOT%\venv\Scripts\waitress-serve.exe"

echo Starting server...
echo URL: http://localhost:8080
echo Press Ctrl+C to stop
echo.
echo ========================================
echo.

if exist "%WAITRESS%" (
    "%WAITRESS%" --listen=0.0.0.0:8080 mes_dashboard:create_app
) else (
    echo [WARN] waitress-serve not found, falling back to development server
    "%PYTHON%" -m mes_dashboard
)

echo.
echo ========================================
echo Server stopped
pause
