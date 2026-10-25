@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Development environment not found.
    echo Double-click scripts\setup-dev.cmd first.
    goto :failed
)

".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto :failed

echo.
echo All tests passed.
pause
exit /b 0

:failed
echo.
echo Tests could not be completed. Review the message above.
pause
exit /b 1
