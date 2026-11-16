@echo off
setlocal
chcp 65001 >nul
set "AWAITLAB_ROOT=%~dp0"
set "AWAITLAB_CODE=%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"
if not exist "%AWAITLAB_CODE%" set "AWAITLAB_CODE=code.cmd"
set "AWAITLAB_DATA=D:\CodexWork\cache\awaitlab-vscode-user"
set "AWAITLAB_EXT=D:\CodexWork\cache\awaitlab-vscode-extensions"
set "AWAITLAB_DEMO=%AWAITLAB_ROOT%artifacts\vscode-demo"
set "TEMP=D:\CodexWork\temp\awaitlab"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%AWAITLAB_DEMO%" mkdir "%AWAITLAB_DEMO%"
if not exist "%AWAITLAB_DEMO%\review_me.py" copy /y "%AWAITLAB_ROOT%examples\defensive_vscode_sample.py" "%AWAITLAB_DEMO%\review_me.py" >nul
if not exist "%AWAITLAB_DEMO%\review_me.py" (
  echo 演示文件不存在，请检查 examples/defensive_vscode_sample.py
  pause
  exit /b 1
)
call "%AWAITLAB_CODE%" --user-data-dir "%AWAITLAB_DATA%" --extensions-dir "%AWAITLAB_EXT%" --install-extension "%AWAITLAB_ROOT%artifacts\vscode\awaitlab-0.1.0.vsix" --force >nul
if errorlevel 1 (
  echo 扩展安装失败。请确认本机已安装 VS Code，且安装包存在。
  pause
  exit /b 1
)
call "%AWAITLAB_CODE%" --user-data-dir "%AWAITLAB_DATA%" --extensions-dir "%AWAITLAB_EXT%" --new-window "%AWAITLAB_DEMO%\review_me.py"
endlocal
