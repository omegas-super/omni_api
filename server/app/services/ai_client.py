from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import get_settings


class AiGatewayError(RuntimeError):
    pass


def client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.resolved_ai_api_key, base_url=settings.resolved_ai_base_url)


def compact_json(value: Any, max_chars: int = 60000) -> str:
    text = json.dumps(value, ensure_ascii=True, default=str, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...[truncated {len(text) - max_chars} chars]"


def chat_completion(messages: list[dict[str, str]], model: str | None = None) -> str:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "model": model or settings.ai_chat_model,
        "messages": messages,
    }
    if settings.ai_max_output_tokens > 0:
        kwargs["max_tokens"] = settings.ai_max_output_tokens
    try:
        response = client().chat.completions.create(**kwargs)
    except Exception as exc:
        raise AiGatewayError(str(exc)) from exc

    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise AiGatewayError("AI gateway returned an unexpected chat response shape") from exc
    return content or ""


def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    settings = get_settings()
    if not texts:
        return []
    try:
        response = client().embeddings.create(model=model or settings.ai_embedding_model, input=texts)
    except Exception as exc:
        raise AiGatewayError(str(exc)) from exc
    return [item.embedding for item in response.data]


def model_health() -> dict:
    settings = get_settings()
    try:
        models = client().models.list()
        ids = [item.id for item in getattr(models, "data", [])]
        return {
            "ok": True,
            "baseUrl": settings.resolved_ai_base_url,
            "chatModel": settings.ai_chat_model,
            "embeddingModel": settings.ai_embedding_model,
            "chatModelAvailable": settings.ai_chat_model in ids,
            "embeddingModelAvailable": settings.ai_embedding_model in ids,
            "modelCount": len(ids),
        }
    except Exception as exc:
        return {
            "ok": False,
            "baseUrl": settings.resolved_ai_base_url,
            "chatModel": settings.ai_chat_model,
            "embeddingModel": settings.ai_embedding_model,
            "error": str(exc),
        }
