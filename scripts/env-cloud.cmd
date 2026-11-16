@echo off
rem Settings for the cloud (remote access) server. On this computer it simulates the cloud.
call "%~dp0..\backend\.devdata\secrets.cmd"
if not defined HOSPITAL_PORT set "HOSPITAL_PORT=8000"
if not defined CLOUD_PORT set "CLOUD_PORT=8001"
set "APP_ROLE=cloud"
set "DATABASE_URL=postgresql+psycopg://dispensary:dispensary123@localhost:5432/cloud_db"
set "PEER_API_URL=http://127.0.0.1:%HOSPITAL_PORT%"
set "JWT_SECRET=%CLOUD_JWT_SECRET%"
rem No SMS gateway configured locally: the one-time code is shown on screen.
set "DEV_EXPOSE_OTP=true"
