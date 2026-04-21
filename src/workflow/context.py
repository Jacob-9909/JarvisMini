from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.schema.state import UserContext, PetStatus, SystemSnapshot, DashboardResult
from src.schema.workflow import WorkflowInput, InitResult, MonitorResult, StateBundle



# Per-request input carrier for Runner.run_async (state_delta 가 init_node 에
# 투입되지 않는 문제 회피). async 태스크 경계를 따라 전달된다.
CURRENT_WORKFLOW_INPUT: "ContextVar[Optional[WorkflowInput]]" = ContextVar(
    "CURRENT_WORKFLOW_INPUT", default=None
)
