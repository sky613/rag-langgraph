import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    # Chroma 검색 결과. {id, document_id, filename, chunk_index, page, content, score}
    retrieved_documents: list[dict[str, Any]]
    answer: str
    # {"valid": bool, "reason": str | None, "cited": list[int]}
    validation_result: dict[str, Any] | None
    retry_count: int
    error: str | None
    # 답변에서 실제로 인용된 검색 결과만 담는다.
    source_documents: list[dict[str, Any]]
    require_approval: bool
    approval_status: str | None
    approval_comment: str | None
    # 각 node가 자신의 측정값을 append한다. reducer로 합쳐지므로 node는 이전 값을 읽지 않는다.
    metrics: Annotated[list[dict[str, Any]], operator.add]
