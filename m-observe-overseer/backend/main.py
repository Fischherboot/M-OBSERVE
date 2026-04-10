import asyncio
import json
import time
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager

import database as db
import auth
from ws_manager import manager
from actions import dispatch_action, request_on_demand

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield

app = FastAPI(lifespan=lifespan)


# ──────────────────────────────────────────────
#  REST API
# ──────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    setup_done = await db.is_setup_done()
    return {"setup_done": setup_done}


@app.post("/api/setup")
async def api_setup(request: Request):
    if await db.is_setup_done():
        raise HTTPException(400, "Setup already completed")

    body = await request.json()
    password = body.get("password", "").strip()
    if len(password) < 4:
        raise HTTPException(400, "Password too short (min 4)")

    hashed = auth.hash_password(password)
    api_key = auth.generate_api_key()
    await db.save_setup(hashed, api_key)
    return {"success": True, "api_key": api_key}


@app.post("/api/login")
async def api_login(request: Request):
    body = await request.json()
    password = body.get("password", "")
    config = await db.get_config()
    if not config:
        raise HTTPException(400, "Setup not done")

    if auth.check_password(password, config["password_hash"]):
        token = auth.generate_action_token()
        return {"success": True, "token": token}
    raise HTTPException(401, "Wrong password")


@app.post("/api/verify-password")
async def api_verify_password(request: Request):
    body = await request.json()
    password = body.get("password", "")
    config = await db.get_config()
    if not config:
        raise HTTPException(400, "Setup not done")
    if auth.check_password(password, config["password_hash"]):
        return {"valid": True}
    return {"valid": False}


@app.get("/api/machines")
async def api_machines():
    machines = await db.get_all_machines()
    # Attach live data where available
    for m in machines:
        cid = m["client_id"]
        m["live"] = manager.live_data.get(cid)
        m["online"] = manager.is_client_connected(cid)
    return {"machines": machines}


@app.get("/api/machines/{client_id}")
async def api_machine_detail(client_id: str):
    machines = await db.get_all_machines()
    machine = next((m for m in machines if m["client_id"] == client_id), None)
    if not machine:
        raise HTTPException(404, "Machine not found")
    machine["live"] = manager.live_data.get(client_id)
    machine["online"] = manager.is_client_connected(client_id)
    return machine


@app.get("/api/machines/{client_id}/snapshot")
async def api_machine_snapshot(client_id: str):
    snap = await db.get_snapshot(client_id)
    if snap:
        return {"snapshot": snap}
    return {"snapshot": None}


@app.delete("/api/machines/{client_id}")
async def api_machine_delete(client_id: str, request: Request):
    body = await request.json()
    password = body.get("password", "")
    config = await db.get_config()
    if not config or not auth.check_password(password, config["password_hash"]):
        raise HTTPException(401, "Wrong password")
    await db.delete_machine(client_id)
    return {"success": True}


@app.post("/api/action/{client_id}")
async def api_action(client_id: str, request: Request):
    body = await request.json()
    password = body.get("password", "")
    action = body.get("action", "")
    params = body.get("params", {})

    # Disk check doesn't need password
    if action != "disk_check":
        config = await db.get_config()
        if not config or not auth.check_password(password, config["password_hash"]):
            raise HTTPException(401, "Wrong password")

    sent = await dispatch_action(client_id, action, params)
    if sent:
        return {"success": True}
    raise HTTPException(503, "Client not connected")


@app.post("/api/request/{client_id}")
async def api_request_data(client_id: str, request: Request):
    body = await request.json()
    data_type = body.get("type", "")
    password = body.get("password", "")

    # Some on-demand requests need password
    needs_pw = data_type in ("logs", "shell")
    if needs_pw:
        config = await db.get_config()
        if not config or not auth.check_password(password, config["password_hash"]):
            raise HTTPException(401, "Wrong password")

    sent = await request_on_demand(client_id, data_type)
    if sent:
        return {"success": True}
    raise HTTPException(503, "Client not connected")


@app.get("/api/settings")
async def api_settings():
    config = await db.get_config()
    if not config:
        raise HTTPException(400, "Setup not done")
    return {
        "api_key": config["api_key"],
        "telemetry_interval": config["telemetry_interval"],
        "snapshot_interval": config["snapshot_interval"]
    }


@app.post("/api/settings/password")
async def api_change_password(request: Request):
    body = await request.json()
    current = body.get("current_password", "")
    new_pw = body.get("new_password", "")

    config = await db.get_config()
    if not config or not auth.check_password(current, config["password_hash"]):
        raise HTTPException(401, "Wrong password")
    if len(new_pw) < 4:
        raise HTTPException(400, "New password too short")

    await db.update_password(auth.hash_password(new_pw))
    return {"success": True}


@app.post("/api/settings/regenerate-key")
async def api_regenerate_key(request: Request):
    body = await request.json()
    password = body.get("password", "")
    config = await db.get_config()
    if not config or not auth.check_password(password, config["password_hash"]):
        raise HTTPException(401, "Wrong password")

    new_key = auth.generate_api_key()
    await db.update_api_key(new_key)
    return {"success": True, "api_key": new_key}


@app.post("/api/settings/intervals")
async def api_update_intervals(request: Request):
    body = await request.json()
    telemetry = int(body.get("telemetry_interval", 3))
    snapshot = int(body.get("snapshot_interval", 5))
    await db.update_intervals(telemetry, snapshot)
    return {"success": True}


# ──────────────────────────────────────────────
#  WEBSOCKET: Client Connections (from monitored machines)
# ──────────────────────────────────────────────

@app.websocket("/ws/client")
async def ws_client(ws: WebSocket):
    await ws.accept()

    # First message must be auth
    try:
        init = await asyncio.wait_for(ws.receive_json(), timeout=10)
    except Exception:
        await ws.close(1008, "Auth timeout")
        return

    api_key = init.get("api_key", "")
    client_id = init.get("client_id", "")
    client_name = init.get("client_name", "Unknown")

    config = await db.get_config()
    if not config or api_key != config["api_key"]:
        await ws.close(1008, "Invalid API key")
        return

    # Register
    await manager.connect_client(client_id, ws)

    # Update/insert machine in DB from first telemetry or init data
    hostname = init.get("hostname", "")
    os_str = init.get("os", "")
    platform = init.get("platform", "")
    ip_addr = init.get("ip", "")
    await db.upsert_machine(client_id, client_name, hostname, os_str, platform, ip_addr)

    # Notify frontends
    await manager.broadcast_to_frontends({
        "type": "client_online",
        "client_id": client_id,
        "client_name": client_name
    })

    snapshot_interval = config.get("snapshot_interval", 5) * 60  # minutes -> seconds

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "telemetry")

            if msg_type == "telemetry":
                cid = data.get("client_id", client_id)
                manager.update_live_data(cid, data)

                # Update last_seen
                await db.upsert_machine(
                    cid,
                    data.get("client_name", client_name),
                    data.get("hostname", hostname),
                    data.get("os", os_str),
                    data.get("platform", platform),
                    data.get("ip", ip_addr)
                )

                # Snapshot throttle
                now = time.time()
                last = manager.last_snapshot.get(cid, 0)
                if now - last >= snapshot_interval:
                    await db.upsert_snapshot(cid, data)
                    manager.last_snapshot[cid] = now

                # Forward to frontends
                await manager.broadcast_to_frontends({
                    "type": "telemetry",
                    "client_id": cid,
                    "data": data
                })

            elif msg_type in ("processes", "services", "updates", "smart", "logs_line", "shell_output"):
                # On-demand data response from client -> forward to frontends
                await manager.broadcast_to_frontends({
                    "type": msg_type,
                    "client_id": client_id,
                    "data": data.get("data")
                })

            elif msg_type == "action_result":
                await manager.broadcast_to_frontends({
                    "type": "action_result",
                    "client_id": client_id,
                    "action": data.get("action"),
                    "result": data.get("result")
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect_client(client_id)
        await db.set_machine_offline(client_id)
        await manager.broadcast_to_frontends({
            "type": "client_offline",
            "client_id": client_id
        })


# ──────────────────────────────────────────────
#  WEBSOCKET: Frontend Connections (browsers)
# ──────────────────────────────────────────────

@app.websocket("/ws/frontend")
async def ws_frontend(ws: WebSocket):
    await ws.accept()
    await manager.connect_frontend(ws)

    # Send current state of all machines
    machines = await db.get_all_machines()
    for m in machines:
        cid = m["client_id"]
        m["online"] = manager.is_client_connected(cid)
        m["live"] = manager.live_data.get(cid)
    await ws.send_json({"type": "init", "machines": machines})

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")

            # Frontend can send shell input to a client
            if msg_type == "shell_input":
                client_id = data.get("client_id")
                await manager.send_to_client(client_id, {
                    "type": "shell_input",
                    "data": data.get("data", "")
                })

            elif msg_type == "stop_stream":
                client_id = data.get("client_id")
                stream_type = data.get("stream")
                await manager.send_to_client(client_id, {
                    "type": "stop_stream",
                    "stream": stream_type
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect_frontend(ws)


# ──────────────────────────────────────────────
#  STATIC FILES (Frontend on same port)
# ──────────────────────────────────────────────

# Serve frontend files — fallback to index.html for SPA
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ──────────────────────────────────────────────
#  RUN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3501, reload=False)
