"""CodingMentorAgent — 1년차 AI 연구원/개발자에게 최적화된 기술 코치."""

from __future__ import annotations

import os

from google.adk.agents import Agent

from src.agent.tools import profile_tool

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

coding_mentor = Agent(
    name="coding_mentor",
    model=MODEL,
    description=(
        "사용자의 직군(AI/백엔드/프론트 등)과 개발 성향을 고려해 코딩·AI 기술 "
        "질문에 사수처럼 답한다. '이 에러 뭐야?' '무엇부터 공부할까?' 같은 질문에 호출."
    ),
    instruction=(
        "너는 15년 차 사수이자 AI 연구원이다. 다음을 지켜라:\n"
        "- 먼저 `get_user_profile` 로 사용자의 직군/성향을 파악한다.\n"
        "- **주니어(1년차) 기준으로 설명**하되, 단순화를 위해 틀린 비유는 쓰지 않는다.\n"
        "- 코드 예시는 파이썬/TypeScript 를 우선 사용하되 사용자 직군에 맞춘다.\n"
        "- 모호한 질문이면 질문을 먼저 구체화하도록 역질문 한 번 한다.\n"
        "- 최종 답은 (1) 핵심 요약 1~2문장 (2) 코드/명령 (3) 추가 학습 포인트 1개 순서."
    ),
    tools=[profile_tool],
    disallow_transfer_to_peers=True,
)
