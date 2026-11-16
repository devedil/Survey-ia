from typing import NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.documents.embedding_service import (
    EmbeddingConfigurationError,
    OpenAIEmbeddingService,
    get_embedding_service,
)
from backend.app.documents.models import Document
from backend.app.documents.processor import DocumentProcessingError
from backend.app.documents.schemas import DocumentRead, DocumentSearchRequest, DocumentSearchResult
from backend.app.documents.service import (
    DocumentServiceError,
    find_document,
    find_documents,
    reindex_document,
    remove_document,
    search_documents,
    upload_document,
)
from backend.app.profiles.repository import get_profile

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_read(document: Document) -> DocumentRead:
    return DocumentRead.model_validate(
        {
            "id": document.id,
            "profile_id": document.profile_id,
            "filename": document.filename,
            "mime_type": document.mime_type,
            "status": document.status,
            "error_message": document.error_message,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
            "chunk_count": len(document.chunks),
        }
    )


def _raise_processing_error(error: Exception) -> NoReturn:
    if isinstance(error, EmbeddingConfigurationError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    if isinstance(error, DocumentProcessingError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    raise error


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload(
    profile_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    embedder: OpenAIEmbeddingService = Depends(get_embedding_service),
) -> DocumentRead:
    profile = get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    settings_limit = get_settings().max_upload_mb * 1024 * 1024
    content = file.file.read(settings_limit + 1)
    try:
        document = upload_document(db, profile, file.filename or "", file.content_type, content, embedder)
    except (DocumentProcessingError, EmbeddingConfigurationError) as error:
        _raise_processing_error(error)
    return _to_read(document)


@router.get("", response_model=list[DocumentRead])
def list_all(
    profile_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    if profile_id is not None and get_profile(db, profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return [_to_read(document) for document in find_documents(db, profile_id)]


@router.get("/{document_id}", response_model=DocumentRead)
def get_one(document_id: str, db: Session = Depends(get_db)) -> DocumentRead:
    document = find_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _to_read(document)


@router.post("/{document_id}/reindex", response_model=DocumentRead)
def reindex(
    document_id: str,
    db: Session = Depends(get_db),
    embedder: OpenAIEmbeddingService = Depends(get_embedding_service),
) -> DocumentRead:
    document = find_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        return _to_read(reindex_document(db, document, embedder))
    except (DocumentProcessingError, EmbeddingConfigurationError) as error:
        _raise_processing_error(error)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_one(document_id: str, db: Session = Depends(get_db)) -> Response:
    document = find_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        remove_document(db, document)
    except DocumentServiceError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search", response_model=list[DocumentSearchResult])
def search(
    payload: DocumentSearchRequest,
    db: Session = Depends(get_db),
    embedder: OpenAIEmbeddingService = Depends(get_embedding_service),
) -> list[DocumentSearchResult]:
    if get_profile(db, payload.profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    try:
        results = search_documents(
            db,
            payload.profile_id,
            payload.query,
            payload.limit,
            embedder,
        )
    except EmbeddingConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return [
        DocumentSearchResult(
            document_id=document.id,
            filename=document.filename,
            chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            score=score,
            metadata=chunk.chunk_metadata,
        )
        for chunk, document, score in results
    ]
