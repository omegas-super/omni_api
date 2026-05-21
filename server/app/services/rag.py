from __future__ import annotations

import json
import math
from threading import Lock
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.services.ai_client import AiGatewayError, embed_texts
from app.services.database import normalized_database_url

_MEMORY_DOCS: list[dict[str, Any]] = []
_MEMORY_LOCK = Lock()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def lexical_score(query: str, text: str) -> float:
    q_terms = {item.lower() for item in query.split() if len(item) > 2}
    if not q_terms:
        return 0.0
    target = text.lower()
    hits = sum(1 for term in q_terms if term in target)
    return hits / len(q_terms)


def ensure_schema(conn) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS omni9")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS omni9.ai_context_documents (
          id UUID PRIMARY KEY,
          site_id TEXT NOT NULL,
          machine_id TEXT,
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          tags TEXT[] NOT NULL DEFAULT '{}',
          embedding_model TEXT,
          embedding_json JSONB,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ai_context_documents_site_idx ON omni9.ai_context_documents (site_id, machine_id)")


def db_connection():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(normalized_database_url(), row_factory=dict_row, connect_timeout=10)


def _embed_or_empty(text: str) -> tuple[list[float], str | None]:
    settings = get_settings()
    if not settings.ai_enable_rag:
        return [], "RAG is disabled"
    try:
        vectors = embed_texts([text], model=settings.ai_embedding_model)
        return vectors[0] if vectors else [], None
    except AiGatewayError as exc:
        return [], str(exc)


def upsert_document(site_id: str, title: str, body: str, machine_id: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    settings = get_settings()
    doc_id = str(uuid4())
    tags = tags or []
    embedding, embed_error = _embed_or_empty(f"{title}\n{body}")
    document = {
        "id": doc_id,
        "siteId": site_id,
        "machineId": machine_id,
        "title": title,
        "body": body,
        "tags": tags,
        "embeddingModel": settings.ai_embedding_model if embedding else None,
        "embedding": embedding,
    }

    if normalized_database_url():
        try:
            with db_connection() as conn:
                ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO omni9.ai_context_documents
                      (id, site_id, machine_id, title, body, tags, embedding_model, embedding_json)
                    VALUES (%(id)s, %(site_id)s, %(machine_id)s, %(title)s, %(body)s, %(tags)s, %(embedding_model)s, %(embedding_json)s)
                    """,
                    {
                        "id": doc_id,
                        "site_id": site_id,
                        "machine_id": machine_id,
                        "title": title,
                        "body": body,
                        "tags": tags,
                        "embedding_model": settings.ai_embedding_model if embedding else None,
                        "embedding_json": json.dumps(embedding) if embedding else None,
                    },
                )
                conn.commit()
            return {"id": doc_id, "storedIn": "postgresql", "embeddingReady": bool(embedding), "embeddingError": embed_error}
        except Exception as exc:
            document["storageError"] = str(exc)

    with _MEMORY_LOCK:
        _MEMORY_DOCS.append(document)
    return {"id": doc_id, "storedIn": "memory", "embeddingReady": bool(embedding), "embeddingError": embed_error, "storageError": document.get("storageError")}


def _load_documents(site_id: str, machine_id: str | None, limit: int) -> list[dict[str, Any]]:
    if normalized_database_url():
        try:
            with db_connection() as conn:
                ensure_schema(conn)
                rows = conn.execute(
                    """
                    SELECT id, site_id, machine_id, title, body, tags, embedding_model, embedding_json, created_at
                    FROM omni9.ai_context_documents
                    WHERE site_id = %(site_id)s
                      AND (%(machine_id)s::text IS NULL OR machine_id IS NULL OR machine_id = %(machine_id)s::text)
                    ORDER BY updated_at DESC
                    LIMIT %(limit)s
                    """,
                    {"site_id": site_id, "machine_id": machine_id, "limit": max(limit * 5, 20)},
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception:
            pass

    with _MEMORY_LOCK:
        docs = [item for item in _MEMORY_DOCS if item.get("siteId") == site_id and (not machine_id or not item.get("machineId") or item.get("machineId") == machine_id)]
    return docs[-max(limit * 5, 20) :]


def search_documents(site_id: str, query: str, machine_id: str | None = None, limit: int = 5) -> dict[str, Any]:
    if not get_settings().ai_enable_rag:
        return {"enabled": False, "items": []}

    query_embedding, embed_error = _embed_or_empty(query)
    docs = _load_documents(site_id, machine_id, limit)
    scored = []
    for doc in docs:
        body = doc.get("body") or ""
        title = doc.get("title") or ""
        embedding = doc.get("embedding") or doc.get("embedding_json") or []
        score = cosine(query_embedding, embedding) if query_embedding and embedding else lexical_score(query, f"{title}\n{body}")
        scored.append(
            {
                "id": str(doc.get("id")),
                "title": title,
                "body": body[:1600],
                "machineId": doc.get("machineId") or doc.get("machine_id"),
                "tags": doc.get("tags") or [],
                "score": round(float(score), 4),
                "source": "rag",
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"enabled": True, "embeddingReady": bool(query_embedding), "embeddingError": embed_error, "items": scored[:limit]}


