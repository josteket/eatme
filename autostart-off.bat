@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo == Removing EAT ME autostart ==
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-autostart.ps1"
pause
