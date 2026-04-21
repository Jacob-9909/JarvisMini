from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from src.schema.state import UserContext, PetStatus


class ChatWorkflowInput(BaseModel):
    """채팅 워크플로우 진입 시 입력 데이터."""
    user_id: int
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ChatRouteInput(BaseModel):
    """라우터 노드에서 결정된 경로 정보를 포함한 데이터."""
    user_id: int
    message: str
    route: str


class ChatInit(BaseModel):
    """채팅 초기화 단계의 결과물 (사용자/펫 정보 포함)."""
    user: UserContext
    pet: PetStatus
    message: str
    intent: str


class ChatBundle(BaseModel):
    """도메인 노드 간 전달되는 채팅 데이터 묶음."""
    user: UserContext
    pet: PetStatus
    message: str
    intent: str
    response_text: str = ""
    pending_exp: int = 0
    pending_stress: int = 0
    source: str = "chat"


class AgentOutput(BaseModel):
    """서브에이전트 실행 후 후처리 파이프라인에 전달되는 구조화된 데이터."""
    user_id: int = 0
    route: str = ""
    original_message: str = ""
    agent_response: str = ""
    pending_exp: int = 0
    pending_stress: int = 0
