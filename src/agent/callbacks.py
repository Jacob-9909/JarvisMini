"""펫 Supervisor/서브에이전트에 붙는 Callback.

- `before_model_callback` (``inject_runtime_state``): 매 LLM 턴마다 **현재 시스템
  상태**(CPU/RAM/펫 무드)를 system instruction 앞에 추가. LLM 의 "자기상태 인지"를
  구현한다. 펫 EXP/stress 반영은 Graph Workflow 의 ``pet_care_node`` 단일 지점에서
  수행하므로 여기서는 다루지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest

from src.db.session import SessionLocal
from src.db.models import PetProfile
from src.tools.system_monitor import SystemMonitor

logger = logging.getLogger(__name__)


def _user_id_from_ctx(ctx: Any) -> Optional[int]:
    try:
        state = ctx.state if hasattr(ctx, "state") else ctx.session.state
        uid = state.get("user_id")
        return int(uid) if uid is not None else None
    except Exception:
        return None


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
    snap: dict = {}
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

    try:
        cfg = llm_request.config
        current = getattr(cfg, "system_instruction", None) or ""
        merged = f"{extra}\n\n{current}" if current else extra
        cfg.system_instruction = merged
    except Exception as e:
        logger.debug("system_instruction inject failed: %s", e)
