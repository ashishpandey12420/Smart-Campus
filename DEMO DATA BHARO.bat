@echo off
title Smart Campus - demo data
cd /d "%~dp0"
echo.
echo   Demo data bhar rahe hain (2000 students, 60 faculty, 24 din attendance)...
echo   Pehle app band honi chahiye (black window me Ctrl+C).
echo.
"%~dp0python\python.exe" -m backend.seed --students 2000 --faculty 60 --attendance-days 24
echo.
echo   Ho gaya. Ab START SMART CAMPUS.bat par double-click karo.
pause
