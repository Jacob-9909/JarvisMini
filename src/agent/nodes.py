"""Graph workflow 공용 노드 — init / post_process / pet_care / end.

라우터·도메인 에이전트를 사이에 두고 양 끝에서 상태를 정규화한다.
펫 보상(EXP/stress) DB 반영은 ``pet_care_node`` 단일 지점.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Dict, Optional

from google.adk import Event

from src.schema.chat import AgentOutput, ChatRouteInput, ChatWorkflowInput

logger = logging.getLogger(__name__)


# Runner.run_async 가 state_delta 를 init_node 에 주지 못하는 경우를 위한
# per-request input carrier. async 태스크 경계를 따라 전달된다.
CURRENT_CHAT_INPUT: "ContextVar[Optional[ChatWorkflowInput]]" = ContextVar(
    "CURRENT_CHAT_INPUT", default=None
)


# ---------------------------------------------------------------------------
# init_node
# ---------------------------------------------------------------------------
def _extract_chat_input(
    node_input: ChatWorkflowInput | dict | None,
    state_input: Any,
) -> tuple[int, str]:
    """node_input / state / ContextVar 세 소스 중 먼저 있는 것에서 user_id+message 추출."""
    src = node_input or state_input or CURRENT_CHAT_INPUT.get() or {}
    if isinstance(src, ChatWorkflowInput):
        return src.user_id, src.message
    return int(src.get("user_id") or 0), str(src.get("message") or "")


def init_node(ctx, node_input: ChatWorkflowInput | dict | None = None) -> Event:
    """state_delta / node_input / ContextVar 에서 user_id+message 를 추출."""
    try:
        state_input = ctx.state.get("input")
    except Exception:
        state_input = None

    user_id, message = _extract_chat_input(node_input, state_input)
    return Event(output=ChatRouteInput(user_id=user_id, message=message, route=""))


# ---------------------------------------------------------------------------
# post_process_node — 도메인별 EXP/stress 정책은 여기서만 결정한다.
# pet_care_node 가 이 값을 읽어 DB 에 반영한다.
# ---------------------------------------------------------------------------
_DOMAIN_PET_POLICY: Dict[str, Dict[str, int]] = {
    "bus_agent":         {"exp": 2, "stress": -10},
    "cafe_agent":        {"exp": 2, "stress": -1},
    "lunch_agent":       {"exp": 3, "stress": -5},
    "calendar_agent":    {"exp": 1, "stress": 5},
    "wellness_coach":    {"exp": 1, "stress": -3},
    "general_chat_agent": {"exp": 0, "stress": 0},
}
_DEFAULT_POLICY = {"exp": 0, "stress": 0}


def _read_route_state(ctx) -> tuple[str, int, str]:
    """ctx.state 에서 current_route / user_id / original_message 를 안전하게 읽는다."""
    try:
        route = ctx.state.get("current_route", "general_chat_agent")
        user_id = int(ctx.state.get("user_id", 0))
        original_message = str(ctx.state.get("original_message", ""))
        return route, user_id, original_message
    except Exception:
        return "general_chat_agent", 0, ""


def post_process_node(ctx, node_input: Any) -> Event:
    """서브에이전트 응답 + 라우트 정보 + 정책값을 AgentOutput 으로 묶는다."""
    # 서브에이전트 output_key = "response"
    if isinstance(node_input, dict):
        agent_response = node_input.get("response", str(node_input))
    else:
        agent_response = str(node_input)

    route, user_id, original_message = _read_route_state(ctx)
    policy = _DOMAIN_PET_POLICY.get(route, _DEFAULT_POLICY)

    return Event(
        output=AgentOutput(
            user_id=user_id,
            route=route,
            original_message=original_message,
            agent_response=agent_response,
            pending_exp=policy["exp"],
            pending_stress=policy["stress"],
        )
    )


# ---------------------------------------------------------------------------
# pet_care_node — monitor 경로와 동일한 apply_pet_care_deltas 재사용.
# ---------------------------------------------------------------------------
def _load_user_pet(user_id: int):
    """(user_ctx, pet_status) 쌍을 반환. 없으면 (None, None)."""
    from src.db.models import PetProfile, User
    from src.db.session import SessionLocal
    from src.tools.monitor_pipeline import pet_row_to_status, user_row_to_context

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        pet = (
            db.query(PetProfile)
            .filter(PetProfile.user_id == user_id)
            .first()
        )
        if not user or not pet:
            return None, None
        return user_row_to_context(user), pet_row_to_status(pet)
    finally:
        db.close()


def pet_care_node(ctx, node_input: AgentOutput) -> Event:
    """펫 EXP/stress DB 반영 — 레벨업·무드·진화 규칙 단일 지점."""
    from src.tools.monitor_pipeline import apply_pet_care_deltas

    result: Dict[str, Any] = {
        "text": node_input.agent_response,
        "route": node_input.route,
        "care": {},
    }

    if not node_input.user_id:
        return Event(output=result)

    user_ctx, pet_status = _load_user_pet(node_input.user_id)
    if user_ctx is None or pet_status is None:
        return Event(output=result)

    try:
        care = apply_pet_care_deltas(
            node_input.user_id,
            user_ctx,
            pet_status,
            node_input.pending_exp,
            node_input.pending_stress,
            source="chat",
        )
        result["care"] = care.model_dump()
    except Exception as e:
        logger.warning("pet care failed: %s", e)

    return Event(output=result)


# ---------------------------------------------------------------------------
# end_node — 사용자에게 보일 문장은 pet_care_node 의 `text` 를 그대로 쓴다.
# ---------------------------------------------------------------------------
def end_node(ctx, node_input: Any) -> Event:
    if isinstance(node_input, dict):
        text = node_input.get("text")
        if text is not None and str(text).strip():
            return Event(message=str(text), output=node_input)
    return Event(output=node_input)


__all__ = [
    "CURRENT_CHAT_INPUT",
    "init_node",
    "post_process_node",
    "pet_care_node",
    "end_node",
]
