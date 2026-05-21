from fastapi import APIRouter

from app.config import get_settings
from app.state import store

router = APIRouter(prefix="/v1/app", tags=["app"])


@router.get("/bootstrap")
def bootstrap():
    settings = get_settings()
    machines = store.list_machines(settings.default_site_id)
    open_alerts = [
        item
        for item in store.snapshot(store.alerts)
        if item.get("siteId") == settings.default_site_id and not item.get("read")
    ]
    critical_count = len([m for m in machines if m.get("state") == "critical"])
    watch_count = len([m for m in machines if m.get("state") == "watch"])
    protected_count = len([m for m in machines if m.get("state") == "protected"])
    offline_count = len([m for m in machines if m.get("state") == "offline"])
    health_score = 0 if not machines else max(0, 100 - critical_count * 18 - protected_count * 12 - watch_count * 8 - offline_count * 10)
    impact_items = store.snapshot(store.impact)
    downtime_prevented = sum(
        float(item.get("value") or 0)
        for item in impact_items
        if item.get("metric") == "downtime_prevented" and item.get("unit") == "h"
    )

    return {
        "user": {"id": "local-operator", "name": "Omni9 operator", "role": "technician"},
        "site": store.snapshot(store.sites[settings.default_site_id]),
        "capabilities": {
            "voiceAssistant": True,
            "cameraInspection": True,
            "safetyCommands": True,
            "protectionModeEdit": True,
            "meshCoverage": True,
        },
        "summary": {
            "healthScore": health_score,
            "machineCount": len(machines),
            "openAlerts": len(open_alerts),
            "protectedMachines": protected_count,
            "downtimePreventedHours": downtime_prevented,
        },
    }
