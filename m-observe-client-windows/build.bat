@echo off
REM =========================================================================
REM  M-OBSERVE Client — Build Script
REM  Produces: dist\M-OBSERVE-Setup.exe
REM =========================================================================

echo.
echo  M-OBSERVE Client Build
echo  ======================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

echo [1/5] Installing dependencies...
pip install -r requirements.txt --quiet

echo [2/5] Cleaning...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [3/5] Building m-observe-svc.exe...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name m-observe-svc ^
    --hidden-import win32timezone ^
    --hidden-import win32serviceutil ^
    --hidden-import win32service ^
    --hidden-import win32event ^
    --hidden-import servicemanager ^
    --hidden-import pynvml ^
    client_service.py
if errorlevel 1 ( echo [ERROR] Service build failed. & pause & exit /b 1 )

echo [4/5] Building m-observe-overlay.exe...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name m-observe-overlay ^
    overlay.py
if errorlevel 1 ( echo [ERROR] Overlay build failed. & pause & exit /b 1 )

echo [5/5] Building M-OBSERVE-Setup.exe...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name M-OBSERVE-Setup ^
    --add-data "dist\m-observe-svc.exe;." ^
    --add-data "dist\m-observe-overlay.exe;." ^
    --add-data "logo.png;." ^
    --add-data "tray_icon.png;." ^
    --add-data "msol.txt;." ^
    --icon logo.ico ^
    installer.py
if errorlevel 1 (
    echo [INFO] Retrying without .ico...
    pyinstaller ^
        --onefile ^
        --noconsole ^
        --name M-OBSERVE-Setup ^
        --add-data "dist\m-observe-svc.exe;." ^
        --add-data "dist\m-observe-overlay.exe;." ^
        --add-data "logo.png;." ^
        --add-data "tray_icon.png;." ^
        --add-data "msol.txt;." ^
        installer.py
    if errorlevel 1 ( echo [ERROR] Installer build failed. & pause & exit /b 1 )
)

echo.
echo  BUILD COMPLETE!  Output: dist\M-OBSERVE-Setup.exe
echo.
pause
