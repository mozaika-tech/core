"""Vector store management with LlamaIndex and PGVector."""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from llama_index.core import VectorStoreIndex, Document
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.vector_stores import (
    MetadataFilters,
    MetadataFilter,
    FilterOperator,
    FilterCondition
)
from llama_index.core.response_synthesizers import (
    get_response_synthesizer,
    ResponseMode
)
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import make_url

from src.config import settings
from src.llm.embeddings import embedding_service
from src.llm.llm_factory import get_llm
from src.models.event import EventSearchResult, QueryIntent

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Service for managing vector store operations."""

    def __init__(self):
        """Initialize the vector store service."""
        self.vector_store = None
        self.index = None
        self._initialize_store()

    def _initialize_store(self):
        """Initialize the PGVector store."""
        logger.info("Initializing PGVector store...")

        # Parse the database URL for SQLAlchemy
        db_url = make_url(settings.database_url)

        # Extract username and password (might be in query params for some providers like Neon)
        username = db_url.username
        password = db_url.password

        # If not in standard location, check query parameters
        if not username and db_url.query.get('user'):
            username = db_url.query['user']
        if not password and db_url.query.get('password'):
            password = db_url.query['password']

        # Create PGVector store
        self.vector_store = PGVectorStore.from_params(
            database=db_url.database,
            host=db_url.host,
            password=password,
            port=db_url.port,
            user=username,
            table_name="events",
            embed_dim=384,
            hybrid_search=False,
            text_search_config="simple"
        )

        # Create index
        self.index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            embed_model=embedding_service._embed_model
        )

        logger.info("PGVector store initialized successfully")

    async def index_event(
        self,
        event_id: UUID,
        title: str,
        raw_text: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Index an event in the vector store.

        Args:
            event_id: Event UUID
            title: Event title
            raw_text: Event raw text
            metadata: Event metadata for filtering
        """
        try:
            # Create document
            text = f"{title}\n\n{raw_text}"
            doc = Document(
                text=text,
                id_=str(event_id),
                metadata=metadata
            )

            # Index the document
            self.index.insert(doc)
            logger.debug(f"Indexed event {event_id} in vector store")

        except Exception as e:
            logger.error(f"Failed to index event {event_id}: {e}")
            raise

    async def search_similar(
        self,
        query: str,
        intent: Optional[QueryIntent] = None,
        top_k: int = 12
    ) -> List[EventSearchResult]:
        """
        Search for similar events using vector similarity.

        Args:
            query: Search query text
            intent: Parsed query intent with filters
            top_k: Number of results to return

        Returns:
            List of similar events
        """
        # Build metadata filters from intent
        filters = []

        if intent:
            if intent.city:
                filters.append(
                    MetadataFilter(
                        key="city",
                        value=intent.city,
                        operator=FilterOperator.EQ
                    )
                )

            if intent.country:
                filters.append(
                    MetadataFilter(
                        key="country",
                        value=intent.country,
                        operator=FilterOperator.EQ
                    )
                )

            if intent.language:
                filters.append(
                    MetadataFilter(
                        key="language",
                        value=intent.language,
                        operator=FilterOperator.EQ
                    )
                )

            if intent.is_remote is not None:
                filters.append(
                    MetadataFilter(
                        key="is_remote",
                        value=intent.is_remote,
                        operator=FilterOperator.EQ
                    )
                )

            # Category filters (OR within categories)
            if intent.categories_slugs:
                for cat in intent.categories_slugs:
                    filters.append(
                        MetadataFilter(
                            key="categories_slugs",
                            value=cat,
                            operator=FilterOperator.CONTAINS
                        )
                    )

            # Date range filters
            if intent.date_from:
                filters.append(
                    MetadataFilter(
                        key="posted_at",
                        value=intent.date_from.isoformat(),
                        operator=FilterOperator.GTE
                    )
                )

            if intent.date_to:
                filters.append(
                    MetadataFilter(
                        key="posted_at",
                        value=intent.date_to.isoformat(),
                        operator=FilterOperator.LTE
                    )
                )

        # Create retriever with filters
        metadata_filters = MetadataFilters(
            filters=filters,
            condition=FilterCondition.AND
        ) if filters else None

        retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=top_k,
            filters=metadata_filters
        )

        # Retrieve similar documents
        nodes = await retriever.aretrieve(query)

        # Convert to EventSearchResult
        results = []
        for node in nodes:
            # Extract metadata and score
            metadata = node.metadata
            score = node.score if hasattr(node, 'score') else None

            results.append(EventSearchResult(
                id=UUID(node.id_),
                title=metadata.get("title", ""),
                city=metadata.get("city"),
                country=metadata.get("country"),
                language=metadata.get("language", "uk"),
                is_remote=metadata.get("is_remote"),
                source_url=metadata.get("source_url", ""),
                posted_at=datetime.fromisoformat(metadata["posted_at"]) if metadata.get("posted_at") else None,
                occurs_from=datetime.fromisoformat(metadata["occurs_from"]) if metadata.get("occurs_from") else None,
                occurs_to=datetime.fromisoformat(metadata["occurs_to"]) if metadata.get("occurs_to") else None,
                deadline_at=datetime.fromisoformat(metadata["deadline_at"]) if metadata.get("deadline_at") else None,
                status=metadata.get("status", "active"),
                categories_slugs=metadata.get("categories_slugs", []),
                score=score
            ))

        return results

    async def synthesize_answer(
        self,
        query: str,
        events: List[EventSearchResult],
        language: str = "uk"
    ) -> str:
        """
        Synthesize a chat answer based on retrieved events.

        Args:
            query: Original user query
            events: Retrieved events
            language: Response language

        Returns:
            Synthesized chat answer
        """
        # Prepare context from events
        context_parts = []
        for i, event in enumerate(events[:5], 1):  # Use top 5 for context
            context_parts.append(
                f"{i}. {event.title}\n"
                f"   Місто: {event.city or 'Не вказано'}\n"
                f"   Дедлайн: {event.deadline_at.strftime('%Y-%m-%d') if event.deadline_at else 'Не вказано'}\n"
                f"   Категорії: {', '.join(event.categories_slugs) if event.categories_slugs else 'Не вказано'}"
            )

        context = "\n\n".join(context_parts)

        # Create synthesis prompt
        if language == "uk":
            prompt = f"""
Користувач шукає: {query}

Знайдені події:
{context}

Поясни українською мовою, які події найкраще підходять під запит і чому. Будь лаконічним (2-3 речення).
"""
        else:
            prompt = f"""
User is searching for: {query}

Found events:
{context}

Explain which events best match the query and why. Be concise (2-3 sentences).
"""

        # Get response from LLM
        try:
            llm = get_llm()
            synthesizer = get_response_synthesizer(
                response_mode=ResponseMode.COMPACT,
                llm=llm
            )

            response = await synthesizer.asynthesize(
                query=prompt,
                nodes=[]  # We're providing context in the prompt directly
            )

            return response.response

        except Exception as e:
            logger.error(f"Failed to synthesize answer: {e}")
            if language == "uk":
                return "Знайдено події, які можуть вас зацікавити. Перегляньте результати вище."
            else:
                return "Found events that might interest you. Please review the results above."


# Global vector store service instance
_vector_store: Optional[VectorStoreService] = None


def get_vector_store() -> VectorStoreService:
    """Get or create the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStoreService()
    return _vector_store