"""LangGraph node 함수들.

각 node는 state를 직접 수정하지 않고 변경할 key만 dict로 반환한다.
외부 의존성(llm, vector_store)은 모듈 함수로 호출하므로 테스트에서 monkeypatch로 대체할 수 있다.
"""

import re
import time
from collections.abc import Callable
from typing import Any

from langgraph.types import interrupt

from app.agent.state import AgentState
from app.core.config import settings
from app.services import llm, vector_store

INSUFFICIENT_CONTEXT_ANSWER = "업로드된 문서에서 질문에 답할 수 있는 충분한 근거를 찾지 못했습니다."

SYSTEM_PROMPT = (
    "You answer questions using only the provided context passages.\n"
    "Cite every factual statement with the passage number in square brackets, e.g. [1] or [2][3].\n"
    "If the context does not contain the answer, say so explicitly and still cite the closest passage.\n"
    "Answer in the same language as the question."
)

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def timed(name: str, fn: Callable[[AgentState], dict[str, Any]]) -> Callable[[AgentState], dict[str, Any]]:
    # node 실행 시간을 metrics 항목에 기록한다. interrupt 예외는 그대로 전파된다.
    def wrapper(state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        update = fn(state)
        duration_ms = (time.perf_counter() - started) * 1000
        entries = update.get("metrics") or [{}]
        entries[0] = {"node": name, **entries[0], "duration_ms": round(duration_ms, 2)}
        return {**update, "metrics": entries}

    return wrapper


def cited_indices(answer: str) -> list[int]:
    return sorted({int(match) for match in _CITATION_PATTERN.findall(answer)})


def retrieve(state: AgentState) -> dict[str, Any]:
    embedding = llm.embed([state["question"]])
    started = time.perf_counter()
    hits = vector_store.query(embedding.vectors[0], settings.retrieval_top_k)
    search_ms = (time.perf_counter() - started) * 1000
    return {
        "retrieved_documents": hits,
        "metrics": [
            {
                # 검색 지연시간은 query embedding + vector search를 합친 값이다.
                "retrieval_latency_ms": round(embedding.latency_ms + search_ms, 2),
                "input_tokens": embedding.input_tokens,
                "cost_usd": embedding.cost_usd,
            }
        ],
    }


def check_retrieval(state: AgentState) -> dict[str, Any]:
    # 결정적 규칙: 하나 이상의 chunk가 min_relevance_score 이상이어야 충분하다고 본다.
    best = max((doc["score"] for doc in state.get("retrieved_documents", [])), default=0.0)
    sufficient = best >= settings.min_relevance_score
    return {"error": None if sufficient else "insufficient_context", "metrics": [{"best_score": best}]}


def route_after_check(state: AgentState) -> str:
    return "insufficient_context" if state.get("error") == "insufficient_context" else "generate"


def insufficient_context(state: AgentState) -> dict[str, Any]:
    # LLM을 호출하지 않고 고정 응답을 반환해 근거 없는 답변 생성을 막는다.
    return {"answer": INSUFFICIENT_CONTEXT_ANSWER, "source_documents": []}


def build_user_prompt(state: AgentState) -> str:
    passages = "\n\n".join(
        f"[{index}] (source: {doc['filename']}"
        + (f", page {doc['page']}" if doc.get("page") else "")
        + f")\n{doc['content']}"
        for index, doc in enumerate(state.get("retrieved_documents", []), start=1)
    )
    prompt = f"Context passages:\n{passages}\n\nQuestion: {state['question']}"
    previous = state.get("validation_result")
    if previous and not previous.get("valid"):
        # 재시도 시에는 직전 검증 실패 사유를 알려 같은 실수를 반복하지 않게 한다.
        prompt += (
            f"\n\nYour previous answer was rejected by validation: {previous.get('reason')}. "
            f"Only cite passage numbers between 1 and {len(state.get('retrieved_documents', []))}."
        )
    return prompt


def generate(state: AgentState) -> dict[str, Any]:
    result = llm.chat(SYSTEM_PROMPT, build_user_prompt(state))
    docs = state.get("retrieved_documents", [])
    cited = [docs[i - 1] for i in cited_indices(result.text) if 1 <= i <= len(docs)]
    return {
        "answer": result.text,
        "source_documents": cited,
        "metrics": [
            {
                "llm_latency_ms": round(result.latency_ms, 2),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
            }
        ],
    }


def validate_answer(state: AgentState) -> dict[str, Any]:
    # 추가 LLM 호출 없이 결정적 규칙으로 검증한다.
    answer = (state.get("answer") or "").strip()
    doc_count = len(state.get("retrieved_documents", []))
    cited = cited_indices(answer)

    reason = None
    if not answer:
        reason = "empty_answer"
    elif not cited:
        reason = "missing_citation"
    elif any(index < 1 or index > doc_count for index in cited):
        reason = "invalid_citation"

    update: dict[str, Any] = {"validation_result": {"valid": reason is None, "reason": reason, "cited": cited}}
    if reason is not None:
        retry_count = state.get("retry_count", 0) + 1
        update["retry_count"] = retry_count
        if retry_count > settings.max_retries:
            update["error"] = f"validation_failed: {reason}"
    return update


def route_after_validate(state: AgentState) -> str:
    result = state.get("validation_result") or {}
    if not result.get("valid"):
        # validate_answer가 최대 재시도 초과 시 error를 설정하므로 루프가 반드시 종료된다.
        return "end" if state.get("error") else "generate"
    return "human_approval" if state.get("require_approval") else "end"


def human_approval(state: AgentState) -> dict[str, Any]:
    # resume 시 이 node는 처음부터 다시 실행된다. interrupt 이전 코드는 부작용이 없어야 한다.
    decision = interrupt(
        {
            "type": "answer_approval",
            "question": state["question"],
            "draft_answer": state.get("answer"),
            "source_documents": state.get("source_documents", []),
        }
    )
    # 명시적으로 approved=True인 경우에만 승인한다. 그 외 값은 모두 거절로 처리한다.
    approved = isinstance(decision, dict) and decision.get("approved") is True
    return {
        "approval_status": "approved" if approved else "rejected",
        "approval_comment": decision.get("comment") if isinstance(decision, dict) else None,
    }
