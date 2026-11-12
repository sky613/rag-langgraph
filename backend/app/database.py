from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# 백그라운드 워크플로 스레드에서도 사용하므로 check_same_thread를 끈다.
engine = create_engine(settings.metadata_db_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    # 모든 SQLAlchemy 모델이 상속하는 공통 Base 클래스다.
    pass


def get_db() -> Generator[Session, None, None]:
    # FastAPI dependency: 요청마다 DB 세션을 열고 응답 후 반드시 닫는다.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
