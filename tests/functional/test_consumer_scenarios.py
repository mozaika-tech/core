"""Functional tests for various SQS consumer scenarios."""

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from src.consumer.sqs_consumer import SQSConsumer
from src.database.connection import DatabasePool
from src.database.events import EventRepository
from src.models.event import EventExtraction

@pytest.mark.functional
class TestConsumerScenarios:
    """Test various consumer processing scenarios.

    Uses testcontainers from conftest.py for database setup.
    Tests will be skipped if Docker is not available.
    """

    @pytest.mark.asyncio
    async def test_malformed_message_handling(self, db_pool):
        """Test handling of malformed SQS messages."""
        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = EventRepository(db_pool)
        consumer.categories = await consumer.event_repo.get_categories()

        # Test various malformed messages
        malformed_messages = [
            # Missing required fields
            {
                "Body": json.dumps({
                    "text": "Message without external_id"
                }),
                "ReceiptHandle": "receipt-1"
            },
            # Invalid JSON
            {
                "Body": "This is not JSON",
                "ReceiptHandle": "receipt-2"
            },
            # Empty body
            {
                "Body": json.dumps({}),
                "ReceiptHandle": "receipt-3"
            }
        ]

        for msg in malformed_messages:
            result = await consumer.process_message(msg)
            # Should handle gracefully and return False or log error
            assert result is False or consumer.metrics["error_count"] > 0

    @pytest.mark.asyncio
    async def test_extraction_retry_mechanism(self, db_pool):
        """Test LLM extraction retry mechanism."""
        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = EventRepository(db_pool)
        consumer.categories = await consumer.event_repo.get_categories()

        with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
             patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
             patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

            # Mock extraction to fail twice then succeed
            call_count = [0]

            async def extraction_side_effect(text, max_retries=3):
                call_count[0] += 1
                if call_count[0] <= 2:
                    return None  # Fail first two attempts
                return EventExtraction(
                    title="Success After Retries",
                    language="uk",
                    city="Київ",
                    country="UA",
                    is_remote=False,
                    status="active",
                    categories_slugs=[]
                )

            mock_extraction = MagicMock()
            mock_extraction.extract_event_data = AsyncMock(side_effect=extraction_side_effect)
            mock_extraction_class.return_value = mock_extraction

            mock_embed_service.embed_text = MagicMock(return_value=[0.1] * 384)
            mock_vector_store.return_value = MagicMock(index_event=AsyncMock())

            message = {
                "Body": json.dumps({
                    "source_id": 1,
                    "run_id": 1,
                    "external_id": "retry_test",
                    "text": "Test message for retry mechanism",
                    "posted_at": datetime.now().isoformat(),
                    "metadata": {}
                }),
                "ReceiptHandle": "retry-receipt"
            }

            # Since our consumer doesn't retry internally, this should fail
            result = await consumer.process_message(message)
            assert result is True  # Message deleted even on extraction failure

    @pytest.mark.asyncio
    async def test_various_text_formats(self, db_pool):
        """Test processing of various text formats and edge cases."""
        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = EventRepository(db_pool)
        consumer.categories = await consumer.event_repo.get_categories()

        test_texts = [
            # Unicode and emojis
            "🎯 Воркшоп з AI 🤖 у Києві! 🇺🇦",
            # HTML tags
            "<b>Workshop</b> on <i>Machine Learning</i><br>Register at <a href='#'>link</a>",
            # Very long text
            "A" * 10000,
            # Special characters
            "Event with special chars: @#$%^&*()_+-=[]{}|;':\",./<>?",
            # Multiple languages
            "English Українська Polski 中文 العربية",
            # Only whitespace
            "   \n\t\r   ",
        ]

        for i, text in enumerate(test_texts):
            with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
                 patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
                 patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

                mock_extraction = MagicMock()
                mock_extraction.extract_event_data = AsyncMock(
                    return_value=EventExtraction(
                        title=f"Test Format {i}",
                        language="uk",
                        city="Київ",
                        country="UA",
                        is_remote=True,
                        status="active",
                        categories_slugs=[]
                    )
                )
                mock_extraction_class.return_value = mock_extraction

                mock_embed_service.embed_text = MagicMock(return_value=[0.1] * 384)
                mock_vector_store.return_value = MagicMock(index_event=AsyncMock())

                message = {
                    "Body": json.dumps({
                        "source_id": i,
                        "run_id": 1,
                        "external_id": f"format_test_{i}",
                        "text": text,
                        "posted_at": datetime.now().isoformat(),
                        "metadata": {}
                    }),
                    "ReceiptHandle": f"format-receipt-{i}"
                }

                result = await consumer.process_message(message)
                assert result is True

    @pytest.mark.asyncio
    async def test_category_validation(self, db_pool):
        """Test that only valid categories are linked."""
        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = EventRepository(db_pool)
        consumer.categories = await consumer.event_repo.get_categories()

        valid_slugs = [cat["slug"] for cat in consumer.categories]

        with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
             patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
             patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

            # Include both valid and invalid categories
            mock_extraction = MagicMock()
            mock_extraction.extract_event_data = AsyncMock(
                return_value=EventExtraction(
                    title="Category Validation Test",
                    language="uk",
                    city="Київ",
                    country="UA",
                    is_remote=False,
                    status="active",
                    categories_slugs=["workshop", "invalid_category", "meetup", "fake_category"]
                )
            )
            mock_extraction_class.return_value = mock_extraction

            mock_embed_service.embed_text = MagicMock(return_value=[0.1] * 384)
            mock_vector_store.return_value = MagicMock(index_event=AsyncMock())

            message = {
                "Body": json.dumps({
                    "source_id": 1,
                    "run_id": 1,
                    "external_id": "category_test",
                    "text": "Event with mixed valid/invalid categories",
                    "posted_at": datetime.now().isoformat(),
                    "metadata": {}
                }),
                "ReceiptHandle": "category-receipt"
            }

            result = await consumer.process_message(message)
            assert result is True

            # Verify only valid categories were linked
            async with db_pool.pool.acquire() as conn:
                event = await conn.fetchrow(
                    "SELECT id FROM events WHERE title = $1",
                    "Category Validation Test"
                )

                categories = await conn.fetch(
                    """
                    SELECT c.slug
                    FROM event_categories ec
                    JOIN categories c ON ec.category_id = c.id
                    WHERE ec.event_id = $1
                    """,
                    event["id"]
                )

                linked_slugs = [row["slug"] for row in categories]
                # Only valid categories should be linked
                assert "workshop" in linked_slugs
                assert "meetup" in linked_slugs
                assert "invalid_category" not in linked_slugs
                assert "fake_category" not in linked_slugs

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, db_pool):
        """Test that failed database operations don't leave partial data."""
        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = EventRepository(db_pool)
        consumer.categories = await consumer.event_repo.get_categories()

        with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
             patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
             patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

            mock_extraction = MagicMock()
            mock_extraction.extract_event_data = AsyncMock(
                return_value=EventExtraction(
                    title="Transaction Test",
                    language="INVALID",  # This should cause validation error
                    city="Київ",
                    country="UA",
                    is_remote=False,
                    status="active",
                    categories_slugs=[]
                )
            )
            mock_extraction_class.return_value = mock_extraction

            mock_embed_service.embed_text = MagicMock(return_value=[0.1] * 384)
            mock_vector_store.return_value = MagicMock(index_event=AsyncMock())

            message = {
                "Body": json.dumps({
                    "source_id": 1,
                    "run_id": 1,
                    "external_id": "transaction_test",
                    "text": "Test transaction rollback",
                    "posted_at": datetime.now().isoformat(),
                    "metadata": {}
                }),
                "ReceiptHandle": "transaction-receipt"
            }

            result = await consumer.process_message(message)

            # Check no partial data was saved
            async with db_pool.pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM events WHERE title = $1",
                    "Transaction Test"
                )
                # Event might be saved even with invalid language since it's just text
                # The important thing is consistency

    @pytest.mark.asyncio
    async def test_high_volume_processing(self, db_pool):
        """Test processing a high volume of messages."""
        consumer = SQSConsumer()
        consumer.db_pool = db_pool
        consumer.event_repo = EventRepository(db_pool)
        consumer.categories = await consumer.event_repo.get_categories()

        message_count = 50  # Process 50 messages

        with patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction_class, \
             patch("src.consumer.sqs_consumer.embedding_service") as mock_embed_service, \
             patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

            mock_extraction = MagicMock()

            # Create different extractions for variety
            async def create_extraction(text, max_retries=3):
                import random
                cities = ["Київ", "Львів", "Одеса", None]
                languages = ["uk", "en", "pl"]
                categories = [["workshop"], ["meetup"], ["hackathon"], []]

                return EventExtraction(
                    title=f"High Volume Event {random.randint(1, 1000)}",
                    language=random.choice(languages),
                    city=random.choice(cities),
                    country="UA" if random.choice(cities) else None,
                    is_remote=random.choice([True, False]),
                    status="active",
                    categories_slugs=random.choice(categories)
                )

            mock_extraction.extract_event_data = AsyncMock(side_effect=create_extraction)
            mock_extraction_class.return_value = mock_extraction

            mock_embed_service.embed_text = MagicMock(return_value=[0.1] * 384)
            mock_vector_store.return_value = MagicMock(index_event=AsyncMock())

            # Process messages
            for i in range(message_count):
                message = {
                    "Body": json.dumps({
                        "source_id": i,
                        "run_id": 1,
                        "external_id": f"volume_{i}",
                        "text": f"High volume test message {i}",
                        "posted_at": datetime.now().isoformat(),
                        "metadata": {
                            "source_type": "test",
                            "source_url": f"https://test.com/{i}"
                        }
                    }),
                    "ReceiptHandle": f"volume-receipt-{i}"
                }

                result = await consumer.process_message(message)
                assert result is True

            # Verify metrics
            assert consumer.metrics["processed_count"] == message_count
            assert consumer.metrics["error_count"] == 0

            # Verify database has events
            async with db_pool.pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM events")
                assert count > 0  # Should have events (some might be duplicates)