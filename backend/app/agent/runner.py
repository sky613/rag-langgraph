"""그래프 실행, 재개, 상태 조회를 담당한다.

API 요청 스레드는 실행 권한만 확보(claim)하고, 실제 그래프 실행은 백그라운드에서 수행한다.
WorkflowRun.status를 조건부 UPDATE로 변경해 같은 thread의 중복 실행을 막는다.
"""

import time
import uuid
from typing import Any

from fastapi import HTTPException, status
from langgraph.types import Command, StateSnapshot
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.graph import get_graph
from app.database import SessionLocal
from app.models import WorkflowRun
from app.schemas import ChatRequest, ResumeRequest, WorkflowMetrics, WorkflowResponse

# 실패한 node 이름으로 실패 유형을 분류한다.
FAILURE_BY_NODE = {
    "retrieve": "retrieval_error",
    "generate": "llm_error",
}
# 그래프 결과가 사용자에게 공개되는 상태다. 승인 대기/거절/검증 실패 답변은 공개하지 않는다.
PUBLISHED_STATUSES = {"completed", "insufficient_context"}


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def get_run_or_404(db: Session, thread_id: str) -> WorkflowRun:
    run = db.get(WorkflowRun, thread_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found")
    return run


def start(db: Session, request: ChatRequest) -> tuple[WorkflowRun, dict[str, Any]]:
    run = WorkflowRun(
        thread_id=request.thread_id or str(uuid.uuid4()),
        mode=request.mode,
        question=request.question,
        # Basic 모드는 결정적 벤치마크 경로이므로 승인 단계를 두지 않는다.
        require_approval=request.require_approval and request.mode == "advanced",
        status="running",
        current_node="retrieve",
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow with this thread_id already exists") from exc
    db.refresh(run)

    graph_input = {
        "question": run.question,
        "require_approval": run.require_approval,
        "retry_count": 0,
        "error": None,
        "approval_status": None,
        "metrics": [],
    }
    return run, graph_input


def claim_resume(db: Session, thread_id: str, request: ResumeRequest) -> Command | None:
    run = get_run_or_404(db, thread_id)
    snapshot = get_graph(run.mode).get_state(_config(thread_id))

    if run.status == "awaiting_approval":
        if request.approved is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "'approved' is required to resume an approval")
        graph_input: Command | None = Command(resume={"approved": request.approved, "comment": request.comment})
    elif run.status in ("failed", "interrupted") and snapshot.next:
        # 마지막 checkpoint부터 남은 node를 다시 실행한다. 실패한 node는 처음부터 재실행된다.
        graph_input = None
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Workflow in status '{run.status}' cannot be resumed")

    # 조건부 UPDATE로 실행 권한을 원자적으로 확보한다. 동시 resume 요청 중 하나만 성공한다.
    result = db.execute(
        update(WorkflowRun)
        .where(WorkflowRun.thread_id == thread_id, WorkflowRun.status == run.status)
        .values(status="running", current_node=snapshot.next[0] if snapshot.next else None,
                failure_category=None, error=None)
    )
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow is already being resumed")
    return graph_input


def execute(thread_id: str, graph_input: dict[str, Any] | Command | None) -> None:
    # 백그라운드 작업에서 호출된다. 요청 스레드의 DB 세션을 공유하지 않는다.
    db = SessionLocal()
    try:
        run = db.get(WorkflowRun, thread_id)
        graph = get_graph(run.mode)
        config = _config(thread_id)
        started = time.perf_counter()
        try:
            # durability="sync": 각 node 완료 후 다음 단계 전에 checkpoint가 저장된다.
            for _ in graph.stream(graph_input, config, stream_mode="updates", durability="sync"):
                next_nodes = graph.get_state(config).next
                run.current_node = next_nodes[0] if next_nodes else None
                db.commit()
        except Exception as exc:
            run.status = "failed"
            run.failure_category = FAILURE_BY_NODE.get(run.current_node or "", "internal_error")
            run.error = str(getattr(exc, "detail", exc))
        else:
            _finalize(run, graph.get_state(config))
        run.duration_ms += (time.perf_counter() - started) * 1000
        db.commit()
    finally:
        db.close()


def _finalize(run: WorkflowRun, snapshot: StateSnapshot) -> None:
    values = snapshot.values
    error = values.get("error")
    run.current_node = None
    run.failure_category = None
    run.error = None
    if snapshot.interrupts:
        run.status = "awaiting_approval"
        run.current_node = "human_approval"
    elif snapshot.next:
        run.status = "interrupted"
        run.current_node = snapshot.next[0]
    elif values.get("approval_status") == "rejected":
        run.status = "rejected"
        run.failure_category = "rejected"
    elif error == "insufficient_context":
        run.status = "insufficient_context"
        run.failure_category = "insufficient_context"
    elif error:
        run.status = "failed"
        run.failure_category = "validation_failed"
        run.error = error
    else:
        run.status = "completed"


def mark_stale_runs_interrupted() -> None:
    # 서버가 실행 도중 종료되면 running 상태가 남는다. 재시작 시 resume 가능한 상태로 바꾼다.
    db = SessionLocal()
    try:
        db.execute(
            update(WorkflowRun)
            .where(WorkflowRun.status == "running")
            .values(
                status="interrupted",
                failure_category="process_interrupted",
                error="Server stopped during execution. Resume to continue from the last checkpoint.",
            )
        )
        db.commit()
    finally:
        db.close()


def build_response(run: WorkflowRun) -> WorkflowResponse:
    snapshot = get_graph(run.mode).get_state(_config(run.thread_id))
    values = snapshot.values
    entries = values.get("metrics", [])
    published = run.status in PUBLISHED_STATUSES

    return WorkflowResponse(
        thread_id=run.thread_id,
        mode=run.mode,
        question=run.question,
        require_approval=run.require_approval,
        status=run.status,
        current_node=run.current_node,
        next_nodes=list(snapshot.next),
        failure_category=run.failure_category,
        error=run.error,
        answer=values.get("answer") if published else None,
        source_documents=values.get("source_documents", []) if published else [],
        retry_count=values.get("retry_count", 0),
        validation_result=values.get("validation_result"),
        approval_status=values.get("approval_status"),
        pending_approval=snapshot.interrupts[0].value if snapshot.interrupts else None,
        metrics=WorkflowMetrics(
            node_timings=[{"node": e["node"], "duration_ms": e["duration_ms"]} for e in entries],
            total_duration_ms=round(run.duration_ms, 2),
            retrieval_latency_ms=round(sum(e.get("retrieval_latency_ms", 0) for e in entries), 2),
            llm_latency_ms=round(sum(e.get("llm_latency_ms", 0) for e in entries), 2),
            input_tokens=sum(e.get("input_tokens", 0) for e in entries),
            output_tokens=sum(e.get("output_tokens", 0) for e in entries),
            estimated_cost_usd=round(sum(e.get("cost_usd", 0) for e in entries), 6),
        ),
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
