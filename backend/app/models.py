import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    # DB에 저장되는 시간은 timezone-aware UTC datetime으로 통일한다.
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Document(Base):
    # 업로드된 문서의 메타데이터다. 실제 chunk와 embedding은 ChromaDB에 저장된다.
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # 같은 내용의 파일이 중복 인덱싱되지 않도록 SHA-256 해시에 unique 제약을 둔다.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class WorkflowRun(Base):
    # LangGraph thread 하나의 실행 상태 요약이다. 그래프 state 자체는 checkpointer가 저장한다.
    __tablename__ = "workflow_runs"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # running | awaiting_approval | completed | insufficient_context | rejected | failed | interrupted
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 모든 실행(최초 실행 + resume)의 wall-clock 시간 합계다.
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
