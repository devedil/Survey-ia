from collections.abc import Sequence

from openai import OpenAI

from backend.app.core.config import get_settings
from backend.app.documents.models import VECTOR_DIMENSIONS


class EmbeddingConfigurationError(RuntimeError):
    """Raised when embedding configuration is incomplete or inconsistent."""


class OpenAIEmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _client(self) -> OpenAI:
        api_key = self.settings.openai_api_key
        if not api_key or api_key == "replace_me":
            raise EmbeddingConfigurationError("OPENAI_API_KEY must be configured for document indexing")
        if not self.settings.openai_embedding_model:
            raise EmbeddingConfigurationError("OPENAI_EMBEDDING_MODEL must be configured")
        return OpenAI(api_key=api_key)

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._client()
        embeddings: list[list[float]] = []
        for offset in range(0, len(texts), 100):
            batch = list(texts[offset : offset + 100])
            response = client.embeddings.create(
                model=self.settings.openai_embedding_model,
                input=batch,
            )
            batch_data = sorted(response.data, key=lambda item: item.index)
            if len(batch_data) != len(batch):
                raise RuntimeError("Embedding provider returned an unexpected number of vectors")
            embeddings.extend(item.embedding for item in batch_data)
        if any(len(vector) != VECTOR_DIMENSIONS for vector in embeddings):
            raise EmbeddingConfigurationError(
                f"Embedding model must return {VECTOR_DIMENSIONS}-dimensional vectors"
            )
        return embeddings


def get_embedding_service() -> OpenAIEmbeddingService:
    return OpenAIEmbeddingService()
