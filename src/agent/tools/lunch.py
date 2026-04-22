"""Lunch 툴 — 점심/저녁 메뉴 추첨 (제비/사다리/룰렛)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool, ToolContext

from src.agent.tools._context import resolve_user_id
from src.tools import lunch_roulette


def draw_lunch(
    menus: Optional[List[str]] = None,
    method: Optional[str] = None,
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """점심 메뉴를 제비뽑기/사다리/룰렛으로 뽑는다.

    사용자가 "점심 뭐 먹지?" 같이 물을 때 호출. 메뉴를 명시하지 않으면 직전
    세션의 메뉴 후보를 사용하며, 기본값은 랜덤 한식/중식/일식 조합.

    Args:
        menus: ["한식", "일식", "샐러드"] 같은 후보 리스트. 비우면 기본값.
        method: "lottery" | "ladder" | "roulette". 비우면 랜덤 선택.

    Returns:
        {winner, method_label, history, ...}
    """
    uid = resolve_user_id(tool_context) or 0
    result = lunch_roulette.draw(user_id=uid, menus=menus, method=method)
    return {**result, "history": lunch_roulette.recent_picks(uid)}


lunch_tool = FunctionTool(draw_lunch)

__all__ = ["lunch_tool"]
