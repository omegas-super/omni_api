from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.config import get_settings
from app.services.ai_client import AiGatewayError, chat_completion, compact_json


USER_AGENT = "Omni9IndustrialAssistant/1.0"
INSTANCE_CACHE_TTL_SECONDS = 1800
SEARCH_CACHE_TTL_SECONDS = 300
MAX_PAGE_TEXT_CHARS = 12000

_instance_cache: dict[str, Any] = {"expiresAt": 0.0, "items": []}
_search_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self.title = ""
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data or "").strip()
        if not text or self._skip:
            return
        if not self.title and len(text) < 140:
            self.title = text
        self.parts.append(text)


def _request_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(1_500_000)
    return json.loads(raw.decode("utf-8", errors="replace"))


def _request_text(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(1_500_000)
    return raw.decode("utf-8", errors="replace")


def _clean_instance_url(value: str) -> str | None:
    raw = (value or "").strip().rstrip("/")
    if not raw or ".onion" in raw.lower():
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return raw


def _configured_instances() -> list[str]:
    settings = get_settings()
    return [item for item in (_clean_instance_url(value) for value in settings.searxng_instances.split(",")) if item]


def _uptime_score(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        scores = [_uptime_score(item) for item in value.values()]
        return max(scores) if scores else 0.0
    return 0.0


def discover_instances(force_refresh: bool = False) -> dict[str, Any]:
    settings = get_settings()
    now = time.time()
    configured = _configured_instances()
    if configured and not force_refresh:
        return {"source": "env", "items": configured, "errors": []}
    if not force_refresh and _instance_cache["expiresAt"] > now and _instance_cache["items"]:
        return {"source": "cache", "items": list(_instance_cache["items"]), "errors": []}

    errors: list[str] = []
    candidates: list[tuple[float, str]] = []
    try:
        payload = _request_json(settings.searx_space_url, settings.searxng_timeout_seconds)
        instances = payload.get("instances", {})
        if isinstance(instances, dict):
            for url, meta in instances.items():
                clean_url = _clean_instance_url(url)
                if not clean_url or not isinstance(meta, dict):
                    continue
                if meta.get("network_type") not in {None, "normal"}:
                    continue
                score = _uptime_score(meta.get("uptime"))
                if meta.get("version"):
                    score += 1.0
                candidates.append((score, clean_url))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        errors.append(str(exc))

    discovered = [url for _, url in sorted(candidates, key=lambda item: item[0], reverse=True)]
    items = list(dict.fromkeys([*configured, *discovered]))[: max(1, settings.searxng_max_instances)]
    _instance_cache.update({"expiresAt": now + INSTANCE_CACHE_TTL_SECONDS, "items": items})
    return {"source": "searx.space", "items": items, "errors": errors}


def _normalize_results(instance: str, payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    results = []
    for item in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or item.get("snippet") or "").strip()
        if not url or not title:
            continue
        results.append(
            {
                "title": title[:220],
                "url": url,
                "content": re.sub(r"\s+", " ", content)[:700],
                "engine": item.get("engine") or item.get("engines"),
                "instance": instance,
            }
        )
        if len(results) >= limit:
            break
    return results


def search_web(query: str, limit: int = 5, force_refresh: bool = False) -> dict[str, Any]:
    settings = get_settings()
    clean_query = re.sub(r"\s+", " ", (query or "").strip())[:260]
    limit = max(1, min(limit, 10))
    if not clean_query:
        return {"enabled": False, "query": clean_query, "items": [], "errors": ["empty query"]}

    cache_key = f"{clean_query}|{limit}"
    cached = _search_cache.get(cache_key)
    if cached and cached[0] > time.time() and not force_refresh:
        return {**cached[1], "cached": True}

    discovery = discover_instances(force_refresh=force_refresh)
    errors = list(discovery.get("errors") or [])
    for instance in discovery.get("items", []):
        params = urlencode({"q": clean_query, "format": "json", "language": "en", "safesearch": "1"})
        search_url = f"{instance.rstrip('/')}/search?{params}"
        try:
            payload = _request_json(search_url, settings.searxng_timeout_seconds)
            results = _normalize_results(instance, payload, limit)
            if results:
                response = {
                    "enabled": True,
                    "query": clean_query,
                    "instance": instance,
                    "items": results,
                    "errors": errors,
                    "cached": False,
                }
                _search_cache[cache_key] = (time.time() + SEARCH_CACHE_TTL_SECONDS, response)
                return response
            errors.append(f"{instance}: no JSON results")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            errors.append(f"{instance}: {exc}")

    response = {"enabled": False, "query": clean_query, "instance": None, "items": [], "errors": errors[-8:], "cached": False}
    _search_cache[cache_key] = (time.time() + 45, response)
    return response


def crawl_page(url: str) -> dict[str, Any]:
    settings = get_settings()
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "url": url, "error": "unsupported URL"}
    try:
        html = _request_text(url, settings.searxng_timeout_seconds)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "url": url, "error": str(exc)}

    parser = _TextExtractor()
    parser.feed(html[:1_200_000])
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return {"ok": True, "url": url, "title": parser.title[:220], "text": text[:MAX_PAGE_TEXT_CHARS]}


def _numbers(pattern: str, text: str, low: float, high: float) -> list[float]:
    values = []
    for match in re.finditer(pattern, text, flags=re.I):
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        if low <= value <= high:
            values.append(value)
    return values


def _first_reasonable(values: list[float], preferred: set[int] | None = None) -> float | None:
    if not values:
        return None
    if preferred:
        for value in values:
            if int(round(value)) in preferred:
                return value
    return values[0]


def _estimate_current_from_power(power_w: float | None, voltage: float | None, hp: float | None) -> float | None:
    watts = power_w or ((hp or 0) * 746.0 if hp else None)
    if not watts or not voltage or voltage <= 0:
        return None
    current = watts / (voltage * 0.72)
    return round(current, 2) if 0 < current < 500 else None


def extract_appliance_profile(query: str, appliance_type: str, search_result: dict[str, Any], crawled: dict[str, Any] | None = None) -> dict[str, Any]:
    snippets = " ".join(
        f"{item.get('title', '')} {item.get('content', '')}" for item in search_result.get("items", [])[:6]
    )
    crawled_text = (crawled or {}).get("text") or ""
    text = re.sub(r"\s+", " ", f"{query} {snippets} {crawled_text[:5000]}")
    voltage = _first_reasonable(_numbers(r"(\d+(?:\.\d+)?)\s*(?:v|volt|volts)\b", text, 3, 690), {12, 24, 48, 110, 115, 120, 220, 230, 240, 380, 400, 415, 460})
    current = _first_reasonable(_numbers(r"(\d+(?:\.\d+)?)\s*(?:a|amp|amps|amperes)\b", text, 0.05, 500))
    rpm = _first_reasonable(_numbers(r"(\d{2,5})\s*(?:rpm|r/min)\b", text, 30, 60000), {900, 1200, 1400, 1450, 1725, 1750, 2800, 2850, 3450, 3600})
    hp = _first_reasonable(_numbers(r"(\d+(?:\.\d+)?)\s*(?:hp|horsepower)\b", text, 0.01, 1000))
    kw = _first_reasonable(_numbers(r"(\d+(?:\.\d+)?)\s*(?:kw|kilowatt|kilowatts)\b", text, 0.01, 1000))
    if current is None:
        current = _estimate_current_from_power(kw * 1000 if kw else None, voltage, hp)

    confidence = 0.15
    confidence += 0.2 if voltage else 0
    confidence += 0.25 if current else 0
    confidence += 0.2 if rpm else 0
    confidence += 0.1 if search_result.get("items") else 0
    confidence += 0.1 if crawled and crawled.get("ok") else 0

    connected_load = query.strip()[:120]
    if hp and "hp" not in connected_load.lower():
        connected_load = f"{connected_load} ({hp:g} HP)"
    if kw and "kw" not in connected_load.lower():
        connected_load = f"{connected_load} ({kw:g} kW)"

    return {
        "type": appliance_type or "motor",
        "name": query.strip()[:90] or "Motor",
        "connectedLoad": connected_load,
        "nominalVoltageV": voltage,
        "nominalCurrentA": current,
        "nominalRpm": rpm,
        "expectedVibrationG": 0.3 if (appliance_type or "motor") in {"motor", "pump", "fan", "compressor"} else None,
        "confidence": round(min(confidence, 0.95), 2),
        "sourceCount": len(search_result.get("items") or []),
    }


def suggest_appliance_profile(query: str, appliance_type: str = "motor", crawl_first_result: bool = True) -> dict[str, Any]:
    search_query = f"{query} {appliance_type} rated voltage rated current rpm datasheet"
    search_result = search_web(search_query, limit=6)
    crawled = None
    if crawl_first_result and search_result.get("items"):
        crawled = crawl_page(search_result["items"][0]["url"])
    profile = extract_appliance_profile(query, appliance_type, search_result, crawled)
    sources = [
        {"title": item.get("title"), "url": item.get("url"), "content": item.get("content")}
        for item in search_result.get("items", [])[:5]
    ]
    assistant_text = ""
    if search_result.get("items"):
        try:
            assistant_text = chat_completion(
                [
                    {
                        "role": "system",
                        "content": "Extract a concise appliance setup profile. Return one short sentence with voltage, rated current, rpm, and a caution if values are uncertain. Do not invent missing values.",
                    },
                    {
                        "role": "user",
                        "content": compact_json({"query": query, "profile": profile, "sources": sources}, max_chars=12000),
                    },
                ]
            ).strip()
        except AiGatewayError:
            assistant_text = ""
    return {
        "query": query,
        "applianceType": appliance_type,
        "profile": profile,
        "assistantText": assistant_text,
        "search": search_result,
        "crawled": crawled,
        "sources": sources,
    }


def _sensor_profile_from_text(query: str, search_result: dict[str, Any], crawled: dict[str, Any] | None = None) -> dict[str, Any]:
    snippets = " ".join(f"{item.get('title', '')} {item.get('content', '')}" for item in search_result.get("items", [])[:6])
    text = re.sub(r"\s+", " ", f"{query} {snippets} {(crawled or {}).get('text') or ''}"[:9000])
    lower = text.lower()

    current_model = query.strip()[:90] or "Analog current sensor"
    current_zero_v: float | None = None
    current_v_per_a: float | None = None
    current_notes = ""

    if re.search(r"\bv\s*/\s*i\b|\bv-i\b|\bvi converter\b|current transducer|current converter", lower):
        output_voltage = _first_reasonable(_numbers(r"0\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*v", lower, 0.1, 10))
        current_range = _first_reasonable(_numbers(r"0\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*a", lower, 0.1, 500))
        current_zero_v = 0.0
        current_v_per_a = round(output_voltage / current_range, 6) if output_voltage and current_range else 1.0
        current_model = "Analog V/I converter"
        current_notes = "Unipolar V/I converter default; enter measured current during setup or set exact V/A from the converter datasheet."
    elif "acs712" in lower:
        current_zero_v = 2.5
        current_notes = "ACS712 is center-biased; keep the ESP32 ADC input below 3.3V at peak current."
        if re.search(r"\b5\s*a\b|5a", lower):
            current_v_per_a = 0.185
            current_model = "ACS712 5A"
        elif re.search(r"\b20\s*a\b|20a", lower):
            current_v_per_a = 0.100
            current_model = "ACS712 20A"
        elif re.search(r"\b30\s*a\b|30a", lower):
            current_v_per_a = 0.066
            current_model = "ACS712 30A"
        else:
            current_v_per_a = 0.066
            current_model = "ACS712"
    elif "acs758" in lower:
        current_zero_v = 2.5
        current_notes = "ACS758 is center-biased; choose the exact range from the sensor marking when possible."
        if re.search(r"\b50\s*a\b|50a", lower):
            current_v_per_a = 0.040
            current_model = "ACS758 50A"
        elif re.search(r"\b100\s*a\b|100a", lower):
            current_v_per_a = 0.020
            current_model = "ACS758 100A"
        elif re.search(r"\b200\s*a\b|200a", lower):
            current_v_per_a = 0.010
            current_model = "ACS758 200A"
        else:
            current_v_per_a = 0.040
            current_model = "ACS758"
    elif "ina219" in lower or "ina226" in lower:
        current_model = "INA219/INA226 digital current sensor"
        current_notes = "This firmware expects analog current on GPIO 35; digital I2C current sensors need firmware driver changes."

    voltage_model = "Analog voltage input"
    voltage_scale: float | None = 1.0
    voltage_notes = "Confirm with a multimeter; measured voltage calibration overrides this scale."
    divider_match = re.search(r"(\d+(?:\.\d+)?)\s*k(?:ohm|\u03a9|\s)?\D{0,24}(\d+(?:\.\d+)?)\s*k(?:ohm|\u03a9)?", lower)
    if divider_match and "divider" in lower:
        high = float(divider_match.group(1))
        low = float(divider_match.group(2))
        if high > 0 and low > 0:
            voltage_scale = round((high + low) / low, 4)
            voltage_model = f"Voltage divider {high:g}k/{low:g}k"
    elif re.search(r"0\s*[-to]+\s*25\s*v|25\s*v\s+sensor", lower):
        voltage_scale = 5.0
        voltage_model = "0-25V analog voltage module"
    elif re.search(r"0\s*[-to]+\s*30\s*v|30\s*v\s+sensor", lower):
        voltage_scale = 6.0
        voltage_model = "0-30V analog voltage module"
    elif re.search(r"0\s*[-to]+\s*50\s*v|50\s*v\s+sensor", lower):
        voltage_scale = 10.0
        voltage_model = "0-50V analog voltage module"

    hall_model = "W41FC Hall sensor" if "w41fc" in lower else ("Hall effect pulse sensor" if "hall" in lower else "Hall effect pulse sensor")
    hall_pulses = _first_reasonable(_numbers(r"(\d+(?:\.\d+)?)\s*(?:pulse|pulses)\s*(?:per|/)\s*(?:rev|revolution)", lower, 0.1, 100)) or 1.0
    temperature_model = "DS18B20" if "ds18b20" in lower else "Not installed"
    vibration_model = "MPU6050" if "mpu6050" in lower or not lower.strip() else "Vibration sensor"

    confidence = 0.2
    confidence += 0.25 if current_v_per_a else 0
    confidence += 0.2 if voltage_scale else 0
    confidence += 0.15 if hall_pulses else 0
    confidence += 0.1 if search_result.get("items") else 0
    confidence += 0.1 if crawled and crawled.get("ok") else 0

    return {
        "currentSensorModel": current_model,
        "currentSensorZeroV": current_zero_v,
        "currentSensorVPerA": current_v_per_a,
        "currentSensorNotes": current_notes,
        "voltageSensorModel": voltage_model,
        "voltageScale": voltage_scale,
        "voltageSensorNotes": voltage_notes,
        "hallSensorModel": hall_model,
        "hallPulsesPerRev": hall_pulses,
        "temperatureSensorModel": temperature_model,
        "vibrationSensorModel": vibration_model,
        "confidence": round(min(confidence, 0.95), 2),
        "sourceCount": len(search_result.get("items") or []),
    }


def suggest_sensor_profile(query: str, crawl_first_result: bool = True) -> dict[str, Any]:
    search_query = f"{query} sensor datasheet sensitivity voltage output pulses per revolution"
    search_result = search_web(search_query, limit=6)
    crawled = None
    if crawl_first_result and search_result.get("items"):
        crawled = crawl_page(search_result["items"][0]["url"])
    profile = _sensor_profile_from_text(query, search_result, crawled)
    sources = [{"title": item.get("title"), "url": item.get("url"), "content": item.get("content")} for item in search_result.get("items", [])[:5]]
    assistant_text = ""
    if search_result.get("items"):
        try:
            assistant_text = chat_completion(
                [
                    {"role": "system", "content": "Extract an Omni9 ESP32 sensor setup profile. Return one short sentence with current sensitivity, voltage scale, Hall pulses, and any uncertainty. Do not invent missing values."},
                    {"role": "user", "content": compact_json({"query": query, "profile": profile, "sources": sources}, max_chars=12000)},
                ]
            ).strip()
        except AiGatewayError:
            assistant_text = ""
    return {"query": query, "profile": profile, "assistantText": assistant_text, "search": search_result, "crawled": crawled, "sources": sources}