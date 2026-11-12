from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # 모든 값은 환경변수 또는 backend/.env에서 덮어쓸 수 있다.
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # 비용 추정용 단가(USD / 1M tokens). 모델을 바꾸면 함께 갱신한다.
    chat_input_cost_per_1m: float = 0.15
    chat_output_cost_per_1m: float = 0.60
    embedding_cost_per_1m: float = 0.02

    # 메타데이터 DB, ChromaDB, LangGraph checkpoint 파일이 저장되는 위치다.
    data_dir: Path = BACKEND_DIR / "data"

    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_upload_bytes: int = 20 * 1024 * 1024

    retrieval_top_k: int = 4
    # Advanced 모드에서 검색 결과가 충분한지 판단하는 cosine similarity 하한값이다.
    min_relevance_score: float = 0.3
    # Advanced 모드에서 검증 실패 시 재생성 최대 횟수다. 무한 루프를 막는다.
    max_retries: int = 2

    cors_origins: list[str] = ["http://localhost:5173"]

    # 이전 버전의 .env 키(GEMINI_* 등)가 남아 있어도 시작이 실패하지 않도록 무시한다.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def metadata_db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'metadata.sqlite'}"

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_dir / "checkpoints.sqlite"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
