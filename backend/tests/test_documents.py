import io
from pathlib import Path

import pytest
from docx import Document as WordDocument
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.core.database import Base, get_db
from backend.app.documents.embedding_service import EmbeddingConfigurationError, get_embedding_service
from backend.app.documents.processor import DocumentProcessingError, detect_mime_type, extract_text
from backend.app.main import app


class FakeEmbeddingService:
    def embed_texts(self, texts):
        return [[1.0] + [0.0] * 1535 for _ in texts]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_embedding_service] = FakeEmbeddingService
    monkeypatch.setattr(get_settings(), "document_storage_path", str(tmp_path / "private-documents"))
    with TestClient(app) as test_client:
        test_client.app.state.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_format_validation_and_extraction_for_office_documents():
    pdf_writer = PdfWriter()
    pdf_page = pdf_writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = pdf_writer._add_object(font)
    pdf_page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Proof of approved use) Tj ET")
    pdf_page[NameObject("/Contents")] = pdf_writer._add_object(stream)
    pdf_buffer = io.BytesIO()
    pdf_writer.write(pdf_buffer)
    pdf_content = pdf_buffer.getvalue()
    assert detect_mime_type("proof.pdf", pdf_content, "application/pdf") == "application/pdf"
    assert "Proof of approved use" in extract_text("proof.pdf", pdf_content)

    word = WordDocument()
    word.add_paragraph("Authorized project background")
    word_buffer = io.BytesIO()
    word.save(word_buffer)
    docx_content = word_buffer.getvalue()
    assert detect_mime_type("background.docx", docx_content, None).endswith("wordprocessingml.document")
    assert "Authorized project background" in extract_text("background.docx", docx_content)

    workbook = Workbook()
    workbook.active.append(["topic", "value"])
    workbook.active.append(["experience", "community research"])
    xlsx_buffer = io.BytesIO()
    workbook.save(xlsx_buffer)
    xlsx_content = xlsx_buffer.getvalue()
    assert detect_mime_type("details.xlsx", xlsx_content, None).endswith("spreadsheetml.sheet")
    extracted = extract_text("details.xlsx", xlsx_content)
    assert "community research" in extracted

    with pytest.raises(DocumentProcessingError, match="does not match"):
        detect_mime_type("fake.pdf", b"not a PDF", "application/pdf")


def test_upload_search_and_delete_documents(client: TestClient, monkeypatch):
    profile_response = client.post("/api/v1/profiles", json={"name": "Test profile"})
    assert profile_response.status_code == 201
    profile_id = profile_response.json()["id"]

    invalid_response = client.post(
        "/api/v1/documents",
        data={"profile_id": profile_id},
        files={"file": ("bad.exe", b"binary", "application/octet-stream")},
    )
    assert invalid_response.status_code == 422

    response = client.post(
        "/api/v1/documents",
        data={"profile_id": profile_id},
        files={"file": ("notes.txt", b"Research background approved by the user.", "text/plain")},
    )
    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "indexed"
    assert document["chunk_count"] == 1
    document_id = document["id"]

    response = client.post(
        "/api/v1/documents/search",
        json={"profile_id": profile_id, "query": "research background", "limit": 5},
    )
    assert response.status_code == 200
    result = response.json()[0]
    assert result["document_id"] == document_id
    assert result["filename"] == "notes.txt"
    assert "Research background" in result["content"]

    monkeypatch.setattr(get_settings(), "document_chunk_size", 20)
    monkeypatch.setattr(get_settings(), "document_chunk_overlap", 5)
    response = client.post(f"/api/v1/documents/{document_id}/reindex")
    assert response.status_code == 200
    assert response.json()["status"] == "indexed"
    assert response.json()["chunk_count"] > 1

    stored_path = next(Path(get_settings().document_storage_path).rglob("source.txt"))
    response = client.delete(f"/api/v1/documents/{document_id}")
    assert response.status_code == 204
    assert not stored_path.exists()
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    from backend.app.documents.models import DocumentChunk

    with client.app.state.test_session() as db:
        assert db.query(DocumentChunk).count() == 0


def test_embedding_configuration_failure_is_reported_and_saved(client: TestClient):
    class UnconfiguredEmbeddingService:
        def embed_texts(self, texts):
            raise EmbeddingConfigurationError("Embedding provider is not configured")

    profile_id = client.post("/api/v1/profiles", json={"name": "Test profile"}).json()["id"]
    app.dependency_overrides[get_embedding_service] = UnconfiguredEmbeddingService

    response = client.post(
        "/api/v1/documents",
        data={"profile_id": profile_id},
        files={"file": ("notes.txt", b"Useful background.", "text/plain")},
    )
    assert response.status_code == 503

    documents = client.get("/api/v1/documents", params={"profile_id": profile_id}).json()
    assert len(documents) == 1
    assert documents[0]["status"] == "failed"
    assert documents[0]["error_message"] == "Embedding provider is not configured"


def test_chunker_respects_overlap_and_limits():
    from backend.app.documents.chunker import split_into_chunks

    chunks = split_into_chunks("one two three four five six", chunk_size=12, overlap=4)
    assert chunks == ["one two", "two three", "four five", "five six"]
    assert all(len(chunk) <= 12 for chunk in split_into_chunks("x" * 30, chunk_size=12, overlap=2))
