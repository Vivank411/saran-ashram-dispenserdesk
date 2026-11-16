@echo off
rem ============================================================
rem  Dispensary Desk - FRESH SETUP SCRIPT
rem  Run this ONCE on a brand-new computer.
rem  Needs: Python 3.11+ and Node.js 20+ installed first.
rem ============================================================
cd /d "%~dp0"
echo.
echo  =========================================
echo   Dispensary Desk - Fresh Setup
echo  =========================================
echo.

rem --- Check Python ---
python --version >nul 2>nul || (
  echo  [ERROR] Python not found.
  echo  Install from https://www.python.org/downloads/
  echo  IMPORTANT: tick "Add python.exe to PATH" during install.
  pause & exit /b 1
)

rem --- Check Node ---
where npm >nul 2>nul || (
  echo  [ERROR] Node.js not found.
  echo  Install LTS from https://nodejs.org/
  pause & exit /b 1
)

echo  [1/7] Creating Python virtual environment...
if exist backend\.venv (
  backend\.venv\Scripts\python.exe -c "import fastapi" >nul 2>nul || (
    echo         Old venv is broken - recreating...
    rmdir /s /q backend\.venv
  )
)
if not exist backend\.venv (
  python -m venv backend\.venv || goto :fail
)
echo         Done.

echo  [2/7] Installing Python packages (needs internet)...
backend\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r backend\requirements.txt || goto :fail
echo         Done.

echo  [3/7] Generating secrets...
backend\.venv\Scripts\python.exe scripts\make_secrets.py backend\.devdata\secrets.cmd || goto :fail
echo         Done.

echo  [4/7] Running hospital database migration...
pushd backend
setlocal
call ..\scripts\env-hospital.cmd
.venv\Scripts\python.exe -m alembic upgrade head || (endlocal & popd & goto :fail)
endlocal
popd
echo         Done.

echo  [5/7] Seeding medicine stock...
if exist backend\.devdata\stock-imported.txt (
  echo         Already imported - skipping.
) else (
  pushd backend
  setlocal
  call ..\scripts\env-hospital.cmd
  .venv\Scripts\python.exe -m app.cli seed-stock ..\data\stock.csv || (endlocal & popd & goto :fail)
  endlocal
  echo Stock imported> .devdata\stock-imported.txt
  popd
  echo         Done.
)

echo  [6/7] Running cloud database migration...
pushd backend
setlocal
call ..\scripts\env-cloud.cmd
.venv\Scripts\python.exe -m alembic upgrade head || (endlocal & popd & goto :fail)
endlocal
popd
echo         Done.

echo  [7/7] Installing frontend packages (needs internet)...
pushd frontend
call npm install --no-audit --no-fund --loglevel=error || (popd & goto :fail)
popd
echo         Done.

echo.
echo  =========================================
echo   Setup complete!
echo   Now double-click  start.bat  to run.
echo  =========================================
echo.
pause
exit /b 0

:fail
echo.
echo  [FAILED] Fix the error above and run setup-fresh.bat again.
pause
exit /b 1
