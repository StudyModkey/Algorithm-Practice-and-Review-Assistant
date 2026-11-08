@echo off
setlocal
cd /d "%~dp0"
where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pyw.exe -3 "%~dp0app.py"
    exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0app.py"
    exit /b
)
if exist "C:\Python313\pythonw.exe" (
    start "" "C:\Python313\pythonw.exe" "%~dp0app.py"
    exit /b
)
echo Install Python 3.10 or later with Tkinter, then try again.
echo Existing data in the data folder will be kept.
pause
