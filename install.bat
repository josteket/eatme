@echo off
cd /d "%~dp0"
echo == EAT ME: install ==
where python >nul 2>nul
if errorlevel 1 goto NOPY
echo [1/3] Creating virtual environment...
python -m venv .venv
if errorlevel 1 goto ERR
echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto ERR
echo [3/3] Seeding database with recipes...
".venv\Scripts\python.exe" seed.py
if errorlevel 1 goto ERR
echo.
echo Done! Now run start-online.bat (for Telegram) or start.bat (local test).
pause
goto END
:NOPY
echo [!] Python not found. Install Python 3.11+ from python.org and check "Add to PATH".
pause
goto END
:ERR
echo.
echo [!] Something failed. See the messages above.
pause
goto END
:END
