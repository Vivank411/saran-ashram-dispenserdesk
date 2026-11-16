@echo off
rem Starts Dispensary Desk: hospital server, cloud server, hospital app and remote app.
rem Each runs in its own window. Close those windows (or run stop.bat) to stop.
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe goto :needsetup
if not exist backend\.devdata\secrets.cmd goto :needsetup
if not exist frontend\node_modules goto :needsetup

start "Dispensary - Cloud server" /min cmd /k scripts\run-cloud.cmd
start "Dispensary - Hospital server" /min cmd /k scripts\run-hospital.cmd
start "Dispensary - Hospital app" /min cmd /k scripts\run-web.cmd
start "Dispensary - Remote app" /min cmd /k scripts\run-remote-web.cmd

echo.
echo  Starting Dispensary Desk...
timeout /t 8 /nobreak >nul
start "" http://localhost:5173
echo.
echo  Hospital app : http://localhost:5173
echo  Remote app   : http://localhost:5174
echo.
echo  Other computers on the same network can open the hospital app at
echo  http://THIS-COMPUTER-IP:5173   (find the IP with:  ipconfig)
echo.
echo  To stop everything, run stop.bat
echo.
pause
exit /b 0

:needsetup
echo  Setup has not been run on this computer yet. Double-click setup.bat first.
pause
exit /b 1
