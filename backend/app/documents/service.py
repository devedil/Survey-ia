import os
import shutil
import uuid
from pathlib import Path
from typing import Protocol, Sequence

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.documents.chunker import split_into_chunks
from backend.app.documents.embedding_service import EmbeddingConfigurationError
from backend.app.documents.models import VECTOR_DIMENSIONS, Document, DocumentChunk
from backend.app.documents.processor import DocumentProcessingError, detect_mime_type, extract_text
from backend.app.documents.repository import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    mark_document_failed,
    replace_chunks,
    search_chunks,
)
from backend.app.profiles.models import Profile


class Embedder(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class DocumentServiceError(RuntimeError):
    pass


def _storage_root() -> Path:
    return Path(get_settings().document_storage_path).expanduser().resolve()


def _document_path(document: Document) -> Path:
    root = _storage_root()
    path = Path(document.storage_path).resolve()
    if path == root or root not in path.parents:
        raise DocumentServiceError("Stored document path is outside the private storage directory")
    return path


def _safe_filename(filename: str) -> str:
    safe = Path(filename.replace("\\", "/")).name
    safe = "".join(char for char in safe if char.isprintable() and char not in '<>:"/\\|?*')
    if not safe or len(safe) > 255:
        raise DocumentProcessingError("Invalid filename")
    return safe


def _mark_failed(db: Session, document_id: str, error: Exception) -> None:
    if isinstance(error, (DocumentProcessingError, EmbeddingConfigurationError)):
        message = str(error)
    else:
        message = f"Document indexing failed ({type(error).__name__})"
    mark_document_failed(db, document_id, message)


def _index(
    db: Session,
    document: Document,
    content: bytes,
    embedder: Embedder,
) -> Document:
    try:
        text = extract_text(document.filename, content)
        settings = get_settings()
        chunks = split_into_chunks(
            text,
            chunk_size=settings.document_chunk_size,
            overlap=settings.document_chunk_overlap,
        )
        if not chunks:
            raise DocumentProcessingError("No searchable text was produced")
        vectors = embedder.embed_texts(chunks)
        if len(vectors) != len(chunks):
            raise DocumentServiceError("Embedding provider returned an unexpected number of vectors")
        if any(len(vector) != VECTOR_DIMENSIONS for vector in vectors):
            raise DocumentServiceError(f"Embedding vectors must have {VECTOR_DIMENSIONS} dimensions")
        chunk_rows = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=chunk,
                embedding=vector,
                chunk_metadata={"source_filename": document.filename},
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]
        replace_chunks(db, document, chunk_rows)
        return document
    except Exception as error:
        _mark_failed(db, document.id, error)
        raise


def upload_document(
    db: Session,
    profile: Profile,
    filename: str,
    declared_mime: str | None,
    content: bytes,
    embedder: Embedder,
) -> Document:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise DocumentProcessingError(f"File exceeds the {settings.max_upload_mb} MB upload limit")

    safe_filename = _safe_filename(filename)
    mime_type = detect_mime_type(safe_filename, content, declared_mime)
    document_id = str(uuid.uuid4())
    root = _storage_root()
    root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        root.chmod(0o700)
    document_dir = root / document_id
    document_dir.mkdir(parents=True, exist_ok=False)
    if os.name != "nt":
        document_dir.chmod(0o700)
    storage_path = document_dir / f"source{Path(safe_filename).suffix.lower()}"
    try:
        storage_path.write_bytes(content)
        if os.name != "nt":
            storage_path.chmod(0o600)
        document = Document(
            id=document_id,
            profile_id=profile.id,
            filename=safe_filename,
            mime_type=mime_type,
            storage_path=str(storage_path),
            status="processing",
        )
        create_document(db, document)
    except Exception:
        if document_dir.exists():
            shutil.rmtree(document_dir)
        raise

    return _index(db, document, content, embedder)


def reindex_document(db: Session, document: Document, embedder: Embedder) -> Document:
    path = _document_path(document)
    try:
        content = path.read_bytes()
    except OSError as error:
        _mark_failed(db, document.id, DocumentProcessingError("Stored document file is unavailable"))
        raise DocumentProcessingError("Stored document file is unavailable") from error
    return _index(db, document, content, embedder)


def remove_document(db: Session, document: Document) -> None:
    path = _document_path(document)
    document_dir = path.parent
    delete_document(db, document)
    try:
        path.unlink(missing_ok=True)
        document_dir.rmdir()
    except OSError as error:
        raise DocumentServiceError("Document record was deleted but its stored file could not be removed") from error


def find_documents(db: Session, profile_id: str | None = None) -> list[Document]:
    return list(list_documents(db, profile_id))


def find_document(db: Session, document_id: str) -> Document | None:
    return get_document(db, document_id)


def search_documents(
    db: Session,
    profile_id: str,
    query: str,
    limit: int,
    embedder: Embedder,
) -> list[tuple[DocumentChunk, Document, float]]:
    query_vector = embedder.embed_texts([query])
    if len(query_vector) != 1:
        raise DocumentServiceError("Embedding provider returned an unexpected number of vectors")
    if len(query_vector[0]) != VECTOR_DIMENSIONS:
        raise DocumentServiceError(f"Embedding vectors must have {VECTOR_DIMENSIONS} dimensions")
    return search_chunks(db, profile_id, query_vector[0], limit)
