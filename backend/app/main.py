from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.runner import mark_stale_runs_interrupted
from app.core.config import settings
from app.database import Base, engine
from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.workflows import router as workflows_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # MVP에서는 Alembic 대신 앱 시작 시 테이블을 자동 생성한다.
    Base.metadata.create_all(bind=engine)
    mark_stale_runs_interrupted()
    yield


app = FastAPI(title="rag-langgraph API", lifespan=lifespan)

# 프론트엔드 개발 서버에서 백엔드 API를 호출할 수 있도록 CORS를 설정한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(workflows_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
