@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
python -m awaitlab demo --scenario parallel --output artifacts/parallel-latest.json
if errorlevel 1 goto failed
python -m awaitlab demo --scenario pool --output artifacts/pool-latest.json
if errorlevel 1 goto failed
start "" "%~dp0artifacts\parallel-latest.html"
exit /b 0
:failed
echo Experiment failed. Existing reports have been retained.
pause
exit /b 1
