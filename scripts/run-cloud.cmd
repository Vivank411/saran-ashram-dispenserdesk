@echo off
cd /d "%~dp0..\backend"
call "%~dp0env-cloud.cmd"
title Dispensary - Cloud server (port %CLOUD_PORT%)
echo Cloud server on http://127.0.0.1:%CLOUD_PORT%   (close this window to stop)
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port %CLOUD_PORT%
