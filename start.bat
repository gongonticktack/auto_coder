@echo off
setlocal
cd /d "%~dp0"
title Fretlab setup and launch
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo Fretlab could not start. See the error above.
  pause
  exit /b 1
)
exit /b 0
