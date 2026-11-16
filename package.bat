@echo off
rem Makes a small zip of this project to copy to another computer.
rem   package.bat            -> fresh copy (no accounts/bills; the new computer starts with the sign-up screen)
rem   package.bat with-data  -> also includes this computer's data (accounts, bills, stock) and secrets
setlocal
cd /d "%~dp0.."
set "OUT=%~dp0..\dispensary-desk.zip"
set "EXTRA=--exclude=dispensary-desk/backend/.devdata"
if /i "%~1"=="with-data" set "EXTRA="
if exist "%OUT%" del "%OUT%"
tar -a -c -f "%OUT%" --exclude=dispensary-desk/backend/.venv --exclude=dispensary-desk/frontend/node_modules ^
  --exclude=dispensary-desk/frontend/dist --exclude=__pycache__ --exclude=.pytest_cache --exclude=dispensary-desk/backend/.uidemo ^
  --exclude=*.db-shm --exclude=*.db-wal %EXTRA% dispensary-desk || (echo Packaging failed. & pause & exit /b 1)
echo.
echo  Created: %OUT%
if /i "%~1"=="with-data" (echo  Includes this computer's data. Stop the app first so the database file is complete.) else (echo  Fresh copy - the new computer starts with first-time sign-up.)
echo  Copy the zip to the other computer, extract it, then run setup.bat and start.bat.
pause
