from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.services.mqtt_client import build_mqtt_client, connect_mqtt_client


logger = logging.getLogger("omni9.mqtt")


def command_topic(site_id: str, machine_id: str) -> str:
    settings = get_settings()
    return f"{settings.mqtt_base_topic}/sites/{site_id}/machines/{machine_id}/commands"


def build_command_payload(machine_id: str, command_type: str, reason: str, extra: dict | None = None) -> dict:
    payload = {
        "kind": "command",
        "targetMachineId": machine_id,
        "machineId": machine_id,
        "type": command_type,
        "reason": reason,
    }
    if extra:
        payload.update(extra)
    return payload


def publish_command(site_id: str, machine_id: str, command_type: str, reason: str, extra: dict | None = None) -> dict:
    """Publish a command if paho-mqtt is available and broker config works.

    The API still records the command even if MQTT is offline. That makes local
    development useful before the broker is running.
    """
    settings = get_settings()
    topic = command_topic(site_id, machine_id)
    payload = build_command_payload(machine_id, command_type, reason, extra)

    try:
        client = build_mqtt_client()
        connect_mqtt_client(client, keepalive=20)
        client.publish(topic, json.dumps(payload), qos=1)
        client.disconnect()
        return {"published": True, "topic": topic, "payload": payload}
    except Exception as exc:  # pragma: no cover - depends on local broker
        logger.warning("MQTT command publish failed via %s: %s", settings.mqtt_connection_summary, exc)
        return {"published": False, "topic": topic, "payload": payload, "error": str(exc)}
