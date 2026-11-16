@echo off
rem ================================================================
rem  Dispensary Desk - one-time setup on a new Windows computer.
rem  Needs: Python 3.11+ (python.org) and Node.js 20+ (nodejs.org).
rem ================================================================
setlocal
cd /d "%~dp0"
echo.
echo  Dispensary Desk - setup
echo  -----------------------

rem --- find Python 3.11+ ---
set "PY="
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if not defined PY py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  echo  [!] Python 3.11 or newer was not found.
  echo      Install it from https://www.python.org/downloads/  and tick "Add python.exe to PATH".
  goto :fail
)
rem --- find Node.js ---
where npm >nul 2>nul || (
  echo  [!] Node.js was not found. Install the LTS version from https://nodejs.org/
  goto :fail
)

echo  [1/4] Python environment
if exist backend\.venv (
  backend\.venv\Scripts\python.exe -c "import fastapi" >nul 2>nul
  if errorlevel 1 (
    echo        Existing .venv is from another computer - recreating it...
    rmdir /s /q backend\.venv
  )
)
if not exist backend\.venv %PY% -m venv backend\.venv || goto :fail
backend\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r backend\requirements.txt || goto :fail

echo  [2/4] Secrets and databases
backend\.venv\Scripts\python.exe scripts\make_secrets.py backend\.devdata\secrets.cmd || goto :fail
pushd backend
setlocal
call ..\scripts\env-hospital.cmd
.venv\Scripts\python.exe -m alembic upgrade head || (popd & goto :fail)
if not exist .devdata\stock-imported.txt (
  .venv\Scripts\python.exe -m app.cli seed-stock ..\data\stock.csv || (popd & goto :fail)
  echo Stock register imported> .devdata\stock-imported.txt
)
endlocal
setlocal
call ..\scripts\env-cloud.cmd
.venv\Scripts\python.exe -m alembic upgrade head || (popd & goto :fail)
endlocal
popd

echo  [3/4] Web app packages (this can take a minute)
pushd frontend
call npm install --no-audit --no-fund --loglevel=error || (popd & goto :fail)
popd

echo  [4/4] Done.
echo.
echo  Setup complete. Now double-click start.bat
echo.
pause
exit /b 0

:fail
echo.
echo  Setup did not finish. Read the message above, fix it, and run setup.bat again.
pause
exit /b 1
