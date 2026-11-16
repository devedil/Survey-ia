import math
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.documents.models import Document, DocumentChunk


def create_document(db: Session, document: Document) -> Document:
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, profile_id: str | None = None) -> Sequence[Document]:
    statement = select(Document).options(selectinload(Document.chunks)).order_by(Document.created_at.desc())
    if profile_id:
        statement = statement.where(Document.profile_id == profile_id)
    return db.scalars(statement).all()


def get_document(db: Session, document_id: str) -> Document | None:
    return db.scalar(
        select(Document)
        .options(selectinload(Document.chunks))
        .where(Document.id == document_id)
    )


def replace_chunks(db: Session, document: Document, chunks: list[DocumentChunk]) -> None:
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete(synchronize_session=False)
    db.add_all(chunks)
    document.status = "indexed"
    document.error_message = None
    db.commit()
    db.expire(document, ["chunks"])
    db.refresh(document)


def mark_document_failed(db: Session, document_id: str, message: str) -> None:
    db.rollback()
    document = db.get(Document, document_id)
    if document is not None:
        document.status = "failed"
        document.error_message = message
        db.commit()


def delete_document(db: Session, document: Document) -> None:
    db.delete(document)
    db.commit()


def search_chunks(
    db: Session,
    profile_id: str,
    query_embedding: list[float],
    limit: int,
) -> list[tuple[DocumentChunk, Document, float]]:
    statement = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.profile_id == profile_id, Document.status == "indexed")
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        rows = db.execute(statement.order_by(distance).limit(limit)).all()
        return [(chunk, document, max(-1.0, min(1.0, 1.0 - float(score)))) for chunk, document, score in rows]

    rows = db.execute(statement).all()
    ranked = []
    for chunk, document in rows:
        left = chunk.embedding
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in query_embedding))
        score = sum(a * b for a, b in zip(left, query_embedding)) / (left_norm * right_norm) if left_norm and right_norm else 0.0
        ranked.append((chunk, document, score))
    ranked.sort(key=lambda result: result[2], reverse=True)
    return ranked[:limit]
