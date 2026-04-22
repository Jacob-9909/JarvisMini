"""BusAgent — 서울 시내버스 도착정보 / 정류소 검색 전용 서브에이전트."""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.tools import bus_arrival_tool, bus_search_tool, ask_user_tool
from src.agent.callbacks import inject_runtime_state

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

bus_agent = Agent(
    name="bus_agent",
    model=MODEL,
    description=(
        "서울시 버스 도착 정보와 정류소 검색을 담당."
    ),
    instruction=(
        "너는 서울 시내버스 정보 전문 에이전트다. 가능한 한 간결하게 답한다.\n"
        "- 사용자가 버스 정보를 물었을 때 정류소 정보(ARS 번호 또는 이름)가 없거나 불확실하다면, "
        "임의로 추측하지 말고 `ask_user` 도구를 호출해 사용자에게 어느 정류소인지 물어봐라.\n"
        "- 정류소가 주어지지 않으면 `get_bus_arrival` 을 stop_id 없이 호출해 "
        "사용자 기본 정류소(ARS)를 사용한다.\n"
        "- 정류소 이름만 알고 있으면 먼저 `search_bus_stations` 로 ARS 번호를 찾은 뒤 "
        "`get_bus_arrival` 을 호출한다.\n"
        "- 도착 정보가 비어 있으면 '지금 도착 예정 버스가 없어요' 라고 답한다.\n"
        "- 응답은 '🚌 7211번 · 3분 · 여유' 같은 한 줄 포맷을 최대 5줄까지."
    ),
    tools=[bus_arrival_tool, bus_search_tool, ask_user_tool],
    output_key="response",
    before_model_callback=inject_runtime_state,
    disallow_transfer_to_peers=True,
)
