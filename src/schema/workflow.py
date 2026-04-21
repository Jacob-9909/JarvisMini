from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from src.schema.state import UserContext, PetStatus, SystemSnapshot, DashboardResult


class WorkflowInput(BaseModel):
    """메인 워크플로우 진입 시 입력 데이터."""
    user_id: int
    action: str = "status"
    payload: Dict[str, Any] = Field(default_factory=dict)


class InitResult(BaseModel):
    """초기화 노드 결과."""
    user: UserContext
    pet: PetStatus
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class MonitorResult(BaseModel):
    """모니터링 노드 결과."""
    user_id: int
    snapshot: SystemSnapshot


class StateBundle(BaseModel):
    """워크플로우 전반에서 전달되는 상태 묶음."""
    user: UserContext
    pet: PetStatus
    snapshot: Optional[SystemSnapshot] = None
    dashboard: Optional[DashboardResult] = None
    pending_exp: int = 0
    pending_stress: int = 0
    source: str = "unknown"
