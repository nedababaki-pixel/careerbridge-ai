@echo off
rem Start CareerBridge AI locally on Windows (double-click this file).
rem Needs Python and the packages from requirements.txt, and a .env file with GEMINI_API_KEY.
cd /d "%~dp0"
if not exist ".env" (
  echo No .env file found. Copy .env.example to .env and add your Gemini API key first.
  pause
  exit /b 1
)
start "CareerBridge AI server - close this window to stop" cmd /k python app.py
echo Starting CareerBridge AI...
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:5055
