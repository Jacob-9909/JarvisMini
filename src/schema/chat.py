from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel, Field


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


class AgentOutput(BaseModel):
    """서브에이전트 실행 후 후처리 파이프라인에 전달되는 구조화된 데이터."""
    user_id: int = 0
    route: str = ""
    original_message: str = ""
    agent_response: str = ""
    pending_exp: int = 0
    pending_stress: int = 0
