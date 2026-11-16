@echo off
cd /d "%~dp0..\backend"
call "%~dp0env-hospital.cmd"
title Dispensary - Hospital server (port %HOSPITAL_PORT%)
echo Hospital server on http://127.0.0.1:%HOSPITAL_PORT%   (close this window to stop)
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port %HOSPITAL_PORT%
