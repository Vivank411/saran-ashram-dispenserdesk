@echo off
rem Remote (cloud) web app — for trying remote access on this computer.
cd /d "%~dp0..\frontend"
if not defined CLOUD_PORT set "CLOUD_PORT=8001"
if not defined REMOTE_WEB_PORT set "REMOTE_WEB_PORT=5174"
set "VITE_API_PROXY=http://127.0.0.1:%CLOUD_PORT%"
title Dispensary - Remote app (port %REMOTE_WEB_PORT%)
call npx vite --host --port %REMOTE_WEB_PORT% --strictPort
