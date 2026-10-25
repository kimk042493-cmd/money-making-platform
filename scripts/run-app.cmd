@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Development environment not found.
    echo Double-click scripts\setup-dev.cmd first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m src.app
pause
