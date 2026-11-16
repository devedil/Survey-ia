from dataclasses import dataclass
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallBudget
from backend.app.documents.embedding_service import EmbeddingConfigurationError, OpenAIEmbeddingService
from backend.app.documents.models import Document
from backend.app.documents.repository import search_chunks
from backend.app.profiles.models import ProfileFact


@dataclass(frozen=True)
class Evidence:
    source_type: str
    source_id: str
    content: str
    label: str

    def as_payload(self) -> dict[str, str]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "label": self.label,
            "content": self.content,
        }


class MemoryManager:
    def __init__(self, embedding_service: OpenAIEmbeddingService):
        self.embedding_service = embedding_service

    def retrieve(
        self,
        db: Session,
        profile_id: str,
        query: str,
        limit: int = 5,
        call_budget: ModelCallBudget | None = None,
    ) -> list[Evidence]:
        question_terms = set(re.findall(r"\w+", query.casefold()))
        facts = db.scalars(
            select(ProfileFact)
            .where(ProfileFact.profile_id == profile_id, ProfileFact.is_verified.is_(True))
            .order_by(ProfileFact.updated_at.desc())
            .limit(50)
        ).all()
        evidence = [
            Evidence(
                source_type="profile_fact",
                source_id=fact.id,
                content=f"{fact.field_name}: {fact.value}",
                label=fact.field_name,
            )
            for fact in facts
            if question_terms.intersection(re.findall(r"\w+", fact.field_name.casefold()))
        ]
        has_indexed_documents = db.scalar(
            select(1)
            .select_from(Document)
            .where(
                Document.profile_id == profile_id,
                Document.status == "indexed",
            )
            .limit(1)
        )
        if has_indexed_documents and (call_budget is None or not call_budget.exhausted):
            query_vectors = self.embedding_service.embed_texts(
                [query],
                db=db,
                profile_id=profile_id,
                operation="document_search",
                call_budget=call_budget,
            )
            if len(query_vectors) != 1:
                raise RuntimeError("Embedding provider returned an unexpected number of vectors")
            rows = search_chunks(db, profile_id, query_vectors[0], limit)
            evidence.extend(
                Evidence(
                    source_type="document_chunk",
                    source_id=chunk.id,
                    content=chunk.content,
                    label=document.filename,
                )
                for chunk, document, _score in rows
            )
        return evidence
