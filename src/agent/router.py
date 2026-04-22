"""Intent router — LLM 분류기 + JSON 파싱 + lunch intent 보정.

실상은 ADK Agent 가 아니라 **분류기 LLM 한 번 호출**이다. output_schema 가 특정
google-adk/Gemini 조합에서 실패하는 버그가 있어, JSON 한 줄로 받아
``_extract_route_decision`` 에서 파싱한다. 파싱/예외 시 general_chat_agent 로 폴백.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal, Optional, get_args

from google.adk import Event
from google.adk.agents import Agent
from pydantic import BaseModel, Field, ValidationError

from src.schema.chat import ChatRouteInput

logger = logging.getLogger(__name__)

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

RouteName = Literal[
    "bus_agent",
    "cafe_agent",
    "lunch_agent",
    "calendar_agent",
    "wellness_coach",
    "general_chat_agent",
]
VALID_ROUTES: frozenset[str] = frozenset(get_args(RouteName))


class RouteDecision(BaseModel):
    """라우터 LLM 의 출력 스키마."""

    route: RouteName = Field(description="가장 적합한 에이전트 이름")
    reason: str = Field(default="", description="선택 근거 한 줄(디버깅용)")


ROUTER_INSTRUCTION = """사용자 발화와 직전 대화 맥락을 반영해 가장 적합한 에이전트를 하나 고른다.

에이전트:
- bus_agent: 버스 도착 시간, 노선 정보, 정류소 검색
- cafe_agent: 주변 카페·맛집·식당 정보
- lunch_agent: 점심/저녁 **메뉴 정하기**, 제비·사다리·룰렛 추첨, "뭐 먹지" 류
- calendar_agent: 개인 일정·회의·캘린더
- wellness_coach: 피로·휴식·번아웃·스트레칭·집중 — **식단·메뉴 추천은 담당하지 않는다**
- general_chat_agent: 인사·잡담, 위 목록에 없는 일반적인 대화

우선 규칙: "점심/저녁 메뉴", "뭐 먹지", "메뉴 추천", 룰렛·제비 등은 **반드시 lunch_agent**. 펫 스트레스가 높아 보여도 식사 선택 질문이면 lunch_agent.

응답 형식 (매우 중요):
- **설명 문장 없이** JSON 객체 **한 개만** 출력한다.
- 키는 정확히 `"route"`, `"reason"` 두 개. `route` 값은 아래 문자열 중 하나와 **완전히 동일**해야 한다.
  bus_agent, cafe_agent, lunch_agent, calendar_agent, wellness_coach, general_chat_agent
- 예: {"route":"lunch_agent","reason":"점심 메뉴 추천 요청"}
"""

router_agent = Agent(
    name="router_agent",
    model=MODEL,
    instruction=ROUTER_INSTRUCTION,
)


# ---------------------------------------------------------------------------
# Lunch intent 보정 — LLM 이 세션 스트레스 맥락만 보고 wellness/general 로 오분류하는
# 경우가 있어, 식사 선택 질문을 키워드 기반으로 재라우팅한다.
# ---------------------------------------------------------------------------
def _looks_like_lunch_intent(message: str) -> bool:
    s = (message or "").strip()
    if not s:
        return False
    low = s.lower()
    if any(k in low for k in ("lunch roulette", "lunch menu", "what should i eat")):
        return True
    if "점메추" in s or "저메추" in s:
        return True
    if "메뉴" in s and any(x in s for x in ("추천", "뽑", "룰렛", "제비", "사다리")):
        return True
    if "뭐" in s and "먹" in s:
        return True
    if "점심" in s and any(x in s for x in ("추천", "메뉴", "뭐", "룰렛", "제비", "사다리")):
        return True
    if "저녁" in s and any(x in s for x in ("메뉴", "추천", "뭐", "룰렛")):
        return True
    return False


# ---------------------------------------------------------------------------
# LLM 응답에서 RouteDecision 추출
# ---------------------------------------------------------------------------
def _coerce_router_json_blob(raw: str) -> Optional[dict]:
    """LLM 응답 문자열에서 dict 하나를 최대한 뽑아낸다 (```json``` 블록·본문 내 {...} 등)."""
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    i0, i1 = text.find("{"), text.rfind("}")
    if i0 != -1 and i1 > i0:
        try:
            data = json.loads(text[i0 : i1 + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _extract_route_decision(event: Any) -> Optional[RouteDecision]:
    # 1) event.output 이 dict / str 로 내려오는 경우
    out = getattr(event, "output", None)
    if isinstance(out, dict) and "route" in out:
        try:
            return RouteDecision.model_validate(out)
        except ValidationError:
            pass
    if isinstance(out, str):
        data = _coerce_router_json_blob(out)
        if data and "route" in data:
            try:
                return RouteDecision.model_validate(data)
            except ValidationError:
                pass

    # 2) content.parts[].text 에 JSON 문자열이 들어있는 경우 (Gemini 기본 동작)
    content = getattr(event, "content", None)
    if content and getattr(content, "parts", None):
        text = "".join(
            (getattr(p, "text", "") or "") for p in content.parts
        ).strip()
        data = _coerce_router_json_blob(text)
        if data and "route" in data:
            try:
                return RouteDecision.model_validate(data)
            except ValidationError:
                return None
    return None


# ---------------------------------------------------------------------------
# Router node
# ---------------------------------------------------------------------------
async def _invoke_router(ctx) -> Optional[RouteDecision]:
    """라우터 LLM 호출 → RouteDecision. 실패 시 None.

    ``Agent.run_async`` 의 첫 인자는 사용자 문장(str) 이 아니라
    ``InvocationContext`` 다. 문자열을 넘기면 ``'str' object has no attribute
    'model_copy'`` 로 라우팅이 항상 실패한다.
    """
    try:
        inv = ctx.get_invocation_context()
    except Exception as e:
        logger.warning("router_node: get_invocation_context failed: %s", e)
        return None

    decision: Optional[RouteDecision] = None
    try:
        async for event in router_agent.run_async(inv):
            parsed = _extract_route_decision(event)
            if parsed is not None:
                decision = parsed
    except Exception as e:
        logger.warning("router_agent.run_async failed: %s", e)
    return decision


def _apply_lunch_override(
    decision: Optional[RouteDecision], message: str
) -> Optional[RouteDecision]:
    """식사 의도면 wellness/general 판정을 lunch_agent 로 교정."""
    if decision is None:
        return None
    if decision.route not in ("wellness_coach", "general_chat_agent"):
        return decision
    if not _looks_like_lunch_intent(message):
        return decision
    prev = decision.route
    return RouteDecision(route="lunch_agent", reason=f"override(lunch-intent;was={prev})")


def _resolve_route(decision: Optional[RouteDecision]) -> tuple[str, str]:
    """최종 route 이름과 로그용 reason."""
    if decision is None:
        return "general_chat_agent", "fallback(no_decision)"
    if decision.route not in VALID_ROUTES:
        logger.warning("unknown route %r from router, fallback to general", decision.route)
        return "general_chat_agent", f"fallback(unknown:{decision.route})"
    return decision.route, decision.reason or "llm"


async def router_node(ctx, node_input: ChatRouteInput) -> Event:
    """라우터 전용 LLM 한 번 호출 → route 결정. 실패 시 general_chat_agent."""
    decision = await _invoke_router(ctx)
    decision = _apply_lunch_override(decision, node_input.message)
    target_route, reason = _resolve_route(decision)

    logger.info(
        "[router] msg=%r → %s (%s)",
        (node_input.message or "")[:80],
        target_route,
        reason,
    )

    routed_input = ChatRouteInput(
        user_id=node_input.user_id,
        message=node_input.message,
        route=target_route,
    )
    return Event(
        route=[target_route],
        output=routed_input,
        state={
            "current_route": target_route,
            "user_id": node_input.user_id,
            "original_message": node_input.message,
        },
    )


__all__ = [
    "RouteName",
    "RouteDecision",
    "router_agent",
    "router_node",
]
