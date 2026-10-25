@echo off
setlocal
cd /d "%~dp0"
call scripts\run-app.cmd
exit /b %errorlevel%
