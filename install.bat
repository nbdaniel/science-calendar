@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   Calendar Știință — Installer           ║
echo  ╚══════════════════════════════════════════╝
echo.

:: Run the PowerShell installer with elevated privileges
powershell -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-ExecutionPolicy Bypass -File ""%~dp0install.ps1"" -AppDir ""%~dp0""'"

echo.
echo  Instalare finalizata. Apasa orice tasta pentru a inchide.
pause >nul
