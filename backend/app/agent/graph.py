import sqlite3
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent import nodes
from app.agent.state import AgentState
from app.core.config import settings


def build_basic_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    # 결정적 RAG: START -> retrieve -> generate -> END. 순수 Python/LangChain 구현과 비교 가능한 형태다.
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", nodes.timed("retrieve", nodes.retrieve))
    graph.add_node("generate", nodes.timed("generate", nodes.generate))
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile(checkpointer=checkpointer)


def build_advanced_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", nodes.timed("retrieve", nodes.retrieve))
    graph.add_node("check_retrieval", nodes.timed("check_retrieval", nodes.check_retrieval))
    graph.add_node("insufficient_context", nodes.timed("insufficient_context", nodes.insufficient_context))
    graph.add_node("generate", nodes.timed("generate", nodes.generate))
    graph.add_node("validate_answer", nodes.timed("validate_answer", nodes.validate_answer))
    graph.add_node("human_approval", nodes.timed("human_approval", nodes.human_approval))

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "check_retrieval")
    graph.add_conditional_edges(
        "check_retrieval",
        nodes.route_after_check,
        {"generate": "generate", "insufficient_context": "insufficient_context"},
    )
    graph.add_edge("insufficient_context", END)
    graph.add_edge("generate", "validate_answer")
    graph.add_conditional_edges(
        "validate_answer",
        nodes.route_after_validate,
        {"generate": "generate", "human_approval": "human_approval", "end": END},
    )
    graph.add_edge("human_approval", END)
    return graph.compile(checkpointer=checkpointer)


@lru_cache
def get_checkpointer() -> SqliteSaver:
    # FastAPI threadpool과 백그라운드 작업에서 공유하므로 check_same_thread를 끈다. SqliteSaver가 내부 lock을 사용한다.
    conn = sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False)
    return SqliteSaver(conn)


@lru_cache
def get_graph(mode: str) -> CompiledStateGraph:
    builder = build_advanced_graph if mode == "advanced" else build_basic_graph
    return builder(get_checkpointer())
