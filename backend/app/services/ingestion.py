import hashlib
import io
from pathlib import Path

from fastapi import HTTPException, status
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document, new_id
from app.services import llm, vector_store

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}


def parse(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    # (page 번호, 텍스트) 목록을 반환한다. PDF가 아니면 page는 None이다.
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported file type: {extension or 'none'}. Use PDF, TXT or Markdown.",
        )
    if extension == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            return [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
        except Exception as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Failed to parse PDF: {exc}") from exc
    return [(None, data.decode("utf-8", errors="replace"))]


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    # shortcut: 문자 수 기준 고정 크기 chunking, 품질 이슈가 생기면 문단/토큰 기반 splitter로 교체한다.
    text = text.strip()
    step = size - overlap
    return [chunk for start in range(0, len(text), step) if (chunk := text[start : start + size].strip())]


def ingest(db: Session, filename: str, data: bytes) -> Document:
    content_hash = hashlib.sha256(data).hexdigest()
    if db.scalar(select(Document).where(Document.content_hash == content_hash)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Document with identical content already exists")

    chunks: list[tuple[int | None, str]] = [
        (page, chunk)
        for page, text in parse(filename, data)
        for chunk in chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    ]
    if not chunks:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Document contains no extractable text")

    document_id = new_id()
    texts = [text for _, text in chunks]
    embeddings = llm.embed(texts).vectors
    vector_store.add_chunks(
        ids=[f"{document_id}:{index}" for index in range(len(chunks))],
        embeddings=embeddings,
        texts=texts,
        metadatas=[
            {
                "document_id": document_id,
                "filename": filename,
                "chunk_index": index,
                # Chroma metadata는 None을 허용하지 않으므로 page 없음은 -1로 저장한다.
                "page": page if page is not None else -1,
            }
            for index, (page, _) in enumerate(chunks)
        ],
    )

    document = Document(
        id=document_id,
        filename=filename,
        content_hash=content_hash,
        size_bytes=len(data),
        chunk_count=len(chunks),
    )
    db.add(document)
    try:
        db.commit()
    except Exception as exc:
        # 메타데이터 저장 실패 시 이미 들어간 vector를 정리해 고아 chunk가 남지 않게 한다.
        db.rollback()
        vector_store.delete_document(document_id)
        if isinstance(exc, IntegrityError):
            raise HTTPException(status.HTTP_409_CONFLICT, "Document with identical content already exists") from exc
        raise
    db.refresh(document)
    return document


def list_documents(db: Session) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.created_at.desc())).all())


def delete_document(db: Session, document_id: str) -> None:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    # vector를 먼저 지운다. 실패하면 메타데이터가 남아 재시도로 다시 삭제할 수 있다.
    vector_store.delete_document(document_id)
    db.delete(document)
    db.commit()
