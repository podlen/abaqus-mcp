@echo off
rem abaqus-mcp setup for native Windows: double-click this file, or type setup-windows in a
rem terminal in this folder. It runs setup-windows.ps1 (allowed under any execution policy).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
