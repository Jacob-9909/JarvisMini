from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any, Dict, Optional

from google.adk import Event, Workflow
from pydantic import BaseModel, Field

from src.db.models import User
from src.db.session import SessionLocal
from src.schema.state import PetStatus, UserContext
from src.tools import bus_api, calendar_api, lunch_roulette, map_api
from src.tools.monitor_pipeline import apply_pet_care_deltas
from src.tools.system_monitor import SystemMonitor
from src.workflow.helpers import ensure_pet_profile, log_node, session_id


class ChatInput(BaseModel):
    user_id: int
    message: str


CURRENT_CHAT_INPUT: "ContextVar[Optional[ChatInput]]" = ContextVar(
    "CURRENT_CHAT_INPUT", default=None
)


class ChatInit(BaseModel):
    user: UserContext
    pet: PetStatus
    message: str
    intent: str


class ChatBundle(BaseModel):
    user: UserContext
    pet: PetStatus
    message: str
    intent: str
    response_text: str = ""
    pending_exp: int = 0
    pending_stress: int = 0
    source: str = "chat"


def _intent_of(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["버스", "정류장", "몇분", "도착"]):
        return "bus"
    if any(k in t for k in ["카페", "커피", "맛집", "식당"]):
        return "cafe"
    if any(k in t for k in ["점심", "메뉴", "먹지", "룰렛"]):
        return "lunch"
    if any(k in t for k in ["일정", "회의", "캘린더"]):
        return "calendar"
    if any(k in t for k in ["피곤", "집중", "스트레스", "휴식", "힘들"]):
        return "wellness"
    if any(k in t for k in ["코드", "에러", "디버그", "리팩토링", "아키텍처", "adk"]):
        return "coding"
    return "general"


def init_node(ctx, node_input: Dict[str, Any] | None = None) -> Event:
    started = time.perf_counter()
    state_input = None
    try:
        state_input = ctx.state.get("input")  # type: ignore[union-attr]
    except Exception:
        pass
    src = node_input or state_input or CURRENT_CHAT_INPUT.get()
    if isinstance(src, ChatInput):
        user_id = src.user_id
        message = src.message
    else:
        src = src or {}
        user_id = int(src.get("user_id") or 0)
        message = str(src.get("message") or "")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            log_node(session_id(ctx), user_id, "chat_init", started, route="end", status="no-user")
            return Event(route=["end"])
        pet_row = ensure_pet_profile(db, user_id, user)
        user_ctx = UserContext(
            user_id=user.id,
            display_name=user.display_name,
            job_role=user.job_role,
            dev_tendency=user.dev_tendency,
            company_lat=user.company_lat,
            company_lng=user.company_lng,
            bus_stop_id=user.bus_stop_id,
            bus_route_id=user.bus_route_id,
        )
        pet = PetStatus(
            species=pet_row.species,
            nickname=pet_row.nickname,
            level=pet_row.level,
            exp=pet_row.exp,
            mood=pet_row.mood,
            stress=pet_row.stress,
        )
    finally:
        db.close()

    out = ChatInit(user=user_ctx, pet=pet, message=message, intent=_intent_of(message))
    log_node(session_id(ctx), user_id, "chat_init", started, route="chat_router", payload={"intent": out.intent})
    return Event(output=out)


def router_node(ctx, node_input: ChatInit) -> Event:
    route_map = {
        "bus": "bus_node",
        "cafe": "cafe_node",
        "lunch": "lunch_node",
        "calendar": "calendar_node",
        "wellness": "wellness_node",
        "coding": "coding_node",
    }
    route = route_map.get(node_input.intent, "general_node")
    return Event(route=[route], output=node_input)


async def bus_node(ctx, node_input: ChatInit) -> Event:
    u = node_input.user
    if not u.bus_stop_id:
        text = "등록된 정류장이 없어요. 프로필에서 정류소를 먼저 저장해 주세요."
    else:
        info = await bus_api.get_arrival(u.bus_stop_id, u.bus_route_id)
        arr = info.get("arrivals", [])
        if not arr:
            text = "지금 도착 예정 버스가 없어요."
        else:
            lines = [f"{a.get('route','-')}번 {a.get('minutes','-')}분 ({a.get('seat','-')})" for a in arr[:3]]
            text = "버스 상황이에요: " + " / ".join(lines)
    return Event(output=ChatBundle(user=u, pet=node_input.pet, message=node_input.message, intent=node_input.intent, response_text=text, pending_exp=2))


async def cafe_node(ctx, node_input: ChatInit) -> Event:
    u = node_input.user
    if u.company_lat is None:
        text = "회사 좌표가 없어서 주변 장소를 찾기 어려워요. 프로필을 먼저 채워 주세요."
    else:
        places = await map_api.nearby_places(u.company_lat, u.company_lng, radius_m=500, category="CE7")
        if not places:
            text = "근처 카페를 찾지 못했어요."
        else:
            picks = [f"{p['name']}({p['distance_m']}m)" for p in places[:3]]
            text = "근처 카페 추천: " + ", ".join(picks)
    return Event(output=ChatBundle(user=u, pet=node_input.pet, message=node_input.message, intent=node_input.intent, response_text=text, pending_exp=2))


def lunch_node(ctx, node_input: ChatInit) -> Event:
    result = lunch_roulette.draw(user_id=node_input.user.user_id)
    text = f"오늘 점심은 {result.get('winner','추천 없음')} 어때요? ({result.get('method_label','랜덤')})"
    return Event(output=ChatBundle(user=node_input.user, pet=node_input.pet, message=node_input.message, intent=node_input.intent, response_text=text, pending_exp=3, pending_stress=-2))


def calendar_node(ctx, node_input: ChatInit) -> Event:
    events = calendar_api.upcoming_events(hours=4)
    if not events:
        text = "앞으로 4시간 내 일정은 없어요."
    else:
        text = "다가오는 일정: " + " / ".join(f"{e.get('summary','(제목없음)')}({e.get('start','-')})" for e in events[:3])
    return Event(output=ChatBundle(user=node_input.user, pet=node_input.pet, message=node_input.message, intent=node_input.intent, response_text=text, pending_exp=1, pending_stress=1))


def wellness_node(ctx, node_input: ChatInit) -> Event:
    mon = SystemMonitor.instance()
    mon.start()
    snap = mon.peek_snapshot()
    text = (
        f"지금 CPU {snap.get('cpu_percent',0):.0f}% / RAM {snap.get('mem_percent',0):.0f}% / "
        f"탭 {snap.get('active_tabs',0)}개예요. 25분 집중 + 5분 휴식 루틴 추천해요."
    )
    return Event(output=ChatBundle(user=node_input.user, pet=node_input.pet, message=node_input.message, intent=node_input.intent, response_text=text, pending_exp=1, pending_stress=-3))


def coding_node(ctx, node_input: ChatInit) -> Event:
    text = (
        "좋아요. 문제를 1) 재현조건 2) 기대동작 3) 실제로그 로 나눠서 보내주면 "
        "원인 후보를 빠르게 좁혀볼게요."
    )
    return Event(output=ChatBundle(user=node_input.user, pet=node_input.pet, message=node_input.message, intent=node_input.intent, response_text=text, pending_exp=1))


def general_node(ctx, node_input: ChatInit) -> Event:
    name = node_input.user.display_name or "사용자"
    text = f"{name}님, 버스/카페/점심/일정/컨디션/코딩 중에서 무엇을 도와드릴까요?"
    return Event(output=ChatBundle(user=node_input.user, pet=node_input.pet, message=node_input.message, intent=node_input.intent, response_text=text))


def pet_care_node(ctx, node_input: ChatBundle) -> Event:
    care = apply_pet_care_deltas(
        node_input.user.user_id,
        node_input.user,
        node_input.pet,
        node_input.pending_exp,
        node_input.pending_stress,
        node_input.source,
    )
    return Event(
        output={
            "text": node_input.response_text,
            "intent": node_input.intent,
            "care": care.model_dump(),
        }
    )


def end_node(ctx, node_input: Any) -> Event:
    return Event(message="ok")


chat_root_agent = Workflow(
    name="smart_office_chat_workflow",
    edges=[
        ("START", init_node, router_node),
        (
            router_node,
            {
                "bus_node": bus_node,
                "cafe_node": cafe_node,
                "lunch_node": lunch_node,
                "calendar_node": calendar_node,
                "wellness_node": wellness_node,
                "coding_node": coding_node,
                "general_node": general_node,
                "end": end_node,
            },
        ),
        (bus_node, pet_care_node),
        (cafe_node, pet_care_node),
        (lunch_node, pet_care_node),
        (calendar_node, pet_care_node),
        (wellness_node, pet_care_node),
        (coding_node, pet_care_node),
        (general_node, pet_care_node),
        (pet_care_node, end_node),
    ],
)

