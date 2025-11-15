# API HTTP Requests

This folder contains IntelliJ IDEA / WebStorm / PyCharm compatible HTTP request files for testing the Mozaika Core API.

## Files

- **`health-and-categories.http`** - Basic service endpoints (health check, categories)
- **`sql-search.http`** - SQL-based search examples with various filters
- **`ai-search.http`** - AI-powered semantic search examples
- **`http-client.env.json`** - Environment configuration (dev, staging, production)

## Usage

### In JetBrains IDEs (IntelliJ IDEA, PyCharm, WebStorm)

1. Open any `.http` file
2. Select environment in the dropdown (dev/staging/production)
3. Click the ▶️ play button next to any request
4. View response in the bottom panel

### Environment Variables

The `{{base_url}}` variable is configured in `http-client.env.json`:
- **dev**: `http://localhost:8000` (default)
- **staging**: `https://staging-api.mozaika.com`
- **production**: `https://api.mozaika.com`

## Request Examples

### Health & Categories
- Health check - verify service is running
- Get all event categories

### SQL Search
- Basic text search with pagination
- Filtered search (city, country, language, categories)
- Date range filtering (posted, occurrence, deadline dates)
- Remote/onsite filtering
- Multiple sorting options

### AI Search
- Natural language queries (Ukrainian and English)
- Personalized search with user profiles
- Remote preference filtering
- Category preferences
- Relevance scoring based on user "about" description

## Quick Start

1. Ensure the API server is running: `python main.py`
2. Open `health-and-categories.http`
3. Run the health check request to verify connectivity
4. Explore other examples in `sql-search.http` and `ai-search.http`
