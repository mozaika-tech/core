"""Tests for SQS consumer."""

import json
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

from src.consumer.sqs_consumer import SQSConsumer
from src.models.event import EventExtraction


@pytest.mark.asyncio
async def test_process_message_success(
    mock_sqs_message,
    mock_extraction_response,
    mock_embedding_service
):
    """Test successful message processing."""
    consumer = SQSConsumer()

    # Mock dependencies
    with patch("src.consumer.sqs_consumer.get_db_pool") as mock_db_pool, \
         patch("src.consumer.sqs_consumer.EventRepository") as mock_repo, \
         patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction, \
         patch("src.consumer.sqs_consumer.embedding_service", mock_embedding_service), \
         patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

        # Setup mocks
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_categories = AsyncMock(return_value=[
            {"slug": "internship", "name": "Стажування"},
            {"slug": "workshop", "name": "Воркшопи"}
        ])
        mock_repo_instance.upsert_event = AsyncMock(return_value=(uuid4(), True))
        mock_repo_instance.link_categories = AsyncMock()
        mock_repo.return_value = mock_repo_instance

        mock_extraction_instance = MagicMock()
        mock_extraction_instance.extract_event_data = AsyncMock(return_value=mock_extraction_response)
        mock_extraction.return_value = mock_extraction_instance

        mock_vector_instance = MagicMock()
        mock_vector_instance.index_event = AsyncMock()
        mock_vector_store.return_value = mock_vector_instance

        # Initialize consumer
        await consumer.initialize()

        # Process message
        result = await consumer.process_message(mock_sqs_message)

        # Assertions
        assert result is True
        assert consumer.metrics["processed_count"] == 1
        assert consumer.metrics["error_count"] == 0
        mock_extraction_instance.extract_event_data.assert_called_once()
        mock_repo_instance.upsert_event.assert_called_once()
        mock_repo_instance.link_categories.assert_called_once()
        mock_vector_instance.index_event.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_duplicate(
    mock_sqs_message,
    mock_extraction_response,
    mock_embedding_service
):
    """Test processing duplicate message."""
    consumer = SQSConsumer()

    with patch("src.consumer.sqs_consumer.get_db_pool") as mock_db_pool, \
         patch("src.consumer.sqs_consumer.EventRepository") as mock_repo, \
         patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction, \
         patch("src.consumer.sqs_consumer.embedding_service", mock_embedding_service), \
         patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

        # Setup mocks
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_categories = AsyncMock(return_value=[])
        mock_repo_instance.upsert_event = AsyncMock(return_value=(uuid4(), False))  # Duplicate
        mock_repo_instance.link_categories = AsyncMock()
        mock_repo.return_value = mock_repo_instance

        mock_extraction_instance = MagicMock()
        mock_extraction_instance.extract_event_data = AsyncMock(return_value=mock_extraction_response)
        mock_extraction.return_value = mock_extraction_instance

        mock_vector_instance = MagicMock()
        mock_vector_instance.index_event = AsyncMock()
        mock_vector_store.return_value = mock_vector_instance

        await consumer.initialize()

        # Process message
        result = await consumer.process_message(mock_sqs_message)

        # Assertions
        assert result is True
        assert consumer.metrics["processed_count"] == 1
        assert consumer.metrics["duplicate_count"] == 1
        # Categories and vector indexing should not be called for duplicates
        mock_repo_instance.link_categories.assert_not_called()
        mock_vector_instance.index_event.assert_not_called()


@pytest.mark.asyncio
async def test_process_message_extraction_failure(
    mock_sqs_message,
    mock_embedding_service
):
    """Test message processing when extraction fails."""
    consumer = SQSConsumer()

    with patch("src.consumer.sqs_consumer.get_db_pool") as mock_db_pool, \
         patch("src.consumer.sqs_consumer.EventRepository") as mock_repo, \
         patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction, \
         patch("src.consumer.sqs_consumer.embedding_service", mock_embedding_service), \
         patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store:

        # Setup mocks
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_categories = AsyncMock(return_value=[])
        mock_repo.return_value = mock_repo_instance

        mock_extraction_instance = MagicMock()
        mock_extraction_instance.extract_event_data = AsyncMock(return_value=None)  # Extraction fails
        mock_extraction.return_value = mock_extraction_instance

        mock_vector_store.return_value = MagicMock()

        await consumer.initialize()

        # Process message
        result = await consumer.process_message(mock_sqs_message)

        # Assertions
        assert result is True  # Message should still be deleted to avoid reprocessing
        assert consumer.metrics["processed_count"] == 0
        assert consumer.metrics["error_count"] == 1


@pytest.mark.asyncio
async def test_poll_messages_with_messages(mock_sqs_client):
    """Test polling messages when queue has messages."""
    consumer = SQSConsumer()
    consumer.sqs_client = mock_sqs_client
    consumer.running = True

    # Mock receive_message to return messages once then stop
    messages = [
        {
            "Body": json.dumps({
                "external_id": "test_123",
                "text": "Test message",
                "metadata": {}
            }),
            "ReceiptHandle": "receipt-1"
        }
    ]

    mock_sqs_client.receive_message = MagicMock(
        side_effect=[
            {"Messages": messages},
            KeyboardInterrupt()  # Stop the loop
        ]
    )

    # Mock process_message
    with patch.object(consumer, "process_message", new=AsyncMock(return_value=True)):
        with pytest.raises(KeyboardInterrupt):
            await consumer.poll_messages()

        # Verify SQS client was called
        mock_sqs_client.receive_message.assert_called()
        mock_sqs_client.delete_message_batch.assert_called_once()


@pytest.mark.asyncio
async def test_consumer_initialization():
    """Test consumer initialization."""
    consumer = SQSConsumer()

    with patch("src.consumer.sqs_consumer.get_db_pool") as mock_db_pool, \
         patch("src.consumer.sqs_consumer.EventRepository") as mock_repo, \
         patch("src.consumer.sqs_consumer.ExtractionService") as mock_extraction, \
         patch("src.consumer.sqs_consumer.get_vector_store") as mock_vector_store, \
         patch("src.consumer.sqs_consumer.boto3.client") as mock_boto_client:

        # Setup mocks
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_categories = AsyncMock(return_value=[
            {"slug": "internship", "name": "Стажування"}
        ])
        mock_repo.return_value = mock_repo_instance

        mock_extraction.return_value = MagicMock()
        mock_vector_store.return_value = MagicMock()
        mock_boto_client.return_value = MagicMock()

        # Initialize
        await consumer.initialize()

        # Assertions
        assert consumer.db_pool is not None
        assert consumer.event_repo is not None
        assert consumer.extraction_service is not None
        assert consumer.vector_store is not None
        assert consumer.sqs_client is not None
        assert len(consumer.categories) == 1
        assert consumer.categories[0]["slug"] == "internship"