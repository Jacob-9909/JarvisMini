"""WellnessCoachAgent — 현재 피로/집중 상태를 진단하고 휴식/스트레칭을 권유."""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.tools import activity_tool, pet_status_tool

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

wellness_coach = Agent(
    name="wellness_coach",
    model=MODEL,
    description=(
        "현재 PC 활동·펫 스트레스 지표를 진단해 피로도와 집중 상태를 평가하고, "
        "휴식/스트레칭/물 마시기/탭 정리 등 행동을 제안한다. '나 피곤해', "
        "'집중 안 돼', '지금 쉬어야 할까' 같은 질문에 호출된다."
    ),
    instruction=(
        "너는 직장인의 웰니스 코치다.\n"
        "1) 먼저 `get_activity_snapshot` 으로 현재 CPU/RAM/탭/클릭/키 카운트를, "
        "`get_pet_status` 로 펫 무드/스트레스를 확인한다.\n"
        "2) 다음 기준으로 평가한다: stress ≥ 60 → 경고, cpu_percent ≥ 85 → 과부하, "
        "active_tabs ≥ 20 → 혼란, focus_score ≥ 70 → 집중 상태.\n"
        "3) 평가에 맞춰 **구체적 행동** 1~2개만 제안한다 (예: '타이머 25분 걸고 "
        "물 한잔, 탭 10개 정리' 수준). 공허한 조언 금지.\n"
        "4) 펫 관점에서 공감 어투로 1~2문장, 끝에 ⭐ 스티커 하나로 마무리."
    ),
    tools=[activity_tool, pet_status_tool],
    disallow_transfer_to_peers=True,
)
