from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Timeblind AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = "sqlite:///./timeblind_ai.db"
    database_echo: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
