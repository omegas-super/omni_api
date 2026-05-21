from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.routers.mesh import send_command_to_gateways
from app.services.mqtt_bridge import build_command_payload, publish_command
from app.state import store

router = APIRouter(prefix="/v1/sites/{site_id}/machines", tags=["machines"])


class CommandRequest(BaseModel):
    reason: str = "operator request"
    enabled: bool | None = None


class ProtectionModeRequest(BaseModel):
    mode: str


@router.get("")
def list_machines(site_id: str):
    return {"items": store.list_machines(site_id)}


@router.delete("")
def clear_machines(site_id: str):
    return store.clear_site(site_id)


@router.get("/{machine_id}")
def get_machine(site_id: str, machine_id: str):
    machine = store.get_machine(machine_id)
    if not machine or machine.get("siteId") != site_id:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine


@router.get("/{machine_id}/readings")
def get_readings(site_id: str, machine_id: str, range: str = "1h"):
    machine = get_machine(site_id, machine_id)
    latest = machine.get("latest", {})
    return {
        "machineId": machine_id,
        "range": range,
        "items": [
            {
                "temperatureC": latest.get("temperatureC"),
                "vibrationG": latest.get("vibrationG"),
                "currentA": latest.get("currentA"),
                "voltageV": latest.get("voltageV"),
                "powerW": latest.get("powerW"),
                "rpm": latest.get("rpm"),
                "hallActive": latest.get("hallActive"),
                "offsetMinutes": -i * 5,
            }
            for i in range_points()
        ],
    }


def range_points():
    return range(12)


@router.post("/{machine_id}/commands/{command_type}")
async def send_command(site_id: str, machine_id: str, command_type: str, body: CommandRequest):
    allowed = {
        "safe-stop": "safe_stop",
        "resume": "resume",
        "identify": "identify",
        "force-resume": "force_resume",
        "protection-override": "set_protection_override",
    }
    if command_type not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported command")
    extra = {}
    if command_type == "force-resume":
        extra["enabled"] = True
        store.set_protection_override(machine_id, True)
    elif command_type == "protection-override":
        extra["enabled"] = bool(body.enabled)
        store.set_protection_override(machine_id, bool(body.enabled))
    action = store.record_command(site_id, machine_id, allowed[command_type], body.reason)
    publish = publish_command(site_id, machine_id, allowed[command_type], body.reason, extra)
    websocket = await send_command_to_gateways(site_id, build_command_payload(machine_id, allowed[command_type], body.reason, extra))
    return {"action": action, "publish": publish, "websocket": websocket}


@router.post("/{machine_id}/protection-mode")
def set_protection_mode(site_id: str, machine_id: str, body: ProtectionModeRequest):
    if body.mode not in {"standard", "early", "very_early"}:
        raise HTTPException(status_code=400, detail="Use standard, early, or very_early")
    machine = store.set_protection_mode(machine_id, body.mode)
    if not machine or machine.get("siteId") != site_id:
        raise HTTPException(status_code=404, detail="Machine not found")
    store.record_command(site_id, machine_id, "set_protection_mode", f"mode={body.mode}")
    return machine
