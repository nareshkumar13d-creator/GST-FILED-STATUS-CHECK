@echo off
REM Windows par double-click karo (internet chahiye). Dono exe ban jayengi:
REM   dist\GSTPortal.exe  = captcha wala (API key nahi chahiye)
REM   dist\GSTStatus.exe  = API key wala
echo Python check ho raha hai...
python --version >nul 2>&1
if errorlevel 1 (
  echo Python nahi mila. python.org/downloads se install karo ^("Add Python to PATH" tick karke^), phir dobara chalao.
  pause
  exit /b 1
)
echo PyInstaller install ho raha hai...
python -m pip install --upgrade pyinstaller pillow
echo GSTPortal.exe ban raha hai...
python -m PyInstaller --onefile --windowed --icon gst_icon.ico --add-data "gst_icon.ico;." --name GSTPortal gst_portal_app.py
echo GSTStatus.exe ban raha hai...
python -m PyInstaller --onefile --windowed --icon gst_icon.ico --add-data "gst_icon.ico;." --name GSTStatus gst_app.py
echo.
if exist dist\GSTPortal.exe (echo Taiyar: dist\GSTPortal.exe) else (echo GSTPortal build fail hua, upar ka error dekho.)
if exist dist\GSTStatus.exe (echo Taiyar: dist\GSTStatus.exe) else (echo GSTStatus build fail hua, upar ka error dekho.)
pause
