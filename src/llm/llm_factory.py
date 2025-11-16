"""LLM factory for creating configurable LLM instances."""

import logging
from typing import Optional

from llama_index.core.llms import LLM
from llama_index.llms.anthropic import Anthropic
from llama_index.llms.gemini import Gemini
from llama_index.llms.openai import OpenAI
from llama_index.llms.deepseek import DeepSeek

from src.config import settings

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM instances based on configuration."""

    @staticmethod
    def create_llm(
        provider: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> LLM:
        """
        Create an LLM instance based on provider configuration.

        Args:
            provider: LLM provider name (defaults to settings)
            api_key: API key (defaults to settings)

        Returns:
            LLM instance

        Raises:
            ValueError: If provider is not supported or API key is missing
        """
        provider = provider or settings.llm_provider

        if provider == "anthropic":
            api_key = api_key or settings.anthropic_api_key
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")
            logger.info("Creating Anthropic LLM instance")
            return Anthropic(
                model="claude-3-5-sonnet-20241022",
                api_key=api_key,
                temperature=0.1,
                max_tokens=2048
            )

        elif provider == "gemini":
            api_key = api_key or settings.gemini_api_key
            if not api_key:
                raise ValueError("GEMINI_API_KEY is required for Gemini provider")
            logger.info("Creating Gemini LLM instance")
            return Gemini(
                model="gemini-2.0-flash-exp",
                api_key=api_key,
                temperature=0.1
            )

        elif provider == "openai":
            api_key = api_key or settings.openai_api_key
            if not api_key:
                raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
            logger.info("Creating OpenAI LLM instance")
            return OpenAI(
                model="gpt-4o",
                api_key=api_key,
                temperature=0.1
            )

        elif provider == "deepseek":
            api_key = api_key or settings.deepseek_api_key
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek provider")
            logger.info("Creating DeepSeek LLM instance")
            return DeepSeek(
                model="deepseek-chat",
                api_key=api_key,
                temperature=0.1,
                max_tokens=2048
            )

        elif provider == "openrouter":
            api_key = api_key or settings.openrouter_api_key
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY is required for OpenRouter provider")

            # Use gpt-3.5-turbo as the model - it's cheaper and OpenRouter supports it
            # OpenRouter will route to their gpt-3.5-turbo provider using your free credits
            model = "gpt-3.5-turbo"
            logger.info(f"Creating OpenRouter LLM instance (using {model})")

            # OpenRouter is OpenAI-compatible
            llm = OpenAI(
                model=model,
                api_key=api_key,
                api_base="https://openrouter.ai/api/v1",
                temperature=0.1,
                max_tokens=2048
            )

            logger.info("OpenRouter configured successfully")
            return llm

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


# Global LLM instance
_llm_instance: Optional[LLM] = None


def get_llm() -> LLM:
    """Get or create the global LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMFactory.create_llm()
    return _llm_instance