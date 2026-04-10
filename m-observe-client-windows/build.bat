@echo off
REM =========================================================================
REM  M-OBSERVE Client — Build Script
REM  Run this on a Windows machine with Python 3.10+ installed.
REM  Produces: dist\M-OBSERVE-Setup.exe (the only file you distribute)
REM =========================================================================

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   M-OBSERVE Client Build Script      ║
echo  ╚══════════════════════════════════════╝
echo.

REM --- Check Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

REM --- Install dependencies ---
echo [1/5] Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

REM --- Clean previous builds ---
echo [2/5] Cleaning previous builds...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

REM --- Build Service EXE ---
echo [3/5] Building m-observe-svc.exe (Windows Service)...
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
if errorlevel 1 (
    echo [ERROR] Service build failed.
    pause
    exit /b 1
)

REM --- Build Tray EXE ---
echo [4/5] Building m-observe-tray.exe (Tray + Overlay)...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name m-observe-tray ^
    --hidden-import pystray._win32 ^
    tray_overlay.py
if errorlevel 1 (
    echo [ERROR] Tray build failed.
    pause
    exit /b 1
)

REM --- Build Installer EXE (bundles the other two + assets) ---
echo [5/5] Building M-OBSERVE-Setup.exe (Installer)...
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name M-OBSERVE-Setup ^
    --add-data "dist\m-observe-svc.exe;." ^
    --add-data "dist\m-observe-tray.exe;." ^
    --add-data "logo.png;." ^
    --add-data "msol.txt;." ^
    --icon logo.ico ^
    installer.py
if errorlevel 1 (
    REM Try without icon if logo.ico doesn't exist
    echo [INFO] Retrying without .ico...
    pyinstaller ^
        --onefile ^
        --noconsole ^
        --name M-OBSERVE-Setup ^
        --add-data "dist\m-observe-svc.exe;." ^
        --add-data "dist\m-observe-tray.exe;." ^
        --add-data "logo.png;." ^
        --add-data "msol.txt;." ^
        installer.py
    if errorlevel 1 (
        echo [ERROR] Installer build failed.
        pause
        exit /b 1
    )
)

echo.
echo ══════════════════════════════════════════════════
echo  BUILD COMPLETE!
echo.
echo  Output:  dist\M-OBSERVE-Setup.exe
echo.
echo  This single .exe is all you need to distribute.
echo  It contains the service, tray app, logo, and license.
echo ══════════════════════════════════════════════════
echo.
pause
