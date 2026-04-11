# M-OBSERVE — Client Protocol Reference

Dieses Dokument beschreibt exakt, wie ein Client sich mit dem Overseer (Host-Backend) verbindet, authentifiziert, Daten sendet und Befehle empfängt. Alles was nötig ist um Clients für Linux, FreeBSD und Windows zu bauen.

---

## 1. Verbindung

Der Client hält eine **persistente WebSocket-Verbindung** zum Host-Backend.

**URL:** `ws://<HOST_IP>:3501/ws/client`

Beispiel: `ws://192.168.1.50:3501/ws/client`

---

## 2. Authentifizierung (Erste Nachricht)

Direkt nach dem WebSocket-Handshake **muss** der Client innerhalb von 10 Sekunden eine JSON-Nachricht senden:

```json
{
    "api_key": "observe-delta-7392",
    "client_id": "550e8400-e29b-41d4-a716-446655440000",
    "client_name": "Redemption 1",
    "hostname": "redemption1",
    "os": "Ubuntu 24.04 LTS",
    "platform": "linux",
    "ip": "192.168.1.10"
}
```

**Felder:**
- `api_key` — Der Key vom Host-Setup. Muss exakt übereinstimmen.
- `client_id` — UUID, beim Client-Setup einmalig generiert und in `config.json` gespeichert.
- `client_name` — Vom User gewählter Anzeigename.
- `hostname` — Netzwerk-Hostname der Maschine.
- `os` — OS-String (z.B. "Ubuntu 24.04 LTS", "Windows 11 Pro 23H2", "FreeBSD 14.0").
- `platform` — Eins von: `"linux"`, `"freebsd"`, `"windows"`.
- `ip` — Lokale IP-Adresse der Maschine.

**Antwort:** Keine explizite Antwort bei Erfolg. Bei falschem API-Key wird die Verbindung sofort geschlossen (Code 1008, Reason "Invalid API key").

---

## 3. Telemetrie senden (Client → Host)

Alle **3 Sekunden** (konfigurierbar) sendet der Client einen Telemetrie-Datensatz:

```json
{
    "type": "telemetry",
    "client_id": "550e8400-...",
    "client_name": "Redemption 1",
    "timestamp": 1712764800,
    "os": "Ubuntu 24.04 LTS",
    "platform": "linux",
    "hostname": "redemption1",
    "ip": "192.168.1.10",
    "uptime_seconds": 1234567,

    "cpu": {
        "usage_percent": 23.5,
        "per_core": [12.3, 34.5, 8.1, 45.2],
        "model": "Intel Xeon E5-2670 v1",
        "cores": 16,
        "freq_mhz": 2600
    },

    "cpus": [
        {
            "usage_percent": 25.0,
            "per_core": [12.3, 34.5, 8.1, 45.2, 18.9, 22.1, 30.5, 15.0],
            "model": "Intel Xeon E5-2670 v1 @ 2.60GHz",
            "cores": 8,
            "freq_mhz": 2600
        },
        {
            "usage_percent": 22.0,
            "per_core": [10.1, 28.3, 5.6, 40.0, 12.7, 19.8, 33.2, 11.4],
            "model": "Intel Xeon E5-2670 v1 @ 2.60GHz",
            "cores": 8,
            "freq_mhz": 2600
        }
    ],

    "ram": {
        "total_mb": 65536,
        "used_mb": 39000,
        "percent": 59.5
    },

    "disks": [
        {
            "mount": "/",
            "total_gb": 500.0,
            "used_gb": 230.4,
            "percent": 46,
            "fs_type": "ext4"
        }
    ],

    "gpus": [
        {
            "name": "NVIDIA RTX 3090",
            "usage_percent": 45,
            "vram_used_mb": 4096,
            "vram_total_mb": 24576,
            "temp_c": 65,
            "power_draw_w": 280,
            "power_limit_w": 350,
            "fan_speed_percent": 55,
            "encoder_percent": 0,
            "decoder_percent": 12,
            "pcie_gen": 4,
            "pcie_width": 16,
            "driver": "550.54.14",
            "cuda_version": "12.4"
        },
        {
            "name": "NVIDIA RTX 4060 Ti",
            "usage_percent": 12,
            "vram_used_mb": 1024,
            "vram_total_mb": 16384,
            "temp_c": 42,
            "fan_speed_percent": 30,
            "driver": "550.54.14"
        }
    ],

    "temperatures": {
        "cpu": 45,
        "cpu0": {"current": 44, "high": 80, "critical": 100},
        "cpu1": {"current": 46, "high": 80, "critical": 100},
        "nvme_composite": 38,
        "pch": 52,
        "gpu0": 65,
        "gpu1": 42,
        "ambient": 28
    },

    "network": {
        "interfaces": [
            {
                "name": "eth0",
                "ip": "192.168.1.10",
                "rx_bytes": 123456789,
                "tx_bytes": 98765432
            },
            {
                "name": "eth1",
                "ip": "10.0.0.1",
                "rx_bytes": 5678900,
                "tx_bytes": 1234567
            }
        ]
    },

    "load_avg": [1.23, 0.98, 0.76],

    "users": [
        {
            "name": "moritz",
            "terminal": "pts/0",
            "host": "192.168.1.5",
            "started": "10:30"
        }
    ],

    "plaintext": "Beliebiger Text den der Client mitschicken will.\nKann mehrzeilig sein.\nHier kann man custom Infos anzeigen die kein festes Schema haben.\n\nBeispiel: Letzte Backup-Zeit: 2026-04-10 03:00 UTC\nRAID Status: ONLINE\nDocker Container: 14 running, 2 stopped"
}
```

### Felder-Details:

**`cpu` vs `cpus`:**
- `cpu` — Einzelnes CPU-Objekt (Rückwärtskompatibel, für Single-CPU Systeme). Das Frontend zeigt es als einen Block.
- `cpus` — **Array** von CPU-Objekten für Multi-CPU Systeme (z.B. Dual-Xeon). Jeder Eintrag hat eigene `per_core`, `model`, `cores`, `freq_mhz`. Das Frontend zeigt jeden Prozessor separat mit eigenen Per-Core-Balken.
- Wenn `cpus` vorhanden ist, wird `cpu` ignoriert. Schicke entweder `cpu` ODER `cpus`.

**`gpus`:**
- Array. Leeres Array `[]` wenn keine GPU vorhanden. Beliebig viele Einträge.
- **Pflichtfelder:** `name`
- **Optionale Felder:** `usage_percent`, `vram_used_mb`, `vram_total_mb`, `temp_c`, `power_draw_w`, `power_limit_w`, `fan_speed_percent`, `encoder_percent`, `decoder_percent`, `pcie_gen`, `pcie_width`, `driver`, `cuda_version`
- **Beliebige Extra-Keys:** Alle unbekannten Key-Value-Paare werden im Frontend automatisch als `key: value` angezeigt. Du kannst also z.B. `"memory_clock_mhz": 1200` oder `"sm_count": 128` hinzufügen — es wird einfach dargestellt.

**`temperatures`:**
- Objekt mit beliebig vielen Sensor-Keys.
- Wert kann eine **Zahl** sein: `"cpu": 45`
- Oder ein **Objekt** mit Schwellwerten: `"cpu0": {"current": 44, "high": 80, "critical": 100}`
  - Das Frontend zeigt dann die Schwellwerte mit an und färbt den Wert rot/orange wenn Schwellwerte überschritten.
- Alle Sensor-Keys werden als einzelne Temperatur-Chips dargestellt. Schicke so viele wie du willst.

**`plaintext`:**
- **Optional.** String mit beliebigem Inhalt.
- Wird im Frontend in einem eigenen "Plaintext"-Tab als Monospace-Text angezeigt.
- Mehrzeilig mit `\n` getrennt.
- Gedacht für custom Infos die kein Schema haben: RAID-Status, Docker-Container, Backup-Zeiten, Cron-Jobs, oder was auch immer der User auf dem Client scriptet.
- Kann auch ein JSON-Objekt sein — wird dann formatiert dargestellt.

**`load_avg`:** Nur Linux/FreeBSD. Auf Windows: `null`.
**`users`:** Array aktiver Login-Sessions. Kann leer sein.

---

## 4. On-Demand Daten Requests (Host → Client)

Der Host kann dem Client auffordern, bestimmte Daten zu senden. Der Client empfängt:

```json
{
    "type": "request",
    "request": "processes"
}
```

Mögliche `request`-Werte:
- `"processes"` — Prozessliste senden
- `"services"` — Service-Liste senden (nur Linux/FreeBSD)
- `"updates"` — Verfügbare Updates senden (nur Linux/FreeBSD)
- `"disk_check"` — SMART-Daten senden
- `"logs"` — Log-Streaming starten
- `"shell"` — Shell-Session starten

### Antwort-Formate:

**Prozesse** (Client → Host):
```json
{
    "type": "processes",
    "client_id": "...",
    "data": [
        {
            "pid": 1423,
            "name": "nginx",
            "cpu_percent": 2.1,
            "ram_percent": 0.8,
            "user": "www-data",
            "started": "2024-04-08 10:00"
        }
    ]
}
```

**Services** (Client → Host):
```json
{
    "type": "services",
    "client_id": "...",
    "data": [
        {
            "name": "nginx",
            "state": "active",
            "sub": "running"
        },
        {
            "name": "redis",
            "state": "failed",
            "sub": "exited"
        }
    ]
}
```
`state` Werte: `"active"`, `"inactive"`, `"failed"`

**Updates** (Client → Host):
```json
{
    "type": "updates",
    "client_id": "...",
    "data": {
        "packages": [
            {
                "name": "nginx",
                "current": "1.24.0-1",
                "available": "1.24.0-2"
            }
        ]
    }
}
```

**Logs** (Client → Host, gestreamt):
```json
{
    "type": "logs_line",
    "client_id": "...",
    "data": "Apr 08 14:23:01 systemd[1]: Started nginx.service"
}
```
Eine Nachricht pro Zeile. Kontinuierlich streamen solange der Tab offen ist.

**Shell Output** (Client → Host, gestreamt):
```json
{
    "type": "shell_output",
    "client_id": "...",
    "data": "moritz@redemption1:~$ "
}
```

**S.M.A.R.T. Daten** (Client → Host):

Kann als strukturiertes JSON ODER als Raw-Text geschickt werden. Das Frontend kann beides.

Option A — Strukturiert (empfohlen):
```json
{
    "type": "smart",
    "client_id": "...",
    "data": [
        {
            "device": "/dev/sda",
            "model": "Samsung SSD 870 EVO 1TB",
            "serial": "S5Y1NX0T123456",
            "firmware": "SVT02B6Q",
            "capacity": "1.0 TB",
            "health": "PASSED",
            "temperature": 34,
            "power_on_hours": 12847,
            "power_cycle_count": 342,
            "reallocated_sectors": 0,
            "wear_leveling": 97,
            "attributes": [
                {"id": 5, "name": "Reallocated_Sector_Ct", "value": 100, "worst": 100, "thresh": 10, "raw": "0"},
                {"id": 9, "name": "Power_On_Hours", "value": 99, "worst": 99, "thresh": 0, "raw": "12847"},
                {"id": 12, "name": "Power_Cycle_Count", "value": 99, "worst": 99, "thresh": 0, "raw": "342"},
                {"id": 177, "name": "Wear_Leveling_Count", "value": 97, "worst": 97, "thresh": 0, "raw": "97"},
                {"id": 194, "name": "Temperature_Celsius", "value": 66, "worst": 52, "thresh": 0, "raw": "34"}
            ],
            "raw_output": "optional: die komplette smartctl -a Ausgabe als String"
        },
        {
            "device": "/dev/nvme0",
            "model": "WD Black SN770 500GB",
            "serial": "21234A456789",
            "health": "PASSED",
            "temperature": 41,
            "power_on_hours": 5234,
            "wear_leveling": 99
        }
    ]
}
```

Option B — Raw-Text (Fallback, wenn Parsing zu aufwändig):
```json
{
    "type": "smart",
    "client_id": "...",
    "data": "=== START OF INFORMATION SECTION ===\nModel: Samsung SSD 870...\n..."
}
```
Das Frontend zeigt Raw-Text in einem Terminal-Container an.

**Hinweise zu SMART:**
- `attributes` Array ist optional. Wenn vorhanden, wird eine vollständige Tabelle gerendert.
- `health`/`smart_status`: Wird grün gefärbt wenn "PASSED"/"OK" enthalten, sonst rot.
- `reallocated_sectors > 0` wird rot markiert.
- Beliebige Extra-Keys pro Drive werden automatisch angezeigt (wie bei GPUs).
- Jeder Drive ist ein eigener Block im UI.

---

## 5. Aktions-Befehle (Host → Client)

Wenn der User eine Aktion auslöst (z.B. Reboot), empfängt der Client:

```json
{
    "type": "action",
    "action": "reboot",
    "auth_token": "a1b2c3d4e5f6...",
    "params": {}
}
```

### Aktionen und ihre Ausführung:

| `action` | Linux | FreeBSD | Windows | `params` |
|---|---|---|---|---|
| `reboot` | `systemctl reboot` | `shutdown -r now` | `shutdown /r /t 0` | — |
| `shutdown` | `systemctl poweroff` | `shutdown -p now` | `shutdown /s /t 0` | — |
| `kick_user` | `loginctl terminate-session <sid>` | `pkill -u <user>` | `logoff <sid>` | `{"user": "moritz", "terminal": "pts/0"}` |
| `update_packages` | `apt update && apt upgrade -y` | `pkg update && pkg upgrade -y` | — | — |
| `service_restart` | `systemctl restart <name>` | `service <name> restart` | — | `{"service_name": "nginx"}` |
| `disk_check` | `smartctl -a /dev/sdX` | `smartctl -a /dev/adaX` | `wmic diskdrive` | — |

### Aktionsergebnis zurückmelden (Client → Host):
```json
{
    "type": "action_result",
    "client_id": "...",
    "action": "reboot",
    "result": "ok"
}
```

---

## 6. Shell Input (Host → Client)

Wenn der User im Shell-Tab tippt, empfängt der Client:

```json
{
    "type": "shell_input",
    "data": "ls -la\n"
}
```

Der Client piped das in den PTY-Prozess und sendet Output als `shell_output` zurück.

---

## 7. Stream stoppen (Host → Client)

Wenn der User den Logs/Shell-Tab verlässt:

```json
{
    "type": "stop_stream",
    "stream": "logs"
}
```

`stream` Werte: `"logs"`, `"shell"`

---

## 8. Verbindungsverlust & Reconnect

Wenn die WebSocket-Verbindung verloren geht:
- **Exponential Backoff**: 1s → 2s → 4s → 8s → ... max 60s
- Bei Reconnect: Auth-Nachricht erneut senden (Schritt 2)
- Der Host markiert den Client automatisch als offline wenn die Verbindung bricht

---

## 9. Client `config.json`

Beim Setup generiert. Wird vom Client beim Start geladen.

```json
{
    "client_id": "550e8400-e29b-41d4-a716-446655440000",
    "client_name": "Redemption 1",
    "backend_url": "ws://192.168.1.50:3501/ws/client",
    "api_key": "observe-delta-7392"
}
```

---

## 10. Python-Bibliotheken für Datensammlung

| Daten | Linux | FreeBSD | Windows |
|---|---|---|---|
| CPU, RAM, Disk, Netzwerk, Users | `psutil` | `psutil` | `psutil` |
| GPU (NVIDIA) | `pynvml` | — | `pynvml` oder WMI |
| GPU (Fallback) | `GPUtil` | — | `GPUtil` |
| Temperaturen | `psutil.sensors_temperatures()` | `psutil` (evtl. sysctl) | WMI / OpenHardwareMonitor |
| Prozesse | `psutil.process_iter()` | `psutil.process_iter()` | `psutil.process_iter()` |
| Services | `subprocess: systemctl` | `subprocess: service -e` | — |
| Updates | `subprocess: apt list --upgradable` | `subprocess: pkg audit` | — |
| SMART | `subprocess: smartctl -a` | `subprocess: smartctl -a` | `subprocess: wmic` |
| Shell/PTY | `pty` + `subprocess` | `pty` + `subprocess` | `subprocess` (cmd.exe) |
| Logs | `subprocess: journalctl -f` | `subprocess: tail -f /var/log/messages` | Event Viewer (eingeschränkt) |

---

## 11. systemd Service (Linux Client)

```ini
[Unit]
Description=M-OBSERVE Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/m-observe-client
ExecStart=/usr/bin/python3 client.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 12. sudoers (Linux Client)

Datei: `/etc/sudoers.d/m-observe-client`

```
# M-OBSERVE Client — erlaubt passwortloses Ausführen von Systembefehlen
m-observe ALL=(ALL) NOPASSWD: /sbin/reboot
m-observe ALL=(ALL) NOPASSWD: /sbin/shutdown
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl reboot
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl poweroff
m-observe ALL=(ALL) NOPASSWD: /bin/systemctl restart *
m-observe ALL=(ALL) NOPASSWD: /usr/bin/apt update
m-observe ALL=(ALL) NOPASSWD: /usr/bin/apt upgrade -y
m-observe ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
m-observe ALL=(ALL) NOPASSWD: /usr/bin/loginctl terminate-session *
```

---

Das Backend (Overseer) ist fertig und empfängt all diese Nachrichten. Einfach einen Client bauen, der sich per WebSocket verbindet und dieses Protokoll spricht.
