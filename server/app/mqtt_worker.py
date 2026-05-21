from __future__ import annotations

import json
import logging
import signal
import time

import paho.mqtt.client as mqtt

from app.config import get_settings
from app.services.mqtt_client import build_mqtt_client, connect_mqtt_client
from app.state import store

running = True
logger = logging.getLogger("omni9.mqtt")
worker_client: mqtt.Client | None = None


def stop_worker(*_args):
    global running
    running = False


def on_message(_client, _userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except json.JSONDecodeError:
        return
    payload.setdefault("kind", message.topic.rsplit("/", 1)[-1])
    store.ingest_gateway_event(payload)


def build_client() -> mqtt.Client:
    settings = get_settings()
    client = build_mqtt_client()
    client.on_message = on_message
    connect_mqtt_client(client, keepalive=30)
    client.subscribe(f"{settings.mqtt_base_topic}/sites/+/machines/+/+")
    return client


def start_background_worker() -> bool:
    global worker_client
    settings = get_settings()
    if worker_client is not None:
        return True
    try:
        worker_client = build_client()
        worker_client.loop_start()
        logger.info("MQTT ingest connected and subscribed via %s", settings.mqtt_connection_summary)
        return True
    except Exception:
        worker_client = None
        logger.exception("MQTT ingest could not start via %s; API will continue without broker telemetry", settings.mqtt_connection_summary)
        return False


def stop_background_worker() -> None:
    global worker_client
    if worker_client is None:
        return
    worker_client.loop_stop()
    worker_client.disconnect()
    worker_client = None
    logger.info("MQTT ingest stopped")


def main():
    client = build_client()
    client.loop_start()

    signal.signal(signal.SIGINT, stop_worker)
    signal.signal(signal.SIGTERM, stop_worker)
    while running:
        time.sleep(1)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
