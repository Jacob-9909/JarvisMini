"""길찾기 — 회사 좌표 출발, 목적지는 키워드 검색(Kakao Local) 후 카카오맵 웹 링크."""

from __future__ import annotations

from typing import Any, Dict, Literal

from google.adk.tools import FunctionTool, ToolContext

from src.agent.tools._context import fetch_user
from src.tools import map_api
from src.tools.kakao_map_links import (
    SUBWAY_REGIONS,
    kakao_directions_by_mode,
    kakao_subway_directions,
)

RouteMode = Literal["traffic", "car", "walk"]


async def get_route_to_place(
    destination_query: str,
    mode: str = "traffic",
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """회사에서 목적지까지 카카오맵 웹 길찾기 링크를 만든다.

    사용자가 '회사에서 강남역까지 대중교통으로', '여기까지 차로 가는 법' 등을 물을 때 호출.
    실제 노선·환승 안내는 카카오맵 앱/웹에서 보게 하며, 여기서는 출발·도착 좌표를 맞춘 링크만 준다.

    Args:
        destination_query: 도착지 이름 또는 검색어 (예: '강남역 2호선', '스타벅스 역삼점').
        mode: ``traffic``(대중교통, 기본), ``car``, ``walk``.

    Returns:
        origin, destination, mode, kakao_url, hint
    """
    user = fetch_user(tool_context)
    if not user or user.company_lat is None or user.company_lng is None:
        return {
            "error": "no_company_coords",
            "message": "회사 좌표가 없어 길찾기 링크를 만들 수 없어요. 프로필 설정을 안내해 주세요.",
        }
    q = (destination_query or "").strip()
    if not q:
        return {"error": "empty_query", "message": "도착지를 한 줄로 말해 달라고 해 주세요."}

    m: RouteMode = "traffic"
    low = (mode or "traffic").lower().strip()
    if low in ("car", "drive", "자동차"):
        m = "car"
    elif low in ("walk", "도보", "walking"):
        m = "walk"
    elif low in ("traffic", "대중교통", "지하철", "버스", "transit", "public"):
        m = "traffic"

    places = await map_api.nearby_places(
        float(user.company_lat),
        float(user.company_lng),
        radius_m=15000,
        category="CE7",
        query=q,
        size=5,
    )
    if not places:
        return {
            "error": "not_found",
            "message": f"'{q}' 근처에서 장소를 찾지 못했어요. 더 구체적인 이름으로 다시 검색해 달라고 해 주세요.",
        }
    dest = places[0]
    dlat = dest.get("lat")
    dlng = dest.get("lng")
    if dlat is None or dlng is None:
        return {
            "error": "no_coords",
            "message": "검색 결과에 좌표가 없어 링크를 만들 수 없어요.",
        }

    from_label = (user.display_name or user.company_address or "회사").strip() or "회사"
    url = kakao_directions_by_mode(
        from_label,
        float(user.company_lat),
        float(user.company_lng),
        str(dest.get("name") or q),
        float(dlat),
        float(dlng),
        mode=m,
    )
    hint = (
        "아래 링크를 누르면 카카오맵에서 길찾기가 열립니다. "
        "대중교통이면 노선·환승은 맵 화면에서 확인하면 됩니다."
    )
    return {
        "origin": {"name": from_label, "lat": user.company_lat, "lng": user.company_lng},
        "destination": {
            "name": dest.get("name"),
            "lat": dlat,
            "lng": dlng,
            "address": dest.get("address"),
        },
        "mode": m,
        "kakao_url": url,
        "hint": hint,
    }


async def get_subway_route(
    from_station: str,
    to_station: str,
    region: str = "seoul",
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """두 역 사이의 카카오맵 지하철 길찾기 URL을 만든다.

    사용자가 '회기역에서 강남역 지하철로', '판교역에서 선릉역 전철로 몇 분' 같이
    **역 대 역** 경로를 물을 때 호출. 실제 노선/환승/소요시간은 카카오맵 페이지에서 본다.

    Args:
        from_station: 출발역 이름 (예: '회기역', '판교역'). '역' 접미사 포함 권장.
        to_station: 도착역 이름 (예: '강남역').
        region: 지역 코드. seoul(수도권, 기본) / busan / daegu / gwangju / daejeon.

    Returns:
        from_station, to_station, region, kakao_url, hint
        실패 시 error/message.
    """
    fs = (from_station or "").strip()
    ts = (to_station or "").strip()
    if not fs or not ts:
        return {
            "error": "empty_stations",
            "message": "출발역과 도착역을 둘 다 알려 달라고 해 주세요.",
        }
    r = (region or "seoul").strip().lower()
    if r not in SUBWAY_REGIONS:
        r = "seoul"
    url = kakao_subway_directions(fs, ts, region=r)  # type: ignore[arg-type]
    hint = (
        "아래 링크를 누르면 카카오맵 지하철 길찾기가 열립니다. "
        "노선/환승/소요시간은 맵 화면에서 확인하면 됩니다."
    )
    return {
        "from_station": fs,
        "to_station": ts,
        "region": r,
        "kakao_url": url,
        "hint": hint,
    }


navigation_tool = FunctionTool(get_route_to_place)
subway_route_tool = FunctionTool(get_subway_route)

__all__ = [
    "navigation_tool",
    "subway_route_tool",
    "get_route_to_place",
    "get_subway_route",
]
