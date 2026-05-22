import logging
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.mqtt_worker import start_background_worker, stop_background_worker
from app.routers import ai, app_shell, live, machines, media, mesh, sites, voice

settings = get_settings()
logger = logging.getLogger("omni9.api")

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_shell.router)
app.include_router(sites.router)
app.include_router(machines.router)
app.include_router(live.router)
app.include_router(media.router)
app.include_router(mesh.router)
app.include_router(ai.router)
app.include_router(voice.router)


@app.on_event("startup")
def startup_services():
    logger.info("Starting %s in %s mode", settings.app_name, settings.app_env)
    if os.getenv("OMNI9_ENABLE_MQTT_INGEST", "1") != "0":
        start_background_worker()


@app.on_event("shutdown")
def shutdown_services():
    stop_background_worker()


@app.middleware("http")
async def log_requests(request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "dist"))
if os.path.isdir(dist_dir):
    app.mount("/app", StaticFiles(directory=dist_dir, html=True), name="omni9-app")


@app.get("/health")
def health():
    return {"status": "ok", "service": "omni9-api", "env": settings.app_env}
