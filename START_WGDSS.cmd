@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-WGDSS.ps1"
if errorlevel 1 (
    echo.
    echo WGDSS could not be started. Review the message above and try again.
    pause
)

endlocal
