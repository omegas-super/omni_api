FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    OMNI9_HOST=0.0.0.0 \
    OMNI9_PORT=8080 \
    OMNI9_WORKERS=1 \
    OMNI9_LOG_LEVEL=info \
    OMNI9_ENABLE_MQTT_INGEST=1 \
    APP_ENV=production \
    APP_NAME="Omni9 API" \
    APP_CORS_ORIGINS="https://api.taxsomega.com,http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost,https://localhost,capacitor://localhost,ionic://localhost" \
    DEFAULT_SITE_ID=main_site \
    MQTT_HOST=mosquitto.taxsomega.com \
    MQTT_PORT=443 \
    MQTT_BASE_TOPIC=omni9 \
    MQTT_TRANSPORT=tcp \
    MQTT_TLS=true \
    MQTT_WS_PATH=/mqtt \
    SERVICE_FQDN_MOSQUITTO=mosquitto.taxsomega.com \
    SERVICE_URL_MOSQUITTO=https://mosquitto.taxsomega.com \
    SERVICE_URL_MOSQUITTO_1883="" \
    SERVICE_FQDN_MOSQUITTO_1883="" \
    STORAGE_DRIVER=s3 \
    S3_ENDPOINT_URL=https://s3.taxsomega.com \
    S3_ADMIN_URL=https://s3-admin.taxsomega.com \
    S3_REGION=us-east-1 \
    S3_BUCKET=omni9-media \
    S3_PUBLIC_BASE_URL=https://s3.taxsomega.com \
    SERVICE_URL_S3=https://s3.taxsomega.com \
    SERVICE_URL_ADMIN=https://s3-admin.taxsomega.com \
    SERVICE_FQDN_S3=s3.taxsomega.com \
    SERVICE_FQDN_ADMIN=s3-admin.taxsomega.com

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=3).read()"

CMD ["python", "main.py"]