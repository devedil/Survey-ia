import ipaddress
from functools import lru_cache
import re
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Survey Assistant"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "postgresql+psycopg://app_user:app_password@localhost:5432/ai_survey_assistant"
    jwt_secret_key: str = "replace_with_a_strong_secret"
    chrome_extension_api_token: SecretStr = SecretStr("")
    cors_allowed_origins: str = "http://localhost:4200,http://127.0.0.1:4200"
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
    browser_allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("chrome_extension_api_token")
    @classmethod
    def validate_chrome_extension_api_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if token and len(token) < 32:
            raise ValueError("CHROME_EXTENSION_API_TOKEN must contain at least 32 characters")
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_allowed_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain exact origins and cannot use *")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ALLOWED_ORIGINS must contain origins without paths")
            if parsed.scheme == "chrome-extension":
                if not re.fullmatch(r"[a-p]{32}", parsed.netloc):
                    raise ValueError("Chrome extension CORS origins must contain an exact extension ID")
            elif parsed.scheme in {"http", "https"} and parsed.hostname:
                try:
                    loopback = parsed.hostname.casefold() == "localhost" or ipaddress.ip_address(
                        parsed.hostname
                    ).is_loopback
                except ValueError:
                    loopback = False
                if not loopback:
                    raise ValueError("HTTP CORS origins must use a loopback host")
                try:
                    parsed.port
                except ValueError as error:
                    raise ValueError("CORS origin port is invalid") from error
            else:
                raise ValueError("CORS origins must be loopback HTTP(S) or an exact Chrome extension origin")
        return ",".join(origin.rstrip("/") for origin in origins)

    @model_validator(mode="after")
    def validate_document_chunking(self) -> "Settings":
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError("DOCUMENT_CHUNK_OVERLAP must be smaller than DOCUMENT_CHUNK_SIZE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
