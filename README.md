<p align="center">
  <img src="https://raw.githubusercontent.com/Fischherboot/M-OBSERVE/refs/heads/main/img/logo.png" alt="M-OBSERVE" width="700">
</p>

<p align="center">
  <strong>Self-hosted Server-Monitoring für Homelabs.</strong><br>
  Echtzeit-Telemetrie · Remote Shell · Multi-Client · Kein Cloud-Zwang
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Lizenz-MSOL-blue" alt="Lizenz">
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/Frontend-Vanilla_JS-f7df1e" alt="JS">
  <img src="https://img.shields.io/badge/Protokoll-WebSocket-purple" alt="WebSocket">
</p>

---

## Was ist M-OBSERVE?

M-OBSERVE ist ein leichtgewichtiges, selbst gehostetes Monitoring-System für Homelabs und kleine Netzwerke. Den **Overseer** (Host) auf einer Maschine installieren, **Clients** auf allem anderen deployen, und du hast ein Live-Dashboard mit CPU, RAM, Disk, GPU, Temperaturen, Prozessen, Services, S.M.A.R.T.-Daten und einer Remote Shell — alles im Browser. Keine Cloud. Keine Accounts. Keine Telemetrie die nach Hause funkt.

---

## Screenshots

### Dashboard — Client-Übersicht

![BILD_LINK_HIER_—_Dashboard_Übersicht_mit_allen_verbundenen_Clients_als_Karten,_Online/Offline_Status,_OS-Icons](https://raw.githubusercontent.com/Fischherboot/M-OBSERVE/refs/heads/main/img/dashboard.png)

> Die Hauptansicht. Jeder verbundene Client erscheint als Karte mit Live-Status, OS, Hostname und Schnellübersicht.

### Client-Detail — Telemetrie

![BILD_LINK_HIER_—_Detail-Ansicht_eines_Clients_mit_CPU-Auslastung,_Per-Core_Balken,_RAM,_Disk,_Netzwerk,_Temperatur-Chips](https://raw.githubusercontent.com/Fischherboot/M-OBSERVE/refs/heads/main/img/tel.png)

> Reinzoomen in jeden Client: Echtzeit-CPU (Per-Core-Balken, auch für Multi-Socket), RAM, Disk, Netzwerk-Durchsatz und Temperatursensoren mit Schwellwert-Einfärbung.

### Remote Shell

![BILD_LINK_HIER_—_Shell_Tab_mit_Terminal-Output,_dunkler_Hintergrund,_Monospace_Font](https://raw.githubusercontent.com/Fischherboot/M-OBSERVE/refs/heads/main/img/shell.png)

> Ein Browser-basiertes PTY-Terminal in jeden verbundenen Client. Kein SSH-Setup nötig.

### Prozesse & Services

![BILD_LINK_HIER_—_Prozessliste_mit_PID,_CPU%,_RAM%,_User_und_Service-Status_Liste](https://raw.githubusercontent.com/Fischherboot/M-OBSERVE/refs/heads/main/img/processes.png)

> Live-Prozessliste und systemd-Service-Status, on-demand abgerufen um Bandbreite zu sparen.

### S.M.A.R.T. Disk Health

![BILD_LINK_HIER_—_SMART_Ansicht_mit_Disk-Blöcken,_Health_Status_grün/rot,_Attribut-Tabelle](https://raw.githubusercontent.com/Fischherboot/M-OBSERVE/refs/heads/main/img/smart.png)

> Pro-Laufwerk Gesundheitsübersicht mit vollständiger Attribut-Tabelle. Reallocated Sectors werden automatisch rot markiert.

---

## Features

- **Echtzeit-Telemetrie** — CPU, RAM, Disk, Netzwerk, Load Average, eingeloggte User, alle 3 Sekunden aktualisiert
- **Multi-Socket CPU** — Dual-Xeon? Jeder Prozessor bekommt seine eigene Per-Core-Aufschlüsselung
- **GPU-Monitoring** — NVIDIA-GPUs via `pynvml` mit VRAM, Power, Temperaturen, Encoder/Decoder
- **Temperatursensoren** — Alle Sensoren automatisch erkannt, Schwellwert-basierte Einfärbung (Orange/Rot)
- **S.M.A.R.T.-Daten** — Strukturiert oder Raw, pro Laufwerk als eigener Block
- **Prozessliste & Service-Status** — On-Demand, nicht dauerhaft gepollt
- **Remote Shell** — Volles PTY über WebSocket, direkt im Browser
- **Log-Streaming** — `journalctl -f` gepiped ins Dashboard
- **Remote-Aktionen** — Reboot, Shutdown, User kicken, Service neustarten, Updates anstoßen
- **Plaintext-Feld** — Clients können beliebigen Text mitschicken (RAID-Status, Docker-Container, Backup-Zeiten — was auch immer du scriptest)
- **Kein History** — Speichert nur den letzten Snapshot pro Client. Keine Zeitreihen-DB, kein Disk-Bloat
- **Ein-Befehl-Setup** — Ein `install.sh`, ein Port, ein systemd Service

---

### Client einrichten

Siehe [`CLIENT_PROTOCOL.md`](CLIENT_PROTOCOL.md) für die vollständige Protokoll-Spezifikation. Ein Client ist jedes Script das:

1. Einen WebSocket zu `ws://<HOST_IP>:3501/ws/client` öffnet
2. Eine Auth-Nachricht mit dem API-Key schickt
3. Alle paar Sekunden Telemetrie-JSON pusht

Das war's. Bau einen in Python, Go, Rust, Bash — was auch immer auf deiner Kiste läuft.

---

## Architektur

```
┌─────────────────────────────────────┐
│           Browser (SPA)             │
│         http://<IP>:3501            │
└──────────────┬──────────────────────┘
               │ HTTP + WebSocket
┌──────────────▼──────────────────────┐
│     Overseer (FastAPI + uvicorn)    │
│          Port 3501                  │
│  ┌──────────┐  ┌─────────────────┐  │
│  │ REST API │  │ WS Manager      │  │
│  │ + Static │  │ (Client-Conns)  │  │
│  └──────────┘  └─────────────────┘  │
│  ┌──────────────────────────────┐   │
│  │ SQLite (nur Config, kein    │   │
│  │ History, < 1 MB)            │   │
│  └──────────────────────────────┘   │
└──────────────┬──────────────────────┘
               │ WebSocket (persistent)
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│Client 1│ │Client 2│ │Client 3│
│Linux   │ │Windows │ │FreeBSD │
└────────┘ └────────┘ └────────┘
```

---

## Client-Protokoll (Kurzfassung)

| Richtung | Nachricht | Zweck |
|---|---|---|
| Client → Host | Auth-JSON | API-Key + Client-Metadaten beim Verbinden |
| Client → Host | `type: "telemetry"` | CPU, RAM, Disk, GPU, Temps, Netzwerk — alle 3s |
| Host → Client | `type: "request"` | Prozesse, Services, Updates, SMART, Logs, Shell anfordern |
| Client → Host | `type: "processes"` / `"services"` / ... | Antwort auf Request |
| Host → Client | `type: "action"` | Reboot, Shutdown, User kicken, Service neustarten |
| Client → Host | `type: "action_result"` | Bestätigung |
| Host → Client | `type: "shell_input"` | Tastatureingaben für Remote Shell |
| Client → Host | `type: "shell_output"` | PTY-Output zurück |

Vollständige Spezifikation mit allen Feldern: [`CLIENT_PROTOCOL.md`](CLIENT_PROTOCOL.md)

---

## Ressourcenverbrauch

Der Overseer ist bewusst minimal gehalten. Keine Zeitreihen-Datenbank, kein Prometheus, keine Grafana-Abhängigkeit. SQLite speichert nur Config und einen Snapshot pro Client. Gesamter Footprint inklusive Python-venv unter **200 MB RAM**.

---

## Plattform-Support

| Plattform | Client | Overseer |
|---|---|---|
| Ubuntu / Debian | ✅ | ✅ |
| Raspbian / Pi OS | ✅ | ✅ |
| Windows 10/11 | ✅ | — |
| FreeBSD | 🚧 Geplant | — |

---

## Lizenz

<p align="center">
  <a href="https://moritzsoft.de/#license">Moritzsoft Open License</a>
</p>
