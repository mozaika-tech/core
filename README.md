# Mozaika Core Service

Production-ready Python service for processing scraped events using LlamaIndex and PostgreSQL with pgvector extension. The service consumes messages from SQS, extracts metadata using configurable LLMs, and provides both SQL-based and AI-powered semantic search APIs.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Mozaika Core Service                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐              ┌──────────────────┐           │
│  │  SQS Consumer    │              │   FastAPI Server │           │
│  │  (Async Process) │              │   (REST API)     │           │
│  └────────┬─────────┘              └────────┬─────────┘           │
│           │                                  │                      │
│           │  ┌──────────────────────────────┤                      │
│           │  │                               │                      │
│           ▼  ▼                               ▼                      │
│  ┌────────────────────────────────────────────────────┐            │
│  │           Shared Components Layer                  │            │
│  ├────────────────────────────────────────────────────┤            │
│  │  • PostgreSQL Pool (asyncpg)                       │            │
│  │  • LlamaIndex (embeddings, vector store, LLM)      │            │
│  │  • Event Repository (DB operations)                │            │
│  │  • Extraction Service (LLM integration)            │            │
│  └────────────────────────────────────────────────────┘            │
│                           │                                         │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            │                               │
            ▼                               ▼
    ┌──────────────┐              ┌─────────────────┐
    │  PostgreSQL  │              │  LLM Providers  │
    │  + pgvector  │              │  (Anthropic,    │
    │              │              │   Gemini, OpenAI)│
    └──────────────┘              └─────────────────┘
```

### Data Flow

**SQS Consumer Process:**
```
AWS SQS → Poll Messages → Extract Text → LLM Processing (extract metadata)
    → Generate Embeddings → Store in PostgreSQL → Index in Vector Store
    → Delete from SQS
```

**API Server - SQL Search (GET /search):**
```
HTTP Request → Parse Query Parameters → Build SQL Query
    → Execute in PostgreSQL → Return Results
```

**API Server - AI Search (POST /ai/search):**
```
HTTP Request → Parse Natural Language Query → LLM (extract filters from query)
    → Apply Filters (city, country, language, categories, dates, remote)
    → Generate Query Embedding → Vector Search on Filtered Subset
    → Calculate Relevance (with user profile) → LLM (generate answer)
    → Return Results + AI Answer
```

## Features

- **SQS Consumer**: Asynchronous message processing from AWS SQS
- **LLM Integration**: Configurable support for Anthropic Claude, Google Gemini, and OpenAI
- **Semantic Search**: Vector similarity search using pgvector and LlamaIndex
- **Dual Search APIs**: Traditional SQL filtering and AI-powered semantic search
- **Multilingual Support**: Embeddings using multilingual-e5-small model (384 dimensions)
- **Production Ready**: Connection pooling, graceful shutdown, comprehensive error handling
- **Deduplication**: Fingerprint-based duplicate detection
- **Comprehensive Testing**: Full test coverage with testcontainers and mocking

## Prerequisites

- Python 3.13+ (compatible with 3.9+)
- PostgreSQL 16+ with pgvector extension
- AWS SQS queue
- API key for chosen LLM provider (Anthropic/Gemini/OpenAI)
- Docker (optional, for functional tests)

## Installation

### 1. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install dependencies

We use the standard Python practice of separate requirements files:

- **`requirements.txt`** - All production dependencies (includes testing/linting for CI/CD)
- **`requirements-dev.txt`** - Adds development-only tools (5 extra packages)

```bash
# For production/testing/CI
pip install -r requirements.txt

# For local development (adds interactive tools)
pip install -r requirements-dev.txt
```

**Why separate files?** (Standard Python practice)
- **Production lean**: Deployments only install what's needed
- **Development convenience**: Adds ipython, ipdb, pre-commit, sphinx (docs)
- **Single source of truth**: Same pinned versions for core dependencies
- **Common pattern**: Used by most Python projects

### 3. Set up PostgreSQL with pgvector

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

### 4. Initialize database schema

```bash
psql -h localhost -U mozaika -d mozaika_db -f schema.sql
```

### 5. Configure environment

Copy `.env.example` to `.env` and update with your settings:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:
- Database connection URL
- SQS queue URL and AWS credentials
- LLM provider and API key

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | Required |
| `SQS_QUEUE_URL` | AWS SQS queue URL | Required |
| `AWS_REGION` | AWS region | us-east-1 |
| `AWS_ACCESS_KEY_ID` | AWS access key | Optional (use IAM roles) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Optional (use IAM roles) |
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

Set `LLM_PROVIDER` and provide the corresponding API key:

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

### HTTP Request Files

Ready-to-use HTTP request files in `http-requests/` folder for JetBrains IDEs (IntelliJ IDEA, PyCharm, WebStorm).

Files included:
- **`health-and-categories.http`** - Basic endpoints
- **`sql-search.http`** - SQL search with filters and date ranges
- **`ai-search.http`** - AI semantic search (Ukrainian/English)
- **`http-client.env.json`** - Environment configuration (dev/staging/production)

See [http-requests/README.md](http-requests/README.md) for usage instructions.

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
- `q`: Full-text search query
- `city`: Filter by city name
- `country`: ISO-3166-1 alpha-2 country code (e.g., UA, PL, US)
- `language`: ISO-639-1 language code (e.g., uk, en, pl)
- `is_remote`: Boolean for remote/onsite events
- `category[]`: Category slugs (multiple allowed)
- `posted_from/posted_to`: Posted date range (ISO format)
- `occurs_from/occurs_to`: Event date range (ISO format)
- `deadline_before/deadline_after`: Deadline filters (ISO format)
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
5. **Database Storage**: Upsert event with deduplication (fingerprint-based)
6. **Category Linking**: Associate event with categories
7. **Vector Indexing**: Index in LlamaIndex for semantic search
8. **Message Acknowledgment**: Delete from SQS on success

## Testing

### Run Tests

```bash
# Run all tests (unit + functional if Docker available)
pytest

# Run only unit tests (no Docker needed)
pytest tests/unit tests/test_*.py

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_sqs_consumer.py -v

# Using test runner script
./run_tests.sh quick      # Unit tests only
./run_tests.sh coverage   # With coverage report
```

### Test Coverage

Test suite includes:
- **Unit tests** - No Docker required, all external services mocked
- **Functional tests** - Require Docker, use testcontainers for real PostgreSQL
- **SQS consumer** message processing and error handling
- **API endpoints** with comprehensive mocking
- **Database operations** with real database via testcontainers
- **LLM extraction** fully mocked (no API calls)
- **Vector store** operations

See [TESTING.md](TESTING.md) for detailed testing guide.

## Database Schema

See `schema.sql` for the complete database schema with:
- Events table with vector embeddings (pgvector)
- Categories and event-category relationships
- Full-text and vector search indexes

## License

[Your License Here]