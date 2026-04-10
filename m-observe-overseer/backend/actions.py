from ws_manager import manager
from auth import generate_action_token


async def dispatch_action(client_id: str, action: str, params: dict = None) -> bool:
    """Send an action command to a client. Returns True if sent successfully."""
    token = generate_action_token()
    message = {
        "type": "action",
        "action": action,
        "auth_token": token,
        "params": params or {}
    }
    return await manager.send_to_client(client_id, message)


async def request_on_demand(client_id: str, data_type: str) -> bool:
    """Request on-demand data from a client (processes, services, updates, smart, logs, shell)."""
    message = {
        "type": "request",
        "request": data_type
    }
    return await manager.send_to_client(client_id, message)
