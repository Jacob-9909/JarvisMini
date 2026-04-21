from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.schema.state import UserContext, PetStatus, SystemSnapshot, DashboardResult


class WorkflowInput(BaseModel):
    user_id: int
    action: str = "status"
    payload: Dict[str, Any] = Field(default_factory=dict)


# Per-request input carrier for Runner.run_async (state_delta 가 init_node 에
# 투입되지 않는 문제 회피). async 태스크 경계를 따라 전달된다.
CURRENT_WORKFLOW_INPUT: "ContextVar[Optional[WorkflowInput]]" = ContextVar(
    "CURRENT_WORKFLOW_INPUT", default=None
)


class InitResult(BaseModel):
    user: UserContext
    pet: PetStatus
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class MonitorResult(BaseModel):
    user_id: int
    snapshot: SystemSnapshot


class StateBundle(BaseModel):
    user: UserContext
    pet: PetStatus
    snapshot: Optional[SystemSnapshot] = None
    dashboard: Optional[DashboardResult] = None
    pending_exp: int = 0
    pending_stress: int = 0
    source: str = "unknown"
