from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.storage import check_storage, create_download_url, create_upload_url

router = APIRouter(tags=["media"])


class UploadUrlRequest(BaseModel):
    filename: str | None = None
    contentType: str = "application/octet-stream"
    kind: str = "evidence"
    machineId: str | None = None


class DownloadUrlRequest(BaseModel):
    storageKey: str


@router.get("/v1/storage/health")
def storage_health():
    try:
        return check_storage()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/v1/sites/{site_id}/media/upload-url")
def upload_url(site_id: str, body: UploadUrlRequest):
    try:
        return create_upload_url(site_id, body.contentType, body.kind, body.filename, body.machineId)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/v1/media/download-url")
def download_url(body: DownloadUrlRequest):
    try:
        return create_download_url(body.storageKey)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
