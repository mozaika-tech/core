"""Configuration management for the application."""

import os
from typing import Optional
from pydantic import BaseModel, Field, validator


class Settings(BaseModel):
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
    llm_provider: str = "anthropic"  # anthropic | gemini | openai | deepseek
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None

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
        valid_providers = {"anthropic", "gemini", "openai", "deepseek"}
        if v not in valid_providers:
            raise ValueError(f"LLM provider must be one of: {valid_providers}")
        return v

    @validator("anthropic_api_key")
    def validate_anthropic_key(cls, v, values):
        """Ensure Anthropic API key is provided when using Anthropic provider."""
        if values.get("llm_provider") == "anthropic" and not v:
            raise ValueError("ANTHROPIC_API_KEY is required when using anthropic provider")
        return v

    @validator("gemini_api_key")
    def validate_gemini_key(cls, v, values):
        """Ensure Gemini API key is provided when using Gemini provider."""
        if values.get("llm_provider") == "gemini" and not v:
            raise ValueError("GEMINI_API_KEY is required when using gemini provider")
        return v

    @validator("openai_api_key")
    def validate_openai_key(cls, v, values):
        """Ensure OpenAI API key is provided when using OpenAI provider."""
        if values.get("llm_provider") == "openai" and not v:
            raise ValueError("OPENAI_API_KEY is required when using openai provider")
        return v

    @validator("deepseek_api_key")
    def validate_deepseek_key(cls, v, values):
        """Ensure DeepSeek API key is provided when using DeepSeek provider."""
        if values.get("llm_provider") == "deepseek" and not v:
            raise ValueError("DEEPSEEK_API_KEY is required when using deepseek provider")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings singleton."""
    # Load from environment variables
    from dotenv import load_dotenv
    load_dotenv()

    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        sqs_queue_url=os.getenv("SQS_QUEUE_URL", ""),
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
        llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        sqs_poll_interval_seconds=int(os.getenv("SQS_POLL_INTERVAL_SECONDS", "20")),
        sqs_batch_size=int(os.getenv("SQS_BATCH_SIZE", "10")),
        sqs_visibility_timeout=int(os.getenv("SQS_VISIBILITY_TIMEOUT", "300")),
        sqs_max_retries=int(os.getenv("SQS_MAX_RETRIES", "3")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        environment=os.getenv("ENVIRONMENT", "production")
    )


# Create a global settings instance
settings = get_settings()