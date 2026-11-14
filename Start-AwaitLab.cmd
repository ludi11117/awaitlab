@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "artifacts\sqlite-latest.html" goto open
python -m awaitlab demo --scenario sqlite --output artifacts/sqlite-latest.json
if errorlevel 1 goto failed
:open
start "" "%~dp0artifacts\sqlite-latest.html"
exit /b 0
:failed
echo Experiment failed. See the error above.
pause
exit /b 1
