"""Database operations for events."""

import hashlib
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

import asyncpg
from asyncpg import UniqueViolationError

from src.models.event import Event, EventExtraction, EventSearchResult, SearchRequest

logger = logging.getLogger(__name__)


class EventRepository:
    """Repository for event database operations."""

    def __init__(self, db_pool):
        """Initialize the repository."""
        self.db_pool = db_pool

    @staticmethod
    def generate_fingerprint(source_url: str, title: str, raw_text: str) -> str:
        """Generate deduplication fingerprint."""
        # Take first 200 chars of raw text
        text_prefix = raw_text[:200] if len(raw_text) > 200 else raw_text
        # Create fingerprint string
        fingerprint_str = f"{source_url.lower()}|{title.lower()}|{text_prefix.lower()}"
        # Generate SHA-256 hash
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()

    async def upsert_event(
        self,
        source_type: str,
        source_url: str,
        raw_text: str,
        extraction: EventExtraction,
        embedding: List[float],
        posted_at: Optional[datetime] = None
    ) -> Tuple[UUID, bool]:
        """
        Upsert an event to the database.

        Returns:
            Tuple of (event_id, is_new) where is_new is True if inserted, False if updated
        """
        fingerprint = self.generate_fingerprint(source_url, extraction.title, raw_text)
        discovered_at = datetime.utcnow()

        # Convert embedding list to pgvector format string
        if isinstance(embedding, list):
            embedding_str = str(embedding)
        else:
            embedding_str = embedding

        query = """
            INSERT INTO events (
                source_type, source_url, discovered_at, posted_at,
                occurs_from, occurs_to, deadline_at,
                language, title, raw_text,
                organizer, city, country, is_remote, apply_url,
                embedding, status, dedupe_fingerprint
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18
            )
            ON CONFLICT (dedupe_fingerprint)
            DO UPDATE SET
                updated_at = NOW(),
                status = EXCLUDED.status,
                occurs_from = EXCLUDED.occurs_from,
                occurs_to = EXCLUDED.occurs_to,
                deadline_at = EXCLUDED.deadline_at
            RETURNING id, (xmax = 0) as is_new
        """

        try:
            result = await self.db_pool.fetchrow(
                query,
                source_type, source_url, discovered_at, posted_at,
                extraction.occurs_from, extraction.occurs_to, extraction.deadline_at,
                extraction.language, extraction.title, raw_text,
                extraction.organizer, extraction.city, extraction.country,
                extraction.is_remote, extraction.apply_url,
                embedding_str, extraction.status, fingerprint
            )

            event_id = result["id"]
            is_new = result["is_new"]

            if is_new:
                logger.info(f"Inserted new event {event_id}")
            else:
                logger.info(f"Updated existing event {event_id}")

            return event_id, is_new

        except Exception as e:
            logger.error(f"Failed to upsert event: {e}")
            raise

    async def link_categories(self, event_id: UUID, category_slugs: List[str]) -> None:
        """Link categories to an event."""
        if not category_slugs:
            return

        # First, get category IDs for the slugs
        query = "SELECT id, slug FROM categories WHERE slug = ANY($1)"
        categories = await self.db_pool.fetch(query, category_slugs)

        if not categories:
            logger.warning(f"No valid categories found for slugs: {category_slugs}")
            return

        # Insert event-category links
        for cat in categories:
            try:
                await self.db_pool.execute(
                    """
                    INSERT INTO event_categories (event_id, category_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    event_id, cat["id"]
                )
                logger.debug(f"Linked category {cat['slug']} to event {event_id}")
            except Exception as e:
                logger.error(f"Failed to link category {cat['slug']} to event {event_id}: {e}")

    async def get_categories(self) -> List[Dict[str, str]]:
        """Get all categories."""
        query = "SELECT slug, name FROM categories ORDER BY slug"
        rows = await self.db_pool.fetch(query)
        return [dict(row) for row in rows]

    async def search_events(self, request: SearchRequest) -> Tuple[List[EventSearchResult], int]:
        """
        Search events with SQL filters.

        Returns:
            Tuple of (events, total_count)
        """
        # Build WHERE clauses
        where_clauses = ["status = 'active'"]
        params = []
        param_count = 0

        # Text search
        if request.q:
            param_count += 1
            params.append(request.q)
            where_clauses.append(f"""
                to_tsvector('simple', title || ' ' || raw_text) @@
                plainto_tsquery('simple', ${param_count})
            """)

        # Simple filters
        if request.city:
            param_count += 1
            params.append(request.city)
            where_clauses.append(f"city = ${param_count}")

        if request.country:
            param_count += 1
            params.append(request.country)
            where_clauses.append(f"country = ${param_count}")

        if request.language:
            param_count += 1
            params.append(request.language)
            where_clauses.append(f"language = ${param_count}")

        if request.is_remote is not None:
            param_count += 1
            params.append(request.is_remote)
            where_clauses.append(f"is_remote = ${param_count}")

        # Date filters
        if request.posted_from:
            param_count += 1
            params.append(request.posted_from)
            where_clauses.append(f"posted_at >= ${param_count}")

        if request.posted_to:
            param_count += 1
            params.append(request.posted_to)
            where_clauses.append(f"posted_at <= ${param_count}")

        if request.deadline_before:
            param_count += 1
            params.append(request.deadline_before)
            where_clauses.append(f"deadline_at <= ${param_count}")

        if request.deadline_after:
            param_count += 1
            params.append(request.deadline_after)
            where_clauses.append(f"deadline_at >= ${param_count}")

        # Date overlap for occurs_from/occurs_to
        if request.occurs_from and request.occurs_to:
            param_count += 2
            params.extend([request.occurs_to, request.occurs_from])
            where_clauses.append(
                f"(occurs_from <= ${param_count - 1} AND occurs_to >= ${param_count})"
            )
        elif request.occurs_from:
            param_count += 1
            params.append(request.occurs_from)
            where_clauses.append(f"occurs_to >= ${param_count}")
        elif request.occurs_to:
            param_count += 1
            params.append(request.occurs_to)
            where_clauses.append(f"occurs_from <= ${param_count}")

        # Build base query
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Handle category filter with JOIN
        if request.category:
            category_query = f"""
                SELECT DISTINCT e.*
                FROM events e
                JOIN event_categories ec ON e.id = ec.event_id
                JOIN categories c ON ec.category_id = c.id
                WHERE {where_clause} AND c.slug = ANY(${param_count + 1})
            """
            param_count += 1
            params.append(request.category)
            base_query = category_query
        else:
            base_query = f"SELECT * FROM events WHERE {where_clause}"

        # Count total
        count_query = f"SELECT COUNT(*) FROM ({base_query}) as filtered"
        total = await self.db_pool.fetchval(count_query, *params)

        # Add sorting and pagination
        order_clause = f"ORDER BY {request.sort_by} {request.order.upper()}"
        offset = (request.page - 1) * request.size

        final_query = f"""
            WITH filtered_events AS ({base_query})
            SELECT
                e.*,
                array_agg(c.slug) FILTER (WHERE c.slug IS NOT NULL) as categories
            FROM filtered_events e
            LEFT JOIN event_categories ec ON e.id = ec.event_id
            LEFT JOIN categories c ON ec.category_id = c.id
            GROUP BY e.id, e.source_type, e.source_url, e.discovered_at, e.posted_at,
                     e.occurs_from, e.occurs_to, e.deadline_at, e.language, e.title,
                     e.raw_text, e.organizer, e.city, e.country, e.is_remote, e.apply_url,
                     e.embedding, e.status, e.dedupe_fingerprint, e.created_at, e.updated_at
            {order_clause}
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
        """
        params.extend([request.size, offset])

        rows = await self.db_pool.fetch(final_query, *params)

        # Convert to EventSearchResult
        events = []
        for row in rows:
            events.append(EventSearchResult(
                id=row["id"],
                title=row["title"],
                city=row["city"],
                country=row["country"],
                language=row["language"],
                is_remote=row["is_remote"],
                source_url=row["source_url"],
                posted_at=row["posted_at"],
                occurs_from=row["occurs_from"],
                occurs_to=row["occurs_to"],
                deadline_at=row["deadline_at"],
                status=row["status"],
                categories_slugs=row["categories"] or []
            ))

        return events, total