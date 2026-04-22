"""Bus 툴 — 서울시 실시간 도착 + 정류소 검색."""

from __future__ import annotations

from typing import Any, Dict, Optional

from google.adk.tools import FunctionTool, ToolContext

from src.agent.tools._context import fetch_user
from src.tools import bus_api


async def get_bus_arrival(
    stop_id: Optional[str] = None,
    route_filter: Optional[str] = None,
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """서울 시내버스 정류소의 실시간 도착 정보를 반환한다.

    사용자가 "우리 회사 버스 언제 와?", "7211번 몇 분 남았어?" 처럼 버스 도착을 물을 때 호출.
    정류소 ID 가 주어지지 않으면 사용자 프로필(`auth.users.bus_stop_id`) 을 사용한다.

    Args:
        stop_id: 5자리 ARS 정류소 번호 (예: "12121"). 없으면 사용자 등록 정류소 사용.
        route_filter: 특정 노선만 필터링 ("7211" 또는 "7211,146"). 비우면 전체.

    Returns:
        {stop_name, stop_id, arrivals: [{route, minutes, seat, stop_count, congestion, ...}]}
    """
    if not stop_id:
        user = fetch_user(tool_context)
        stop_id = getattr(user, "bus_stop_id", None) if user else None
        if not stop_id:
            return {
                "error": "no_stop_id",
                "message": "등록된 정류소가 없어요. 사용자에게 정류소 ARS 번호를 물어봐 주세요.",
            }
        if not route_filter:
            route_filter = getattr(user, "bus_route_id", None)
    return await bus_api.get_arrival(stop_id, route_filter)


async def search_bus_stations(query: str) -> Dict[str, Any]:
    """정류소 이름 또는 ARS 번호로 정류소를 검색한다.

    사용자가 "강남역 정류장 번호 뭐야?" 같이 정류소를 찾고 싶을 때 호출.

    Args:
        query: "강남역", "12121" 처럼 이름 또는 5자리 ARS 번호.

    Returns:
        {stations: [{ars_id, name, lat, lng, ...}]}
    """
    stations = await bus_api.search_stations(query)
    return {"stations": stations}


bus_arrival_tool = FunctionTool(get_bus_arrival)
bus_search_tool = FunctionTool(search_bus_stations)

__all__ = ["bus_arrival_tool", "bus_search_tool"]
