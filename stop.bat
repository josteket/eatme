@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo == Stopping EAT ME ==
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo Note: a manually opened start-online window must be closed by hand.
pause
