from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys
    OPENROUTER_API_KEY: str
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ats_user:ats_password@localhost:5432/ats_parser"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # LLM Settings — OpenRouter model ID, e.g. google/gemini-2.0-flash-exp:free
    LLM_MODEL: str = "google/gemini-2.5-flash"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 8192
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 90

    # Parser Settings
    MAX_FILE_SIZE_MB: int = 10
    MIN_TEXT_LENGTH: int = 100
    MIN_CONFIDENCE_FOR_AUTO_ACCEPT: float = 0.70

    # Embeddings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # Storage
    UPLOAD_DIR: str = "./uploads"


settings = Settings()
