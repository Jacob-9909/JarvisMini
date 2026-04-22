"""General chat fallback 에이전트.

라우터가 분류 실패·일반 대화로 판정한 경우 응답하는 기본 Agent.
서브에이전트(bus/cafe/lunch/...)와 동일한 콜백 체계를 쓴다.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.callbacks import inject_runtime_state

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

_GENERAL_INSTRUCTION = """너는 직장인 전용 펫 비서이다.
간결하고 친근한 존댓말로 인사·잡담·가벼운 조언을 한다.
"""

general_chat_agent = Agent(
    name="general_chat_agent",
    model=MODEL,
    description="일반 대화 fallback 에이전트",
    instruction=_GENERAL_INSTRUCTION,
    output_key="response",
    before_model_callback=inject_runtime_state,
)

__all__ = ["general_chat_agent"]
