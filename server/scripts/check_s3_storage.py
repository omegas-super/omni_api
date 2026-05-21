from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - helper script fallback
    load_dotenv = None


if load_dotenv:
    script_root = Path(__file__).resolve().parents[1]
    load_dotenv(script_root / ".env")
    load_dotenv(Path.cwd() / ".env")


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


ENDPOINT_URL = env_first("S3_ENDPOINT_URL", "SERVICE_URL_S3", default="https://s3.taxsomega.com").rstrip("/")
REGION = env_first("S3_REGION", "AWS_DEFAULT_REGION", default="us-east-1")
ACCESS_KEY = env_first("S3_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "SERVICE_USER_S3")
SECRET_KEY = env_first("S3_SECRET_KEY", "AWS_SECRET_ACCESS_KEY", "SERVICE_PASSWORD_S3")
BUCKET = env_first("S3_BUCKET", default="omni9-media")
CREATE_BUCKET = os.environ.get("S3_CREATE_BUCKET", "true").lower() not in {"0", "false", "no"}


def client():
    if not ACCESS_KEY or not SECRET_KEY:
        raise SystemExit("S3_ACCESS_KEY/S3_SECRET_KEY or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are required")
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        region_name=REGION,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def main() -> int:
    s3 = client()
    print(f"endpoint={ENDPOINT_URL}")
    print(f"region={REGION}")
    print(f"bucket={BUCKET}")

    buckets = s3.list_buckets().get("Buckets", [])
    print("list_buckets=ok", [bucket.get("Name") for bucket in buckets])

    try:
        s3.head_bucket(Bucket=BUCKET)
        print("head_bucket=ok")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in {"404", "NoSuchBucket", "NotFound"} or not CREATE_BUCKET:
            raise
        s3.create_bucket(Bucket=BUCKET)
        print("create_bucket=ok")

    key = f"sites/main_site/system/healthcheck/{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"omni9 s3 healthcheck\n", ContentType="text/plain")
    print("put_object=ok", key)

    data = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8").strip()
    print("get_object=ok", data)

    s3.delete_object(Bucket=BUCKET, Key=key)
    print("delete_object=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
