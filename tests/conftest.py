"""Pytest configuration and fixtures."""

import asyncio
import json
import os
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock, AsyncMock

import asyncpg
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from src.config import Settings
from src.database.connection import DatabasePool
from src.database.events import EventRepository
from src.llm.extraction import ExtractionService
from src.models.event import EventExtraction


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container() -> Generator:
    """Create a PostgreSQL test container with pgvector extension."""
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        user="test",
        password="test",
        dbname="test_db",
        driver=None
    )
    container.start()

    # Wait for container to be ready
    import time
    time.sleep(2)

    yield container
    container.stop()


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    """Get the database URL for the test container."""
    return postgres_container.get_connection_url().replace("psycopg2", "asyncpg")


@pytest_asyncio.fixture
async def db_pool(database_url: str) -> AsyncGenerator:
    """Create a database pool for testing."""
    pool = DatabasePool()
    await pool.initialize(database_url)

    # Initialize schema
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path, "r") as f:
            schema_sql = f.read()

        async with pool.pool.acquire() as conn:
            # Split and execute statements
            statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
            for statement in statements:
                try:
                    await conn.execute(statement)
                except Exception as e:
                    print(f"Error executing statement: {e}")

    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def event_repo(db_pool: DatabasePool) -> EventRepository:
    """Create an event repository for testing."""
    return EventRepository(db_pool)


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    mock = AsyncMock()
    mock.achat = AsyncMock()
    return mock


@pytest.fixture
def mock_extraction_response() -> EventExtraction:
    """Mock extraction response."""
    return EventExtraction(
        title="Test Event Title",
        language="uk",
        city="Київ",
        country="UA",
        is_remote=False,
        organizer="Test Organization",
        apply_url="https://example.com/apply",
        occurs_from=None,
        occurs_to=None,
        deadline_at=None,
        status="active",
        categories_slugs=["internship", "workshop"]
    )


@pytest.fixture
def mock_sqs_message() -> dict:
    """Mock SQS message."""
    return {
        "Body": json.dumps({
            "source_id": 1,
            "run_id": 1,
            "external_id": "test_msg_123",
            "text": "Test workshop on AI Ethics in Kyiv. Apply at https://example.com",
            "posted_at": "2025-11-15T10:00:00Z",
            "author": "TestChannel",
            "metadata": {
                "source_type": "telegram",
                "source_url": "https://t.me/testchannel/123"
            }
        }),
        "ReceiptHandle": "test-receipt-handle"
    }


@pytest.fixture
def mock_sqs_client():
    """Mock SQS client."""
    mock_client = MagicMock()
    mock_client.receive_message = MagicMock(return_value={"Messages": []})
    mock_client.delete_message_batch = MagicMock(return_value={"Successful": []})
    return mock_client


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    mock = MagicMock()
    mock.embed_text = MagicMock(return_value=[0.1] * 384)
    mock.embed_texts = MagicMock(return_value=[[0.1] * 384])
    return mock


@pytest.fixture
def test_settings() -> Settings:
    """Test settings."""
    return Settings(
        database_url="postgresql://test:test@localhost:5432/test_db",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
        aws_region="us-east-1",
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        embedding_model="intfloat/multilingual-e5-small",
        api_host="0.0.0.0",
        api_port=8000,
        sqs_poll_interval_seconds=1,
        sqs_batch_size=10,
        sqs_visibility_timeout=300,
        sqs_max_retries=3,
        log_level="INFO",
        environment="test"
    )