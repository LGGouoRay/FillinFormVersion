@echo off
setlocal
title FillinForm - NTUST Peer Review Tool
cd /d "%~dp0"

echo =========================================================================
echo   FillinForm - NTUST Peer Review Synchronizer
echo =========================================================================
echo.

set PYTHON_CMD=python

if exist "%~dp0..\..\.venv\Scripts\python.exe" (
    set PYTHON_CMD=%~dp0..\..\.venv\Scripts\python.exe
    goto CHECK_ENV
)

if exist "%~dp0..\.venv\Scripts\python.exe" (
    set PYTHON_CMD=%~dp0..\.venv\Scripts\python.exe
    goto CHECK_ENV
)

if exist "%~dp0.venv\Scripts\python.exe" (
    set PYTHON_CMD=%~dp0.venv\Scripts\python.exe
    goto CHECK_ENV
)

echo [SETUP] Initializing virtual environment (.venv)...
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv >nul 2>&1
)
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Failed to create virtual environment! Please install Python 3.10+.
    pause
    exit /b 1
)

set PYTHON_CMD=%~dp0.venv\Scripts\python.exe

:CHECK_ENV
echo [1/2] Checking dependencies...
"%PYTHON_CMD%" -c "import fastapi, uvicorn, requests, playwright" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing required packages...
    "%PYTHON_CMD%" -m pip install --upgrade pip
    "%PYTHON_CMD%" -m pip install -r requirements.txt
)

:LAUNCH
echo [2/2] Starting FillinForm Launcher...
"%PYTHON_CMD%" --version
if errorlevel 1 (
    echo [ERROR] Python execution failed!
    pause
    exit /b 1
)

echo Dashboard URL: http://127.0.0.1:8000
echo.

"%PYTHON_CMD%" launcher.py
pause