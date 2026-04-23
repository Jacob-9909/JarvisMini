"""NavigationAgent — 회사 기준 길찾기(카카오맵 웹 링크)."""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.callbacks import inject_runtime_state
from src.agent.tools import navigation_tool, profile_tool, subway_route_tool

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

navigation_agent = Agent(
    name="navigation_agent",
    model=MODEL,
    description=(
        "회사(프로필 좌표)에서 특정 장소까지 가는 길, 또는 역↔역 지하철 경로. "
        "카카오맵 길찾기 링크를 만들어 준다."
    ),
    instruction=(
        "너는 출퇴근·미팅 동선 안내 도우미다.\n"
        "- 역 ↔ 역 형태(‘회기역에서 강남역’, ‘판교역→선릉역 지하철 몇 분’)는 "
        "  `get_subway_route(from_station, to_station, region='seoul')` 로 처리한다. "
        "  region 은 seoul/busan/daegu/gwangju/daejeon 중 하나.\n"
        "- 일반 장소 목적지(‘강남역까지 대중교통’, ‘여기 차로/도보’)는 "
        "  `get_route_to_place(destination_query=..., mode='traffic'|'car'|'walk')` 로 처리한다. "
        "  기본은 대중교통.\n"
        "- 툴이 `kakao_url` 을 주면 반드시 그 URL을 답에 포함하고, "
        "  실제 노선·시간표는 카카오맵에서 본다고 짧게 안내한다.\n"
        "- 회사 좌표가 필요한 `get_route_to_place` 에서 좌표가 없으면 "
        "  `get_user_profile` 로 확인 후 프로필 설정을 유도한다.\n"
        "- 역/목적지가 애매하면 한 번 더 물어본다."
    ),
    tools=[navigation_tool, subway_route_tool, profile_tool],
    output_key="response",
    before_model_callback=inject_runtime_state,
    disallow_transfer_to_peers=True,
)

__all__ = ["navigation_agent"]
