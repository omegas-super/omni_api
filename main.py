from __future__ import annotations

import argparse
import logging
import logging.config
import os
import sys
from multiprocessing import cpu_count
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
SERVER_DIR = ROOT_DIR / "server"
LOG_DIR = SERVER_DIR / "logs"
ROOT_ENV_FILE = ROOT_DIR / ".env"
SERVER_ENV_FILE = SERVER_DIR / ".env"


def load_environment() -> list[Path]:
    loaded_files: list[Path] = []
    for env_file in (ROOT_ENV_FILE, SERVER_ENV_FILE):
        if env_file.is_file():
            load_dotenv(env_file, override=False)
            loaded_files.append(env_file)
    return loaded_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Host the Omni9 API, app shell, mesh gateway API, and MQTT ingest.")
    parser.add_argument("--host", default=os.getenv("OMNI9_HOST", "0.0.0.0"), help="Bind host, default 0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("OMNI9_PORT") or os.getenv("PORT", "8080")), help="Bind port, default 8080")
    parser.add_argument("--workers", default=os.getenv("OMNI9_WORKERS", "1"), help="Worker count or 'auto'. Default 1 for shared live memory state.")
    parser.add_argument("--reload", action="store_true", help="Enable reload for local development")
    parser.add_argument("--no-mqtt", action="store_true", help="Disable in-process MQTT telemetry ingest")
    parser.add_argument("--log-level", default=os.getenv("OMNI9_LOG_LEVEL", "info"), choices=["debug", "info", "warning", "error", "critical"])
    return parser.parse_args()


def resolve_workers(value: str, reload_enabled: bool) -> int:
    if reload_enabled:
        return 1
    if value.lower() == "auto":
        if not os.getenv("DATABASE_URL"):
            logging.getLogger("omni9.host").warning(
                "OMNI9_WORKERS=auto requested, but DATABASE_URL is not set. Using 1 worker so live in-memory node data remains consistent."
            )
            return 1
        return max(1, cpu_count())
    return max(1, int(value))


def build_log_config(log_level: str) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = log_level.upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"},
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"},
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": str(LOG_DIR / "omni9-host.log"),
                "maxBytes": 5_000_000,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "access_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": str(LOG_DIR / "omni9-access.log"),
                "maxBytes": 5_000_000,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "omni9": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "uvicorn": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["console", "access_file"], "level": level, "propagate": False},
        },
        "root": {"handlers": ["console", "file"], "level": level},
    }


def main() -> None:
    loaded_env_files = load_environment()
    args = parse_args()
    log_config = build_log_config(args.log_level)
    logging.config.dictConfig(log_config)
    logger = logging.getLogger("omni9.host")

    if args.no_mqtt:
        os.environ["OMNI9_ENABLE_MQTT_INGEST"] = "0"

    os.chdir(SERVER_DIR)
    sys.path.insert(0, str(SERVER_DIR))
    workers = resolve_workers(args.workers, args.reload)

    logger.info("Omni9 host starting on %s:%s workers=%s reload=%s", args.host, args.port, workers, args.reload)
    if loaded_env_files:
        logger.info("Environment files: %s", ", ".join(str(path) for path in loaded_env_files))
    else:
        logger.info("Environment files: none found; using process environment and defaults")
    logger.info("Logs: %s", LOG_DIR)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        workers=workers,
        reload=args.reload,
        log_config=log_config,
        access_log=True,
    )


if __name__ == "__main__":
    main()