from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


APP_DIR = Path(__file__).resolve().parents[2]
ROOT_ENV_FILE = APP_DIR / ".env"
SERVER_ENV_FILE = APP_DIR / "server" / ".env"


def _host_from_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    return parsed.hostname or raw.split("/", 1)[0].split(":", 1)[0]


def _port_from_value(value: str) -> int:
    raw = (value or "").strip()
    if not raw:
        return 0
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    return parsed.port or 0


def _scheme_from_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    return parsed.scheme.lower()


def _resolve_reference(value: str, aliases: dict[str, str]) -> str:
    raw = (value or "").strip()
    if raw.startswith("${") and raw.endswith("}"):
        return aliases.get(raw[2:-1], "")
    return raw


def _url_from_value(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    return raw if "://" in raw else f"https://{raw}"


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Omni9 API"
    app_cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost,https://localhost,capacitor://localhost,ionic://localhost"
    default_site_id: str = "main_site"
    jwt_secret: str = "development-only"

    database_url: str = ""

    mqtt_host: str = ""
    mqtt_port: int = 0
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_base_topic: str = "omni9"
    mqtt_transport: str = "tcp"
    mqtt_tls: bool = False
    mqtt_ws_path: str = "/mqtt"
    service_url_mosquitto: str = ""
    service_fqdn_mosquitto: str = ""
    service_url_mosquitto_1883: str = ""
    service_fqdn_mosquitto_1883: str = ""
    service_user_mosquitto: str = ""
    service_password_mosquitto: str = ""

    mesh_gateway_token: str = "replace_with_gateway_token"

    storage_driver: str = "seaweedfs"
    s3_endpoint_url: str = ""
    s3_admin_url: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "omni9-media"
    s3_public_base_url: str = ""

    service_url_s3: str = ""
    service_url_s3_8333: str = ""
    service_fqdn_s3: str = ""
    service_fqdn_s3_8333: str = ""
    service_url_admin: str = ""
    service_url_admin_23646: str = ""
    service_fqdn_admin: str = ""
    service_fqdn_admin_23646: str = ""
    service_user_s3: str = ""
    service_password_s3: str = ""
    service_user_admin: str = ""
    service_password_admin: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    seaweed_user_admin: str = ""
    seaweed_password_admin: str = ""

    ai_base_url: str = "https://copilot.taxsomega.com"
    ai_api_key: str = ""
    ai_chat_model: str = "gpt-5-mini"
    ai_embedding_model: str = "text-embedding-3-small"
    ai_context_row_limit: int = 20
    ai_enable_sql_context: bool = True
    ai_enable_rag: bool = True
    ai_enable_web_search: bool = True
    searx_space_url: str = "https://searx.space/data/instances.json"
    searxng_instances: str = ""
    searxng_timeout_seconds: float = 5.0
    searxng_max_instances: int = 16
    ai_default_system_prompt: str = ""
    ai_max_output_tokens: int = 120

    audio_base_url: str = "https://api.naga.ac"
    audio_api_key: str = ""
    openai_api_key: str = ""
    stt_model: str = "whisper-large-v3:free"
    ai_reasoning_model: str = "gpt-5-mini"
    tts_model: str = "gpt-4o-mini-tts:free"
    tts_voice: str = "alloy"

    model_config = SettingsConfigDict(env_file=(SERVER_ENV_FILE, ROOT_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.app_cors_origins.split(",") if item.strip()]

    @property
    def resolved_mqtt_host(self) -> str:
        return _host_from_value(
            self.mqtt_host
            or self.service_fqdn_mosquitto_1883
            or self.service_fqdn_mosquitto
            or self.service_url_mosquitto_1883
            or self.service_url_mosquitto
            or "127.0.0.1"
        )

    @property
    def resolved_mqtt_transport(self) -> str:
        transport = self.mqtt_transport.strip().lower()
        return transport if transport in {"tcp", "websockets"} else "tcp"

    @property
    def resolved_mqtt_port(self) -> int:
        if self.mqtt_port:
            return self.mqtt_port
        transport = self.resolved_mqtt_transport
        secure_service_values = (self.mqtt_host, self.service_url_mosquitto, self.service_fqdn_mosquitto)
        for value in secure_service_values:
            if _scheme_from_value(value) in {"https", "mqtts", "ssl", "tls", "wss"}:
                return _port_from_value(value) or 443
        if self.mqtt_tls and transport == "tcp":
            return _port_from_value(self.service_url_mosquitto or self.service_fqdn_mosquitto) or 443
        for value in (
            self.service_url_mosquitto_1883,
            self.service_fqdn_mosquitto_1883,
            self.service_url_mosquitto,
            self.service_fqdn_mosquitto,
        ):
            port = _port_from_value(value)
            if port:
                return port
        if transport == "websockets" and self.mqtt_tls:
            return 443
        return 1883

    @property
    def resolved_mqtt_tls(self) -> bool:
        if self.mqtt_tls:
            return True
        if self.resolved_mqtt_port == 443:
            return True
        return any(
            _scheme_from_value(value) in {"https", "mqtts", "ssl", "tls", "wss"}
            for value in (
                self.mqtt_host,
                self.service_url_mosquitto,
                self.service_fqdn_mosquitto,
                self.service_url_mosquitto_1883,
                self.service_fqdn_mosquitto_1883,
            )
        )

    @property
    def mqtt_connection_summary(self) -> dict[str, str | int | bool]:
        return {
            "host": self.resolved_mqtt_host,
            "port": self.resolved_mqtt_port,
            "transport": self.resolved_mqtt_transport,
            "tls": self.resolved_mqtt_tls,
            "baseTopic": self.mqtt_base_topic,
            "usernameConfigured": bool(self.resolved_mqtt_username),
            "passwordConfigured": bool(self.resolved_mqtt_password),
        }

    @property
    def resolved_mqtt_username(self) -> str:
        username = _resolve_reference(self.mqtt_username, {"SERVICE_USER_MOSQUITTO": self.service_user_mosquitto})
        return username or self.service_user_mosquitto or "omni_backend"

    @property
    def resolved_mqtt_password(self) -> str:
        password = _resolve_reference(self.mqtt_password, {"SERVICE_PASSWORD_MOSQUITTO": self.service_password_mosquitto})
        return password or self.service_password_mosquitto

    @property
    def resolved_s3_endpoint_url(self) -> str:
        return _url_from_value(self.s3_endpoint_url or self.service_url_s3 or self.service_url_s3_8333 or self.service_fqdn_s3 or self.service_fqdn_s3_8333)

    @property
    def resolved_s3_access_key(self) -> str:
        aliases = {"SERVICE_USER_S3": self.service_user_s3, "SERVICE_USER_ADMIN": self.service_user_admin}
        return _resolve_reference(self.s3_access_key, aliases) or _resolve_reference(self.aws_access_key_id, aliases) or self.service_user_s3

    @property
    def resolved_s3_secret_key(self) -> str:
        aliases = {"SERVICE_PASSWORD_S3": self.service_password_s3, "SERVICE_PASSWORD_ADMIN": self.service_password_admin}
        return _resolve_reference(self.s3_secret_key, aliases) or _resolve_reference(self.aws_secret_access_key, aliases) or self.service_password_s3

    @property
    def resolved_s3_admin_url(self) -> str:
        return _url_from_value(self.s3_admin_url or self.service_url_admin or self.service_url_admin_23646 or self.service_fqdn_admin or self.service_fqdn_admin_23646)

    @property
    def resolved_ai_api_key(self) -> str:
        return self.ai_api_key or self.openai_api_key or "not-required"

    @property
    def resolved_ai_base_url(self) -> str:
        value = (self.ai_base_url or "https://copilot.taxsomega.com").rstrip("/")
        if value.endswith("/v1"):
            return value
        return f"{value}/v1"

    @property
    def resolved_audio_api_key(self) -> str:
        return self.audio_api_key or self.openai_api_key

    @property
    def resolved_audio_base_url(self) -> str:
        value = (self.audio_base_url or "https://api.naga.ac").rstrip("/")
        if value.endswith("/v1"):
            return value
        return f"{value}/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
