"""DB 세션 & 초기화.

auth / agent_state / workflow 세 개의 스키마를 분리 운용하며
`init_db()` 호출 시 스키마와 테이블을 모두 보장한다.
"""

from __future__ import annotations

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

POSTGRES_USER = os.getenv("POSTGRES_USER", "officeuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "officepass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "smart_office_db")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

SCHEMAS = ("auth", "agent_state", "workflow")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def _ensure_schemas() -> None:
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        # ILIKE 검색(메모리 서비스) 가속. 권한 없으면 조용히 패스.
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception as e:  # noqa: BLE001
            logger.debug("pg_trgm unavailable: %s", e)


def _ensure_trgm_index() -> None:
    """adk_memory_entries.content_text 에 trigram GIN 인덱스 생성."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_adk_memory_content_trgm "
                    "ON agent_state.adk_memory_entries "
                    "USING GIN (content_text gin_trgm_ops)"
                )
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("trgm index skipped: %s", e)


def init_db() -> None:
    """스키마 + 테이블을 모두 보장. 초기 부트스트랩에서 한 번 호출."""
    from src.db.models import Base

    _ensure_schemas()
    Base.metadata.create_all(bind=engine)
    _ensure_trgm_index()
    logger.info("DB initialized (schemas: %s)", ", ".join(SCHEMAS))
