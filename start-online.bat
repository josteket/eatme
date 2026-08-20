@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto NOVENV
if not exist "tools\cloudflared.exe" goto NOCF
echo == EAT ME ONLINE (Telegram-ready) ==
echo Starting tunnel + server + bot...
echo Wait for the "GOTOVO" line with a public URL, then press /start in the bot.
echo Stop: Ctrl+C
echo.
".venv\Scripts\python.exe" run_public.py
echo.
echo === Stopped. ===
pause
goto END
:NOVENV
echo [!] Run install.bat first
pause
goto END
:NOCF
echo [!] tools\cloudflared.exe not found. See README (Tunnel section).
pause
goto END
:END
