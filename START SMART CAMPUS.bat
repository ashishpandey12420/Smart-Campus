@echo off
title Smart Campus - Student & Faculty Management System
cd /d "%~dp0"
echo.
echo   SMART CAMPUS - Student ^& Faculty Management System
echo   -------------------------------------------------
echo   App start ho rahi hai...
echo   Browser khud khul jayega (http://127.0.0.1:8080).
echo.
echo   Login:  admin  /  Admin@12345
echo.
echo   IS WINDOW KO BAND MAT KARNA - yahi app chal rahi hai.
echo   Band karna ho to isi window me Ctrl+C dabao.
echo.
"%~dp0python\python.exe" "%~dp0run.py" --port 8080
echo.
echo   App band ho gayi. Dobara chalane ke liye isi file par double-click karo.
pause
