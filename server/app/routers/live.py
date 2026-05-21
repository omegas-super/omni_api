import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.state import store

router = APIRouter(prefix="/v1/sites/{site_id}", tags=["live"])


def site_snapshot(site_id: str) -> dict:
    settings = get_settings()
    machines = store.list_machines(site_id)
    alerts = [item for item in store.snapshot(store.alerts) if item.get("siteId") == site_id]
    actions = [item for item in store.snapshot(store.actions) if item.get("siteId") == site_id]
    impact = [item for item in store.snapshot(store.impact) if item.get("siteId") == site_id]
    critical_count = len([machine for machine in machines if machine.get("state") == "critical"])
    watch_count = len([machine for machine in machines if machine.get("state") == "watch"])
    protected_count = len([machine for machine in machines if machine.get("state") == "protected"])
    offline_count = len([machine for machine in machines if machine.get("state") == "offline"])
    health_score = 0 if not machines else max(0, 100 - critical_count * 18 - protected_count * 12 - watch_count * 8 - offline_count * 10)
    return {
        "kind": "site_snapshot",
        "site": store.snapshot(store.sites.get(site_id, store.sites[settings.default_site_id])),
        "summary": {
            "healthScore": health_score,
            "machineCount": len(machines),
            "openAlerts": len([item for item in alerts if not item.get("read")]),
            "protectedMachines": protected_count,
        },
        "machines": {"items": machines},
        "actions": {"items": actions[:30]},
        "impact": {"items": impact[:30]},
        "alerts": {"items": alerts[:30]},
    }


@router.websocket("/stream")
async def site_stream(websocket: WebSocket, site_id: str):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(site_snapshot(site_id))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return