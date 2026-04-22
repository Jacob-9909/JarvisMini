"""Smart Office Life Agent ORM 모델.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    Boolean,
    JSON,
    Float,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    display_name = Column(String(64), nullable=True)

    gender = Column(String(16), nullable=True)
    age = Column(Integer, nullable=True)
    job_role = Column(String(32), nullable=True, comment="frontend/backend/ai/pm/data/infra/etc")
    dev_tendency = Column(String(32), nullable=True, comment="active/calm/explorer/pragmatic")

    company_lat = Column(Float, nullable=True)
    company_lng = Column(Float, nullable=True)
    company_address = Column(String(255), nullable=True)

    bus_stop_id = Column(String(32), nullable=True, comment="카카오버스 정류장 ID")
    bus_route_id = Column(String(32), nullable=True, comment="카카오버스 노선 ID")

    slack_channel_id = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pet = relationship(
        "PetProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    activity_logs = relationship(
        "ActivityLog", back_populates="user", cascade="all, delete-orphan"
    )


class PetProfile(Base):
    """펫 상태. 사용자 1:1."""

    __tablename__ = "pet_profile"
    __table_args__ = {"schema": "agent_state"}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    species = Column(
        String(32),
        default="egg",
        comment="fox / turtle / owl / dragon / egg ...",
    )
    nickname = Column(String(64), nullable=True)
    level = Column(Integer, default=1)
    exp = Column(Integer, default=0)
    mood = Column(
        String(16),
        default="neutral",
        comment="happy / neutral / tired / stressed / focused",
    )
    stress = Column(Integer, default=0, comment="0~100")
    last_fed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="pet")


class ActivityLog(Base):
    """System Monitor Node 가 주기적으로 남기는 PC 활동 스냅샷."""

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_user_ts", "user_id", "ts"),
        {"schema": "agent_state"},
    )

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    click_count = Column(Integer, default=0)
    key_count = Column(Integer, default=0)
    active_tabs = Column(Integer, default=0)
    cpu_percent = Column(Float, default=0.0)
    mem_percent = Column(Float, default=0.0)
    top_processes = Column(JSON, default=list, comment="상위 N개 프로세스 메타")
    screen_active_sec = Column(Integer, default=0)

    computed_exp_gain = Column(Integer, default=0)
    computed_stress_delta = Column(Integer, default=0)

    user = relationship("User", back_populates="activity_logs")


class NodeExecution(Base):
    """Graph Workflow 노드 단위 실행 로그 (성능 튜닝용)."""

    __tablename__ = "node_execution"
    __table_args__ = (
        Index("ix_node_execution_session", "session_id", "started_at"),
        {"schema": "workflow"},
    )

    id = Column(BigInteger, primary_key=True, index=True)
    session_id = Column(String(128), index=True, nullable=False)
    user_id = Column(Integer, nullable=True, index=True)
    node_name = Column(String(64), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    elapsed_ms = Column(Integer, default=0)
    route = Column(String(64), nullable=True)
    status = Column(String(16), default="ok")
    payload = Column(JSON, default=dict)


class MemoryContext(Base):
    """ADK 2.0 Memory 의 단기/장기 대화 컨텍스트."""

    __tablename__ = "memory_context"
    __table_args__ = {"schema": "workflow"}

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    kind = Column(String(16), default="short", comment="short / long")
    key = Column(String(128), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


# =============================================================================
#  ADK 2.0 Chat Agent 용 저장소
#  - AdkSession  : BaseSessionService 가 요구하는 (app_name, user_id, session_id) 튜플 저장
#  - AdkEvent    : 세션에 쌓이는 Event (LLM turn / tool call / tool result) 직렬화
#  - AdkMemoryEntry : MemoryService.search_memory 대상 — 사용자별 장기 기억
#
#  펫 챗봇이 sub_agents 로 라우팅된 히스토리 / 선호 메뉴 / 관심 버스 노선 등을
#  세션을 넘어 재사용하기 위한 테이블이다.
# =============================================================================
class AdkSession(Base):
    __tablename__ = "adk_sessions"
    __table_args__ = (
        Index("ix_adk_sessions_user", "app_name", "user_id", "last_update_time"),
        {"schema": "agent_state"},
    )

    id = Column(String(128), primary_key=True)   # session_id
    app_name = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    state = Column(JSON, default=dict, nullable=False)
    last_update_time = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AdkEvent(Base):
    __tablename__ = "adk_events"
    __table_args__ = (
        Index("ix_adk_events_session_ts", "session_id", "timestamp"),
        {"schema": "agent_state"},
    )

    id = Column(String(128), primary_key=True)
    session_id = Column(
        String(128),
        ForeignKey("agent_state.adk_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_name = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    author = Column(String(64), nullable=True)
    invocation_id = Column(String(64), nullable=True)
    branch = Column(String(128), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    payload = Column(JSON, default=dict, nullable=False, comment="Event 전체 직렬화")


class AdkMemoryEntry(Base):
    """펫이 세션을 넘어 기억해야 할 내용 (선호/습관/이전 결정 등)."""

    __tablename__ = "adk_memory_entries"
    __table_args__ = (
        Index("ix_adk_memory_user", "app_name", "user_id", "timestamp"),
        {"schema": "agent_state"},
    )

    id = Column(String(64), primary_key=True)  # uuid4
    app_name = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    author = Column(String(64), nullable=True)
    session_id = Column(String(128), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    content_text = Column(Text, nullable=False, comment="검색용 평문 (ILIKE/pg_trgm)")
    content_raw = Column(JSON, default=dict, comment="원본 content (parts 포함)")
    custom_metadata = Column(JSON, default=dict)
