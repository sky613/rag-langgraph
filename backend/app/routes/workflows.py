from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.agent import runner
from app.database import get_db
from app.schemas import ResumeRequest, WorkflowResponse

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("/{thread_id}", response_model=WorkflowResponse)
def get_workflow(thread_id: str, db: Session = Depends(get_db)) -> WorkflowResponse:
    return runner.build_response(runner.get_run_or_404(db, thread_id))


@router.post("/{thread_id}/resume", response_model=WorkflowResponse, status_code=status.HTTP_202_ACCEPTED)
def resume_workflow(
    thread_id: str,
    payload: ResumeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> WorkflowResponse:
    graph_input = runner.claim_resume(db, thread_id, payload)
    background_tasks.add_task(runner.execute, thread_id, graph_input)
    run = runner.get_run_or_404(db, thread_id)
    db.refresh(run)
    return runner.build_response(run)
