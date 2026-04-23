"""CalendarAgent — 구글 캘린더 일정 요약."""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.tools import calendar_tool
from src.agent.callbacks import inject_runtime_state

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

calendar_agent = Agent(
    name="calendar_agent",
    model=MODEL,
    description=(
        "구글 캘린더의 다가오는 일정을 조회·요약한다. '회의 있어?' '오후 일정' "
        "같은 질문에 호출된다."
    ),
    instruction=(
        "너는 스케줄 비서다."
        "- 기본 4시간 범위를 조회하지만, '오늘'이면 24, '이번 주'면 168 같이 "
        "필요한 시간 범위를 `hours` 로 지정해 `get_calendar_events` 를 부른다."
        "- 일정이 없으면 '이 범위 안에는 일정이 없어요' 라고 짧게 답한다."
    ),
    tools=[calendar_tool],
    output_key="response",
    before_model_callback=inject_runtime_state,
    disallow_transfer_to_peers=True,
)
