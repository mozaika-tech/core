"""SQS consumer for processing scraped messages."""

import asyncio
import json
import logging
import signal
import time
from datetime import datetime
from typing import List, Optional, Dict, Any

import boto3
from botocore.exceptions import ClientError

from src.config import settings
from src.database.connection import get_db_pool
from src.database.events import EventRepository
from src.llm.embeddings import embedding_service
from src.llm.extraction import ExtractionService
from src.llm.vector_store import get_vector_store
from src.models.event import SQSMessage
from src.utils.text_processing import beautify_text

logger = logging.getLogger(__name__)


class SQSConsumer:
    """Consumer for processing SQS messages."""

    def __init__(self):
        """Initialize the SQS consumer."""
        self.running = False
        self.sqs_client = None
        self.db_pool = None
        self.event_repo = None
        self.extraction_service = None
        self.vector_store = None
        self.categories = []

        # Metrics
        self.metrics = {
            "processed_count": 0,
            "error_count": 0,
            "duplicate_count": 0,
            "total_processing_time_ms": 0
        }

    async def initialize(self):
        """Initialize all services and connections."""
        logger.info("Initializing SQS consumer...")

        # Initialize database
        self.db_pool = await get_db_pool()
        self.event_repo = EventRepository(self.db_pool)

        # Load categories
        self.categories = await self.event_repo.get_categories()
        category_slugs = [cat["slug"] for cat in self.categories]
        logger.info(f"Loaded {len(self.categories)} categories")

        # Initialize extraction service
        self.extraction_service = ExtractionService(category_slugs)

        # Initialize vector store
        self.vector_store = get_vector_store()

        # Initialize SQS client
        self._init_sqs_client()

        logger.info("SQS consumer initialized successfully")

    def _init_sqs_client(self):
        """Initialize the SQS client."""
        client_kwargs = {
            'region_name': settings.aws_region
        }

        # Support for LocalStack
        if settings.aws_endpoint_url:
            client_kwargs['endpoint_url'] = settings.aws_endpoint_url

        # Add credentials if provided
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            client_kwargs['aws_access_key_id'] = settings.aws_access_key_id
            client_kwargs['aws_secret_access_key'] = settings.aws_secret_access_key

        self.sqs_client = boto3.client('sqs', **client_kwargs)
        logger.info(f"SQS client initialized for queue: {settings.sqs_queue_url}")

    async def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Process a single SQS message.

        Args:
            message: SQS message

        Returns:
            True if processed successfully, False otherwise
        """
        start_time = time.time()

        try:
            # Parse message body
            body = json.loads(message['Body'])

            # Create SQSMessage model from telegram-scrapper format
            sqs_msg = SQSMessage(
                source_id=body.get('source_id'),
                run_id=body.get('run_id'),
                external_id=body['external_id'],
                text=body['text'],
                posted_at=datetime.fromisoformat(body['posted_at']) if body.get('posted_at') else None,
                author=body.get('author'),
                metadata=body.get('metadata', {})
            )

            # Derive source_type and source_url from metadata
            source_type = sqs_msg.metadata.get('source_type', 'telegram')
            source_url = sqs_msg.metadata.get('source_url', f"https://source.com/{sqs_msg.external_id}")

            logger.info(f"Processing message: {sqs_msg.external_id}")

            # Step 1: Beautify text
            beautified_text = beautify_text(sqs_msg.text)

            # Step 2: Extract structured data using LLM
            extraction = await self.extraction_service.extract_event_data(beautified_text)
            if not extraction:
                logger.error(f"Failed to extract data for message {sqs_msg.external_id}")
                self.metrics["error_count"] += 1
                return True  # Delete message anyway to avoid reprocessing

            # Step 3: Generate embedding
            embed_text = f"{extraction.title}\n\n{beautified_text}"
            embedding = embedding_service.embed_text(embed_text)

            # Step 4: Upsert to database
            event_id, is_new = await self.event_repo.upsert_event(
                source_type=source_type,
                source_url=source_url,
                raw_text=beautified_text,
                extraction=extraction,
                embedding=embedding,
                posted_at=sqs_msg.posted_at
            )

            if not is_new:
                self.metrics["duplicate_count"] += 1
                logger.info(f"Duplicate event detected: {event_id}")
            else:
                # Step 5: Link categories
                if extraction.categories_slugs:
                    await self.event_repo.link_categories(event_id, extraction.categories_slugs)

                # Step 6: Index in vector store
                metadata = {
                    "title": extraction.title,
                    "city": extraction.city,
                    "country": extraction.country,
                    "language": extraction.language,
                    "is_remote": extraction.is_remote,
                    "posted_at": sqs_msg.posted_at.isoformat() if sqs_msg.posted_at else None,
                    "occurs_from": extraction.occurs_from.isoformat() if extraction.occurs_from else None,
                    "occurs_to": extraction.occurs_to.isoformat() if extraction.occurs_to else None,
                    "deadline_at": extraction.deadline_at.isoformat() if extraction.deadline_at else None,
                    "categories_slugs": extraction.categories_slugs,
                    "source_url": source_url
                }

                await self.vector_store.index_event(
                    event_id=event_id,
                    title=extraction.title,
                    raw_text=beautified_text,
                    metadata=metadata
                )

            # Update metrics
            self.metrics["processed_count"] += 1
            processing_time_ms = (time.time() - start_time) * 1000
            self.metrics["total_processing_time_ms"] += processing_time_ms

            logger.info(
                f"Processed message {sqs_msg.external_id} in {processing_time_ms:.0f}ms "
                f"(event_id: {event_id}, new: {is_new})"
            )

            return True

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self.metrics["error_count"] += 1
            return False

    async def poll_messages(self):
        """Poll SQS for messages and process them."""
        while self.running:
            try:
                # Receive messages from SQS
                response = self.sqs_client.receive_message(
                    QueueUrl=settings.sqs_queue_url,
                    MaxNumberOfMessages=settings.sqs_batch_size,
                    VisibilityTimeout=settings.sqs_visibility_timeout,
                    WaitTimeSeconds=settings.sqs_poll_interval_seconds,  # Long polling
                    MessageAttributeNames=['All']
                )

                messages = response.get('Messages', [])

                if messages:
                    logger.info(f"Received {len(messages)} messages from SQS")

                    # Process messages concurrently
                    tasks = []
                    for message in messages:
                        tasks.append(self.process_message(message))

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Delete successfully processed messages
                    entries_to_delete = []
                    for i, (message, result) in enumerate(zip(messages, results)):
                        if result is True:
                            entries_to_delete.append({
                                'Id': str(i),
                                'ReceiptHandle': message['ReceiptHandle']
                            })
                        elif isinstance(result, Exception):
                            logger.error(f"Exception processing message: {result}")

                    # Batch delete successful messages
                    if entries_to_delete:
                        try:
                            delete_response = self.sqs_client.delete_message_batch(
                                QueueUrl=settings.sqs_queue_url,
                                Entries=entries_to_delete
                            )

                            if 'Failed' in delete_response:
                                for failure in delete_response['Failed']:
                                    logger.error(
                                        f"Failed to delete message: {failure['Code']} - {failure['Message']}"
                                    )

                            logger.info(f"Deleted {len(entries_to_delete)} messages from SQS")

                        except ClientError as e:
                            logger.error(f"Error deleting messages: {e}")

                else:
                    logger.debug("No messages received from SQS")

            except ClientError as e:
                logger.error(f"SQS client error: {e}")
                await asyncio.sleep(5)  # Wait before retrying

            except Exception as e:
                logger.error(f"Unexpected error in poll loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def start(self):
        """Start the consumer."""
        logger.info("Starting SQS consumer...")
        self.running = True

        # Initialize services
        await self.initialize()

        # Start polling
        await self.poll_messages()

    async def stop(self):
        """Stop the consumer gracefully."""
        logger.info("Stopping SQS consumer...")
        self.running = False

        # Log final metrics
        if self.metrics["processed_count"] > 0:
            avg_time = self.metrics["total_processing_time_ms"] / self.metrics["processed_count"]
            logger.info(
                f"Consumer metrics: processed={self.metrics['processed_count']}, "
                f"errors={self.metrics['error_count']}, "
                f"duplicates={self.metrics['duplicate_count']}, "
                f"avg_time={avg_time:.0f}ms"
            )

        # Close database pool
        if self.db_pool:
            await self.db_pool.close()

        logger.info("SQS consumer stopped")


async def run_consumer():
    """Run the SQS consumer with signal handling."""
    consumer = SQSConsumer()

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        asyncio.create_task(consumer.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await consumer.start()
    except Exception as e:
        logger.error(f"Consumer failed: {e}", exc_info=True)
        await consumer.stop()
        raise