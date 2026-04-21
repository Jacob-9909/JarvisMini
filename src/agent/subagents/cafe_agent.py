"""CafeAgent — 주변 카페/맛집 추천."""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.tools import cafe_tool, profile_tool
from src.agent.callbacks import inject_runtime_state, reward_on_tool_use

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

cafe_agent = Agent(
    name="cafe_agent",
    model=MODEL,
    description=(
        "회사 주변 카페·맛집·커피숍을 500m~1km 반경에서 찾아준다. 사용자가 "
        "'근처 카페 알려줘' '점심 먹을만한 곳' 같이 장소를 물을 때 호출."
    ),
    instruction=(
        "너는 직장 근처 카페/맛집 큐레이터다.\n"
        "- 사용자가 카페를 물으면 `search_nearby_places(category='cafe')` 를 부른다.\n"
        "- 밥집/식당이면 `category='food'` 로 부른다.\n"
        "- 회사 좌표가 없다면 프로필을 `get_user_profile` 로 확인하고, 비어 있으면 "
        "사용자에게 프로필 설정을 안내한다.\n"
        "- 거리가 가까운 순으로 최대 5곳만 추천하고 '☕ 이름 · 150m · 카테고리' 형식으로 답한다."
    ),
    tools=[cafe_tool, profile_tool],
    output_key="response",
    before_model_callback=inject_runtime_state,
    after_tool_callback=reward_on_tool_use,
    disallow_transfer_to_peers=True,
)
