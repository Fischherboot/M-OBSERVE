import asyncio
import json
import time
from fastapi import WebSocket
from typing import Dict, Set


class ConnectionManager:
    """Manages WebSocket connections from clients and frontend browsers."""

    def __init__(self):
        # client_id -> WebSocket (from monitoring clients)
        self.clients: Dict[str, WebSocket] = {}
        # Set of frontend WebSocket connections
        self.frontends: Set[WebSocket] = set()
        # client_id -> latest telemetry dict (in-memory live data)
        self.live_data: Dict[str, dict] = {}
        # client_id -> last snapshot save time
        self.last_snapshot: Dict[str, float] = {}

    async def connect_client(self, client_id: str, ws: WebSocket):
        self.clients[client_id] = ws

    def disconnect_client(self, client_id: str):
        self.clients.pop(client_id, None)
        self.live_data.pop(client_id, None)

    async def connect_frontend(self, ws: WebSocket):
        self.frontends.add(ws)

    def disconnect_frontend(self, ws: WebSocket):
        self.frontends.discard(ws)

    def update_live_data(self, client_id: str, data: dict):
        self.live_data[client_id] = data

    async def broadcast_to_frontends(self, message: dict):
        dead = []
        for ws in self.frontends:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.frontends.discard(ws)

    async def send_to_client(self, client_id: str, message: dict) -> bool:
        ws = self.clients.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception:
                return False
        return False

    def get_client_ws(self, client_id: str) -> WebSocket | None:
        return self.clients.get(client_id)

    def is_client_connected(self, client_id: str) -> bool:
        return client_id in self.clients


manager = ConnectionManager()
