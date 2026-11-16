from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Survey Assistant"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "postgresql+psycopg://app_user:app_password@localhost:5432/ai_survey_assistant"
    openai_api_key: str = "replace_me"
    openai_default_model: str = ""
    openai_embedding_model: str = ""
    openai_pricing_catalog: str = "{}"
    max_input_tokens_per_call: int = Field(default=8000, ge=1)
    max_output_tokens_per_call: int = Field(default=1000, ge=1)
    max_retries_per_question: int = Field(default=1, ge=0, le=3)
    max_calls_per_question: int = Field(default=3, ge=1, le=5)
    document_storage_path: str = "./storage/documents"
    max_upload_mb: int = Field(default=20, ge=1)
    document_chunk_size: int = Field(default=1000, ge=1)
    document_chunk_overlap: int = Field(default=150, ge=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_document_chunking(self) -> "Settings":
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError("DOCUMENT_CHUNK_OVERLAP must be smaller than DOCUMENT_CHUNK_SIZE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
