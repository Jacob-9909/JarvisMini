"""HITL 노드 단위 테스트 — 라우터/워크플로우 연결 없이 노드 로직만 검증.

각 노드는 async generator 로 ``Event`` 또는 ``RequestInput`` 을 yield 한다.
실제 Workflow 를 돌리지 않고 generator 를 직접 소비해 yield 순서·페이로드·
state 쓰기를 확인한다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from google.adk import Event
from google.adk.events import RequestInput

from src.agent import calendar_hitl, lunch_hitl


# ---------------------------------------------------------------------------
# 경량 ctx 더블 — ctx.state.get / ctx.state["k"]=v 만 흉내낸다.
# ---------------------------------------------------------------------------
@dataclass
class _FakeState:
    data: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.data


@dataclass
class _FakeCtx:
    state: _FakeState = field(default_factory=_FakeState)


async def _collect(agen) -> List[Any]:
    out: List[Any] = []
    async for item in agen:
        out.append(item)
        # Event(state=...) 의 상태 변화를 ctx 에 수동 반영 (Workflow 가 하는 일을 흉내).
    return out


def _apply_state_events(ctx: _FakeCtx, events: List[Any]) -> None:
    """yielded Event 중 state_delta 가 있는 것을 ctx.state 에 복사."""
    for ev in events:
        if isinstance(ev, Event) and ev.actions and ev.actions.state_delta:
            for k, v in ev.actions.state_delta.items():
                ctx.state[k] = v


# ---------------------------------------------------------------------------
# Lunch HITL
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lunch_candidates_parses_and_requests_input():
    ctx = _FakeCtx()
    agent_response = "후보: 김치찌개 · 초밥 · 마라탕 · 돈까스 · 라멘"

    events = await _collect(lunch_hitl.lunch_candidates_node(ctx, agent_response))
    _apply_state_events(ctx, events)

    assert len(events) == 2
    assert isinstance(events[0], Event)
    assert ctx.state.get("lunch_candidates") == [
        "김치찌개", "초밥", "마라탕", "돈까스", "라멘"
    ]
    assert ctx.state.get("lunch_agent_text") == agent_response

    req = events[1]
    assert isinstance(req, RequestInput)
    assert "accept" in (req.message or "")
    assert req.payload and req.payload.get("candidates")


@pytest.mark.asyncio
async def test_lunch_candidates_falls_back_to_defaults():
    ctx = _FakeCtx()

    events = await _collect(lunch_hitl.lunch_candidates_node(ctx, ""))
    _apply_state_events(ctx, events)

    assert ctx.state.get("lunch_candidates") == lunch_hitl._DEFAULT_MENUS


@pytest.mark.asyncio
async def test_lunch_draw_parses_agent_text_and_draws(monkeypatch):
    ctx = _FakeCtx()
    ctx.state["user_id"] = 42

    def _fake_draw(*, user_id: int, menus: List[str]) -> Dict[str, Any]:
        assert user_id == 42
        assert menus == ["김밥", "라면", "떡볶이"]
        return {"winner": "떡볶이", "method": "roulette", "method_label": "룰렛"}

    monkeypatch.setattr(lunch_hitl.lunch_roulette, "draw", _fake_draw)

    agent_text = "후보: 김밥 · 라면 · 떡볶이"
    events = await _collect(lunch_hitl.lunch_draw_node(ctx, agent_text))
    _apply_state_events(ctx, events)

    assert len(events) == 1
    assert ctx.state.get("lunch_winner") == "떡볶이"
    assert ctx.state.get("lunch_candidates") == ["김밥", "라면", "떡볶이"]
    assert ctx.state.get("pending_lunch_status") == "accepted"
    ev = events[0]
    assert isinstance(ev, Event)
    assert ev.output.get("lunch_status") == "accepted"
    assert "떡볶이" in (ev.output.get("response") or "")


@pytest.mark.asyncio
async def test_lunch_draw_falls_back_to_state_candidates(monkeypatch):
    ctx = _FakeCtx()
    ctx.state["lunch_candidates"] = ["A", "B"]
    ctx.state["user_id"] = 1

    captured: Dict[str, Any] = {}

    def _fake_draw(*, user_id: int, menus: List[str]) -> Dict[str, Any]:
        captured["menus"] = menus
        return {"winner": menus[0], "method_label": "룰렛"}

    monkeypatch.setattr(lunch_hitl.lunch_roulette, "draw", _fake_draw)

    events = await _collect(lunch_hitl.lunch_draw_node(ctx, ""))
    _apply_state_events(ctx, events)

    assert captured["menus"] == ["A", "B"]


@pytest.mark.asyncio
async def test_lunch_finalize_accept_emits_final_text():
    ctx = _FakeCtx()
    ctx.state["lunch_candidates"] = ["A", "B"]
    ctx.state["lunch_winner"] = "돈까스"
    ctx.state["lunch_method"] = "룰렛"

    events = await _collect(lunch_hitl.lunch_finalize_node(ctx, "accept"))
    _apply_state_events(ctx, events)

    assert len(events) == 1
    ev = events[0]
    assert ev.output["lunch_status"] == "accepted"
    assert "돈까스" in ev.output["response"]
    assert ctx.state.get("pending_lunch_status") == "accepted"


@pytest.mark.asyncio
async def test_lunch_finalize_reroll_redraws(monkeypatch):
    ctx = _FakeCtx()
    ctx.state["lunch_candidates"] = ["A", "B"]
    ctx.state["lunch_winner"] = "A"
    ctx.state["lunch_method"] = "룰렛"
    ctx.state["user_id"] = 1

    monkeypatch.setattr(
        lunch_hitl.lunch_roulette,
        "draw",
        lambda *, user_id, menus: {"winner": "B", "method_label": "사다리"},
    )

    events = await _collect(lunch_hitl.lunch_finalize_node(ctx, "reroll"))
    _apply_state_events(ctx, events)

    ev = events[0]
    assert ev.output["lunch_status"] == "rerolled"
    assert ev.output["winner"] == "B"
    assert ctx.state.get("pending_lunch_status") == "rerolled"


# ---------------------------------------------------------------------------
# Calendar HITL
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_calendar_reminder_with_events_requests_input():
    ctx = _FakeCtx()
    schedule = "🗓 14:00 팀 회의 (회의실 A)\n🗓 16:00 1:1"

    events = await _collect(calendar_hitl.calendar_reminder_node(ctx, schedule))
    _apply_state_events(ctx, events)

    assert isinstance(events[-1], RequestInput)
    assert ctx.state.get("calendar_agent_text") == schedule


@pytest.mark.asyncio
async def test_calendar_reminder_no_events_skips_interrupt():
    ctx = _FakeCtx()
    schedule = "이 범위 안에는 일정이 없어요"

    events = await _collect(calendar_hitl.calendar_reminder_node(ctx, schedule))
    _apply_state_events(ctx, events)

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, Event)
    assert ev.output["calendar_status"] == "no_events"
    assert ctx.state.get("pending_calendar_status") == "no_events"


@pytest.mark.asyncio
async def test_calendar_finalize_yes_turns_reminder_on():
    ctx = _FakeCtx()
    ctx.state["calendar_agent_text"] = "🗓 14:00 회의"

    events = await _collect(calendar_hitl.calendar_finalize_node(ctx, "yes"))
    _apply_state_events(ctx, events)

    ev = events[0]
    assert ev.output["calendar_status"] == "reminder_on"
    assert "30분 전 알림" in ev.output["response"]
    assert ctx.state.get("pending_calendar_status") == "reminder_on"


@pytest.mark.asyncio
async def test_calendar_finalize_passthrough_on_no_events():
    ctx = _FakeCtx()
    ctx.state["pending_calendar_status"] = "no_events"

    passthrough_input = {
        "response": "이 범위 안에는 일정이 없어요.",
        "calendar_status": "no_events",
    }
    events = await _collect(
        calendar_hitl.calendar_finalize_node(ctx, passthrough_input)
    )

    ev = events[0]
    assert ev.output["calendar_status"] == "no_events"
    assert ev.output["response"] == "이 범위 안에는 일정이 없어요."


# ---------------------------------------------------------------------------
# conftest-less asyncio 지원 — pytest-asyncio 플러그인 없을 때도 돌게.
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(config, items):  # pragma: no cover
    pass
