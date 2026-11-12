from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowMode = Literal["basic", "advanced"]


class DocumentResponse(BaseModel):
    id: str
    filename: str
    size_bytes: int
    chunk_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: WorkflowMode = "basic"
    # Advanced 모드에서만 의미가 있다. 최종 답변 공개 전에 사람의 승인을 받는다.
    require_approval: bool = False
    # 클라이언트가 지정하면 idempotency key로 동작한다. 이미 존재하면 409를 반환한다.
    thread_id: str | None = Field(default=None, min_length=1, max_length=64)


class ResumeRequest(BaseModel):
    # awaiting_approval 상태에서는 필수다. 실패/중단 상태의 재개에는 사용하지 않는다.
    approved: bool | None = None
    comment: str | None = Field(default=None, max_length=2000)


class WorkflowMetrics(BaseModel):
    node_timings: list[dict[str, Any]]
    total_duration_ms: float
    retrieval_latency_ms: float
    llm_latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class WorkflowResponse(BaseModel):
    thread_id: str
    mode: WorkflowMode
    question: str
    require_approval: bool
    status: str
    current_node: str | None
    next_nodes: list[str]
    failure_category: str | None
    error: str | None
    # 승인 대기/거절 상태에서는 공개되지 않는다. 초안은 pending_approval에 담긴다.
    answer: str | None
    source_documents: list[dict[str, Any]]
    retry_count: int
    validation_result: dict[str, Any] | None
    approval_status: str | None
    pending_approval: dict[str, Any] | None
    metrics: WorkflowMetrics
    created_at: datetime
    updated_at: datetime
