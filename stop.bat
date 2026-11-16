@echo off
rem Stops all Dispensary Desk windows started by start.bat.
for %%T in ("Dispensary - Cloud server*" "Dispensary - Hospital server*" "Dispensary - Hospital app*" "Dispensary - Remote app*") do (
  taskkill /fi "WINDOWTITLE eq %%~T" /t /f >nul 2>nul
)
echo  Dispensary Desk stopped.
timeout /t 2 >nul
