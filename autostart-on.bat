@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo == Installing EAT ME autostart ==
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-autostart.ps1"
echo.
echo If you see an error about access, right-click this file and Run as administrator.
pause
