@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto NOVENV
echo == EAT ME (local only) ==
echo Web: http://localhost:8080
echo Stop: Ctrl+C
echo.
".venv\Scripts\python.exe" run.py
echo.
echo === Stopped. ===
pause
goto END
:NOVENV
echo [!] Run install.bat first
pause
goto END
:END
