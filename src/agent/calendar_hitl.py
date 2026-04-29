"""Calendar HITL nodes."""

from __future__ import annotations

import re
from typing import Any

from google.adk import Event
from google.adk.events import RequestInput

_YES_KEYS = ("yes", "예", "네", "좋", "ok", "오케", "응", "해줘", "설정")
_NO_KEYS = ("no", "아니", "안 받", "괜찮", "패스", "skip", "나중", "됐")

_EVENT_LINE_RE = re.compile(r"(\d{1,2}[:시])|🗓|🕘|🕑|📅")


def _text(node_input: Any) -> str: # 노드 입력을 텍스트로 변환
    if node_input is None:
        return ""
    if isinstance(node_input, dict):
        # response, result, message 등 다양한 키 대응
        return str(
            node_input.get("response")
            or node_input.get("result")
            or node_input.get("message")
            or node_input.get("content")
            or ""
        )
    # GenAI Content/Part 객체 등 문자열 변환 시도
    return str(node_input).strip()


def _has(text: str, keywords: tuple[str, ...]) -> bool: # 텍스트에 키워드가 포함되어 있는지 확인
    # 특수문자 제거 및 소문자 정규화 후 비교
    clean = re.sub(r"[^\w\s]", "", (text or "").lower()).strip()
    return any(k in clean for k in keywords) or any(k in (text or "").lower() for k in keywords)


def _has_events(text: str) -> bool: # 텍스트에 일정이 포함되어 있는지 확인
    return bool(text and not re.search(r"일정\s*(이|은)?\s*없", text) and _EVENT_LINE_RE.search(text))


async def calendar_reminder_node(ctx, node_input: Any): # 일정 요약 노드
    raw = _text(node_input)

    if not _has_events(raw):
        yield Event(
            state={
                "calendar_agent_text": raw,
                "pending_calendar_status": "no_events",
            },
            output={
                "response": raw or "이 범위 안에는 일정이 없어요.",
                "calendar_status": "no_events",
            },
        )
        return

    yield Event(state={"calendar_agent_text": raw})

    # RequestInput yield 시 워크플로우가 중단됨.
    # 사용자가 답장을 보내면 이 지점에서 재개되며, yield 표현식의 결과값이 사용자 응답이 됨.
    user_response = yield RequestInput(
        message=(
            f"{raw}\n\n"
            "⏰ 가장 가까운 일정 30분 전 알림 받을까요?\n"
            "- **yes** : 알림 설정\n"
            "- **no** : 조회만"
        ),
        payload={"events_summary": raw[:800]},
    )

    # 재개된 사용자 응답을 명시적으로 output으로 내보내어 finalize_node가 받을 수 있게 함.
    yield Event(output=user_response)


async def calendar_finalize_node(ctx, node_input: Any): # 일정 요약 확정 노드
    base = str(ctx.state.get("calendar_agent_text") or "")
    prior_status = str(ctx.state.get("pending_calendar_status") or "")

    if prior_status == "no_events":
        text = _text(node_input) or base or "이 범위 안에는 일정이 없어요."
        yield Event(
            state={"pending_calendar_status": "no_events"},
            output={"response": text, "calendar_status": "no_events"},
        )
        return

    user_resp = _text(node_input)
    if _has(user_resp, _YES_KEYS):
        status = "reminder_on"
        suffix = "⏰ 가장 가까운 일정 30분 전 알림 설정했어요."
    elif _has(user_resp, _NO_KEYS):
        status = "reminder_off"
        suffix = "🔕 알림 없이 진행합니다."
    else:
        status = "reminder_off"
        suffix = "🔕 응답을 이해하지 못해 알림 없이 진행합니다."

    text = f"{base}\n\n{suffix}" if base else suffix
    yield Event(
        state={"pending_calendar_status": status},
        output={"response": text, "calendar_status": status},
    )


__all__ = [
    "calendar_reminder_node",
    "calendar_finalize_node",
]
