@echo off
echo.
echo  Installing PostgreSQL 16 silently (no wizard)...
echo  This will take 2-3 minutes. Do not close this window.
echo.
"c:\Users\asus\Downloads\pg16.exe" --mode unattended --superpassword postgres123 --servicename postgresql-16 --servicepassword postgres123 --serverport 5432
if errorlevel 1 (
    echo.
    echo  [ERROR] Installation failed. Try running as Administrator.
    pause
    exit /b 1
)
echo.
echo  PostgreSQL 16 installed successfully!
echo.

echo  Creating dispensary user and databases...
set "PGPASSWORD=postgres123"
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE USER dispensary WITH PASSWORD 'dispensary123';" 2>nul
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE hospital_db OWNER dispensary;"
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE cloud_db OWNER dispensary;"
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE hospital_db TO dispensary;"
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE cloud_db TO dispensary;"
echo.
echo  Databases created!
echo.
echo  =====================================================
echo   Done! Now double-click  start.bat  to run the app.
echo  =====================================================
echo.
pause
