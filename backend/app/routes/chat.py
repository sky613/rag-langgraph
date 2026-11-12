from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.agent import runner
from app.database import get_db
from app.schemas import ChatRequest, WorkflowResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_202_ACCEPTED)
def start_chat(
    payload: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> WorkflowResponse:
    # 그래프는 백그라운드에서 실행되고, 클라이언트는 GET /api/workflows/{thread_id}로 진행 상태를 조회한다.
    run, graph_input = runner.start(db, payload)
    background_tasks.add_task(runner.execute, run.thread_id, graph_input)
    return runner.build_response(run)
