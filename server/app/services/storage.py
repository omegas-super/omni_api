from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.config import get_settings


def _resolved_settings():
    settings = get_settings()
    endpoint_url = settings.resolved_s3_endpoint_url
    access_key = settings.resolved_s3_access_key
    secret_key = settings.resolved_s3_secret_key
    if not endpoint_url:
        raise RuntimeError("S3_ENDPOINT_URL or SERVICE_URL_S3 is not configured")
    if not access_key or not secret_key:
        raise RuntimeError("S3 access key/secret are not configured")
    return settings, endpoint_url, access_key, secret_key


def _client():
    settings, endpoint_url, access_key, secret_key = _resolved_settings()

    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def build_storage_key(site_id: str, kind: str, filename: str | None = None, machine_id: str | None = None) -> str:
    safe_kind = kind or "evidence"
    ext = "bin"
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()[:12]
    date = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    owner = f"machines/{machine_id}" if machine_id else "site"
    return f"sites/{site_id}/{owner}/{safe_kind}/{date}/{uuid4()}.{ext}"


def check_storage() -> dict:
    settings, endpoint_url, _, _ = _resolved_settings()
    client = _client()
    client.head_bucket(Bucket=settings.s3_bucket)
    return {
        "ok": True,
        "driver": settings.storage_driver,
        "endpoint": endpoint_url,
        "bucket": settings.s3_bucket,
        "region": settings.s3_region,
    }


def create_upload_url(site_id: str, content_type: str, kind: str, filename: str | None, machine_id: str | None) -> dict:
    settings = get_settings()
    key = build_storage_key(site_id=site_id, kind=kind, filename=filename, machine_id=machine_id)
    client = _client()
    upload_url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=900,
    )
    return {
        "method": "PUT",
        "uploadUrl": upload_url,
        "headers": {"Content-Type": content_type},
        "bucket": settings.s3_bucket,
        "storageKey": key,
        "expiresIn": 900,
    }


def create_download_url(storage_key: str) -> dict:
    settings = get_settings()
    client = _client()
    download_url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": storage_key},
        ExpiresIn=900,
    )
    return {"downloadUrl": download_url, "storageKey": storage_key, "expiresIn": 900}


def upload_bytes(site_id: str, content: bytes, content_type: str, kind: str, filename: str, machine_id: str | None = None) -> dict:
    settings = get_settings()
    key = build_storage_key(site_id=site_id, kind=kind, filename=filename, machine_id=machine_id)
    client = _client()
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=content, ContentType=content_type)
    return {
        "bucket": settings.s3_bucket,
        "storageKey": key,
        "contentType": content_type,
        **create_download_url(key),
    }
