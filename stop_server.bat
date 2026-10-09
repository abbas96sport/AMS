@echo off
title Stop Academic Management System
echo ========================================================
echo    Stopping the Server...
echo ========================================================
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1
echo Done. The server has been stopped.
pause
