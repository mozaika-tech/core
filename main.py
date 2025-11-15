"""Main application entry point."""

import asyncio
import logging
import sys
from typing import Optional

import uvicorn
from uvicorn.config import Config
from uvicorn.server import Server

from src.config import settings
from src.consumer.sqs_consumer import run_consumer
from src.api.app import app

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class UvicornServer(Server):
    """Customized Uvicorn server for running in asyncio."""

    def install_signal_handlers(self):
        """Override to prevent signal handler conflicts."""
        pass


async def run_api_server():
    """Run the FastAPI server."""
    logger.info(f"Starting API server on {settings.api_host}:{settings.api_port}")

    config = Config(
        app=app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        access_log=True
    )

    server = UvicornServer(config)
    await server.serve()


async def main():
    """Main application entry point - runs both consumer and API server."""
    logger.info("Starting Mozaika Core Service...")

    # Create tasks for both processes
    tasks = []

    # Task 1: SQS Consumer
    consumer_task = asyncio.create_task(run_consumer())
    tasks.append(consumer_task)
    logger.info("SQS consumer task created")

    # Task 2: FastAPI Server
    api_task = asyncio.create_task(run_api_server())
    tasks.append(api_task)
    logger.info("API server task created")

    try:
        # Run both tasks concurrently
        logger.info("Running consumer and API server...")
        await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
    finally:
        # Cancel all tasks
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete cancellation
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Application shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)