from functools import lru_cache

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import settings

COLLECTION_NAME = "documents"


@lru_cache
def get_collection() -> Collection:
    client = chromadb.PersistentClient(
        path=str(settings.chroma_dir),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    # embedding은 OpenAI로 직접 계산해 넣으므로 Chroma 기본 embedding function은 쓰지 않는다.
    return client.get_or_create_collection(
        COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,
    )


def add_chunks(
    ids: list[str],
    embeddings: list[list[float]],
    texts: list[str],
    metadatas: list[dict],
) -> None:
    get_collection().add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def delete_document(document_id: str) -> None:
    get_collection().delete(where={"document_id": document_id})


def query(embedding: list[float], top_k: int) -> list[dict]:
    result = get_collection().query(
        query_embeddings=[embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for chunk_id, text, metadata, distance in zip(
        result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        page = metadata.get("page", -1)
        hits.append(
            {
                "id": chunk_id,
                "document_id": metadata["document_id"],
                "filename": metadata["filename"],
                "chunk_index": metadata["chunk_index"],
                "page": page if page >= 0 else None,
                "content": text,
                # cosine distance를 사람이 읽기 쉬운 similarity로 변환한다.
                "score": round(1 - distance, 4),
            }
        )
    return hits
