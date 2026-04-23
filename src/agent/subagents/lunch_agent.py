"""LunchAgent — 점심 메뉴 **후보 제안** (추첨은 HITL 노드가 담당).

실제 ``draw_lunch`` 툴 호출은 ``src.agent.lunch_hitl`` 의 HITL 노드들이
사용자 확인 뒤 수행하므로, 이 에이전트는 후보 5개를 한 줄로 제안만 한다.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.callbacks import inject_runtime_state

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

lunch_agent = Agent(
    name="lunch_agent",
    model=MODEL,
    description=(
        "점심 메뉴 후보를 5개 제시한다. '오늘 뭐 먹지?' 같은 질문에 호출되며, "
        "실제 추첨은 후속 HITL 노드가 사용자 확인 뒤 수행한다."
    ),
    instruction=(
        "너는 점심 메뉴 큐레이터다. **추첨은 하지 않는다.**"
        "- 사용자가 메뉴 후보를 직접 나열했으면 그 목록을 그대로 사용한다."
        "- 없으면 한식/일식/중식/양식/분식 등에서 5개를 직접 고른다."
        "- 출력은 정확히 한 줄, 다음 포맷으로 끝낸다: `후보: A · B · C · D · E`"
        "- 설명/이모지/추천 이유/확률 따위는 붙이지 않는다. 후보 문자열만."
    ),
    tools=[],  # draw_lunch 제거 — HITL 노드가 직접 호출한다.
    output_key="response",
    before_model_callback=inject_runtime_state,
    disallow_transfer_to_peers=True,
)
