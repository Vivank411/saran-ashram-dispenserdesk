@echo off
rem Settings for the hospital (local, authoritative) server.
call "%~dp0..\backend\.devdata\secrets.cmd"
if not defined HOSPITAL_PORT set "HOSPITAL_PORT=8000"
if not defined CLOUD_PORT set "CLOUD_PORT=8001"
set "APP_ROLE=hospital"
set "DATABASE_URL=postgresql+psycopg://dispensary:dispensary123@localhost:5432/hospital_db"
set "PEER_API_URL=http://127.0.0.1:%CLOUD_PORT%"
set "JWT_SECRET=%HOSPITAL_JWT_SECRET%"
set "RUN_SYNC_WORKER=true"
