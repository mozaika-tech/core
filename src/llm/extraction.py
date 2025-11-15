"""LLM-based extraction service for event data."""

import json
import logging
from typing import List, Optional

from llama_index.core.llms import ChatMessage

from src.llm.llm_factory import get_llm
from src.models.event import EventExtraction, QueryIntent

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service for extracting structured data from text using LLM."""

    EXTRACTION_PROMPT = """
Проаналізуй текст події та поверни JSON з наступними полями.

Доступні категорії (обирай лише з цього списку): {categories_list}

Поверни ЛИШЕ валідний JSON без пояснень:
{{
  "title": "короткий заголовок (до 120 символів)",
  "language": "uk",
  "city": null або "Київ",
  "country": null або "UA",
  "is_remote": null або true або false,
  "organizer": null або "Назва організації",
  "apply_url": null або "https://...",
  "occurs_from": null або "2025-12-12T09:00:00Z",
  "occurs_to": null або "2025-12-12T17:00:00Z",
  "deadline_at": null або "2025-12-05T23:59:59Z",
  "status": "active",
  "categories_slugs": []
}}

Правила:
- language (ОБОВ'ЯЗКОВО): ISO-639-1 код ('uk', 'en', 'pl')
- country: ISO-3166-1 alpha-2 ('UA', 'PL', null)
- Всі дати: ISO 8601 UTC
- is_remote=true для онлайн/дистанційних подій
- categories_slugs: лише зі списку вище, якщо невпевнений — []

Текст події:
{event_text}
"""

    QUERY_UNDERSTANDING_PROMPT = """
Проаналізуй запит користувача та поверни JSON з фільтрами пошуку.

Доступні категорії: {categories_list}

Поверни ЛИШЕ валідний JSON:
{{
  "city": null або "Київ",
  "country": null або "UA",
  "language": null або "uk",
  "is_remote": null або true або false,
  "date_from": null або "2025-12-01T00:00:00Z",
  "date_to": null або "2025-12-31T23:59:59Z",
  "categories_slugs": [],
  "top_k": 12,
  "user_query_rewritten": "короткий переформульований запит"
}}

Правила:
- Використовуй null для відсутньої інформації
- Нормалізуй категорії до канонічних слугів
- Всі дати: ISO 8601 UTC

Запит: {user_query}

Профіль користувача: {user_profile}
"""

    def __init__(self, categories: List[str]):
        """
        Initialize the extraction service.

        Args:
            categories: List of available category slugs
        """
        self.categories = categories
        self.categories_list = ", ".join(categories)
        self.llm = get_llm()

    async def extract_event_data(
        self,
        raw_text: str,
        max_retries: int = 3
    ) -> Optional[EventExtraction]:
        """
        Extract structured event data from raw text.

        Args:
            raw_text: Raw event text
            max_retries: Maximum number of retries on failure

        Returns:
            EventExtraction object or None if extraction fails

        Raises:
            Exception: Re-raises rate limit errors to allow caller to handle them
        """
        import asyncio

        prompt = self.EXTRACTION_PROMPT.format(
            categories_list=self.categories_list,
            event_text=raw_text
        )

        for attempt in range(max_retries):
            try:
                # Call LLM
                messages = [ChatMessage(role="user", content=prompt)]
                response = await self.llm.achat(messages)
                response_text = response.message.content.strip()

                # Try to parse JSON
                # Remove any markdown code blocks if present
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]

                data = json.loads(response_text)

                # Validate and create EventExtraction
                extraction = EventExtraction(**data)

                # Validate categories are from allowed list
                valid_categories = [
                    cat for cat in extraction.categories_slugs
                    if cat in self.categories
                ]
                extraction.categories_slugs = valid_categories

                return extraction

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt seconds
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to extract event data after {max_retries} attempts")
                    return None

            except Exception as e:
                error_msg = str(e)

                # Check if it's a rate limit error (429 or quota exceeded)
                if "429" in error_msg or "quota" in error_msg.lower() or "rate" in error_msg.lower():
                    logger.warning(f"Rate limit hit (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        # For rate limits, use longer backoff
                        backoff = min(30, 5 * (2 ** attempt))  # Cap at 30 seconds
                        logger.info(f"Waiting {backoff}s before retry due to rate limit")
                        await asyncio.sleep(backoff)
                    else:
                        # Re-raise rate limit errors so consumer can decide whether to delete message
                        logger.error("Rate limit exceeded after all retries")
                        raise
                else:
                    logger.error(f"Error during extraction (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return None

        return None

    async def understand_query(
        self,
        user_query: str,
        user_profile: Optional[dict] = None
    ) -> Optional[QueryIntent]:
        """
        Parse user query to extract search intent.

        Args:
            user_query: User's search query
            user_profile: Optional user profile information

        Returns:
            QueryIntent object or None if parsing fails
        """
        profile_str = json.dumps(user_profile, ensure_ascii=False) if user_profile else "Немає"

        prompt = self.QUERY_UNDERSTANDING_PROMPT.format(
            categories_list=self.categories_list,
            user_query=user_query,
            user_profile=profile_str
        )

        try:
            # Call LLM
            messages = [ChatMessage(role="user", content=prompt)]
            response = await self.llm.achat(messages)
            response_text = response.message.content.strip()

            # Parse JSON
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            data = json.loads(response_text)

            # Create QueryIntent
            intent = QueryIntent(**data)

            # Validate categories
            valid_categories = [
                cat for cat in intent.categories_slugs
                if cat in self.categories
            ]
            intent.categories_slugs = valid_categories

            return intent

        except Exception as e:
            logger.error(f"Error understanding query: {e}")
            return None