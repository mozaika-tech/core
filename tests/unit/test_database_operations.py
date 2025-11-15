"""Unit tests for database operations."""

import hashlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.database.events import EventRepository
from src.models.event import EventExtraction, SearchRequest


class TestEventRepository:
    """Test EventRepository operations."""

    def test_generate_fingerprint(self):
        """Test fingerprint generation."""
        repo = EventRepository(None)

        # Test basic fingerprint
        fingerprint1 = repo.generate_fingerprint(
            "https://example.com/1",
            "Test Title",
            "This is test content"
        )
        assert isinstance(fingerprint1, str)
        assert len(fingerprint1) == 64  # SHA-256 hex length

        # Test same input produces same fingerprint
        fingerprint2 = repo.generate_fingerprint(
            "https://example.com/1",
            "Test Title",
            "This is test content"
        )
        assert fingerprint1 == fingerprint2

        # Test different input produces different fingerprint
        fingerprint3 = repo.generate_fingerprint(
            "https://example.com/2",
            "Test Title",
            "This is test content"
        )
        assert fingerprint1 != fingerprint3

        # Test case normalization
        fingerprint4 = repo.generate_fingerprint(
            "HTTPS://EXAMPLE.COM/1",
            "TEST TITLE",
            "THIS IS TEST CONTENT"
        )
        assert fingerprint1 == fingerprint4  # Should be same after lowercasing

        # Test long text truncation
        long_text = "x" * 500
        fingerprint5 = repo.generate_fingerprint(
            "https://example.com/1",
            "Test Title",
            long_text
        )
        # Should use only first 200 chars
        expected = hashlib.sha256(
            f"https://example.com/1|test title|{'x' * 200}".lower().encode()
        ).hexdigest()
        assert fingerprint5 == expected

    @pytest.mark.asyncio
    async def test_upsert_event_new(self):
        """Test inserting a new event."""
        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value={
            "id": uuid4(),
            "is_new": True
        })

        repo = EventRepository(mock_pool)

        extraction = EventExtraction(
            title="Test Event",
            language="uk",
            city="Київ",
            country="UA",
            is_remote=False,
            status="active",
            categories_slugs=[]
        )

        event_id, is_new = await repo.upsert_event(
            source_type="telegram",
            source_url="https://t.me/test",
            raw_text="Test content",
            extraction=extraction,
            embedding=[0.1] * 384
        )

        assert event_id is not None
        assert is_new is True
        mock_pool.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_event_duplicate(self):
        """Test updating an existing event."""
        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value={
            "id": uuid4(),
            "is_new": False
        })

        repo = EventRepository(mock_pool)

        extraction = EventExtraction(
            title="Test Event",
            language="uk",
            city="Київ",
            country="UA",
            is_remote=False,
            status="active",
            categories_slugs=[]
        )

        event_id, is_new = await repo.upsert_event(
            source_type="telegram",
            source_url="https://t.me/test",
            raw_text="Test content",
            extraction=extraction,
            embedding=[0.1] * 384
        )

        assert event_id is not None
        assert is_new is False

    @pytest.mark.asyncio
    async def test_link_categories_empty(self):
        """Test linking categories with empty list."""
        mock_pool = AsyncMock()
        repo = EventRepository(mock_pool)

        event_id = uuid4()
        await repo.link_categories(event_id, [])

        # Should not make any database calls
        mock_pool.fetch.assert_not_called()
        mock_pool.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_link_categories_with_categories(self):
        """Test linking categories."""
        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=[
            {"id": 1, "slug": "workshop"},
            {"id": 2, "slug": "meetup"}
        ])
        mock_pool.execute = AsyncMock()

        repo = EventRepository(mock_pool)

        event_id = uuid4()
        await repo.link_categories(event_id, ["workshop", "meetup"])

        # Should fetch category IDs
        mock_pool.fetch.assert_called_once()
        # Should insert two links
        assert mock_pool.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_link_categories_invalid_slugs(self):
        """Test linking with invalid category slugs."""
        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=[])  # No categories found

        repo = EventRepository(mock_pool)

        event_id = uuid4()
        await repo.link_categories(event_id, ["invalid1", "invalid2"])

        # Should fetch but not insert anything
        mock_pool.fetch.assert_called_once()
        mock_pool.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_categories(self):
        """Test getting all categories."""
        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=[
            {"slug": "workshop", "name": "Воркшопи"},
            {"slug": "meetup", "name": "Зустрічі"}
        ])

        repo = EventRepository(mock_pool)
        categories = await repo.get_categories()

        assert len(categories) == 2
        assert categories[0]["slug"] == "workshop"
        assert categories[1]["name"] == "Зустрічі"

    @pytest.mark.asyncio
    async def test_search_events_basic(self):
        """Test basic event search."""
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=10)  # Total count
        mock_pool.fetch = AsyncMock(return_value=[
            {
                "id": uuid4(),
                "title": "Test Event",
                "city": "Київ",
                "country": "UA",
                "language": "uk",
                "is_remote": False,
                "source_url": "https://test.com",
                "posted_at": datetime.now(),
                "occurs_from": None,
                "occurs_to": None,
                "deadline_at": None,
                "status": "active",
                "categories": ["workshop"]
            }
        ])

        repo = EventRepository(mock_pool)

        request = SearchRequest(
            page=1,
            size=20
        )

        events, total = await repo.search_events(request)

        assert total == 10
        assert len(events) == 1
        assert events[0].title == "Test Event"

    @pytest.mark.asyncio
    async def test_search_events_with_filters(self):
        """Test event search with multiple filters."""
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=5)
        mock_pool.fetch = AsyncMock(return_value=[])

        repo = EventRepository(mock_pool)

        request = SearchRequest(
            q="workshop",
            city="Київ",
            country="UA",
            language="uk",
            is_remote=False,
            category=["workshop", "meetup"],
            posted_from=datetime(2025, 11, 1),
            posted_to=datetime(2025, 11, 30),
            sort_by="deadline_at",
            order="asc",
            page=2,
            size=10
        )

        events, total = await repo.search_events(request)

        assert total == 5
        assert len(events) == 0

        # Verify the query was built with filters
        calls = mock_pool.fetchval.call_args_list
        assert len(calls) > 0
        # The query should include parameters for all filters
        args = calls[0][0]
        assert len(args) > 1  # Should have parameters

    @pytest.mark.asyncio
    async def test_search_events_date_overlap(self):
        """Test search with date overlap filters."""
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=3)
        mock_pool.fetch = AsyncMock(return_value=[])

        repo = EventRepository(mock_pool)

        request = SearchRequest(
            occurs_from=datetime(2025, 12, 1),
            occurs_to=datetime(2025, 12, 31),
            page=1,
            size=20
        )

        events, total = await repo.search_events(request)

        assert total == 3
        # The query should include date overlap conditions
        mock_pool.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_events_text_search(self):
        """Test full-text search."""
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=2)
        mock_pool.fetch = AsyncMock(return_value=[])

        repo = EventRepository(mock_pool)

        request = SearchRequest(
            q="machine learning AI",
            page=1,
            size=20
        )

        events, total = await repo.search_events(request)

        assert total == 2
        # Verify text search was included in query
        call_args = mock_pool.fetchval.call_args[0]
        assert "machine learning AI" in call_args

    @pytest.mark.asyncio
    async def test_search_events_sorting(self):
        """Test different sorting options."""
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=5)
        mock_pool.fetch = AsyncMock(return_value=[
            {
                "id": uuid4(),
                "title": f"Event {i}",
                "city": "Київ",
                "country": "UA",
                "language": "uk",
                "is_remote": False,
                "source_url": f"https://test.com/{i}",
                "posted_at": datetime(2025, 11, i),
                "occurs_from": None,
                "occurs_to": None,
                "deadline_at": None,
                "status": "active",
                "categories": []
            } for i in range(1, 4)
        ])

        repo = EventRepository(mock_pool)

        # Test different sort options
        for sort_by in ["posted_at", "deadline_at", "occurs_from"]:
            for order in ["asc", "desc"]:
                request = SearchRequest(
                    sort_by=sort_by,
                    order=order,
                    page=1,
                    size=20
                )

                events, total = await repo.search_events(request)
                assert len(events) == 3

    @pytest.mark.asyncio
    async def test_search_events_pagination(self):
        """Test pagination."""
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=100)
        mock_pool.fetch = AsyncMock(return_value=[])

        repo = EventRepository(mock_pool)

        # Test different pages
        for page in [1, 2, 5]:
            request = SearchRequest(
                page=page,
                size=20
            )

            events, total = await repo.search_events(request)
            assert total == 100

            # Verify offset calculation
            expected_offset = (page - 1) * 20
            call_args = mock_pool.fetch.call_args[0]
            # Last two parameters should be size and offset
            assert expected_offset in call_args