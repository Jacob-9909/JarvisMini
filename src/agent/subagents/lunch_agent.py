"""LunchAgent — 점심 메뉴 추첨."""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.tools import lunch_tool

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

lunch_agent = Agent(
    name="lunch_agent",
    model=MODEL,
    description=(
        "점심 메뉴를 제비뽑기/사다리/룰렛으로 추첨한다. '오늘 뭐 먹지?' 같은 "
        "질문에 동원된다."
    ),
    instruction=(
        "너는 점심 메뉴 결정 전문가다.\n"
        "- 사용자가 메뉴 후보를 주면 그대로 `draw_lunch` 로 뽑는다.\n"
        "- 후보가 없으면 대표 메뉴 (한식/일식/중식/샐러드/분식) 5개를 스스로 제시한다.\n"
        "- 추첨 방식은 사용자가 명시하지 않으면 `method=None` 으로 랜덤 선택.\n"
        "- 결과는 '🍽 오늘은 **떡볶이** 어때요? (룰렛)' 같이 친근하게 한 줄로."
    ),
    tools=[lunch_tool],
    disallow_transfer_to_peers=True,
)
