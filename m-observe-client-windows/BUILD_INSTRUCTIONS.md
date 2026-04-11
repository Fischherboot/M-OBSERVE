# Build Instructions — M-OBSERVE Windows Client

## Requirements
- Windows 10/11
- Python 3.10+ (mit PATH)
- ~500 MB Disk für den Build

## Build (One Command)

```
build.bat
```

Das baut 3 EXEs und packt alles in **eine einzige Setup-Datei**:

```
dist\M-OBSERVE-Setup.exe    ← Das ist deine Installer-EXE
```

## Was passiert beim Build?

1. `m-observe-svc.exe` — Der Windows Service (läuft ohne Login)
2. `m-observe-tray.exe` — Tray-Icon + Overlay (läuft bei User-Login)
3. `M-OBSERVE-Setup.exe` — Installer, der 1+2 + Logo + Lizenz einbettet

## Was passiert bei der Installation?

Der User startet `M-OBSERVE-Setup.exe` (wird automatisch als Admin ausgeführt):

1. **Lizenz** — MSOL akzeptieren
2. **Config** — Client-Name, Overseer-IP, Port eingeben
3. **API Key** — Den Key vom Overseer eingeben
4. **Install** — Alles wird nach `C:\Program Files\M-OBSERVE Client\` kopiert:
   - Windows Service `MObserveClient` wird angelegt (auto-start, recovery bei crash)
   - Tray-App wird in Autostart registriert (HKLM)
   - Service wird sofort gestartet
   - Tray wird gestartet

## Nach der Installation

- **Service** läuft im Hintergrund, auch ohne eingeloggten User
- **Tray-Icon** erscheint bei jedem Login in den Hidden Icons
  - Pause / Resume Service
  - Uninstall (entfernt alles sauber)
- **Overlay** zeigt oben rechts: "Dieses Gerät wird von M-OBSERVE überwacht."
  - 50% transparent, click-through, non-interaktiv

## Optional: Logo als .ico

Für ein Fenster-Icon, konvertiere `logo.png` zu `logo.ico` (z.B. mit https://convertio.co) und leg die Datei neben die anderen. Der Build-Script nutzt sie automatisch.

## Deinstallation

Entweder über das Tray-Icon → "Uninstall M-OBSERVE", oder manuell:

```cmd
sc stop MObserveClient
sc delete MObserveClient
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v MObserveTray /f
rmdir /s /q "C:\Program Files\M-OBSERVE Client"
```
