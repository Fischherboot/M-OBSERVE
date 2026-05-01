# M-OBSERVE Plugin Protocol

Doku für Plugins, die sich am M-OBSERVE Overseer als **read-only Consumer** registrieren — also Tools wie das `m-observe-status-addon`. Plugins können Geräte sehen, aber **nichts** auslösen, schreiben oder konfigurieren.

---

## Überblick

Ein Plugin verhält sich aus Sicht des Overseers wie ein dritter Verbraucher neben Clients und Frontends:

```
┌──────────────┐                         ┌──────────────┐
│   Clients    │ ─── /ws/client ───►     │              │
└──────────────┘                         │              │
                                         │   Overseer   │
┌──────────────┐                         │  Port 3501   │
│  Frontends   │ ◄── /ws/frontend ──►    │              │
└──────────────┘                         │              │
                                         │              │
┌──────────────┐                         │              │
│   Plugins    │ ◄── /ws/plugin ───      │              │
└──────────────┘                         └──────────────┘
```

Auth läuft über den **gleichen API-Key**, den auch Clients benutzen (`observe-<word>-<4digits>`). Den findet der User in den Overseer-Settings.

---

## Setup-Flow im Plugin

Beim First-Setup vom Plugin fragt es ab:
1. Overseer-URL (z. B. `http://192.168.1.170:3501`)
2. API-Key
3. Admin-Name + Admin-Passwort (Plugin-eigen, nichts mit Overseer zu tun)

Der API-Key wird einmal validiert (entweder per `GET /api/plugin/devices` oder direkt per WS-Connect), dann persistent gespeichert.

---

## Endpoints

### `GET /api/plugin/devices`

Pollt einmalig den aktuellen Stand. Sinnvoll beim Plugin-Start vor dem WS-Connect, oder als Fallback wenn die WS gerade tot ist.

**Header**
```
X-API-Key: observe-phoenix-4242
```

**Response 200**
```json
{
  "devices": [
    {
      "client_id": "uuid-or-whatever-the-client-sends",
      "client_name": "Redemption1",
      "hostname": "redemption1",
      "os": "Debian 13",
      "platform": "Linux",
      "ip": "192.168.1.170",
      "last_seen": 1730551234.567,
      "online": true
    }
  ]
}
```

**Response 401** bei falschem Key.

---

### `WS /ws/plugin`

Live-Stream für Online/Offline-Events. Das ist der Hauptkanal — hier kommt alles rein, was das Status-Addon zur Uptime-Berechnung braucht.

#### 1. Auth-Handshake

Direkt nach dem Connect schickt das Plugin **als allererstes**:

```json
{ "api_key": "observe-phoenix-4242" }
```

- Bei Erfolg → Server schickt `init`-Frame (siehe unten)
- Bei Fehler → Server schließt mit Code `1008` und Reason `"Invalid API key"` oder `"Auth timeout"` (10 s timeout für die erste Message)

#### 2. Init-Frame (vom Server)

Direkt nach erfolgreicher Auth bekommst du **einmal**:

```json
{
  "type": "init",
  "devices": [
    {
      "client_id": "...",
      "client_name": "Redemption1",
      "hostname": "redemption1",
      "os": "Debian 13",
      "platform": "Linux",
      "ip": "192.168.1.170",
      "last_seen": 1730551234.567,
      "online": true
    },
    { "...": "..." }
  ]
}
```

Damit hast du den vollen aktuellen Stand. Auf der Basis baut das Plugin seine interne Liste auf.

#### 3. Live-Events (vom Server)

Danach pusht der Server folgende Frames, sobald sich was ändert:

##### `device_online`
Ein Client hat sich (neu) verbunden, oder ist nach Reconnect wieder da.

```json
{
  "type": "device_online",
  "client_id": "...",
  "client_name": "Redemption1",
  "hostname": "redemption1",
  "os": "Debian 13",
  "platform": "Linux",
  "ip": "192.168.1.170"
}
```

> **Hinweis:** Wenn `client_id` noch unbekannt ist, ist das ein neues Gerät — Plugin trackt es ab jetzt. Wenn bereits bekannt, wurde es nur reconnected (z. B. nach Reboot).

##### `device_offline`
Client-WebSocket ist getrennt (sauber oder per Timeout).

```json
{
  "type": "device_offline",
  "client_id": "..."
}
```

> **Reboot-Erkennung im Plugin:** Wenn nach einem `device_offline` innerhalb von ≤ 20 Min ein `device_online` für die gleiche `client_id` kommt → das Plugin markiert die Lücke als **orange (Reboot/kurzer Ausfall)**. Bei > 20 Min → **rot (KIA)** für den entsprechenden Tag.

##### `device_deleted`
Ein Gerät wurde im Overseer-Dashboard manuell gelöscht. Plugin sollte das Device komplett aus seinem Tracking entfernen (oder als gelöscht flaggen).

```json
{
  "type": "device_deleted",
  "client_id": "..."
}
```

#### 4. Plugin → Server

**Plugins schicken nichts.** Eingehende Frames vom Plugin werden ignoriert. Halte den Socket einfach offen und lies, damit Disconnects sauber detected werden.

---

## Reconnect-Verhalten

Wenn die WS abreisst (Overseer down, Netzwerk-Hiccup, Neustart):

1. Plugin sollte mit Exponential Backoff reconnecten (z. B. 1 s → 2 s → 5 s → 10 s → max 30 s)
2. Nach erfolgreichem Reconnect kommt **automatisch ein neuer `init`-Frame** mit dem dann aktuellen Stand
3. Plugin sollte den Init-Frame als **Source of Truth** nehmen — alles was zwischendurch passiert ist, ist im neuen Online-Zustand bereits abgebildet

Während die Verbindung weg ist gilt aus Plugin-Sicht für die Uptime-Berechnung: die letzte bekannte Information bleibt stehen, bis was Neues kommt. Das matched genau das was du willst — wenn der Overseer 2 Stunden weg war, weiß das Plugin nichts über die Geräte und sollte diese Lücke neutral behandeln (z. B. grau / unknown, nicht als KIA werten).

---

## Status-Logik (Empfehlung fürs Status-Addon)

| Zustand | Farbe | Trigger |
|---|---|---|
| Online, keine Issues | 🟢 Grün | `device_online` aktiv, kein Offline-Event in den letzten 20 Min |
| Reboot / kurzer Ausfall | 🟠 Orange | `device_offline` → `device_online` innerhalb ≤ 20 Min |
| KIA (Killed In Action) | 🔴 Rot | `device_offline` länger als 20 Min, kein Reconnect |
| Overseer unreachable | ⚪ Grau | Plugin-WS zum Overseer ist down |

Die 90-Tage-History ist Plugin-State. Pro Device pro Tag ein Slot — der schlechteste Zustand des Tages gewinnt (Rot > Orange > Grün). Für den heute-Slot live updaten.

Uptime-% pro Device = `(grün-Tage * 1.0 + orange-Tage * 0.5) / 90`. Oder anders gewichtet — Plugin-Sache.

---

## Services-Tracking (komplett Plugin-Side)

Service-Tracking läuft **nicht** über den Overseer. Das macht das Plugin selbst:

- **Externe Services** (`is_local: false`): Plugin pingt die Domain alle 5 Min, 4 Pings pro Run. Antwort = online.
- **Lokale Services** (`is_local: true`): Plugin checkt sowohl die externe Domain (Ping) **als auch** die interne IP:Port (TCP-Connect oder HTTP-Probe).

Vier fehlgeschlagene Versuche in Folge → erst orange, dann rot. Gleiche Logik wie bei den Devices.

Der Overseer ist hier komplett raus — er weiß nichts von den Services und braucht es auch nicht.

---

## Sicherheit / Limits

- Plugin hat den **vollen API-Key** und sieht damit alle Geräte. Wer den Key hat, sieht auch die Existenz aller verbundenen Maschinen, deren Hostnames und IPs.
- Plugin kann **keine** Aktionen auslösen (kein Reboot, keine Shell, kein Update). Die Plugin-WS ist read-only — auch wenn das Plugin Commands sendet, ignoriert der Overseer die.
- Der Master-Password-Pfad ist für Plugins nicht zugänglich. Sensible Aktionen brauchen das Master-Passwort, und das geht nur über die Frontend-Routes.
- Wenn der API-Key im Overseer regeneriert wird, fliegen alle Plugin-Verbindungen beim nächsten Reconnect-Versuch raus und müssen mit dem neuen Key neu konfiguriert werden.

---

## Mini-Beispiel (Python)

```python
import asyncio
import json
import websockets

OVERSEER = "ws://192.168.1.170:3501/ws/plugin"
API_KEY = "observe-phoenix-4242"

async def run():
    async with websockets.connect(OVERSEER) as ws:
        await ws.send(json.dumps({"api_key": API_KEY}))
        async for raw in ws:
            msg = json.loads(raw)
            t = msg.get("type")
            if t == "init":
                print(f"Got {len(msg['devices'])} devices")
            elif t == "device_online":
                print(f"+ {msg['client_name']} ({msg['client_id']})")
            elif t == "device_offline":
                print(f"- {msg['client_id']}")
            elif t == "device_deleted":
                print(f"x {msg['client_id']}")

asyncio.run(run())
```

---

## Quick Reference

| Was | Wo |
|---|---|
| API-Key holen | Overseer → Settings → API-Key |
| Aktueller Stand (REST) | `GET /api/plugin/devices` mit `X-API-Key` |
| Live-Stream (WS) | `WS /ws/plugin` → erste Message `{"api_key": "..."}` |
| Init-Frame Type | `init` |
| Event-Typen | `device_online`, `device_offline`, `device_deleted` |
| Auth-Fehler | WS-Close `1008` + Reason |

---

M-OBSERVE | [343.im/OBSERVE](https://343.im/OBSERVE) | Moritzsoft ©
