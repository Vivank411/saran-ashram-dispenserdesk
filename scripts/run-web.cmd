@echo off
rem Hospital web app. --host makes it reachable from other PCs on the same network.
cd /d "%~dp0..\frontend"
if not defined HOSPITAL_PORT set "HOSPITAL_PORT=8000"
if not defined WEB_PORT set "WEB_PORT=5173"
set "VITE_API_PROXY=http://127.0.0.1:%HOSPITAL_PORT%"
title Dispensary - Hospital app (port %WEB_PORT%)
call npx vite --host --port %WEB_PORT% --strictPort
