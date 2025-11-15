"""Tests for API endpoints."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.models.event import EventSearchResult, QueryIntent


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_health_check(test_client):
    """Test health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_search_events(test_client):
    """Test GET /search endpoint."""
    # Mock event repository
    with patch("src.api.app.get_db_pool") as mock_db_pool:
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        # Mock search results
        mock_events = [
            EventSearchResult(
                id=uuid4(),
                title="Test Event",
                city="Київ",
                country="UA",
                language="uk",
                is_remote=False,
                source_url="https://example.com",
                posted_at=datetime.now(),
                occurs_from=None,
                occurs_to=None,
                deadline_at=None,
                status="active",
                categories_slugs=["workshop"]
            )
        ]

        with patch("src.database.events.EventRepository.search_events") as mock_search:
            mock_search.return_value = (mock_events, 1)

            response = test_client.get("/search?q=test&city=Київ&page=1&size=20")

            assert response.status_code == 200
            data = response.json()
            assert "hits" in data
            assert data["total"] == 1
            assert data["page"] == 1
            assert data["size"] == 20
            assert len(data["hits"]) == 1
            assert data["hits"][0]["title"] == "Test Event"


@pytest.mark.asyncio
async def test_search_events_with_filters(test_client):
    """Test GET /search with various filters."""
    with patch("src.api.app.get_db_pool") as mock_db_pool:
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        with patch("src.database.events.EventRepository.search_events") as mock_search:
            mock_search.return_value = ([], 0)

            # Test with multiple filters
            response = test_client.get(
                "/search?"
                "q=internship&"
                "city=Київ&"
                "country=UA&"
                "language=uk&"
                "is_remote=false&"
                "category=internship&"
                "category=workshop&"
                "sort_by=deadline_at&"
                "order=asc"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["hits"] == []


@pytest.mark.asyncio
async def test_ai_search(test_client):
    """Test POST /ai/search endpoint."""
    with patch("src.api.app.get_db_pool") as mock_db_pool, \
         patch("src.api.app.get_vector_store") as mock_vector_store, \
         patch("src.llm.extraction.ExtractionService") as mock_extraction_service:

        # Setup mocks
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        # Mock extraction service
        mock_extraction_instance = MagicMock()
        mock_extraction_instance.understand_query = AsyncMock(
            return_value=QueryIntent(
                city="Київ",
                country="UA",
                language="uk",
                is_remote=False,
                date_from=None,
                date_to=None,
                categories_slugs=["internship"],
                top_k=12,
                user_query_rewritten="стажування у Києві"
            )
        )
        mock_extraction_service.return_value = mock_extraction_instance

        # Mock vector store
        mock_vector_instance = MagicMock()
        mock_events = [
            EventSearchResult(
                id=uuid4(),
                title="AI Internship",
                city="Київ",
                country="UA",
                language="uk",
                is_remote=False,
                source_url="https://example.com",
                posted_at=datetime.now(),
                occurs_from=None,
                occurs_to=None,
                deadline_at=None,
                status="active",
                categories_slugs=["internship"],
                score=0.85
            )
        ]
        mock_vector_instance.search_similar = AsyncMock(return_value=mock_events)
        mock_vector_instance.synthesize_answer = AsyncMock(
            return_value="Знайшов стажування в AI у Києві. Найкращий варіант - AI Internship."
        )
        mock_vector_store.return_value = mock_vector_instance

        # Mock event repository for categories
        with patch("src.database.events.EventRepository") as mock_repo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.get_categories = AsyncMock(return_value=[
                {"slug": "internship", "name": "Стажування"}
            ])
            mock_repo.return_value = mock_repo_instance

            # Make request
            request_body = {
                "query": "стажування у Києві в грудні",
                "top_k": 10,
                "profile_inline": {
                    "city": "Київ",
                    "languages": ["uk"],
                    "preferred_categories": ["internship"],
                    "remote_preference": "any",
                    "about": "студент, шукаю стажування"
                }
            }

            response = test_client.post("/ai/search", json=request_body)

            assert response.status_code == 200
            data = response.json()
            assert "hits" in data
            assert "chat_answer" in data
            assert len(data["hits"]) == 1
            assert data["hits"][0]["title"] == "AI Internship"
            assert data["hits"][0]["match_score"] is not None
            assert data["hits"][0]["match_tier"] in ["low", "medium", "high"]
            assert "Знайшов стажування" in data["chat_answer"]


@pytest.mark.asyncio
async def test_ai_search_without_profile(test_client):
    """Test POST /ai/search without user profile."""
    with patch("src.api.app.get_db_pool") as mock_db_pool, \
         patch("src.api.app.get_vector_store") as mock_vector_store, \
         patch("src.llm.extraction.ExtractionService") as mock_extraction_service:

        # Setup mocks
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        mock_extraction_instance = MagicMock()
        mock_extraction_instance.understand_query = AsyncMock(return_value=None)
        mock_extraction_service.return_value = mock_extraction_instance

        mock_vector_instance = MagicMock()
        mock_vector_instance.search_similar = AsyncMock(return_value=[])
        mock_vector_instance.synthesize_answer = AsyncMock(
            return_value="Не знайдено подій за вашим запитом."
        )
        mock_vector_store.return_value = mock_vector_instance

        with patch("src.database.events.EventRepository") as mock_repo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.get_categories = AsyncMock(return_value=[])
            mock_repo.return_value = mock_repo_instance

            request_body = {
                "query": "random search query"
            }

            response = test_client.post("/ai/search", json=request_body)

            assert response.status_code == 200
            data = response.json()
            assert "hits" in data
            assert "chat_answer" in data
            assert len(data["hits"]) == 0


@pytest.mark.asyncio
async def test_get_categories(test_client):
    """Test GET /categories endpoint."""
    with patch("src.api.app.get_db_pool") as mock_db_pool:
        mock_db = AsyncMock()
        mock_db_pool.return_value = mock_db

        with patch("src.database.events.EventRepository.get_categories") as mock_get_categories:
            mock_categories = [
                {"slug": "internship", "name": "Стажування"},
                {"slug": "workshop", "name": "Воркшопи"}
            ]
            mock_get_categories.return_value = mock_categories

            response = test_client.get("/categories")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["slug"] == "internship"
            assert data[1]["slug"] == "workshop"