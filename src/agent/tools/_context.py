"""툴 공용 헬퍼 — ToolContext → 세션 상태/사용자 해석.

``user_id`` 는 ``/api/chat`` 엔드포인트가 세션 최초 생성 시 state 에 넣어 준다.
모든 툴이 동일 규칙을 따른다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from google.adk.tools import ToolContext

from src.db.models import PetProfile, User
from src.db.session import SessionLocal


def session_state(tool_context: ToolContext) -> Dict[str, Any]:
    """ToolContext.state 우선, 실패 시 invocation_context.session.state 폴백."""
    try:
        st = getattr(tool_context, "state", None)
        if st is not None:
            return dict(st)
    except Exception:
        pass
    try:
        return dict(tool_context.get_invocation_context().session.state)  # type: ignore[attr-defined]
    except Exception:
        return {}


def resolve_user_id(tool_context: ToolContext) -> Optional[int]:
    uid = session_state(tool_context).get("user_id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def fetch_user(tool_context: ToolContext) -> Optional[User]:
    uid = resolve_user_id(tool_context)
    if uid is None:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == uid).first()
    finally:
        db.close()


def fetch_pet(tool_context: ToolContext) -> Optional[PetProfile]:
    uid = resolve_user_id(tool_context)
    if uid is None:
        return None
    db = SessionLocal()
    try:
        return db.query(PetProfile).filter(PetProfile.user_id == uid).first()
    finally:
        db.close()


__all__ = ["session_state", "resolve_user_id", "fetch_user", "fetch_pet"]
