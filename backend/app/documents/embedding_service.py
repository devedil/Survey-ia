import time
from collections.abc import Sequence

from openai import OpenAI
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallBudget
from backend.app.core.config import get_settings
from backend.app.documents.models import VECTOR_DIMENSIONS
from backend.app.usage.models import ModelUsage
from backend.app.usage.pricing_catalog import calculate_cost
from backend.app.usage.repository import record_usage


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

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        db: Session | None = None,
        profile_id: str | None = None,
        operation: str = "embedding",
        call_budget: ModelCallBudget | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        client = self._client()
        embeddings: list[list[float]] = []
        for offset in range(0, len(texts), 100):
            batch = list(texts[offset : offset + 100])
            if call_budget:
                call_budget.consume()
            started = time.perf_counter()
            input_tokens = None
            status = "failed"
            error_code = None
            error_message = None
            try:
                response = client.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=batch,
                )
                batch_data = sorted(response.data, key=lambda item: item.index)
                if len(batch_data) != len(batch):
                    raise RuntimeError("Embedding provider returned an unexpected number of vectors")
                if any(len(item.embedding) != VECTOR_DIMENSIONS for item in batch_data):
                    raise EmbeddingConfigurationError(
                        f"Embedding model must return {VECTOR_DIMENSIONS}-dimensional vectors"
                    )
                embeddings.extend(item.embedding for item in batch_data)
                input_tokens = response.usage.prompt_tokens if response.usage else None
                status = "succeeded"
            except Exception as error:
                error_code = type(error).__name__
                error_message = "Embedding provider request failed"
                raise
            finally:
                if db is not None:
                    price = (
                        calculate_cost(self.settings.openai_embedding_model, input_tokens, 0)
                        if input_tokens is not None
                        else None
                    )
                    record_usage(
                        db,
                        ModelUsage(
                            profile_id=profile_id,
                            operation=operation,
                            provider="openai",
                            model=self.settings.openai_embedding_model,
                            input_tokens=input_tokens,
                            output_tokens=0 if status == "succeeded" else None,
                            cached_input_tokens=None,
                            cost_usd=price[0] if price else None,
                            cost_is_estimated=price is None,
                            pricing_version=price[1] if price else None,
                            duration_ms=int((time.perf_counter() - started) * 1000),
                            status=status,
                            error_code=error_code,
                            error_message=error_message,
                        ),
                    )
        if any(len(vector) != VECTOR_DIMENSIONS for vector in embeddings):
            raise EmbeddingConfigurationError(
                f"Embedding model must return {VECTOR_DIMENSIONS}-dimensional vectors"
            )
        return embeddings


def get_embedding_service() -> OpenAIEmbeddingService:
    return OpenAIEmbeddingService()
