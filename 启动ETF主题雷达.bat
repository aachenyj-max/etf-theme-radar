@echo off
setlocal
title ETF Theme Radar
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_local.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" (
  echo.
  echo ETF Theme Radar launcher finished or reused the running service.
) else (
  echo.
  echo ETF Theme Radar failed to start. Review the message above and data\logs.
)
echo Press any key to close this window.
pause >nul
exit /b %EXIT_CODE%
