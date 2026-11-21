@echo off
rem ================================================================
rem  Builds the Windows installer:  desktop\Output\DispensaryDesk-Setup-<version>.exe
rem  Needs on THIS (developer) computer: Python 3.11+, Node.js 20+, Inno Setup 6
rem     winget install JRSoftware.InnoSetup
rem  Usage:  desktop\build.bat            (version 1.0.0)
rem          desktop\build.bat 1.0.1      (set the version shown in Add/Remove Programs)
rem ================================================================
setlocal
cd /d "%~dp0.."
set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=1.0.0"
rem temporary build files live outside OneDrive (OneDrive locks folders while syncing them)
set "BUILD=%LOCALAPPDATA%\DispensaryDeskBuild"

echo.
echo  [1/4] Building the web app
pushd frontend
call npm ci --no-audit --no-fund --loglevel=error || (popd & goto :fail)
call npm run build || (popd & goto :fail)
popd

echo  [2/4] Python build environment
if not exist desktop\.buildenv\Scripts\python.exe (
  python -m venv desktop\.buildenv || goto :fail
)
desktop\.buildenv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r backend\requirements.txt pyinstaller pillow || goto :fail
if not exist desktop\app.ico desktop\.buildenv\Scripts\python.exe desktop\make_icon.py

echo  [3/4] Bundling the app (Python + server + web app in one folder)
desktop\.buildenv\Scripts\python.exe -m PyInstaller --noconfirm --clean --log-level WARN ^
  --distpath "%BUILD%\dist" --workpath "%BUILD%\work" desktop\DispensaryDesk.spec || goto :fail

echo  [4/4] Creating the installer
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
  if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
  echo  [!] Inno Setup 6 not found. Install it with:  winget install JRSoftware.InnoSetup
  goto :fail
)
"%ISCC%" /Q /DAppVersion=%VERSION% "/DDistDir=%BUILD%\dist\DispensaryDesk" desktop\installer.iss || goto :fail

echo.
echo  Done:  desktop\Output\DispensaryDesk-Setup-%VERSION%.exe
echo  Copy that one file to the hospital computers and run it (main computer first).
exit /b 0

:fail
echo.
echo  Build FAILED - see the messages above.
exit /b 1
