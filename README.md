# rag-langgraph

LangGraph 기반 Stateful 문서 RAG Agent입니다. 문서(PDF/TXT/Markdown)를 업로드해 ChromaDB에 인덱싱하고, 두 가지 워크플로로 질문에 답합니다.

- **basic**: `retrieve → generate` (결정적, 벤치마크용)
- **advanced**: 검색 충분성 검사, 결정적 답변 검증, 최대 재시도, 선택적 Human Approval

설계 상세(그래프, checkpoint 경계, 재개/재시도 안전성)는 [docs/architecture.md](docs/architecture.md)를 참고하세요.

## 기술 스택

- Frontend: React, TypeScript, Vite, Tailwind CSS, react-markdown, lucide-react
- Backend: Python 3.11+, FastAPI, LangGraph, langgraph-checkpoint-sqlite, OpenAI SDK, ChromaDB, SQLAlchemy(SQLite), pypdf

## 환경변수

`backend/.env.example`을 `backend/.env`로 복사하고 `OPENAI_API_KEY`를 설정합니다. API Key는 백엔드에서만 사용하며 프론트엔드나 `VITE_*` 변수에 넣지 않습니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| OPENAI_API_KEY | – | 필수 |
| OPENAI_CHAT_MODEL | gpt-4o-mini | 답변 생성 모델 |
| OPENAI_EMBEDDING_MODEL | text-embedding-3-small | 임베딩 모델 |
| CHAT_INPUT_COST_PER_1M / CHAT_OUTPUT_COST_PER_1M / EMBEDDING_COST_PER_1M | 0.15 / 0.60 / 0.02 | 비용 추정 단가(USD) |
| RETRIEVAL_TOP_K | 4 | 검색 chunk 수 |
| MIN_RELEVANCE_SCORE | 0.3 | advanced 검색 충분성 기준 (cosine similarity) |
| MAX_RETRIES | 2 | advanced 검증 실패 시 최대 재생성 횟수 |
| CHUNK_SIZE / CHUNK_OVERLAP | 1000 / 200 | 문자 기준 chunking |
| DATA_DIR | backend/data | SQLite, ChromaDB, checkpoint 저장 위치 |

## 실행

Docker:

```bash
docker compose up --build
```

로컬:

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

cd frontend
pnpm install
pnpm dev
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000 (API 문서: `/docs`)

## API

| Method | Path | 설명 |
|---|---|---|
| POST | /api/documents | multipart `file` 업로드. 동일 내용 중복 시 409, 미지원 형식 415 |
| GET | /api/documents | 문서 목록 |
| DELETE | /api/documents/{id} | 문서 및 vector 삭제 |
| POST | /api/chat | `{question, mode: "basic"\|"advanced", require_approval, thread_id?}` → 202, 백그라운드 실행 |
| GET | /api/workflows/{thread_id} | 상태, 현재 node, 답변, 출처, 재시도, 메트릭 |
| POST | /api/workflows/{thread_id}/resume | 승인 대기: `{approved, comment?}` / 실패·중단: `{}` (마지막 checkpoint부터 재개) |
| GET | /api/health | 헬스 체크 |

## 제한사항

- 테스트 코드는 포함되어 있지 않습니다.
- 실행 상태는 polling으로 갱신합니다(스트리밍 없음).
- 워크플로는 FastAPI BackgroundTasks로 같은 프로세스에서 실행됩니다. 단일 프로세스(worker 1개) 기준입니다.
- 실패한 node는 resume 시 처음부터 재실행되며, 이때 중복 LLM 호출 비용이 발생할 수 있습니다.
- 문서 인덱싱은 그래프 밖에서 수행되며 checkpoint 대상이 아닙니다.
- chunking은 문자 수 기준입니다.
# rag-langgraph
