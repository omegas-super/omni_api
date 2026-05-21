# Omni9 Server Scaffold

This is the first FastAPI backend scaffold for the app, ESP32 direct MQTT nodes, ESP32 mesh gateways, and voice assistant flow.

## Run Locally

```powershell
python -m venv server/.venv
server\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py --reload
```

The root `main.py` wrapper hosts the FastAPI API, app shell, mesh gateway WebSocket, static Vite build at `/app` when `dist/` exists, and in-process MQTT telemetry ingest. The app folder now keeps `main.py`, `.env`, `.env.example`, and `requirements.txt` together for host platforms. Logs are written to `server/logs/omni9-host.log` and access requests to `server/logs/omni9-access.log` while also streaming to the terminal.

Environment loading prefers the root `.env` beside `main.py`; `server/.env` is still accepted as a legacy fallback.

Production example:

```powershell
python main.py --host 0.0.0.0 --port 8080 --workers 1 --log-level info
```

Keep `--workers 1` until PostgreSQL or another shared store backs live machine state; the current store and mesh WebSocket registry are in-memory and should stay in one API process.

Health check:

```bash
curl http://127.0.0.1:8080/health
```

## Main App Endpoints

```text
GET  /health
GET  /v1/app/bootstrap
GET  /v1/sites/{site_id}/summary
GET  /v1/sites/{site_id}/machines
GET  /v1/sites/{site_id}/machines/{machine_id}
GET  /v1/sites/{site_id}/alerts
GET  /v1/sites/{site_id}/actions
GET  /v1/sites/{site_id}/impact
GET  /v1/sites/{site_id}/mesh
POST /v1/sites/{site_id}/machines/{machine_id}/commands/safe-stop
POST /v1/sites/{site_id}/machines/{machine_id}/commands/resume
POST /v1/sites/{site_id}/machines/{machine_id}/commands/identify
POST /v1/sites/{site_id}/machines/{machine_id}/protection-mode
POST /v1/voice/sessions
POST /v1/voice/sessions/{voice_session_id}/turns
WS   /v1/mesh/ws
```

This scaffold uses an in-memory store so the API shape can be tested before wiring PostgreSQL. Replace `app/state.py` with SQLAlchemy/PostgreSQL persistence when moving to deployment.
