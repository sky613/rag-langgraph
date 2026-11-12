# Architecture

```text
React + TypeScript (Vite)
  │  REST + polling (1s)
  ▼
FastAPI ── routes/documents.py ── services/ingestion.py ── services/llm.py (OpenAI embeddings)
   │                                        └──────────── services/vector_store.py (ChromaDB)
   ├── routes/chat.py / workflows.py
   ▼
agent/runner.py   (claim → background execute → finalize, WorkflowRun in SQLite)
   ▼
agent/graph.py    (StateGraph: basic / advanced)
   ├── nodes.retrieve            → llm.embed + vector_store.query
   ├── nodes.check_retrieval     (advanced) deterministic score threshold
   ├── nodes.insufficient_context(advanced) fixed answer, no LLM call
   ├── nodes.generate            → llm.chat
   ├── nodes.validate_answer     (advanced) deterministic citation rules
   └── nodes.human_approval      (advanced, optional) interrupt()
   ▼
SqliteSaver (data/checkpoints.sqlite)
```

Graph orchestration (`app/agent`) only calls service functions; ingestion, retrieval and LLM access live in `app/services`. Nodes return partial state updates and never mutate the incoming state. `metrics` uses an `operator.add` reducer, so every node appends its own measurements.

## Graphs

**Basic** (benchmark mode, deterministic path): `START → retrieve → generate → END`. No validation, retry or approval, so it is directly comparable with a plain Python or LangChain retrieve-then-generate pipeline.

**Advanced**:

```text
START → retrieve → check_retrieval ─┬─ insufficient → insufficient_context → END
                                    └─ sufficient → generate → validate_answer
validate_answer ─┬─ valid & require_approval → human_approval → END
                 ├─ valid                     → END
                 ├─ invalid & retry_count ≤ MAX_RETRIES → generate (retry)
                 └─ invalid & retry_count > MAX_RETRIES → END (status=failed, validation_failed)
```

- Retrieval sufficiency: best cosine similarity ≥ `MIN_RELEVANCE_SCORE`.
- Validation (no LLM call): answer not empty, at least one `[n]` citation, every citation within `1..len(retrieved_documents)`.
- The loop is bounded because `validate_answer` increments `retry_count` and sets `error` once it exceeds `MAX_RETRIES`; the router then exits to `END`.
- On retry, the previous validation reason is added to the prompt.

## Workflow status

| status | meaning |
|---|---|
| running | background execution in progress (`current_node` = node being executed) |
| awaiting_approval | paused at `interrupt()` in `human_approval` |
| completed | answer published |
| insufficient_context | retrieval below threshold, fixed answer published |
| rejected | reviewer rejected the draft; answer not published |
| failed | node raised (`retrieval_error`, `llm_error`, `internal_error`) or validation retries exhausted (`validation_failed`) |
| interrupted | server stopped while running (`process_interrupted`) |

Answers are only returned in `answer` for `completed` / `insufficient_context`. While awaiting approval, the draft is exposed only via `pending_approval`.

## Checkpointing and recovery

- Checkpointer: `SqliteSaver` at `data/checkpoints.sqlite`; `thread_id` identifies a workflow.
- Execution uses `durability="sync"`: a checkpoint is persisted after every node (super-step) before the next one starts. **Checkpoint boundary = node boundary.**
- `GET /api/workflows/{thread_id}` reads `graph.get_state()` (values, `next`, pending interrupts) plus the `WorkflowRun` row.
- Resume:
  - `awaiting_approval` → `Command(resume={"approved": bool, "comment": str})`. Only `approved: true` approves; anything else is a rejection. Nothing is auto-approved.
  - `failed` / `interrupted` with remaining `next` nodes → `invoke(None)` continues from the last checkpoint. `failed` with `validation_failed` has no remaining nodes and cannot be resumed.
- On startup, rows left in `running` are marked `interrupted` so they can be resumed.

### Retry safety / side effects

- A node that fails or is interrupted mid-execution is **re-run from its beginning** on resume. Work done inside it before the failure is not checkpointed.
- `generate` calls the OpenAI API. Re-running it is safe (no external state is changed) but the tokens of the lost call are billed again and are not reflected in metrics.
- `human_approval` is re-executed from the start when resumed; code before `interrupt()` has no side effects.
- Document ingestion is **outside** the graph and is not checkpointed. If vectors were written but the metadata commit fails, the vectors are deleted; if the process dies between those two steps, orphan vectors may remain. This is not recovered automatically.

### Duplicate execution prevention

- `POST /api/chat` with an existing `thread_id` → 409.
- Resume claims the run with a conditional `UPDATE ... WHERE status = <expected>`; concurrent resumes get 409. Resuming a `running` / terminal workflow → 409.
- Duplicate documents are detected by SHA-256 of the file content (unique constraint) → 409.

## Observability

Per node (`metrics` in graph state): `duration_ms`, plus `retrieval_latency_ms` (query embedding + vector search), `llm_latency_ms`, `input_tokens`, `output_tokens`, `cost_usd`. The API aggregates them and adds overall execution time (`WorkflowRun.duration_ms`, summed across runs and resumes), `retry_count`, `failure_category` and `status`. Cost is estimated from the per-1M-token prices in settings.

## Storage

| file | contents |
|---|---|
| `data/metadata.sqlite` | `documents`, `workflow_runs` |
| `data/chroma/` | chunk text, embeddings, metadata (`document_id`, `filename`, `chunk_index`, `page`) |
| `data/checkpoints.sqlite` | LangGraph checkpoints |
