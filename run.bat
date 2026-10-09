@echo off
title Academic Management System - Server
cls
echo ========================================================
echo    Academic Management System (AMS) - Startup Script
echo ========================================================
echo.
echo [1] LOCAL ACCESS (This Computer):
echo     http://127.0.0.1:5000
echo.
echo [2] MOBILE/REMOTE ACCESS (Same Wi-Fi):
echo     Finding your local IP address...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4 Address"') do (
    set IP=%%a
)
set IP=%IP: =%
echo     http://%IP%:5000
echo.
echo ========================================================
echo Starting the server... Please wait.
echo ========================================================
echo.
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to start the server. 
    echo Make sure Python is installed and dependencies are met.
    pause
)
pause
