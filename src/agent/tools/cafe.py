"""Cafe / Places 툴 — 회사 좌표 기준 반경 내 Kakao Local 검색."""

from __future__ import annotations

from typing import Any, Dict

from google.adk.tools import FunctionTool, ToolContext

from src.agent.tools._context import fetch_user
from src.tools import map_api


async def search_nearby_places(
    category: str = "cafe",
    radius_m: int = 500,
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """회사 좌표 기준 반경 내 카페/식당을 검색한다 (Kakao Local).

    사용자가 "근처 커피 어디가 좋아?" 같은 질문을 하면 호출.

    Args:
        category: "cafe" 또는 "food".
        radius_m: 반경(미터). 기본 500.

    Returns:
        {places: [{name, category, distance_m, address, lat, lng, url}], radius_m}
    """
    user = fetch_user(tool_context)
    if not user or user.company_lat is None:
        return {
            "error": "no_company_coords",
            "message": "회사 좌표가 없어서 검색할 수 없어요. 프로필을 먼저 설정해 달라고 안내해 주세요.",
        }
    cat = "CE7" if category.lower().startswith("cafe") else "FD6"
    places = await map_api.nearby_places(
        user.company_lat, user.company_lng, radius_m=radius_m, category=cat
    )
    return {"places": places, "radius_m": radius_m, "category": cat}


cafe_tool = FunctionTool(search_nearby_places)

__all__ = ["cafe_tool"]
