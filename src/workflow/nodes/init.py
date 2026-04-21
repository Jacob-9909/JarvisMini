from __future__ import annotations

import logging
import time
from typing import Any, Dict

from google.adk import Event

from src.db.models import User
from src.db.session import SessionLocal
from src.schema.state import PetStatus, UserContext
from src.workflow.context import CURRENT_WORKFLOW_INPUT, InitResult, WorkflowInput
from src.workflow.helpers import ensure_pet_profile, log_node, session_id

logger = logging.getLogger(__name__)


def init_node(ctx, node_input: WorkflowInput | dict | None = None) -> Event:
    started = time.perf_counter()
    user_id = 0
    action = "status"
    payload: Dict[str, Any] = {}

    state_input = None
    try:
        state_input = ctx.state.get("input")  # type: ignore[union-attr]
    except Exception:
        state_input = None

    ctx_input = CURRENT_WORKFLOW_INPUT.get()
    source: Any = node_input if node_input is not None else (state_input or ctx_input)
    if isinstance(source, WorkflowInput):
        user_id, action, payload = source.user_id, source.action, source.payload
    elif isinstance(source, dict):
        user_id = int(source.get("user_id") or 0)
        action = source.get("action", "status")
        payload = source.get("payload") or {}

    if user_id == 0:
        try:
            user_id = int(ctx.user_id)
        except (AttributeError, TypeError, ValueError):
            user_id = 0

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error("[User %s] not found", user_id)
            log_node(session_id(ctx), user_id, "init_node", started, route="end", status="no-user")
            return Event(route=["end"])

        pet_row = ensure_pet_profile(db, user_id, user)
        user_ctx = UserContext(
            user_id=user.id,
            display_name=user.display_name,
            job_role=user.job_role,
            dev_tendency=user.dev_tendency,
            company_lat=user.company_lat,
            company_lng=user.company_lng,
            bus_stop_id=user.bus_stop_id,
            bus_route_id=user.bus_route_id,
        )
        pet_status = PetStatus(
            species=pet_row.species,
            nickname=pet_row.nickname,
            level=pet_row.level,
            exp=pet_row.exp,
            mood=pet_row.mood,
            stress=pet_row.stress,
        )
    finally:
        db.close()

    result = InitResult(user=user_ctx, pet=pet_status, action=action, payload=payload)
    log_node(session_id(ctx), user_id, "init_node", started, route="router", payload={"action": action})
    return Event(output=result)
