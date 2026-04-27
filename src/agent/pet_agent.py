"""Pet Chat Workflow — ADK 2.0 Graph 조립.

흐름: START → init_node → router_decide_node(키워드면 HITL 생략) → router_finalize_node → {도메인 에이전트}

도메인 경로:
- bus/wellness/navigation/general : 에이전트 → post_process_node
- lunch      : lunch_agent → lunch_draw_node (HITL 없이 즉시 추첨)
               → lunch_restaurant_search_node (Tavily MCP 로 회사 근처 맛집 검색)
               → post_process_node
- calendar   : calendar_agent → calendar_reminder_node (HITL / passthrough)
               → calendar_finalize_node → post_process_node

이후 공통: post_process_node → pet_care_node → end_node

HITL 노드는 ``src.agent.lunch_hitl`` / ``src.agent.calendar_hitl`` 에 정의.
"""

from __future__ import annotations

from google.adk import Workflow

from src.agent.calendar_hitl import calendar_finalize_node, calendar_reminder_node
from src.agent.lunch_hitl import lunch_draw_node
from src.agent.lunch_restaurant import lunch_restaurant_search_node
from src.agent.nodes import (
    CURRENT_CHAT_INPUT,
    end_node,
    init_node,
    pet_care_node,
    post_process_node,
)
from src.agent.router import router_decide_node, router_finalize_node
from src.agent.subagents import (
    ALL_SUBAGENTS,
    bus_agent,
    calendar_agent,
    general_chat_agent,
    lunch_agent,
    navigation_agent,
    wellness_coach,
)

# Router 결정 문자열 → 실제 Agent 객체 매핑 (라우터 Literal 과 이름이 맞아야 함).
_ROUTE_TO_AGENT = {a.name: a for a in ALL_SUBAGENTS}


pet_agent = Workflow(
    name="pet_chat_workflow",
    edges=[
        ("START",            init_node,         router_decide_node),
        (router_decide_node, router_finalize_node),
        (router_finalize_node, dict(_ROUTE_TO_AGENT)),

        # HITL 없이
        (bus_agent,          post_process_node),
        (wellness_coach,     post_process_node),
        (navigation_agent,   post_process_node),
        (general_chat_agent, post_process_node),

        # 점심: HITL 없이 즉시 추첨 → Tavily MCP 로 회사 근처 맛집 검색
        (lunch_agent,                  lunch_draw_node),
        (lunch_draw_node,              lunch_restaurant_search_node),
        (lunch_restaurant_search_node, post_process_node),

        # Calendar: 에이전트(툴 조회) → HITL 노드
        (calendar_agent,           calendar_reminder_node),
        (calendar_reminder_node,   calendar_finalize_node),
        (calendar_finalize_node,   post_process_node),

        # 공통 종료
        (post_process_node,  pet_care_node),
        (pet_care_node,      end_node),
    ],
)


__all__ = ["pet_agent", "CURRENT_CHAT_INPUT"]
