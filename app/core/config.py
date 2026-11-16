from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, field_validator
from typing import Literal


class Settings(BaseSettings):
    app_name: str = "Timeblind AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    render: bool = False
    database_url: str = "sqlite:///./timeblind_ai.db"
    database_echo: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_from: str = ""
    smtp_ssl: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,https://timeblind-frontend.onrender.com"
    llm_enabled: bool = False
    llm_provider: Literal["openai", "groq"] = "openai"
    openai_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    llm_model: str = "gpt-4.1-mini-2025-04-14"
    llm_timeout_seconds: float = Field(25, ge=1, le=120)
    llm_max_output_tokens: int = Field(4000, ge=500, le=16000)
    llm_failure_mode: Literal["fallback", "error"] = "fallback"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        if value.startswith(("postgres://", "postgresql://")):
            return "postgresql+psycopg://" + value.split("://", 1)[1]
        return value

    @property
    def planning_api_key(self) -> SecretStr | None:
        return self.groq_api_key if self.llm_provider == "groq" else self.openai_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
