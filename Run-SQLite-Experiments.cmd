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
python -m awaitlab demo --scenario sqlite --output artifacts/sqlite-latest.json
if errorlevel 1 goto failed
start "" "%~dp0artifacts\sqlite-latest.html"
popd
exit /b 0
:failed
echo Experiment or report save failed. Existing files may be from an earlier run.
popd
pause
exit /b 1
