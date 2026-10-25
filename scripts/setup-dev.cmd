@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -m venv .venv
    ) else (
        where py >nul 2>nul
        if errorlevel 1 (
            echo Python was not found. Install Python 3.10 or newer and try again.
            goto :failed
        )
        py -3 -m venv .venv
    )

    if errorlevel 1 (
        echo Failed to create the development environment.
        goto :failed
    )
)

echo Development environment is ready.
echo Running tests...
call scripts\test.cmd
exit /b %errorlevel%

:failed
echo.
pause
exit /b 1
