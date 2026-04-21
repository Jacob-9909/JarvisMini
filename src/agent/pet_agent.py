"""Pet Chat Workflow — ADK 2.0 Graph 기반 채팅 라우팅.

요구사항:
- 탭 액션(/api/action)은 기존 함수형 Workflow 유지
- 챗봇(/api/chat)도 ADK 2.0 Graph Workflow로 라우팅

이 모듈은 chat 전용 그래프를 제공한다.
1) init_node  : 사용자 발화 수집
2) router_node: 의도 분류(규칙 기반)
3) domain node: 각 도메인 LLM Agent(bus/cafe/lunch/...)
4) end_node
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any, Dict, Optional

from google.adk import Event, Workflow
from google.adk.agents import Agent
from pydantic import BaseModel, Field

from src.agent.subagents import ALL_SUBAGENTS
from src.agent.callbacks import inject_runtime_state, reward_on_tool_use

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

_GENERAL_INSTRUCTION = """너는 반려 펫 비서다.
- 간결하고 친근한 존댓말로 답한다.
- 사용자의 질문이 버스/카페/점심/일정/웰니스/코딩 전문영역이면 해당 라우팅이 처리한다.
- 여기서는 일반 대화(인사/잡담/메타 질문)를 처리한다.
"""

general_chat_agent = Agent(
    name="general_chat_agent",
    model=MODEL,
    description="일반 대화 fallback 에이전트",
    instruction=_GENERAL_INSTRUCTION,
    before_model_callback=inject_runtime_state,
    after_tool_callback=reward_on_tool_use,
)


# 이름으로 빠르게 라우팅하기 위한 인덱스
_SUB_BY_NAME = {a.name: a for a in ALL_SUBAGENTS}


class ChatWorkflowInput(BaseModel):
    user_id: int
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ChatRouteInput(BaseModel):
    user_id: int
    message: str
    route: str


CURRENT_CHAT_INPUT: "ContextVar[Optional[ChatWorkflowInput]]" = ContextVar(
    "CURRENT_CHAT_INPUT", default=None
)


def _classify_route(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("버스", "정류장", "도착", "몇분", "노선")):
        return "bus_agent"
    if any(k in t for k in ("카페", "커피", "맛집", "식당")):
        return "cafe_agent"
    if any(k in t for k in ("점심", "메뉴", "먹지", "룰렛")):
        return "lunch_agent"
    if any(k in t for k in ("일정", "회의", "캘린더")):
        return "calendar_agent"
    if any(k in t for k in ("피곤", "집중", "스트레스", "휴식", "번아웃")):
        return "wellness_coach"
    if any(k in t for k in ("코드", "에러", "디버그", "리팩토링", "아키텍처", "adk")):
        return "coding_mentor"
    return "general_chat_agent"


def init_node(ctx, node_input: ChatWorkflowInput | dict | None = None) -> Event:
    """state_delta/input/contextvar에서 user_id+message를 추출."""
    state_input = None
    try:
        state_input = ctx.state.get("input")  # type: ignore[union-attr]
    except Exception:
        state_input = None

    src = node_input or state_input or CURRENT_CHAT_INPUT.get() or {}
    if isinstance(src, ChatWorkflowInput):
        user_id = src.user_id
        message = src.message
    else:
        user_id = int(src.get("user_id") or 0)
        message = str(src.get("message") or "")
    route = _classify_route(message)
    return Event(output=ChatRouteInput(user_id=user_id, message=message, route=route))


def router_node(ctx, node_input: ChatRouteInput) -> Event:
    route = node_input.route
    if route not in {
        "bus_agent",
        "cafe_agent",
        "lunch_agent",
        "calendar_agent",
        "wellness_coach",
        "coding_mentor",
        "general_chat_agent",
    }:
        route = "general_chat_agent"
    return Event(route=[route], output=node_input)


def end_node(ctx, node_input: Any) -> Event:
    return Event(message="ok")


# Graph 기반 chat workflow (도메인 에이전트는 node로 연결)
pet_agent = Workflow(
    name="pet_chat_workflow",
    edges=[
        ("START", init_node, router_node),
        (
            router_node,
            {
                "bus_agent": _SUB_BY_NAME["bus_agent"],
                "cafe_agent": _SUB_BY_NAME["cafe_agent"],
                "lunch_agent": _SUB_BY_NAME["lunch_agent"],
                "calendar_agent": _SUB_BY_NAME["calendar_agent"],
                "wellness_coach": _SUB_BY_NAME["wellness_coach"],
                "coding_mentor": _SUB_BY_NAME["coding_mentor"],
                "general_chat_agent": general_chat_agent,
            },
        ),
        (_SUB_BY_NAME["bus_agent"], end_node),
        (_SUB_BY_NAME["cafe_agent"], end_node),
        (_SUB_BY_NAME["lunch_agent"], end_node),
        (_SUB_BY_NAME["calendar_agent"], end_node),
        (_SUB_BY_NAME["wellness_coach"], end_node),
        (_SUB_BY_NAME["coding_mentor"], end_node),
        (general_chat_agent, end_node),
    ],
)
