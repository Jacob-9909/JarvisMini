"""펫 Supervisor/서브에이전트에 붙는 Callback 들.

- `before_model_callback`: 매 LLM 턴마다 **현재 시스템 상태**(CPU/RAM/펫 무드)
  를 system instruction 앞에 추가. → LLM 의 "자기상태 인지"를 구현.

- `after_tool_callback`: 서브에이전트가 어떤 도구든 하나 호출하면 펫에 소량 EXP
  가산, 그리고 툴 이름에 따라 stress 델타를 준다. → Graph Workflow 의
  `pet_care_node` 를 대신해 Agent 경로에서도 펫이 "성장"한다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from src.db.session import SessionLocal
from src.db.models import PetProfile
from src.tools.system_monitor import SystemMonitor

logger = logging.getLogger(__name__)


# -- 툴별 EXP/stress 반영 정책 ---------------------------------------------
_TOOL_PET_POLICY: Dict[str, Dict[str, int]] = {
    # 휴식을 유도하는 툴은 스트레스 소폭 완화
    "get_activity_snapshot": {"exp": 1, "stress": -2},
    "get_pet_status":         {"exp": 1, "stress": 0},
    # 외부 호출은 미세한 탐색 EXP
    "get_bus_arrival":        {"exp": 2, "stress": -10},
    "search_bus_stations":    {"exp": 1, "stress": -1},
    "search_nearby_places":   {"exp": 2, "stress": -1},
    "draw_lunch":             {"exp": 3, "stress": -5},
    "get_calendar_events":    {"exp": 1, "stress": 5},
    "get_user_profile":       {"exp": 0, "stress": 0},
}

# 기본 정책 (policy 에 없는 툴용)
_DEFAULT_POLICY = {"exp": 1, "stress": 0}

# stress 자연 감쇠 상한 / EXP 증분 상한
_STRESS_MIN, _STRESS_MAX = 0, 100


def _user_id_from_ctx(ctx: Any) -> Optional[int]:
    try:
        state = ctx.state if hasattr(ctx, "state") else ctx.session.state
        uid = state.get("user_id")
        return int(uid) if uid is not None else None
    except Exception: 
        return None


# ---------------------------------------------------------------------------
# before_model_callback
# ---------------------------------------------------------------------------
def inject_runtime_state(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """매 LLM 호출 전에 사용자 실시간 상태를 system 메시지에 끼워 넣는다."""
    uid = _user_id_from_ctx(callback_context)

    mon = SystemMonitor.instance()
    try:
        mon.start()
    except Exception:
        pass
    snap = {}
    try:
        snap = mon.peek_snapshot()
    except Exception as e: 
        logger.debug("peek_snapshot failed: %s", e)

    pet_line = ""
    if uid is not None:
        db = SessionLocal()
        try:
            pet = db.query(PetProfile).filter(PetProfile.user_id == uid).first()
            if pet:
                pet_line = (
                    f"[Pet] {pet.species} Lv.{pet.level} · mood={pet.mood} · "
                    f"stress={pet.stress} · exp={pet.exp}"
                )
        finally:
            db.close()

    sys_line = (
        "[Runtime] "
        f"cpu={snap.get('cpu_percent', 0):.0f}% · "
        f"ram={snap.get('mem_percent', 0):.0f}% · "
        f"tabs={snap.get('active_tabs', 0)} · "
        f"clicks={snap.get('click_count', 0)} · "
        f"keys={snap.get('key_count', 0)}"
    )

    extra = "\n".join(filter(None, [sys_line, pet_line]))
    if not extra:
        return

    # LlmRequest.config.system_instruction 에 prepend
    try:
        cfg = llm_request.config
        current = getattr(cfg, "system_instruction", None) or ""
        merged = f"{extra}\n\n{current}" if current else extra
        cfg.system_instruction = merged
    except Exception as e: 
        logger.debug("system_instruction inject failed: %s", e)


# ---------------------------------------------------------------------------
# after_tool_callback
# ---------------------------------------------------------------------------
def reward_on_tool_use(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
    tool_response: Any,
) -> None:
    """툴 하나가 끝날 때마다 펫에 EXP/stress 를 반영한다."""
    uid = _user_id_from_ctx(tool_context)
    if uid is None:
        return
    policy = _TOOL_PET_POLICY.get(tool.name, _DEFAULT_POLICY)
    db = SessionLocal()
    try:
        pet = db.query(PetProfile).filter(PetProfile.user_id == uid).first()
        if not pet:
            return
        pet.exp = max(0, (pet.exp or 0) + int(policy.get("exp", 0)))
        new_stress = (pet.stress or 0) + int(policy.get("stress", 0))
        pet.stress = max(_STRESS_MIN, min(_STRESS_MAX, new_stress))
        # 레벨업
        threshold = pet.level * 100
        if pet.exp >= threshold:
            pet.level += 1
            pet.exp -= threshold
        # 간단한 무드 규칙
        if pet.stress >= 70:
            pet.mood = "stressed"
        elif pet.stress >= 40:
            pet.mood = "tired"
        else:
            pet.mood = "neutral"
        db.commit()
    except Exception as e: 
        logger.debug("pet reward failed: %s", e)
        db.rollback()
    finally:
        db.close()
