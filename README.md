# Omni9 API-Only Deploy

Use this folder as the Coolify app root when you only want to host the Python API.

This package intentionally excludes the Vite frontend, Android project, Capacitor files, firmware, and npm files so Coolify does not run `npm run build`.

## Coolify

```text
Base directory: api
Build pack: Nixpacks
Port: 8080
```

The included `nixpacks.toml` installs Python dependencies and starts the API:

```bash
python main.py --host 0.0.0.0
```

The wrapper reads `PORT` / `OMNI9_PORT` and defaults to `8080`.

If Coolify's Nixpacks image still fails around `pip`, switch the build pack to Dockerfile. This folder includes a Python-only `Dockerfile` using `python:3.12-slim`.

Set production values in Coolify environment variables using `.env.example` as the template. Do not rely on committing a real `.env` with secrets.

## Required Environment

Start with these required values in Coolify:

```text
PORT=8080
OMNI9_PORT=8080
APP_ENV=production
APP_CORS_ORIGINS=https://your-web-app.example.com,capacitor://localhost,http://localhost
JWT_SECRET=replace_with_64_character_random_secret
MESH_GATEWAY_TOKEN=replace_with_mesh_gateway_token
```

For real ESP telemetry and commands, add MQTT:

```text
MQTT_HOST=replace_with_mqtt_host
MQTT_PORT=443
MQTT_USERNAME=${SERVICE_USER_MOSQUITTO}
MQTT_PASSWORD=${SERVICE_PASSWORD_MOSQUITTO}
MQTT_BASE_TOPIC=omni9
MQTT_TRANSPORT=tcp
MQTT_TLS=true
SERVICE_URL_MOSQUITTO=https://mosquitto.taxsomega.com
SERVICE_URL_MOSQUITTO_1883=
SERVICE_FQDN_MOSQUITTO_1883=
OMNI9_ENABLE_MQTT_INGEST=1
```

For media evidence, voice output, and reports, add S3-compatible storage:

```text
STORAGE_DRIVER=s3
S3_ENDPOINT_URL=https://replace-with-s3-endpoint.example.com
S3_REGION=us-east-1
S3_ACCESS_KEY=replace_with_s3_access_key
S3_SECRET_KEY=replace_with_s3_secret_key
S3_BUCKET=omni9-media
S3_PUBLIC_BASE_URL=https://replace-with-public-media-domain.example.com
```

`DATABASE_URL` is optional for the current in-memory live API, but host PostgreSQL before production if you want persistent history, SQL context, work orders, and records to survive restarts.

## What To Host Next

1. Host this `api` folder first and confirm `/health` returns `ok`.
2. Host an MQTT broker, then update `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, and `MQTT_PASSWORD`.
3. Host S3-compatible storage such as SeaweedFS, MinIO, Garage, or AWS S3, then fill the `S3_*` values.
4. Host PostgreSQL and run the SQL files in `server/sql` when you need persistent production data.
5. Point the ESP firmware and mobile app API base URL to the Coolify API domain.

## Local Check

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --host 127.0.0.1 --port 8080 --no-mqtt
```

Then open:

```text
http://127.0.0.1:8080/health
```

## Production Route Check

After Coolify/DNS is updated, verify the public domain is serving this API before testing the APK:

```powershell
python ..\scripts\verify_omni_api.py --base-url https://api.taxsomega.com --insecure
```

When `/health` returns `service: omni9-api`, clear stale in-memory nodes with:

```powershell
python ..\scripts\verify_omni_api.py --base-url https://api.taxsomega.com --insecure --clear
```