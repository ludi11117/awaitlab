@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "artifacts\parallel-latest.html" goto open
python -m awaitlab demo --scenario parallel --output artifacts/parallel-latest.json
if errorlevel 1 goto failed
:open
start "" "%~dp0artifacts\parallel-latest.html"
exit /b 0
:failed
echo Experiment failed. See the error above.
pause
exit /b 1
