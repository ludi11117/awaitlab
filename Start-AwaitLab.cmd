@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 exit /b 1
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "TEMP=D:\CodexWork\temp\awaitlab"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
if errorlevel 1 goto failed
if exist "artifacts\sqlite-latest.html" goto open
python -m awaitlab demo --scenario sqlite --output artifacts/sqlite-latest.json
if errorlevel 1 goto failed
:open
start "" "%~dp0artifacts\sqlite-latest.html"
popd
exit /b 0
:failed
echo Experiment or report save failed. See the error above.
popd
pause
exit /b 1
