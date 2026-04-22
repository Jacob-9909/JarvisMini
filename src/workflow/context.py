"""Workflow per-request input carrier + 스키마 re-export.

``Runner.run_async`` 가 ``state_delta`` 를 ``init_node`` 에 전달하지 못하는
경우를 대비해 ContextVar 로 입력을 보조 전달한다. async 태스크 경계를
따라 값이 유지된다.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from src.schema.workflow import InitResult, StateBundle, WorkflowInput

CURRENT_WORKFLOW_INPUT: "ContextVar[Optional[WorkflowInput]]" = ContextVar(
    "CURRENT_WORKFLOW_INPUT", default=None
)

__all__ = [
    "CURRENT_WORKFLOW_INPUT",
    "WorkflowInput",
    "InitResult",
    "StateBundle",
]
