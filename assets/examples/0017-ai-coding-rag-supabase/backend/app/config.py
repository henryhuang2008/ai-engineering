from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Rag with Supabase  API"
    app_version: str = "0.1.0"
    allowed_origins: str
    database_url: str | None = None
    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    dashscope_api_key: SecretStr | None = None
    qwen_base_url: str | None = None
    qwen_embedding_model: str = "text-embedding-v4"
    qwen_embedding_dimensions: int = 1536

    @field_validator("allowed_origins")
    @classmethod
    def normalize_allowed_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("ALLOWED_ORIGINS must contain at least one origin")
        return ",".join(origins)

    @field_validator("supabase_url")
    @classmethod
    def normalize_supabase_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("SUPABASE_URL must not be empty")
        return normalized

    @field_validator("supabase_anon_key")
    @classmethod
    def validate_supabase_anon_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("SUPABASE_ANON_KEY must not be empty")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return self.allowed_origins.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
