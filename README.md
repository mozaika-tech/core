# Mozaika Core Service

Production-ready Python service for processing scraped events using LlamaIndex and PostgreSQL with pgvector extension. The service consumes messages from SQS, extracts metadata using configurable LLMs, and provides both SQL-based and AI-powered semantic search APIs.

## Features

- **SQS Consumer**: Asynchronous message processing from AWS SQS
- **LLM Integration**: Configurable support for Anthropic, Google Gemini, and OpenAI
- **Semantic Search**: Vector similarity search using pgvector and LlamaIndex
- **Dual Search APIs**: Traditional SQL filtering and AI-powered semantic search
- **Multilingual Support**: Embeddings using multilingual-e5-small model
- **Production Ready**: Connection pooling, graceful shutdown, comprehensive error handling

## Architecture

The application runs two concurrent processes:

1. **SQS Consumer**: Polls SQS → Extract metadata → Generate embeddings → Store in PostgreSQL → Index in vector store
2. **FastAPI Server**: Provides REST APIs for searching events

Both processes share:
- PostgreSQL connection pool (asyncpg)
- LlamaIndex components (embeddings, vector store, LLM)

## Prerequisites

- Python 3.9+
- PostgreSQL 16+ with pgvector extension
- AWS SQS queue (or LocalStack for testing)
- API key for chosen LLM provider (Anthropic/Gemini/OpenAI)

## Installation

### 1. Clone the repository

```bash
cd /Users/taras.tarasiuk/Projects/mozaika/core
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up PostgreSQL with pgvector

Using Docker:
```bash
docker run -d \
  --name mozaika-postgres \
  -e POSTGRES_USER=mozaika \
  -e POSTGRES_PASSWORD=mozaika \
  -e POSTGRES_DB=mozaika_db \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 5. Initialize database schema

```bash
psql -h localhost -U mozaika -d mozaika_db -f schema.sql
```

### 6. Configure environment

Copy `.env.example` to `.env` and update with your settings:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:
- Database connection URL
- SQS queue URL and AWS credentials
- LLM provider and API key
- Other settings as needed

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | Required |
| `SQS_QUEUE_URL` | AWS SQS queue URL | Required |
| `AWS_REGION` | AWS region | us-east-1 |
| `AWS_ACCESS_KEY_ID` | AWS access key | Optional |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Optional |
| `LLM_PROVIDER` | LLM provider (anthropic/gemini/openai) | anthropic |
| `ANTHROPIC_API_KEY` | Anthropic API key | Required if provider=anthropic |
| `GEMINI_API_KEY` | Google Gemini API key | Required if provider=gemini |
| `OPENAI_API_KEY` | OpenAI API key | Required if provider=openai |
| `EMBEDDING_MODEL` | HuggingFace embedding model | intfloat/multilingual-e5-small |
| `API_HOST` | API server host | 0.0.0.0 |
| `API_PORT` | API server port | 8000 |
| `SQS_POLL_INTERVAL_SECONDS` | SQS polling interval | 20 |
| `LOG_LEVEL` | Logging level | INFO |

### LLM Provider Configuration

The service supports multiple LLM providers. Set `LLM_PROVIDER` and provide the corresponding API key:

```bash
# For Anthropic Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# For Google Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=...

# For OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

## Running the Service

### Production Mode

Run both the SQS consumer and API server:

```bash
python main.py
```

### Development Mode

Run components separately:

```bash
# Terminal 1: Run only the API server
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Run only the SQS consumer
python -c "import asyncio; from src.consumer.sqs_consumer import run_consumer; asyncio.run(run_consumer())"
```

## API Documentation

### Interactive API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Endpoints

#### GET /health
Health check endpoint.

#### GET /search
SQL-based event search with filters.

Query parameters:
- `q`: Full-text search
- `city`: Filter by city
- `country`: ISO-3166-1 alpha-2 country code
- `language`: ISO-639-1 language code
- `is_remote`: Boolean for remote/onsite
- `category[]`: Category slugs (multiple allowed)
- `posted_from/posted_to`: Posted date range
- `occurs_from/occurs_to`: Event date range
- `deadline_before/deadline_after`: Deadline filters
- `sort_by`: posted_at | deadline_at | occurs_from
- `order`: asc | desc
- `page`: Page number (default: 1)
- `size`: Page size (default: 20, max: 100)

Example:
```bash
curl "http://localhost:8000/search?q=workshop&city=Київ&category=workshop&page=1&size=20"
```

#### POST /ai/search
AI-powered semantic search with natural language query.

Request body:
```json
{
  "query": "стажування у Києві в грудні",
  "top_k": 12,
  "profile_inline": {
    "city": "Київ",
    "languages": ["uk"],
    "preferred_categories": ["internship"],
    "remote_preference": "any",
    "about": "студент, шукаю стажування"
  }
}
```

Response includes:
- Semantically similar events
- Match scores based on profile
- AI-generated chat answer in Ukrainian

#### GET /categories
Get all available event categories.

## SQS Message Format

The service expects messages from the telegram-scrapper in this format:

```json
{
  "source_id": 1,
  "run_id": 1,
  "external_id": "msg_123",
  "text": "Workshop on AI Ethics in Kyiv...",
  "posted_at": "2025-11-15T10:00:00Z",
  "author": "ChannelName",
  "metadata": {
    "source_type": "telegram",
    "source_url": "https://t.me/channel/123"
  }
}
```

## Processing Flow

1. **Message Reception**: Consumer polls SQS queue
2. **Text Processing**: Beautify and normalize text
3. **LLM Extraction**: Extract structured data (title, location, dates, categories)
4. **Embedding Generation**: Create 384-dimensional vector using multilingual-e5-small
5. **Database Storage**: Upsert event with deduplication
6. **Category Linking**: Associate event with categories
7. **Vector Indexing**: Index in LlamaIndex for semantic search
8. **Message Acknowledgment**: Delete from SQS on success

## Testing

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_sqs_consumer.py

# Run with verbose output
pytest -v
```

### Test Coverage

The test suite includes:
- SQS consumer message processing
- API endpoint functionality
- Database operations
- LLM extraction mocking
- Vector store operations

## Monitoring

### Metrics

The SQS consumer tracks:
- `processed_count`: Successfully processed messages
- `error_count`: Failed messages
- `duplicate_count`: Duplicate events detected
- `avg_processing_time_ms`: Average processing time

### Logs

Logs are output to stdout with configurable level:
```
2025-11-15 10:30:45 - src.consumer.sqs_consumer - INFO - Processed message test_123 in 450ms
```

## Database Schema

The service uses a strict schema with three main tables:
- `events`: Main event data with vector embeddings
- `categories`: Controlled vocabulary of event categories
- `event_categories`: Junction table for many-to-many relationship

See `schema.sql` for complete schema definition.

## Deployment

### Docker

Create a Dockerfile:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

Build and run:
```bash
docker build -t mozaika-core .
docker run --env-file .env -p 8000:8000 mozaika-core
```

### AWS ECS/Fargate

1. Build and push Docker image to ECR
2. Create ECS task definition with environment variables
3. Configure service with desired task count
4. Set up Application Load Balancer for API endpoints

### Kubernetes

Create deployment and service manifests with:
- ConfigMap for non-sensitive configuration
- Secrets for API keys
- Horizontal Pod Autoscaler for scaling
- Ingress for API exposure

## Troubleshooting

### Common Issues

1. **Database connection errors**
   - Verify PostgreSQL is running and accessible
   - Check DATABASE_URL format
   - Ensure pgvector extension is installed

2. **SQS connection errors**
   - Verify AWS credentials
   - Check SQS queue URL
   - Ensure queue exists and has proper permissions

3. **LLM API errors**
   - Verify API key is correct
   - Check rate limits
   - Ensure selected provider matches API key

4. **Embedding model download**
   - First run downloads the model (~150MB)
   - Ensure sufficient disk space
   - Check internet connectivity

## Performance Optimization

1. **Database**: Adjust connection pool size based on load
2. **SQS**: Tune batch size and visibility timeout
3. **Embeddings**: Use GPU if available for faster processing
4. **Caching**: Consider Redis for frequently accessed data

## Security

- Store sensitive credentials in environment variables
- Use IAM roles for AWS access in production
- Enable HTTPS for API endpoints
- Implement rate limiting for public APIs
- Regular security updates for dependencies

## License

[Your License Here]

## Support

For issues or questions, please open an issue in the repository.