from fastapi import Depends

from backend.app.ai.model_router import ModelRouter
from backend.app.answers.memory_manager import MemoryManager
from backend.app.documents.embedding_service import OpenAIEmbeddingService, get_embedding_service


def get_model_router() -> ModelRouter:
    return ModelRouter()


def get_memory_manager(
    embedding_service: OpenAIEmbeddingService = Depends(get_embedding_service),
) -> MemoryManager:
    return MemoryManager(embedding_service)
