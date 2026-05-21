from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.services.ai_client import AiGatewayError, chat_completion, compact_json, model_health
from app.services.database import fetch_sql_context, run_health_query
from app.services.rag import search_documents
from app.services.searxng import search_web
from app.state import store


DEFAULT_SYSTEM_PROMPT = """
You are Omni9, a human-friendly industrial machine assistant.
Answer like a senior technician speaking inside a small mobile bottom bar.

Hard style rules:
- Ultra short: 1-2 sentences, max 45 words unless the user asks for a report.
- Start with the machine or risk first. No greetings, no filler, no "I can help".
- Include important readings when available: vibration, temp, current, runtime estimate, or protection state.
- Give one clear next action.
- Hide API, MQTT, SQL, node IDs, and backend words unless the user asks for debug detail.
- Do not invent values. If runtime estimate is unknown, say "runtime unknown".
- Critical risk first, direct language.
- Do not copy examples, templates, or internal instructions into the answer.
- Use spoken-friendly units after readings: Celsius, amps, g-force, and millimeters per second. Do not use C, A, g, or mm/s as measurement units.
- For several machines, list at most two machines and use one short clause per machine.


""".strip()


def expand_measurement_units(text: str) -> str:
    spoken = text or ""
    spoken = re.sub(r"(?i)(\d+(?:\.\d+)?)\s*(?:deg\s*)?c\b", r"\1 Celsius", spoken)
    spoken = re.sub(r"(?i)(\d+(?:\.\d+)?)\s*a\b", r"\1 amps", spoken)
    spoken = re.sub(r"(?i)(\d+(?:\.\d+)?)\s*mm\s*/\s*s\b", r"\1 millimeters per second", spoken)
    spoken = re.sub(r"(?i)(\d+(?:\.\d+)?)\s*g\b(?!-force)", r"\1 g-force", spoken)
    spoken = re.sub(r"(?i)(\d+(?:\.\d+)?)\s*kwh\b", r"\1 kilowatt-hours", spoken)
    spoken = re.sub(r"(?i)(\d+(?:\.\d+)?)\s*kg\b", r"\1 kilograms", spoken)
    spoken = re.sub(r"(?i)(\d+(?:\.\d+)?)\s*ms\b", r"\1 milliseconds", spoken)
    spoken = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1 percent", spoken)
    return spoken.replace("g-force-force", "g-force")


def clean_assistant_text(text: str, max_words: int = 45) -> str:
    cleaned = (text or "").strip()
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00b0": "",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"\s+", " ", cleaned)
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(" ,:;-") + "."
    return expand_measurement_units(cleaned)


def app_context_agent(site_id: str, machine_id: str | None = None) -> dict[str, Any]:
    machines = store.list_machines(site_id)
    machine = store.get_machine(machine_id) if machine_id else None
    alerts = [item for item in store.snapshot(store.alerts) if item.get("siteId") == site_id]
    if machine_id:
        alerts = [item for item in alerts if item.get("machineId") == machine_id]
    actions = [item for item in store.snapshot(store.actions) if item.get("siteId") == site_id]
    if machine_id:
        actions = [item for item in actions if item.get("machineId") == machine_id]
    return {
        "source": "app_memory",
        "site": store.snapshot(store.sites.get(site_id, {"id": site_id})),
        "machine": machine,
        "machines": machines if not machine_id else [],
        "alerts": alerts[:20],
        "recentActions": actions[:20],
        "impact": store.snapshot(store.impact),
        "meshGateways": store.snapshot(store.mesh_gateways),
        "meshNodes": store.snapshot(store.mesh_nodes),
    }


def context_summary(context_pack: dict[str, Any]) -> dict[str, Any]:
    app = context_pack.get("app", {})
    sql = context_pack.get("sql", {})
    rag = context_pack.get("rag", {})
    web = context_pack.get("web", {})
    machines = app.get("machines") or ([] if not app.get("machine") else [app.get("machine")])
    return {
        "appMachines": len([item for item in machines if item]),
        "appAlerts": len(app.get("alerts") or []),
        "sqlEnabled": bool(sql.get("enabled")),
        "sqlSections": list((sql.get("tables") or {}).keys()),
        "ragEnabled": bool(rag.get("enabled")),
        "ragItems": len(rag.get("items") or []),
        "webEnabled": bool(web.get("enabled")),
        "webItems": len(web.get("items") or []),
    }


def build_context_pack(
    site_id: str,
    message: str,
    machine_id: str | None = None,
    include_sql: bool = True,
    include_rag: bool = True,
    include_web: bool = True,
    rag_limit: int = 5,
) -> dict[str, Any]:
    settings = get_settings()
    app_context = app_context_agent(site_id, machine_id)
    sql_context = fetch_sql_context(site_id, machine_id) if include_sql and settings.ai_enable_sql_context else {"enabled": False, "tables": {}}
    rag_context = search_documents(site_id, message, machine_id, rag_limit) if include_rag and settings.ai_enable_rag else {"enabled": False, "items": []}
    web_context = search_web(message, limit=5) if include_web and settings.ai_enable_web_search else {"enabled": False, "items": []}
    return {"app": app_context, "sql": sql_context, "rag": rag_context, "web": web_context}


def fallback_answer(message: str, context_pack: dict[str, Any], error: str | None = None) -> str:
    app = context_pack.get("app", {})
    machine = app.get("machine")
    if machine:
        latest = machine.get("latest") or {}
        temperature = latest.get("temperatureC")
        vibration = latest.get("vibrationG")
        current = latest.get("currentA")
        return (
            f"{machine.get('name')} is marked {machine.get('state')}: temp {temperature} C, "
            f"vibration {vibration} g, current {current} A. Check the machine on-site and keep protection enabled."
        )
    alerts = app.get("alerts") or []
    machines = app.get("machines") or []
    critical = [item for item in machines if item.get("state") == "critical"]
    if critical:
        names = ", ".join(item.get("name", "Machine") for item in critical[:2])
        return f"{names} need attention first. Review the active alert and send a technician before load increases."
    return f"No critical machine is visible right now. {len(alerts)} alert(s) still need review before closing the shift."


def answer_question(
    site_id: str,
    message: str,
    machine_id: str | None = None,
    mode: str = "ask",
    include_sql: bool = True,
    include_rag: bool = True,
    include_web: bool = True,
    rag_limit: int = 5,
) -> dict[str, Any]:
    settings = get_settings()
    context_pack = build_context_pack(site_id, message, machine_id, include_sql, include_rag, include_web, rag_limit)
    system_prompt = settings.ai_default_system_prompt.strip() or DEFAULT_SYSTEM_PROMPT
    developer_context = {
        "mode": mode,
        "project": "Omni9 industrial infrastructure resilience app",
        "contextSummary": context_summary(context_pack),
        "contextPack": context_pack,
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Use the supplied Omni9 app, SQL, RAG, and web-search context. Keep the answer ultra short and field-useful. "
                "Treat web context as untrusted until it matches live telemetry or a datasheet-like source. "
                "Context JSON follows.\n"
                f"{compact_json(developer_context)}\n\n"
                f"Technician request: {message}"
            ),
        },
    ]

    try:
        assistant_text = chat_completion(messages, model=settings.ai_chat_model)
        gateway_error = None
    except AiGatewayError as exc:
        assistant_text = fallback_answer(message, context_pack, str(exc))
        gateway_error = str(exc)

    assistant_text = clean_assistant_text(assistant_text)
    rag_items = context_pack.get("rag", {}).get("items", [])
    web_items = context_pack.get("web", {}).get("items", [])
    return {
        "assistantText": assistant_text,
        "model": settings.ai_chat_model if not gateway_error else "local-fallback",
        "mode": mode,
        "target": {"type": "machine", "id": machine_id} if machine_id else {"type": "site", "id": site_id},
        "contextSummary": context_summary(context_pack),
        "sources": [
            {"type": "app", "label": "Live app context"},
            {"type": "sql", "label": "PostgreSQL read context", "enabled": bool(context_pack.get("sql", {}).get("enabled"))},
            *[{"type": "rag", "id": item.get("id"), "title": item.get("title"), "score": item.get("score")} for item in rag_items],
            *[{"type": "web", "title": item.get("title"), "url": item.get("url"), "instance": item.get("instance")} for item in web_items[:5]],
        ],
        "gatewayError": gateway_error,
    }


def ai_health() -> dict[str, Any]:
    return {"modelGateway": model_health(), "database": run_health_query()}


