from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from google.adk import Event
from google.adk.events import RequestInput

from src.agent import router
from src.schema.chat import ChatRouteInput


@dataclass
class _FakeState:
    data: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value


@dataclass
class _FakeCtx:
    state: _FakeState = field(default_factory=_FakeState)


async def _collect(agen) -> List[Any]:
    out: List[Any] = []
    async for item in agen:
        out.append(item)
    return out


def _apply_state_events(ctx: _FakeCtx, events: List[Any]) -> None:
    for ev in events:
        if isinstance(ev, Event) and ev.actions and ev.actions.state_delta:
            for k, v in ev.actions.state_delta.items():
                ctx.state[k] = v


@pytest.mark.asyncio
async def test_router_uses_llm_route(monkeypatch):
    ctx = _FakeCtx()

    async def _fake_llm(system: str, user: str, schema_cls, key: str):
        assert key == "route"
        assert "내일" in user
        return router.RouteDecision(route="calendar_agent")

    monkeypatch.setattr(router, "_llm_json", _fake_llm)

    events = await _collect(
        router.router_decide_node(ctx, ChatRouteInput(user_id=7, message="내일 뭐 있지?", route=""))
    )
    _apply_state_events(ctx, events)

    assert len(events) == 2
    assert isinstance(events[0], Event)
    assert isinstance(events[1], RequestInput)
    assert ctx.state.get("router_candidate_route") == "calendar_agent"


@pytest.mark.asyncio
async def test_router_hitl_yes_confirms_route(monkeypatch):
    ctx = _FakeCtx()
    ctx.state["router_candidate_route"] = "lunch_agent"
    ctx.state["router_original_message"] = "오늘 점심 뭐 먹지?"

    events = await _collect(
        router.router_finalize_node(ctx, ChatRouteInput(user_id=3, message="yes", route=""))
    )
    _apply_state_events(ctx, events)
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, Event)
    assert ev.output.route == "lunch_agent"
    assert ev.output.message == "오늘 점심 뭐 먹지?"


@pytest.mark.asyncio
async def test_router_hitl_allows_manual_override(monkeypatch):
    ctx = _FakeCtx()
    ctx.state["router_candidate_route"] = "bus_agent"
    ctx.state["router_original_message"] = "6012 언제 와?"

    events = await _collect(
        router.router_finalize_node(
            ctx,
            ChatRouteInput(user_id=11, message="일정 질문이야", route=""),
        )
    )
    _apply_state_events(ctx, events)

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, Event)
    assert ev.output.route == "calendar_agent"
