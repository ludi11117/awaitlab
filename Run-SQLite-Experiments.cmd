@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set TEMP=D:\CodexWork\temp\awaitlab
set TMP=%TEMP%
if not exist "%TEMP%" mkdir "%TEMP%"
python -m awaitlab demo --scenario sqlite --output artifacts/sqlite-latest.json
if errorlevel 1 goto failed
start "" "%~dp0artifacts\sqlite-latest.html"
exit /b 0
:failed
echo Experiment failed. The previous complete report has not been replaced.
pause
exit /b 1
