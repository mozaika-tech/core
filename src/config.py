"""Configuration management for the application."""

import os
from typing import Optional
from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str

    # SQS
    sqs_queue_url: str
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_endpoint_url: Optional[str] = None  # For LocalStack testing

    # LLM Configuration
    llm_provider: str = "anthropic"  # anthropic | gemini | openai
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Embedding
    embedding_model: str = "intfloat/multilingual-e5-small"

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # SQS Consumer Settings
    sqs_poll_interval_seconds: int = 20
    sqs_batch_size: int = 10
    sqs_visibility_timeout: int = 300
    sqs_max_retries: int = 3

    # Application Settings
    log_level: str = "INFO"
    environment: str = "production"

    @validator("llm_provider")
    def validate_llm_provider(cls, v):
        """Validate LLM provider is supported."""
        valid_providers = {"anthropic", "gemini", "openai"}
        if v not in valid_providers:
            raise ValueError(f"LLM provider must be one of: {valid_providers}")
        return v

    @validator("anthropic_api_key", "gemini_api_key", "openai_api_key")
    def validate_api_keys(cls, v, values):
        """Ensure the selected LLM provider has an API key."""
        if "llm_provider" in values:
            provider = values["llm_provider"]
            if provider == "anthropic" and values.get("anthropic_api_key") is None:
                if v is None and cls.__fields__.get("anthropic_api_key"):
                    raise ValueError("ANTHROPIC_API_KEY is required when using anthropic provider")
            elif provider == "gemini" and values.get("gemini_api_key") is None:
                if v is None and cls.__fields__.get("gemini_api_key"):
                    raise ValueError("GEMINI_API_KEY is required when using gemini provider")
            elif provider == "openai" and values.get("openai_api_key") is None:
                if v is None and cls.__fields__.get("openai_api_key"):
                    raise ValueError("OPENAI_API_KEY is required when using openai provider")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()


# Create a global settings instance
settings = get_settings()