"""FastAPI application for the search API."""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field

from src.config import settings
from src.database.connection import get_db_pool
from src.database.events import EventRepository
from src.llm.extraction import ExtractionService
from src.llm.vector_store import get_vector_store
from src.models.event import (
    SearchRequest,
    SearchResponse,
    AISearchRequest,
    AISearchResponse,
    EventSearchResult
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Mozaika Event Search API",
    description="API for searching events with SQL and AI-powered semantic search",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependencies
async def get_event_repository():
    """Dependency to get event repository."""
    db_pool = await get_db_pool()
    return EventRepository(db_pool)


async def get_extraction_service():
    """Dependency to get extraction service."""
    db_pool = await get_db_pool()
    event_repo = EventRepository(db_pool)
    categories = await event_repo.get_categories()
    category_slugs = [cat["slug"] for cat in categories]
    return ExtractionService(category_slugs)


# Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting FastAPI application...")

    # Initialize database pool
    db_pool = await get_db_pool()
    logger.info("Database pool initialized")

    # Initialize vector store
    get_vector_store()
    logger.info("Vector store initialized")

    logger.info("FastAPI application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down FastAPI application...")

    # Close database pool
    db_pool = await get_db_pool()
    await db_pool.close()

    logger.info("FastAPI application shut down")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/search", response_model=SearchResponse)
async def search_events(
    q: Optional[str] = Query(None, description="Full-text search query"),
    city: Optional[str] = Query(None, description="Filter by city"),
    country: Optional[str] = Query(None, description="Filter by country (ISO-3166-1 alpha-2)"),
    language: Optional[str] = Query(None, description="Filter by language (ISO-639-1)"),
    is_remote: Optional[bool] = Query(None, description="Filter by remote/onsite"),
    category: List[str] = Query([], description="Filter by categories (slugs)"),
    posted_from: Optional[datetime] = Query(None, description="Filter by posted date (from)"),
    posted_to: Optional[datetime] = Query(None, description="Filter by posted date (to)"),
    occurs_from: Optional[datetime] = Query(None, description="Filter by event date (from)"),
    occurs_to: Optional[datetime] = Query(None, description="Filter by event date (to)"),
    deadline_before: Optional[datetime] = Query(None, description="Filter by deadline (before)"),
    deadline_after: Optional[datetime] = Query(None, description="Filter by deadline (after)"),
    sort_by: str = Query("posted_at", regex="^(posted_at|deadline_at|occurs_from)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    event_repo: EventRepository = Depends(get_event_repository)
):
    """
    Search events using SQL filters.

    This endpoint provides traditional search with filtering capabilities
    based on various event attributes.
    """
    try:
        # Create search request
        search_request = SearchRequest(
            q=q,
            city=city,
            country=country,
            language=language,
            is_remote=is_remote,
            category=category,
            posted_from=posted_from,
            posted_to=posted_to,
            occurs_from=occurs_from,
            occurs_to=occurs_to,
            deadline_before=deadline_before,
            deadline_after=deadline_after,
            sort_by=sort_by,
            order=order,
            page=page,
            size=size
        )

        # Perform search
        events, total = await event_repo.search_events(search_request)

        return SearchResponse(
            hits=events,
            page=page,
            size=size,
            total=total
        )

    except Exception as e:
        logger.error(f"Error in search endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/ai/search", response_model=AISearchResponse)
async def ai_search(
    request: AISearchRequest,
    extraction_service: ExtractionService = Depends(get_extraction_service)
):
    """
    AI-powered semantic search with natural language understanding.

    This endpoint uses LLMs to understand the user's query intent,
    performs vector similarity search, and generates a natural language response.
    """
    try:
        # Step 1: Understand query intent
        intent = await extraction_service.understand_query(
            user_query=request.query,
            user_profile=request.profile_inline
        )

        if not intent:
            # Fallback to simple semantic search without filters
            intent = None
            query_text = request.query
        else:
            query_text = intent.user_query_rewritten

        # Step 2: Perform vector search
        vector_store = get_vector_store()
        events = await vector_store.search_similar(
            query=query_text,
            intent=intent,
            top_k=request.top_k if not intent else intent.top_k
        )

        # Step 3: Calculate match scores if profile provided
        if request.profile_inline:
            events = calculate_match_scores(events, request.profile_inline)

        # Step 4: Generate chat answer
        language = request.profile_inline.get("languages", ["uk"])[0] if request.profile_inline else "uk"
        chat_answer = await vector_store.synthesize_answer(
            query=request.query,
            events=events,
            language=language
        )

        return AISearchResponse(
            hits=events,
            chat_answer=chat_answer
        )

    except Exception as e:
        logger.error(f"Error in AI search endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


def calculate_match_scores(
    events: List[EventSearchResult],
    profile: dict
) -> List[EventSearchResult]:
    """
    Calculate match scores based on user profile preferences.

    Args:
        events: List of events
        profile: User profile with preferences

    Returns:
        Events with calculated match scores
    """
    for event in events:
        match_score = 0.0
        factors = 0

        # Location match
        if "city" in profile and event.city:
            if event.city.lower() == profile["city"].lower():
                match_score += 0.3
            factors += 0.3

        # Language match
        if "languages" in profile and event.language:
            if event.language in profile["languages"]:
                match_score += 0.2
            factors += 0.2

        # Category match
        if "preferred_categories" in profile and event.categories_slugs:
            matching_categories = set(event.categories_slugs) & set(profile["preferred_categories"])
            if matching_categories:
                match_score += 0.3
            factors += 0.3

        # Remote preference
        if "remote_preference" in profile and event.is_remote is not None:
            pref = profile["remote_preference"]
            if pref == "remote" and event.is_remote:
                match_score += 0.2
            elif pref == "onsite" and not event.is_remote:
                match_score += 0.2
            elif pref == "any":
                match_score += 0.1
            factors += 0.2

        # Normalize match score
        if factors > 0:
            event.match_score = match_score / factors
        else:
            event.match_score = 0.5  # Neutral score

        # Combine with semantic similarity
        if event.score:
            event.match_score = (event.score * 0.7 + event.match_score * 0.3)

        # Determine match tier
        if event.match_score >= 0.7:
            event.match_tier = "high"
        elif event.match_score >= 0.4:
            event.match_tier = "medium"
        else:
            event.match_tier = "low"

    # Sort by match score
    events.sort(key=lambda x: x.match_score or 0, reverse=True)

    return events


@app.get("/categories")
async def get_categories(event_repo: EventRepository = Depends(get_event_repository)):
    """Get all available categories."""
    categories = await event_repo.get_categories()
    return categories