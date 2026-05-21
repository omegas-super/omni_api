from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4


MACHINE_LIVE_SECONDS = 18


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def age_seconds(last_seen_at: str | None, now: datetime) -> float | None:
    if not last_seen_at:
        return None
    try:
        seen_at = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if seen_at.tzinfo is None:
        seen_at = seen_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - seen_at).total_seconds())


def clean_location(value: dict | None) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        latitude = float(value.get("latitude", value.get("lat")))
        longitude = float(value.get("longitude", value.get("lng")))
    except (TypeError, ValueError):
        return None
    if latitude < -90 or latitude > 90 or longitude < -180 or longitude > 180:
        return None
    location = {
        "latitude": latitude,
        "longitude": longitude,
        "updatedAt": value.get("updatedAt") or utc_now(),
    }
    try:
        accuracy = float(value.get("accuracyM", value.get("accuracy")))
    except (TypeError, ValueError):
        accuracy = None
    if accuracy is not None and accuracy >= 0:
        location["accuracyM"] = accuracy
    return location


class MemoryStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.sites = {
            "main_site": {
                "id": "main_site",
                "name": "Main Site",
                "timezone": "UTC",
            }
        }
        self.machines = {}
        self.alerts = []
        self.actions = []
        self.impact = []
        self.mesh_gateways = {
            "mesh_gateway_01": {
                "id": "mesh_gateway_01",
                "siteId": "main_site",
                "name": "Site hub",
                "status": "offline",
                "wsConnected": False,
                "lastSeenAt": None,
            }
        }
        self.mesh_nodes = {}
        self.voice_sessions = {}

    def snapshot(self, value):
        with self._lock:
            return deepcopy(value)

    def list_machines(self, site_id: str):
        with self._lock:
            now = datetime.now(timezone.utc)
            return [deepcopy(self._freshen_machine_locked(item, now)) for item in self.machines.values() if item["siteId"] == site_id]

    def get_machine(self, machine_id: str):
        with self._lock:
            machine = self.machines.get(machine_id)
            if not machine:
                return None
            return deepcopy(self._freshen_machine_locked(machine, datetime.now(timezone.utc)))

    def _freshen_machine_locked(self, machine: dict, now: datetime) -> dict:
        age = age_seconds(machine.get("lastSeenAt"), now)
        machine["lastSeenAgeSeconds"] = round(age, 1) if age is not None else None
        machine["fresh"] = age is not None and age <= MACHINE_LIVE_SECONDS

        if machine["fresh"]:
            if machine.get("state") == "offline" and machine.get("staleState"):
                machine["state"] = machine.pop("staleState")
            if machine.get("protectionOverrideEnabled"):
                machine.pop("issue", None)
            elif machine.get("state") == "protected" or machine.get("safeStopped") or not machine.get("machineEnabled", True):
                reason = machine.get("faultReason") or machine.get("detail") or "Safety relay is open."
                machine["issue"] = {
                    "level": "critical",
                    "title": "Machine stopped",
                    "body": f"Off due to {reason}",
                }
            elif machine.get("state") == "critical":
                machine["issue"] = {
                    "level": "critical",
                    "title": "Critical readings",
                    "body": "Telemetry is above the configured protection threshold.",
                }
            else:
                machine.pop("issue", None)
            return machine

        machine["staleState"] = machine.get("state", "offline") if machine.get("state") != "offline" else machine.get("staleState", "offline")
        machine["state"] = "offline"
        link = machine.setdefault("link", {})
        link.update({"serverReachable": False, "mqttConnected": False, "wsConnected": False})
        wifi = machine.setdefault("wifi", {})
        wifi["connected"] = False
        stale_for = int(age) if age is not None else 0
        machine["coverage"] = {
            "state": "offline",
            "label": "Coverage offline",
            "detail": f"No live telemetry for {stale_for} seconds.",
        }
        machine["issue"] = {
            "level": "warning",
            "title": "Node disconnected",
            "body": f"No telemetry has reached the server for {stale_for} seconds.",
        }
        return machine

    def ingest_gateway_event(self, event: dict) -> dict:
        with self._lock:
            kind = event.get("kind", "unknown")
            site_id = event.get("siteId", "main_site")
            machine_id = event.get("machineId") or event.get("deviceId")
            now = utc_now()

            if kind in {"telemetry", "status"} and machine_id:
                machine = self.machines.setdefault(
                    machine_id,
                    {
                        "id": machine_id,
                        "siteId": site_id,
                        "name": event.get("machineName", machine_id.replace("_", " ").title()),
                        "area": event.get("area", "Unassigned"),
                        "state": "healthy",
                        "protectionMode": "standard",
                        "protectionOverrideEnabled": False,
                        "latest": {},
                        "coverage": {},
                    },
                )
                machine["lastSeenAt"] = now
                machine["fresh"] = True
                machine["name"] = event.get("machineName", machine["name"])
                machine["area"] = event.get("area", machine["area"])
                machine["mode"] = event.get("mode", event.get("linkMode", machine.get("mode", "direct")))
                machine["firmware"] = event.get("firmware", machine.get("firmware"))
                machine["ip"] = event.get("ip", machine.get("ip"))
                machine["mac"] = event.get("mac", machine.get("mac"))
                machine["protectionMode"] = event.get("protectionMode", machine.get("protectionMode", "standard"))
                machine["protectionOverrideEnabled"] = bool(event.get("protectionOverrideEnabled", machine.get("protectionOverrideEnabled", False)))
                machine["safeStopped"] = bool(event.get("safeStopped", machine.get("safeStopped", False)))
                machine["machineEnabled"] = bool(event.get("machineEnabled", machine.get("machineEnabled", True)))
                machine["detail"] = event.get("detail", machine.get("detail"))
                if event.get("faultReason") or event.get("stopReason") or machine["safeStopped"]:
                    machine["faultReason"] = event.get("faultReason") or event.get("stopReason") or event.get("detail") or machine.get("faultReason", "safety protection")
                elif machine.get("machineEnabled", True):
                    machine["faultReason"] = ""
                if isinstance(event.get("appliance"), dict):
                    machine["appliance"] = event["appliance"]
                if isinstance(event.get("calibration"), dict):
                    machine["calibration"] = event["calibration"]
                location = clean_location(event.get("location"))
                if location:
                    machine["location"] = location
                machine["wifi"] = {
                    "ssid": event.get("wifiSsid", machine.get("wifi", {}).get("ssid")),
                    "rssi": event.get("wifiRssi", machine.get("wifi", {}).get("rssi")),
                    "ip": event.get("ip", machine.get("wifi", {}).get("ip")),
                    "connected": bool(event.get("wifiConnected", machine.get("wifi", {}).get("connected", False))),
                }
                mesh_peers = int(event.get("meshPeers") or 0)
                machine["link"] = {
                    "mode": machine["mode"],
                    "serverReachable": bool(event.get("serverReachable", machine.get("link", {}).get("serverReachable", False))),
                    "mqttConnected": bool(event.get("mqttConnected", machine.get("link", {}).get("mqttConnected", False))),
                    "wsConnected": bool(event.get("wsConnected", machine.get("link", {}).get("wsConnected", False))),
                    "meshPeers": mesh_peers,
                }
                machine["latest"] = {
                    "temperatureC": event.get("temperatureC", machine.get("latest", {}).get("temperatureC")),
                    "vibrationG": event.get("vibrationG", machine.get("latest", {}).get("vibrationG")),
                    "currentA": event.get("currentA", machine.get("latest", {}).get("currentA")),
                    "voltageV": event.get("voltageV", machine.get("latest", {}).get("voltageV")),
                    "powerW": event.get("powerW", machine.get("latest", {}).get("powerW")),
                    "rpm": event.get("rpm", machine.get("latest", {}).get("rpm")),
                    "hallActive": event.get("hallActive", machine.get("latest", {}).get("hallActive")),
                    "hallRaw": event.get("hallRaw", machine.get("latest", {}).get("hallRaw")),
                    "accelXG": event.get("accelXG", machine.get("latest", {}).get("accelXG")),
                    "accelYG": event.get("accelYG", machine.get("latest", {}).get("accelYG")),
                    "accelZG": event.get("accelZG", machine.get("latest", {}).get("accelZG")),
                    "mpuReady": event.get("mpuReady", machine.get("latest", {}).get("mpuReady")),
                }
                latest = machine["latest"]
                temperature = float(latest.get("temperatureC") or 0)
                vibration = float(latest.get("vibrationG") or 0)
                current = float(latest.get("currentA") or 0)
                reported_state = str(event.get("state", "")).lower()
                override_enabled = bool(machine.get("protectionOverrideEnabled", False))
                if override_enabled:
                    machine["state"] = "healthy"
                elif machine.get("safeStopped") or not machine.get("machineEnabled", True) or reported_state in {"protected", "stopped", "safe_stop"}:
                    machine["state"] = "protected"
                elif temperature >= 90 or vibration >= 8.5 or current >= 16:
                    machine["state"] = "critical"
                elif temperature >= 70 or vibration >= 5 or current >= 12:
                    machine["state"] = "watch"
                else:
                    machine["state"] = "healthy"
                link = machine["link"]
                if link["mqttConnected"] or link["wsConnected"] or link["serverReachable"] or mesh_peers >= 2:
                    coverage_state = "good"
                elif machine["wifi"]["connected"] or mesh_peers == 1:
                    coverage_state = "weak"
                else:
                    coverage_state = "offline"
                machine["coverage"] = {
                    "state": coverage_state,
                    "label": f"Coverage {coverage_state}",
                    "detail": "Machine link is reaching the server." if coverage_state == "good" else "Machine link needs WiFi, MQTT, WebSocket, or a nearby gateway.",
                }
                if override_enabled:
                    machine.pop("issue", None)
                elif machine["state"] == "protected":
                    reason = machine.get("faultReason") or machine.get("detail") or "safety protection"
                    machine["issue"] = {"level": "critical", "title": "Machine stopped", "body": f"Off due to {reason}"}
                elif machine["state"] == "critical":
                    machine["issue"] = {"level": "critical", "title": "Critical readings", "body": "Telemetry is above the configured protection threshold."}
                else:
                    machine.pop("issue", None)
                if not override_enabled and machine["state"] in {"critical", "protected"}:
                    title = "Protected" if machine["state"] == "protected" else "Critical machine risk"
                    reason = machine.get("issue", {}).get("body") or f"{machine['name']} reported {machine['state']} from live node telemetry."
                    if not any(alert.get("machineId") == machine_id and not alert.get("read") and alert.get("title") == title for alert in self.alerts):
                        self.alerts.insert(
                            0,
                            {
                                "id": str(uuid4()),
                                "siteId": site_id,
                                "machineId": machine_id,
                                "severity": "critical",
                                "title": title,
                                "body": reason,
                                "target": {"type": "machine", "id": machine_id},
                                "read": False,
                                "createdAt": now,
                            },
                        )
                if event.get("meshNodeId"):
                    self.mesh_nodes[str(event["meshNodeId"])] = {
                        "id": str(event["meshNodeId"]),
                        "siteId": site_id,
                        "machineId": machine_id,
                        "friendlyName": machine["name"],
                        "coverageState": coverage_state,
                        "peerCount": mesh_peers,
                        "lastSeenAt": now,
                    }

            if kind == "gateway_topology":
                gateway_id = event.get("gatewayId", "mesh_gateway_01")
                gateway = self.mesh_gateways.setdefault(gateway_id, {"id": gateway_id, "siteId": site_id, "name": "Site hub"})
                gateway.update({"status": "online", "wsConnected": True, "lastSeenAt": now, "peerCount": event.get("meshPeers", 0)})

            if kind == "action":
                self.actions.insert(0, {**event, "createdAt": now})

            return {"accepted": True, "kind": kind, "receivedAt": now}

    def record_command(self, site_id: str, machine_id: str, command_type: str, reason: str, source: str = "user") -> dict:
        with self._lock:
            machine = self.machines.get(machine_id)
            action = {
                "id": str(uuid4()),
                "siteId": site_id,
                "machineId": machine_id,
                "machineName": machine.get("name", machine_id) if machine else machine_id,
                "type": command_type,
                "source": source,
                "reason": reason,
                "createdAt": utc_now(),
            }
            self.actions.insert(0, action)
            return deepcopy(action)

    def clear_site(self, site_id: str) -> dict:
        with self._lock:
            machine_ids = {machine_id for machine_id, machine in self.machines.items() if machine.get("siteId") == site_id}
            for machine_id in machine_ids:
                self.machines.pop(machine_id, None)
            self.alerts = [item for item in self.alerts if item.get("siteId") != site_id]
            self.actions = [item for item in self.actions if item.get("siteId") != site_id]
            self.impact = [item for item in self.impact if item.get("siteId") != site_id]
            self.mesh_nodes = {node_id: node for node_id, node in self.mesh_nodes.items() if node.get("siteId") != site_id}
            for gateway in self.mesh_gateways.values():
                if gateway.get("siteId") == site_id:
                    gateway.update({"status": "offline", "wsConnected": False, "lastSeenAt": utc_now(), "peerCount": 0})
            return {"cleared": True, "siteId": site_id, "machines": len(machine_ids)}

    def set_protection_mode(self, machine_id: str, mode: str) -> dict | None:
        with self._lock:
            machine = self.machines.get(machine_id)
            if not machine:
                return None
            machine["protectionMode"] = mode
            return deepcopy(machine)

    def set_protection_override(self, machine_id: str, enabled: bool) -> dict | None:
        with self._lock:
            machine = self.machines.get(machine_id)
            if not machine:
                return None
            machine["protectionOverrideEnabled"] = enabled
            if enabled:
                machine.pop("issue", None)
            return deepcopy(machine)


store = MemoryStore()
