from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request

ADMIN_URL = os.environ.get("GARAGE_ADMIN_URL", "https://admin-ideobcpf7r7deo967hvsn1m7.team-knights.com").rstrip("/")
ADMIN_TOKEN = os.environ.get("GARAGE_ADMIN_TOKEN", "")
BUCKET = os.environ.get("S3_BUCKET", "omni9-media")
KEY_NAME = os.environ.get("GARAGE_KEY_NAME", "omni9-app")
TLS_VERIFY = os.environ.get("GARAGE_TLS_VERIFY", "true").lower() not in {"0", "false", "no"}


def request(path: str, payload: dict) -> dict:
    if not ADMIN_TOKEN:
        raise SystemExit("GARAGE_ADMIN_TOKEN is required")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ADMIN_URL}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {ADMIN_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    context = None if TLS_VERIFY else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=context) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Garage Admin API failed {exc.code} on {path}: {detail}") from exc


def main() -> int:
    bucket = request("/v2/CreateBucket", {"globalAlias": BUCKET})
    key = request("/v2/CreateKey", {"name": KEY_NAME, "neverExpires": True})
    request(
        "/v2/AllowBucketKey",
        {
            "bucketId": bucket["id"],
            "accessKeyId": key["accessKeyId"],
            "permissions": {"read": True, "write": True, "owner": True},
        },
    )

    print("Garage bucket and app key are ready.")
    print(f"S3_BUCKET={BUCKET}")
    print(f"S3_ACCESS_KEY={key['accessKeyId']}")
    print(f"S3_SECRET_KEY={key.get('secretAccessKey') or '<not returned>'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
