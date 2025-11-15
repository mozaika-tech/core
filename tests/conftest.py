"""Pytest configuration and fixtures with comprehensive mocking and testcontainers."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator, Optional
from unittest.mock import MagicMock, AsyncMock, patch
from dotenv import load_dotenv

import pytest
import pytest_asyncio

from src.config import Settings
from src.database.connection import DatabasePool
from src.database.events import EventRepository
from src.llm.extraction import ExtractionService
from src.models.event import EventExtraction

# Load test environment
load_dotenv('.env.test')

# Disable real API calls in tests
os.environ['DISABLE_EXTERNAL_APIS'] = 'true'
os.environ['USE_MOCKS'] = 'true'


def is_docker_available():
    """Check if Docker is available."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


# Check Docker availability once
DOCKER_AVAILABLE = is_docker_available()


@pytest.fixture(scope="session", autouse=True)
def mock_environment():
    """Ensure test environment is used."""
    os.environ['ENVIRONMENT'] = 'test'
    os.environ['LLM_PROVIDER'] = 'mock'


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[Optional[object], None, None]:
    """Create a PostgreSQL test container with pgvector extension."""
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker is not available - skipping tests requiring database")
        return

    try:
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer(
            image="pgvector/pgvector:pg16",
            username="test",
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
    except Exception as e:
        pytest.skip(f"Failed to start PostgreSQL container: {e}")


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    """Get the database URL for the test container."""
    if postgres_container is None:
        pytest.skip("PostgreSQL container not available")

    return postgres_container.get_connection_url().replace("psycopg2", "asyncpg")


@pytest_asyncio.fixture
async def db_pool(database_url: str) -> AsyncGenerator[DatabasePool, None]:
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

    # Clean up data from previous tests (keep schema, truncate tables)
    async with pool.pool.acquire() as conn:
        try:
            await conn.execute("TRUNCATE TABLE event_categories, events, categories CASCADE")
            # Re-insert default categories
            await conn.execute("""
                INSERT INTO categories (slug, name) VALUES
                ('internship', 'Internship'),
                ('workshop', 'Workshop'),
                ('meetup', 'Meetup'),
                ('conference', 'Conference'),
                ('hackathon', 'Hackathon'),
                ('competition', 'Competition')
                ON CONFLICT (slug) DO NOTHING
            """)
        except Exception as e:
            # First time setup, tables might not exist yet
            pass

    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def event_repo(db_pool: DatabasePool) -> EventRepository:
    """Create an event repository for testing."""
    return EventRepository(db_pool)


@pytest.fixture(autouse=True)
def mock_llm_providers():
    """Mock all LLM providers to prevent real API calls."""
    with patch('src.llm.llm_factory.Anthropic') as mock_anthropic, \
         patch('src.llm.llm_factory.OpenAI') as mock_openai, \
         patch('src.llm.llm_factory.Gemini') as mock_gemini:

        # Mock Anthropic
        mock_anthropic_instance = MagicMock()
        mock_anthropic_instance.messages.create = MagicMock(return_value=MagicMock(
            content=[MagicMock(text=json.dumps({
                "title": "Mock Event Title",
                "language": "uk",
                "city": "Київ",
                "country": "UA",
                "is_remote": False,
                "organizer": "Mock Organization",
                "apply_url": "https://example.com/apply",
                "occurs_from": None,
                "occurs_to": None,
                "deadline_at": None,
                "status": "active",
                "categories_slugs": ["internship"]
            }))]
        ))
        mock_anthropic.return_value = mock_anthropic_instance

        # Mock OpenAI
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create = MagicMock()
        mock_openai.return_value = mock_openai_instance

        # Mock Gemini
        mock_gemini_instance = MagicMock()
        mock_gemini_instance.generate_content = MagicMock()
        mock_gemini.return_value = mock_gemini_instance

        yield {
            'anthropic': mock_anthropic_instance,
            'openai': mock_openai_instance,
            'gemini': mock_gemini_instance
        }


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    mock = AsyncMock()
    mock.achat = AsyncMock(return_value=MagicMock(
        message=MagicMock(content=json.dumps({
            "title": "Test Event",
            "language": "uk",
            "city": "Київ",
            "country": "UA",
            "is_remote": False,
            "organizer": "Test Org",
            "apply_url": "https://example.com",
            "status": "active",
            "categories_slugs": ["internship"]
        }))
    ))
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
        occurs_from=datetime.now(),
        occurs_to=datetime.now() + timedelta(days=7),
        deadline_at=datetime.now() + timedelta(days=3),
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
    """Mock SQS client for LocalStack or testing."""
    mock_client = MagicMock()
    mock_client.receive_message = MagicMock(return_value={"Messages": []})
    mock_client.delete_message_batch = MagicMock(return_value={"Successful": []})
    return mock_client


@pytest.fixture(autouse=True)
def mock_boto3_client():
    """Automatically mock boto3 client for all tests."""
    with patch('boto3.client') as mock_boto:
        mock_sqs = MagicMock()
        mock_sqs.receive_message = MagicMock(return_value={"Messages": []})
        mock_sqs.delete_message_batch = MagicMock(return_value={"Successful": []})
        mock_sqs.send_message = MagicMock(return_value={"MessageId": "test-id"})

        def client_factory(service_name, **kwargs):
            if service_name == 'sqs':
                return mock_sqs
            return MagicMock()

        mock_boto.side_effect = client_factory
        yield mock_boto


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    mock = MagicMock()
    mock.embed_text = MagicMock(return_value=[0.1] * 384)
    mock.embed_texts = MagicMock(return_value=[[0.1] * 384])
    mock.dimension = 384
    return mock


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with mocked configurations."""
    return Settings(
        database_url="postgresql://test:test@localhost:5432/test_db",
        sqs_queue_url="http://localhost:4566/000000000000/test-queue",
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_endpoint_url="http://localhost:4566",
        llm_provider="mock",
        anthropic_api_key="test-key-mock",
        openai_api_key="test-key-mock",
        gemini_api_key="test-key-mock",
        embedding_model="intfloat/multilingual-e5-small",
        api_host="0.0.0.0",
        api_port=8000,
        sqs_poll_interval_seconds=1,
        sqs_batch_size=10,
        sqs_visibility_timeout=300,
        sqs_max_retries=3,
        log_level="INFO",
        environment="test",
        use_mocks=True,
        disable_external_apis=True
    )


# Override ExtractionService to use mocks
@pytest.fixture(autouse=True)
def mock_extraction_service(mock_extraction_response):
    """Mock extraction service for all tests."""
    with patch('src.llm.extraction.ExtractionService') as MockExtraction:
        mock_instance = MagicMock()
        mock_instance.extract_from_text = AsyncMock(return_value=mock_extraction_response)
        mock_instance.understand_query = AsyncMock(return_value={
            "query": "test query",
            "filters": {
                "city": "Київ",
                "categories": ["internship"]
            }
        })
        MockExtraction.return_value = mock_instance
        yield mock_instance


# Mock Categories loading
@pytest.fixture(autouse=True)
def mock_categories():
    """Mock categories to avoid file system access."""
    mock_categories = [
        {"slug": "internship", "name": "Internship"},
        {"slug": "workshop", "name": "Workshop"},
        {"slug": "conference", "name": "Conference"}
    ]
    with patch('src.consumer.sqs_consumer.json.load', return_value=mock_categories):
        yield mock_categories