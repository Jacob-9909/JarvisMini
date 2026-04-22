"""Pet Chat Workflow — ADK 2.0 Graph 조립.

흐름: START → init_node → router_node → {도메인 에이전트} → post_process_node
     → pet_care_node → end_node

각 노드·에이전트 구현은 별도 파일:
- ``src.agent.router``       : RouteDecision + router_node (LLM 분류기)
- ``src.agent.nodes``        : init / post_process / pet_care / end
- ``src.agent.general_agent``: general_chat_agent (fallback)
- ``src.agent.subagents``    : 도메인별 LLM 에이전트 6종
"""

from __future__ import annotations

from google.adk import Workflow

from src.agent.general_agent import general_chat_agent
from src.agent.nodes import (
    CURRENT_CHAT_INPUT,
    end_node,
    init_node,
    pet_care_node,
    post_process_node,
)
from src.agent.router import router_node
from src.agent.subagents import (
    ALL_SUBAGENTS,
    bus_agent,
    cafe_agent,
    calendar_agent,
    lunch_agent,
    wellness_coach,
)

# Router 결정 문자열 → 실제 Agent 객체 매핑.
# ALL_SUBAGENTS 에는 코딩멘토 등 라우터 Literal 에 없는 에이전트가 남아 있을 수
# 있지만 라우터가 선택하지 못하므로 무해하다.
_ROUTE_TO_AGENT = {a.name: a for a in ALL_SUBAGENTS}
_ROUTE_TO_AGENT["general_chat_agent"] = general_chat_agent


pet_agent = Workflow(
    name="pet_chat_workflow",
    edges=[
        ("START",            init_node,         router_node),
        (router_node,        dict(_ROUTE_TO_AGENT)),
        (bus_agent,          post_process_node),  # 버스 정보
        (cafe_agent,         post_process_node),  # 카페 정보
        (lunch_agent,        post_process_node),  # 점심 메뉴 추첨
        (calendar_agent,     post_process_node),  # 일정 정보
        (wellness_coach,     post_process_node),  # 피로·휴식·번아웃
        (general_chat_agent, post_process_node),  # 일반 대화
        (post_process_node,  pet_care_node),      # 펫 EXP/stress DB 반영
        (pet_care_node,      end_node),
    ],
)


__all__ = ["pet_agent", "CURRENT_CHAT_INPUT"]
