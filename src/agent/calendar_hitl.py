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
        return str(node_input.get("response") or node_input.get("result") or "")
    return str(node_input)


def _has(text: str, keywords: tuple[str, ...]) -> bool: # 텍스트에 키워드가 포함되어 있는지 확인
    low = (text or "").lower().strip()
    return any(k in low for k in keywords)


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

    yield RequestInput(
        message=(
            f"{raw}\n\n"
            "⏰ 가장 가까운 일정 30분 전 알림 받을까요?\n"
            "- **yes** : 알림 설정\n"
            "- **no** : 조회만"
        ),
        payload={"events_summary": raw[:800]},
    )


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
