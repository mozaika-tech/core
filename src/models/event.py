"""Event data models."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, validator


class SQSMessage(BaseModel):
    """Incoming SQS message from telegram-scrapper."""
    source_id: int
    run_id: int
    external_id: str
    text: str
    posted_at: Optional[datetime] = None
    author: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class EventExtraction(BaseModel):
    """LLM-extracted event data."""
    title: str = Field(..., max_length=120)
    language: str  # ISO-639-1: 'uk', 'en', 'pl'
    city: Optional[str] = None
    country: Optional[str] = None  # ISO-3166-1 alpha-2
    is_remote: Optional[bool] = None
    organizer: Optional[str] = None
    apply_url: Optional[str] = None
    occurs_from: Optional[datetime] = None
    occurs_to: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    status: str = "active"
    categories_slugs: List[str] = Field(default_factory=list)

    @validator("language")
    def validate_language(cls, v):
        """Validate language code is ISO-639-1."""
        if len(v) != 2:
            raise ValueError("Language must be a 2-letter ISO-639-1 code")
        return v.lower()

    @validator("country")
    def validate_country(cls, v):
        """Validate country code is ISO-3166-1 alpha-2."""
        if v and len(v) != 2:
            raise ValueError("Country must be a 2-letter ISO-3166-1 alpha-2 code")
        return v.upper() if v else None


class Event(BaseModel):
    """Database event model."""
    id: UUID
    source_type: str
    source_url: str
    discovered_at: datetime
    posted_at: Optional[datetime]
    occurs_from: Optional[datetime]
    occurs_to: Optional[datetime]
    deadline_at: Optional[datetime]
    language: str
    title: str
    raw_text: str
    organizer: Optional[str]
    city: Optional[str]
    country: Optional[str]
    is_remote: Optional[bool]
    apply_url: Optional[str]
    embedding: List[float]
    status: str
    dedupe_fingerprint: str
    created_at: datetime
    updated_at: datetime
    categories: List[str] = Field(default_factory=list)  # Category slugs


class EventSearchResult(BaseModel):
    """Search result for an event."""
    id: UUID
    title: str
    city: Optional[str]
    country: Optional[str]
    language: str
    is_remote: Optional[bool]
    source_url: str
    posted_at: Optional[datetime]
    occurs_from: Optional[datetime]
    occurs_to: Optional[datetime]
    deadline_at: Optional[datetime]
    status: str
    categories_slugs: List[str] = Field(default_factory=list)
    score: Optional[float] = None  # Semantic similarity score
    match_score: Optional[float] = None  # Profile-adjusted score
    match_tier: Optional[str] = None  # low/medium/high


class SearchRequest(BaseModel):
    """GET /search query parameters."""
    q: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    is_remote: Optional[bool] = None
    category: List[str] = Field(default_factory=list)
    posted_from: Optional[datetime] = None
    posted_to: Optional[datetime] = None
    occurs_from: Optional[datetime] = None
    occurs_to: Optional[datetime] = None
    deadline_before: Optional[datetime] = None
    deadline_after: Optional[datetime] = None
    sort_by: str = "posted_at"  # posted_at | deadline_at | occurs_from
    order: str = "desc"  # asc | desc
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class SearchResponse(BaseModel):
    """Search API response."""
    hits: List[EventSearchResult]
    page: int
    size: int
    total: int


class AISearchRequest(BaseModel):
    """POST /ai/search request body."""
    query: str
    top_k: int = Field(12, ge=1, le=100)
    profile_inline: Optional[dict] = None


class AISearchResponse(BaseModel):
    """AI search API response."""
    hits: List[EventSearchResult]
    chat_answer: str


class QueryIntent(BaseModel):
    """LLM-parsed query intent for AI search."""
    city: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    is_remote: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    categories_slugs: List[str] = Field(default_factory=list)
    top_k: int = 12
    user_query_rewritten: str