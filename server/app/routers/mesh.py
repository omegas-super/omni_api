from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.config import get_settings
from app.state import store, utc_now

router = APIRouter(prefix="/v1/mesh", tags=["mesh"])
connected_gateways: dict[str, dict] = {}


async def send_command_to_gateways(site_id: str, payload: dict) -> dict:
    sent = 0
    errors = []
    for gateway_id, connection in list(connected_gateways.items()):
        if connection.get("siteId") != site_id:
            continue
        try:
            await connection["websocket"].send_json(payload)
            sent += 1
        except Exception as exc:  # pragma: no cover - depends on live sockets
            errors.append({"gatewayId": gateway_id, "error": str(exc)})
    return {"sent": sent, "errors": errors}


@router.websocket("/ws")
async def mesh_gateway_ws(websocket: WebSocket, siteId: str, gatewayId: str, token: str):
    settings = get_settings()
    if token != settings.mesh_gateway_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    connected_gateways[gatewayId] = {"siteId": siteId, "websocket": websocket}
    gateway = store.mesh_gateways.setdefault(gatewayId, {"id": gatewayId, "siteId": siteId, "name": "Site hub"})
    gateway.update({"status": "online", "wsConnected": True, "lastSeenAt": utc_now()})

    try:
        while True:
            payload = await websocket.receive_json()
            ack = store.ingest_gateway_event(payload)
            await websocket.send_json({"kind": "ack", **ack})
    except WebSocketDisconnect:
        if connected_gateways.get(gatewayId, {}).get("websocket") is websocket:
            connected_gateways.pop(gatewayId, None)
        gateway.update({"status": "offline", "wsConnected": False, "lastSeenAt": utc_now()})
