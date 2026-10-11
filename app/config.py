from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    kafka_bootstrap_servers: str = "localhost:19092"
    kafka_topic: str = "music-events"
    kafka_dlq_topic: str = "music-events-dlq"
    kafka_group_id: str = "music-event-processors"
    kafka_security_protocol: str = "PLAINTEXT"
    eventhub_namespace: str = ""
    redis_url: str = "redis://localhost:6379/0"
    service_role: str = "api"
    api_read_token: SecretStr = SecretStr("")
    api_write_token: SecretStr = SecretStr("")
    pii_hmac_key: SecretStr = SecretStr("")
    archive_dir: str = "data/events"
    azure_storage_account_url: str = ""
    azure_storage_container: str = "music-events"
    recommendation_limit: int = Field(default=10, ge=1, le=100)
    consumer_max_retries: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if self.service_role.lower() not in {"api", "worker"}:
            raise ValueError("SERVICE_ROLE must be api or worker")
        secrets = [("PII_HMAC_KEY", self.pii_hmac_key)]
        if self.service_role.lower() == "api":
            if self.api_read_token.get_secret_value() == self.api_write_token.get_secret_value():
                raise ValueError("API_READ_TOKEN and API_WRITE_TOKEN must be different")
            secrets.extend(
                [("API_READ_TOKEN", self.api_read_token), ("API_WRITE_TOKEN", self.api_write_token)]
            )
        for name, secret in secrets:
            if len(secret.get_secret_value()) < 32:
                raise ValueError(f"{name} must contain at least 32 characters")

        if self.app_env.lower() == "production":
            for name, secret in secrets:
                value = secret.get_secret_value()
                if len(value) < 32 or value.startswith(("replace-with-", "local-")):
                    raise ValueError(f"{name} must be a non-placeholder secret of at least 32 characters")
            if not self.eventhub_namespace:
                raise ValueError("EVENTHUB_NAMESPACE is required in production")
            if not self.azure_storage_account_url:
                raise ValueError("AZURE_STORAGE_ACCOUNT_URL is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
