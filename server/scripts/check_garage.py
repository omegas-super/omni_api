from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request


S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "https://s3-ideobcpf7r7deo967hvsn1m7.team-knights.com").rstrip("/")
GARAGE_ADMIN_URL = os.environ.get("GARAGE_ADMIN_URL", "https://admin-ideobcpf7r7deo967hvsn1m7.team-knights.com").rstrip("/")
GARAGE_ADMIN_TOKEN = os.environ.get("GARAGE_ADMIN_TOKEN", "")
GARAGE_METRICS_TOKEN = os.environ.get("GARAGE_METRICS_TOKEN", "")
TLS_VERIFY = os.environ.get("GARAGE_TLS_VERIFY", "true").lower() not in {"0", "false", "no"}


def _context():
    return None if TLS_VERIFY else ssl._create_unverified_context()


def _read_error(exc: urllib.error.HTTPError) -> str:
    return exc.read().decode("utf-8", errors="replace")[:500]


def request(method: str, url: str, headers: dict[str, str] | None = None, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20, context=_context()) as resp:
            content = resp.read().decode("utf-8", errors="replace")[:500]
            return {"ok": True, "status": resp.status, "contentType": resp.headers.get("content-type", ""), "body": content}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "contentType": exc.headers.get("content-type", ""), "body": _read_error(exc)}
    except Exception as exc:
        return {"ok": False, "status": None, "contentType": "", "body": str(exc)}


def summarize(name: str, result: dict) -> None:
    body = result["body"].replace("\n", " ")
    if len(body) > 220:
        body = f"{body[:220]}..."
    status = result["status"] if result["status"] is not None else "connect-failed"
    print(f"[{name}] status={status} content_type={result['contentType']}")
    print(f"  {body}")


def main() -> int:
    summarize("s3-root", request("GET", f"{S3_ENDPOINT_URL}/"))

    if GARAGE_ADMIN_TOKEN:
        summarize(
            "admin-list-buckets",
            request(
                "POST",
                f"{GARAGE_ADMIN_URL}/v2/ListBuckets",
                headers={"Authorization": f"Bearer {GARAGE_ADMIN_TOKEN}", "Content-Type": "application/json"},
                payload={},
            ),
        )
    else:
        print("[admin-list-buckets] skipped: GARAGE_ADMIN_TOKEN is not set")

    if GARAGE_METRICS_TOKEN:
        summarize(
            "admin-metrics",
            request("GET", f"{GARAGE_ADMIN_URL}/metrics", headers={"Authorization": f"Bearer {GARAGE_METRICS_TOKEN}"}),
        )
    else:
        print("[admin-metrics] skipped: GARAGE_METRICS_TOKEN is not set")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
