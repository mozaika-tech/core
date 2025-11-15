"""Embedding model management."""

import logging
from typing import List, Optional

from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from src.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for managing embeddings."""

    _instance: Optional["EmbeddingService"] = None
    _embed_model: Optional[HuggingFaceEmbedding] = None

    def __new__(cls):
        """Singleton pattern for embedding service."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the embedding service."""
        if self._embed_model is None:
            self._initialize_model()

    def _initialize_model(self):
        """Initialize the embedding model."""
        logger.info(f"Initializing embedding model: {settings.embedding_model}")
        self._embed_model = HuggingFaceEmbedding(
            model_name=settings.embedding_model,
            embed_batch_size=10,
            normalize=True,  # L2 normalization
            trust_remote_code=True
        )
        logger.info("Embedding model initialized successfully")

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of float values representing the embedding
        """
        if not self._embed_model:
            self._initialize_model()

        embedding = self._embed_model.get_text_embedding(text)
        return embedding

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        if not self._embed_model:
            self._initialize_model()

        embeddings = self._embed_model.get_text_embedding_batch(texts)
        return embeddings


# Global embedding service instance
embedding_service = EmbeddingService()