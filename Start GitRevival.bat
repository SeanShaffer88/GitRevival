@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0launch.pyw"
    exit /b
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0launch.pyw"
    exit /b
)
echo GitRevival needs Python 3.11 or newer with Tcl/Tk support.
echo Install Python from python.org, then run this launcher again.
pause
