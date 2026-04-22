"""Calendar 툴 — Google Calendar 일정 조회."""

from __future__ import annotations

from typing import Any, Dict

from google.adk.tools import FunctionTool

from src.tools import calendar_api


def get_calendar_events(hours: int = 4) -> Dict[str, Any]:
    """앞으로 N시간 이내의 캘린더 일정을 조회한다.

    사용자가 "회의 있어?", "오후 일정 알려줘" 같은 질문을 할 때 호출.

    Args:
        hours: 조회 범위(시간). 기본 4.

    Returns:
        {events: [{summary, start, end, location}]}
    """
    return {"events": calendar_api.upcoming_events(hours=hours)}


calendar_tool = FunctionTool(get_calendar_events)

__all__ = ["calendar_tool"]
