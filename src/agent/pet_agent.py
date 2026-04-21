"""Pet Chat Workflow — ADK 2.0 Graph 기반 채팅 라우팅.

요구사항:
- 탭 액션(/api/action)은 기존 함수형 Workflow 유지
- 챗봇(/api/chat)도 ADK 2.0 Graph Workflow로 라우팅

이 모듈은 chat 전용 그래프를 제공한다.
1) init_node        : 사용자 발화 수집
2) router_node      : 의도 분류 (LLM 기반)
3) domain agent     : 각 도메인 LLM Agent (bus/cafe/lunch/...)
4) post_process_node: 에이전트 출력 구조화 + 메타데이터 부착
5) pet_care_node    : 펫 EXP/stress DB 반영
6) end_node
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Any, Dict, Optional

from google.adk import Event, Workflow
from google.adk.agents import Agent
from pydantic import BaseModel, Field

from src.agent.subagents import ALL_SUBAGENTS
from src.agent.callbacks import inject_runtime_state, reward_on_tool_use
from src.schema.chat import ChatWorkflowInput, ChatRouteInput, AgentOutput

logger = logging.getLogger(__name__)

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

_GENERAL_INSTRUCTION = """너는 직장인 전용 펫 비서이다.
- 간결하고 친근한 존댓말로 답해야 한다.
- 사용자의 질문이 버스/카페/점심/일정인 경우 해당 라우팅으로 처리한다.
- 여기서는 일반 대화(인사/잡담/메타 질문)를 처리한다.
"""

general_chat_agent = Agent(
    name="general_chat_agent",
    model=MODEL,
    description="일반 대화 fallback 에이전트",
    instruction=_GENERAL_INSTRUCTION,
    output_key="response",
    before_model_callback=inject_runtime_state,
    after_tool_callback=reward_on_tool_use,
)


# --- Router Agent ---
ROUTER_INSTRUCTION = """사용자의 발화를 분석하여 가장 적합한 에이전트 하나를 선택하세요.
선택 가능한 에이전트 목록:
- bus_agent: 버스 도착 시간, 노선 정보, 정류소 검색 관련
- cafe_agent: 주변 카페 추천, 맛집, 식당 정보 관련
- lunch_agent: 점심 메뉴 추천, 룰렛, 메뉴 고민 관련
- calendar_agent: 개인 일정 조회, 회의 시간, 캘린더 관련
- wellness_coach: 스트레스 관리, 휴식 권고, 번아웃 방지, 건강 관련
- general_chat_agent: 인사, 잡담, 위 목록에 없는 일반적인 대화

출력 형식: 반드시 선택한 에이전트 이름만 출력하세요. (예: bus_agent)
"""

router_agent = Agent(
    name="router_agent",
    model=MODEL,
    instruction=ROUTER_INSTRUCTION,
)


# 이름으로 빠르게 라우팅하기 위한 인덱스
_SUB_BY_NAME = {a.name: a for a in ALL_SUBAGENTS}


CURRENT_CHAT_INPUT: "ContextVar[Optional[ChatWorkflowInput]]" = ContextVar(
    "CURRENT_CHAT_INPUT", default=None
)


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
    
    return Event(output=ChatRouteInput(user_id=user_id, message=message, route=""))


async def router_node(ctx, node_input: ChatRouteInput) -> Event:
    """router_agent(LLM)를 호출하여 실제 라우팅 대상을 결정."""
    prompt = f"다음 사용자 메시지를 분석하여 에이전트를 추천해줘: {node_input.message}"

    target_route = "general_chat_agent"
    try:
        async for event in router_agent.run_async(prompt):
            if hasattr(event, "content") and event.content.parts:
                text = event.content.parts[0].text.strip()
                if text in _SUB_BY_NAME or text == "general_chat_agent":
                    target_route = text
    except Exception:
        target_route = "general_chat_agent"

    # 후처리 노드에서 참조할 컨텍스트를 state 에 저장
    try:
        ctx.state["current_route"] = target_route
        ctx.state["user_id"] = node_input.user_id
        ctx.state["original_message"] = node_input.message
    except Exception:
        pass

    return Event(route=[target_route], output=node_input)


# ---------------------------------------------------------------------------
# 도메인별 EXP/stress 정책
# ---------------------------------------------------------------------------
_DOMAIN_PET_POLICY: Dict[str, Dict[str, int]] = {
    "bus_agent":         {"exp": 2, "stress": -10},
    "cafe_agent":        {"exp": 2, "stress": -1},
    "lunch_agent":       {"exp": 3, "stress": -5},
    "calendar_agent":    {"exp": 1, "stress": 5},
    "wellness_coach":    {"exp": 1, "stress": -3},
    "coding_mentor":     {"exp": 1, "stress": 0},
    "general_chat_agent": {"exp": 0, "stress": 0},
}


def post_process_node(ctx, node_input: Any) -> Event:
    """서브에이전트의 출력을 구조화하고 후처리 메타데이터를 부착한다.

    output_key='response' 로 설정된 에이전트는 {"response": "텍스트"} 형태로 출력.
    이 노드에서 state 에 저장된 라우팅 정보와 결합하여 AgentOutput 으로 통합.
    """
    # 에이전트 응답 텍스트 추출
    if isinstance(node_input, dict):
        agent_response = node_input.get("response", str(node_input))
    else:
        agent_response = str(node_input)

    # router_node 에서 저장한 컨텍스트 복원
    route = "general_chat_agent"
    user_id = 0
    original_message = ""
    try:
        route = ctx.state.get("current_route", "general_chat_agent")
        user_id = int(ctx.state.get("user_id", 0))
        original_message = str(ctx.state.get("original_message", ""))
    except Exception:
        pass

    policy = _DOMAIN_PET_POLICY.get(route, {"exp": 0, "stress": 0})

    output = AgentOutput(
        user_id=user_id,
        route=route,
        original_message=original_message,
        agent_response=agent_response,
        pending_exp=policy["exp"],
        pending_stress=policy["stress"],
    )
    return Event(output=output)


def pet_care_node(ctx, node_input: AgentOutput) -> Event:
    """펫 EXP/stress 를 DB 에 반영하고 최종 응답 payload 를 구성한다."""
    from src.db.session import SessionLocal
    from src.db.models import PetProfile

    result: Dict[str, Any] = {
        "text": node_input.agent_response,
        "route": node_input.route,
        "care": {},
    }

    if node_input.user_id:
        db = SessionLocal()
        try:
            pet = db.query(PetProfile).filter(
                PetProfile.user_id == node_input.user_id
            ).first()
            if pet:
                pet.exp = max(0, (pet.exp or 0) + node_input.pending_exp)
                new_stress = (pet.stress or 0) + node_input.pending_stress
                pet.stress = max(0, min(100, new_stress))

                leveled_up = False
                threshold = pet.level * 100
                if pet.exp >= threshold:
                    pet.level += 1
                    pet.exp -= threshold
                    leveled_up = True

                if pet.stress >= 70:
                    pet.mood = "stressed"
                elif pet.stress >= 40:
                    pet.mood = "tired"
                else:
                    pet.mood = "neutral"

                db.commit()

                result["care"] = {
                    "exp_gain": node_input.pending_exp,
                    "stress_delta": node_input.pending_stress,
                    "leveled_up": leveled_up,
                    "mood": pet.mood,
                    "level": pet.level,
                    "exp": pet.exp,
                }
        except Exception as e:
            logger.debug("pet care failed: %s", e)
            db.rollback()
        finally:
            db.close()

    return Event(output=result)


def end_node(ctx, node_input: Any) -> Event:
    return Event(message="ok")


# ---------------------------------------------------------------------------
# Graph 기반 chat workflow
# 흐름: init → router → {subagent} → post_process → pet_care → end
# ---------------------------------------------------------------------------
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
        # 모든 서브에이전트 → post_process → pet_care → end
        (_SUB_BY_NAME["bus_agent"], post_process_node),
        (_SUB_BY_NAME["cafe_agent"], post_process_node),
        (_SUB_BY_NAME["lunch_agent"], post_process_node),
        (_SUB_BY_NAME["calendar_agent"], post_process_node),
        (_SUB_BY_NAME["wellness_coach"], post_process_node),
        (_SUB_BY_NAME["coding_mentor"], post_process_node),
        (general_chat_agent, post_process_node),
        (post_process_node, pet_care_node),
        (pet_care_node, end_node),
    ],
)
