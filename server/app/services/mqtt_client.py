from __future__ import annotations

import paho.mqtt.client as mqtt

from app.config import get_settings


def build_mqtt_client() -> mqtt.Client:
    settings = get_settings()
    transport = settings.resolved_mqtt_transport

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport=transport)
    if transport == "websockets":
        client.ws_set_options(path=settings.mqtt_ws_path or "/mqtt")
    if settings.resolved_mqtt_tls:
        client.tls_set()
    if settings.resolved_mqtt_username and settings.resolved_mqtt_password:
        client.username_pw_set(settings.resolved_mqtt_username, settings.resolved_mqtt_password)
    return client


def connect_mqtt_client(client: mqtt.Client, keepalive: int = 30) -> None:
    settings = get_settings()
    client.connect(settings.resolved_mqtt_host, settings.resolved_mqtt_port, keepalive=keepalive)
