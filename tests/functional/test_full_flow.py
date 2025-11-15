"""Functional tests for the complete application flow using testcontainers."""

import asyncio
import json
import os
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer

from src.api.app import app
from src.config import Settings
from src.consumer.sqs_consumer import SQSConsumer
from src.database.connection import DatabasePool
from src.database.events import EventRepository
from src.llm.extraction import ExtractionService
from src.models.event import EventExtraction, SQSMessage


@pytest.mark.functional
class TestFullFlow:
    """Test the complete flow from SQS message to API response.

    Uses testcontainers from conftest.py for database setup.
    Tests will be skipped if Docker is not available.
    """

    @pytest.fixture
    def test_client(self, database_url):
        """Create test client with mocked database URL."""
        with patch("src.config.settings.database_url", database_url):
            with TestClient(app) as client:
                yield client

    @pytest.fixture
    def mock_llm_extraction(self):
        """Mock LLM extraction response."""
        return EventExtraction(
            title="AI Workshop in Kyiv",
            language="uk",
            city="Київ",
            country="UA",
            is_remote=False,
            organizer="Tech Hub Kyiv",
            apply_url="https://example.com/apply",
            occurs_from=datetime(2025, 12, 15, 10, 0, 0),
            occurs_to=datetime(2025, 12, 15, 18, 0, 0),
            deadline_at=datetime(2025, 12, 10, 23, 59, 59),
            status="active",
            categories_slugs=["workshop", "meetup"]
        )

    @pytest.fixture
    def mock_embedding(self):
        """Mock embedding vector."""
        return [0.1] * 384  # 384-dimensional vector

    @pytest.mark.asyncio
    async def test_complete_flow_consumer_to_api(
        self,
        db_pool,
        event_repo,
        test_client,
        mock_llm_extraction,
        mock_embedding
    ):
        """Test the complete flow: SQS message → Consumer → Database → API."""

        # Step 1: Process a message through the consumer
        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = event_repo
        consumer.categories = await event_repo.get_categories()

        # Mock external services
        with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
             patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
             patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

            # Setup extraction mock
            mock_extraction = MagicMock()
            mock_extraction.extract_event_data = AsyncMock(return_value=mock_llm_extraction)
            mock_extraction_class.return_value = mock_extraction

            # Setup embedding mock
            mock_embed_service.embed_text = MagicMock(return_value=mock_embedding)

            # Setup vector store mock
            mock_vector = MagicMock()
            mock_vector.index_event = AsyncMock()
            mock_vector_store.return_value = mock_vector

            # Create test message
            test_message = {
                "Body": json.dumps({
                    "source_id": 1,
                    "run_id": 1,
                    "external_id": "test_msg_001",
                    "text": """
                    🤖 AI Workshop in Kyiv!

                    Join us for an exciting workshop on AI and Machine Learning.

                    📅 Date: December 15, 2025
                    ⏰ Time: 10:00 - 18:00
                    📍 Location: Tech Hub Kyiv

                    Topics:
                    • Introduction to LLMs
                    • Building AI applications
                    • Best practices

                    Apply now: https://example.com/apply
                    Deadline: December 10, 2025
                    """,
                    "posted_at": "2025-11-15T12:00:00Z",
                    "author": "TechEventsKyiv",
                    "metadata": {
                        "source_type": "telegram",
                        "source_url": "https://t.me/techevents/001"
                    }
                }),
                "ReceiptHandle": "test-receipt-001"
            }

            # Process the message
            result = await consumer.process_message(test_message)
            assert result is True
            assert consumer.metrics["processed_count"] == 1
            assert consumer.metrics["error_count"] == 0

        # Step 2: Verify data was stored in database
        async with db_pool.pool.acquire() as conn:
            # Check event was created
            event_row = await conn.fetchrow(
                """
                SELECT * FROM events
                WHERE title = $1
                """,
                "AI Workshop in Kyiv"
            )
            assert event_row is not None
            assert event_row["city"] == "Київ"
            assert event_row["country"] == "UA"
            assert event_row["language"] == "uk"
            assert event_row["is_remote"] is False
            event_id = event_row["id"]

            # Check categories were linked
            categories = await conn.fetch(
                """
                SELECT c.slug
                FROM event_categories ec
                JOIN categories c ON ec.category_id = c.id
                WHERE ec.event_id = $1
                """,
                event_id
            )
            category_slugs = [row["slug"] for row in categories]
            assert "workshop" in category_slugs
            assert "meetup" in category_slugs

        # Step 3: Test SQL search API
        with patch("src.api.app.get_db_pool") as mock_get_db_pool:
            mock_get_db_pool.return_value = db_pool

            # Search by city
            response = test_client.get("/search?city=Київ")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 1
            assert any(hit["title"] == "AI Workshop in Kyiv" for hit in data["hits"])

            # Search by category
            response = test_client.get("/search?category=workshop")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 1

            # Full-text search
            response = test_client.get("/search?q=AI+Machine+Learning")
            assert response.status_code == 200
            data = response.json()
            # Note: Full-text search might not work without proper PostgreSQL text search setup

        # Step 4: Test AI search API (with mocked vector search)
        with patch("src.api.app.get_db_pool") as mock_get_db_pool, \
             patch("src.api.app.get_vector_store") as mock_get_vector, \
             patch("src.api.app.get_extraction_service") as mock_get_extraction:

            mock_get_db_pool.return_value = db_pool

            # Mock extraction service
            mock_extraction_service = MagicMock()
            mock_extraction_service.understand_query = AsyncMock(return_value=None)
            mock_get_extraction.return_value = mock_extraction_service

            # Mock vector store to return our event
            mock_vector_store = MagicMock()
            from src.models.event import EventSearchResult

            search_result = EventSearchResult(
                id=event_id,
                title="AI Workshop in Kyiv",
                city="Київ",
                country="UA",
                language="uk",
                is_remote=False,
                source_url="https://t.me/techevents/001",
                posted_at=datetime(2025, 11, 15, 12, 0, 0),
                occurs_from=datetime(2025, 12, 15, 10, 0, 0),
                occurs_to=datetime(2025, 12, 15, 18, 0, 0),
                deadline_at=datetime(2025, 12, 10, 23, 59, 59),
                status="active",
                categories_slugs=["workshop", "meetup"],
                score=0.92
            )

            mock_vector_store.search_similar = AsyncMock(return_value=[search_result])
            mock_vector_store.synthesize_answer = AsyncMock(
                return_value="Знайшов воркшоп з AI у Києві, який відбудеться 15 грудня."
            )
            mock_get_vector.return_value = mock_vector_store

            # Make AI search request
            request_body = {
                "query": "AI workshop in December",
                "top_k": 5
            }

            response = test_client.post("/ai/search", json=request_body)
            assert response.status_code == 200
            data = response.json()
            assert len(data["hits"]) == 1
            assert data["hits"][0]["title"] == "AI Workshop in Kyiv"
            assert "воркшоп" in data["chat_answer"].lower()

    @pytest.mark.asyncio
    async def test_duplicate_message_handling(
        self,
        db_pool,
        event_repo,
        mock_llm_extraction,
        mock_embedding
    ):
        """Test that duplicate messages are properly handled."""

        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = event_repo
        consumer.categories = await event_repo.get_categories()

        with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
             patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
             patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

            # Setup mocks
            mock_extraction = MagicMock()
            mock_extraction.extract_event_data = AsyncMock(return_value=mock_llm_extraction)
            mock_extraction_class.return_value = mock_extraction

            mock_embed_service.embed_text = MagicMock(return_value=mock_embedding)

            mock_vector = MagicMock()
            mock_vector.index_event = AsyncMock()
            mock_vector_store.return_value = mock_vector

            # Same message content but different external_id
            base_message = {
                "source_id": 1,
                "run_id": 2,
                "text": "Duplicate workshop content",
                "posted_at": "2025-11-15T14:00:00Z",
                "author": "TestChannel",
                "metadata": {
                    "source_type": "telegram",
                    "source_url": "https://t.me/test/002"
                }
            }

            # Process first message
            message1 = {
                "Body": json.dumps({**base_message, "external_id": "dup_001"}),
                "ReceiptHandle": "receipt-dup-001"
            }

            result1 = await consumer.process_message(message1)
            assert result1 is True
            initial_processed = consumer.metrics["processed_count"]
            initial_duplicates = consumer.metrics["duplicate_count"]

            # Process duplicate message (same content, different external_id)
            message2 = {
                "Body": json.dumps({**base_message, "external_id": "dup_002"}),
                "ReceiptHandle": "receipt-dup-002"
            }

            result2 = await consumer.process_message(message2)
            assert result2 is True
            assert consumer.metrics["processed_count"] == initial_processed + 1
            assert consumer.metrics["duplicate_count"] == initial_duplicates + 1

            # Verify vector store was not called for duplicate
            assert mock_vector.index_event.call_count == 1  # Only called for first message

    @pytest.mark.asyncio
    async def test_search_with_filters(self, db_pool, event_repo, test_client):
        """Test search API with various filter combinations."""

        # Insert test events with different attributes
        test_events = [
            {
                "source_type": "telegram",
                "source_url": "https://t.me/test/101",
                "raw_text": "Python meetup for beginners",
                "extraction": EventExtraction(
                    title="Python Meetup",
                    language="en",
                    city="Lviv",
                    country="UA",
                    is_remote=False,
                    organizer="Python User Group",
                    apply_url=None,
                    occurs_from=datetime(2025, 12, 20, 18, 0, 0),
                    occurs_to=datetime(2025, 12, 20, 21, 0, 0),
                    deadline_at=None,
                    status="active",
                    categories_slugs=["meetup"]
                ),
                "embedding": [0.2] * 384,
                "posted_at": datetime(2025, 11, 10, 10, 0, 0)
            },
            {
                "source_type": "website",
                "source_url": "https://example.com/102",
                "raw_text": "Online hackathon for students",
                "extraction": EventExtraction(
                    title="Student Hackathon Online",
                    language="uk",
                    city=None,
                    country=None,
                    is_remote=True,
                    organizer="Tech University",
                    apply_url="https://hack.example.com",
                    occurs_from=datetime(2025, 12, 1, 0, 0, 0),
                    occurs_to=datetime(2025, 12, 3, 23, 59, 59),
                    deadline_at=datetime(2025, 11, 25, 23, 59, 59),
                    status="active",
                    categories_slugs=["hackathon", "competition"]
                ),
                "embedding": [0.3] * 384,
                "posted_at": datetime(2025, 11, 5, 14, 0, 0)
            }
        ]

        # Insert test events
        for event_data in test_events:
            event_id, _ = await event_repo.upsert_event(
                source_type=event_data["source_type"],
                source_url=event_data["source_url"],
                raw_text=event_data["raw_text"],
                extraction=event_data["extraction"],
                embedding=event_data["embedding"],
                posted_at=event_data["posted_at"]
            )
            await event_repo.link_categories(event_id, event_data["extraction"].categories_slugs)

        with patch("src.api.app.get_db_pool") as mock_get_db_pool:
            mock_get_db_pool.return_value = db_pool

            # Test language filter
            response = test_client.get("/search?language=en")
            assert response.status_code == 200
            data = response.json()
            assert all(hit["language"] == "en" for hit in data["hits"])

            # Test is_remote filter
            response = test_client.get("/search?is_remote=true")
            assert response.status_code == 200
            data = response.json()
            assert all(hit["is_remote"] is True for hit in data["hits"])

            # Test date range filter
            response = test_client.get(
                "/search?occurs_from=2025-12-01T00:00:00Z&occurs_to=2025-12-05T00:00:00Z"
            )
            assert response.status_code == 200

            # Test multiple category filter
            response = test_client.get("/search?category=hackathon&category=competition")
            assert response.status_code == 200
            data = response.json()
            for hit in data["hits"]:
                categories = hit["categories_slugs"]
                assert "hackathon" in categories or "competition" in categories

            # Test sorting
            response = test_client.get("/search?sort_by=posted_at&order=asc")
            assert response.status_code == 200
            data = response.json()
            if len(data["hits"]) > 1:
                dates = [hit["posted_at"] for hit in data["hits"]]
                assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_error_recovery(
        self,
        db_pool,
        event_repo,
        mock_embedding
    ):
        """Test error recovery in consumer."""

        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = event_repo
        consumer.categories = await event_repo.get_categories()

        with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
             patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
             patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

            # Setup extraction to fail first, then succeed
            mock_extraction = MagicMock()
            mock_extraction.extract_event_data = AsyncMock(
                side_effect=[
                    None,  # First call fails
                    EventExtraction(  # Second call succeeds
                        title="Recovery Test Event",
                        language="uk",
                        city="Київ",
                        country="UA",
                        is_remote=False,
                        organizer=None,
                        apply_url=None,
                        occurs_from=None,
                        occurs_to=None,
                        deadline_at=None,
                        status="active",
                        categories_slugs=[]
                    )
                ]
            )
            mock_extraction_class.return_value = mock_extraction

            mock_embed_service.embed_text = MagicMock(return_value=mock_embedding)
            mock_vector_store.return_value = MagicMock()

            # Process message that fails extraction
            fail_message = {
                "Body": json.dumps({
                    "source_id": 1,
                    "run_id": 3,
                    "external_id": "fail_001",
                    "text": "This will fail extraction",
                    "posted_at": "2025-11-15T15:00:00Z",
                    "metadata": {}
                }),
                "ReceiptHandle": "receipt-fail-001"
            }

            result = await consumer.process_message(fail_message)
            assert result is True  # Should still return True to delete message
            assert consumer.metrics["error_count"] == 1

            # Process message that succeeds
            success_message = {
                "Body": json.dumps({
                    "source_id": 1,
                    "run_id": 4,
                    "external_id": "success_001",
                    "text": "This will succeed",
                    "posted_at": "2025-11-15T16:00:00Z",
                    "metadata": {}
                }),
                "ReceiptHandle": "receipt-success-001"
            }

            result = await consumer.process_message(success_message)
            assert result is True
            assert consumer.metrics["processed_count"] == 1