from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.services.ai_agent import ai_health, answer_question
from app.services.rag import search_documents, upsert_document
from app.services.searxng import discover_instances, search_web, suggest_appliance_profile, suggest_sensor_profile
from app.services.voice_ai import synthesize_reply

router = APIRouter(prefix="/v1/ai", tags=["ai"])


class AskRequest(BaseModel):
    message: str = Field(min_length=1)
    siteId: str = "main_site"
    machineId: str | None = None
    mode: str = "ask"
    includeSql: bool = True
    includeRag: bool = True
    includeWebSearch: bool = True
    includeAudio: bool = False
    ragLimit: int = Field(default=5, ge=0, le=12)


class RagDocumentRequest(BaseModel):
    siteId: str = "main_site"
    machineId: str | None = None
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    tags: list[str] = []


class RagSearchRequest(BaseModel):
    siteId: str = "main_site"
    machineId: str | None = None
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=10)
    forceRefresh: bool = False


class ApplianceProfileRequest(BaseModel):
    query: str = Field(min_length=1)
    applianceType: str = "motor"
    crawlFirstResult: bool = True


class SensorProfileRequest(BaseModel):
    query: str = Field(min_length=1)
    crawlFirstResult: bool = True


@router.get("/health")
def health():
    return ai_health()


@router.post("/ask")
def ask(body: AskRequest):
    try:
        result = answer_question(
            site_id=body.siteId,
            machine_id=body.machineId,
            message=body.message,
            mode=body.mode,
            include_sql=body.includeSql,
            include_rag=body.includeRag,
            include_web=body.includeWebSearch,
            rag_limit=body.ragLimit,
        )
        if body.includeAudio:
            result["audio"] = synthesize_reply(result["assistantText"], site_id=body.siteId, machine_id=body.machineId)
            result["audioUrl"] = (result.get("audio") or {}).get("audioUrl")
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/rag/documents")
def create_rag_document(body: RagDocumentRequest):
    try:
        return upsert_document(
            site_id=body.siteId,
            machine_id=body.machineId,
            title=body.title,
            body=body.body,
            tags=body.tags,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/rag/search")
def rag_search(body: RagSearchRequest):
    try:
        return search_documents(body.siteId, body.query, body.machineId, body.limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/web/instances")
def web_instances(forceRefresh: bool = False):
    return discover_instances(force_refresh=forceRefresh)


@router.post("/web/search")
def web_search(body: WebSearchRequest):
    return search_web(body.query, body.limit, body.forceRefresh)


@router.post("/appliance-profile")
def appliance_profile(body: ApplianceProfileRequest):
    return suggest_appliance_profile(body.query, body.applianceType, body.crawlFirstResult)


@router.post("/sensor-profile")
def sensor_profile(body: SensorProfileRequest):
    return suggest_sensor_profile(body.query, body.crawlFirstResult)
