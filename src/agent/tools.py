"""ADK 2.0 FunctionTool 래퍼.

기존 `src/tools/*` 모듈을 LLM 이 호출 가능한 도구로 포장한다.
각 함수의 **docstring 이 곧 LLM 의 tool schema** 가 되므로, 반드시 언제 쓰는지
`Args`/`Returns` 를 구체적으로 쓴다 (PlanReActPlanner 가 plan 단계에서 읽는다).

`user_id` 는 세션 상태(`state['user_id']`) 에서 읽으며, 서브에이전트/툴 모두
같은 규칙을 따른다. `/api/chat` 엔드포인트에서 세션 최초 생성 시 주입된다.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool, ToolContext

from src.db.session import SessionLocal
from src.db.models import User, PetProfile
from src.tools import bus_api, map_api, lunch_roulette, calendar_api
from src.tools.system_monitor import SystemMonitor
from src.agent.hitl import GetInput
from google.adk.events import RequestInput

logger = logging.getLogger(__name__)


# ---------- helpers ---------------------------------------------------------
def _session_state(tool_context: ToolContext) -> Dict[str, Any]:
    try:
        return tool_context.get_invocation_context().session.state  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return {}


def _resolve_user_id(tool_context: ToolContext) -> Optional[int]:
    st = _session_state(tool_context)
    uid = st.get("user_id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def _fetch_user(tool_context: ToolContext) -> Optional[User]:
    uid = _resolve_user_id(tool_context)
    if uid is None:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == uid).first()
    finally:
        db.close()


# ---------- 1) Bus ----------------------------------------------------------
async def get_bus_arrival(
    stop_id: Optional[str] = None,
    route_filter: Optional[str] = None,
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """서울 시내버스 정류소의 실시간 도착 정보를 반환한다.

    사용자가 "우리 회사 버스 언제 와?", "7211번 몇 분 남았어?" 처럼 버스 도착을 물을 때 호출.
    정류소 ID 가 주어지지 않으면 사용자 프로필(`auth.users.bus_stop_id`) 을 사용한다.

    Args:
        stop_id: 5자리 ARS 정류소 번호 (예: "12121"). 없으면 사용자 등록 정류소 사용.
        route_filter: 특정 노선만 필터링 ("7211" 또는 "7211,146"). 비우면 전체.

    Returns:
        {stop_name, stop_id, arrivals: [{route, minutes, seat, stop_count, congestion, ...}]}
    """
    if not stop_id:
        user = _fetch_user(tool_context)
        stop_id = getattr(user, "bus_stop_id", None) if user else None
        if not stop_id:
            return {
                "error": "no_stop_id",
                "message": "등록된 정류소가 없어요. 사용자에게 정류소 ARS 번호를 물어봐 주세요.",
            }
        if not route_filter:
            route_filter = getattr(user, "bus_route_id", None)
    return await bus_api.get_arrival(stop_id, route_filter)


async def search_bus_stations(query: str) -> Dict[str, Any]:
    """정류소 이름 또는 ARS 번호로 정류소를 검색한다.

    사용자가 "강남역 정류장 번호 뭐야?" 같이 정류소를 찾고 싶을 때 호출.

    Args:
        query: "강남역", "12121" 처럼 이름 또는 5자리 ARS 번호.

    Returns:
        {stations: [{ars_id, name, lat, lng, ...}]}
    """
    stations = await bus_api.search_stations(query)
    return {"stations": stations}


# ---------- 2) Cafe / Places -----------------------------------------------
async def search_nearby_places(
    category: str = "cafe",
    radius_m: int = 500,
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """회사 좌표 기준 반경 내 카페/식당을 검색한다 (Kakao Local).

    사용자가 "근처 커피 어디가 좋아?" 같은 질문을 하면 호출.

    Args:
        category: "cafe" 또는 "food".
        radius_m: 반경(미터). 기본 500.

    Returns:
        {places: [{name, category, distance_m, address, lat, lng, url}], radius_m}
    """
    user = _fetch_user(tool_context)
    if not user or user.company_lat is None:
        return {
            "error": "no_company_coords",
            "message": "회사 좌표가 없어서 검색할 수 없어요. 프로필을 먼저 설정해 달라고 안내해 주세요.",
        }
    cat = "CE7" if category.lower().startswith("cafe") else "FD6"
    places = await map_api.nearby_places(
        user.company_lat, user.company_lng, radius_m=radius_m, category=cat
    )
    return {"places": places, "radius_m": radius_m, "category": cat}


# ---------- 3) Lunch --------------------------------------------------------
def draw_lunch(
    menus: Optional[List[str]] = None,
    method: Optional[str] = None,
    *,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    """점심 메뉴를 제비뽑기/사다리/룰렛으로 뽑는다.

    사용자가 "점심 뭐 먹지?" 같이 물을 때 호출. 메뉴를 명시하지 않으면 직전
    세션의 메뉴 후보를 사용하며, 기본값은 랜덤 한식/중식/일식 조합.

    Args:
        menus: ["한식", "일식", "샐러드"] 같은 후보 리스트. 비우면 기본값.
        method: "lottery" | "ladder" | "roulette". 비우면 랜덤 선택.

    Returns:
        {winner, method_label, history, ...}
    """
    uid = _resolve_user_id(tool_context) or 0
    result = lunch_roulette.draw(user_id=uid, menus=menus, method=method)
    return {**result, "history": lunch_roulette.recent_picks(uid)}


# ---------- 4) Calendar ----------------------------------------------------
def get_calendar_events(hours: int = 4) -> Dict[str, Any]:
    """앞으로 N시간 이내의 캘린더 일정을 조회한다.

    사용자가 "회의 있어?", "오후 일정 알려줘" 같은 질문을 할 때 호출.

    Args:
        hours: 조회 범위(시간). 기본 4.

    Returns:
        {events: [{summary, start, end, location}]}
    """
    return {"events": calendar_api.upcoming_events(hours=hours)}


# ---------- 5) Pet & System (진단용) ---------------------------------------
def get_pet_status(*, tool_context: ToolContext) -> Dict[str, Any]:
    """사용자의 현재 펫 상태(레벨/EXP/무드/스트레스)를 반환한다.

    사용자가 "너 지금 어때?", "펫 레벨 알려줘" 같은 자기 참조형 질문을 할 때 호출.

    Returns:
        {species, nickname, level, exp, mood, stress, exp_to_next_level}
    """
    uid = _resolve_user_id(tool_context)
    if uid is None:
        return {"error": "no_user"}
    db = SessionLocal()
    try:
        pet = db.query(PetProfile).filter(PetProfile.user_id == uid).first()
        if not pet:
            return {"error": "no_pet"}
        return {
            "species": pet.species,
            "nickname": pet.nickname,
            "level": pet.level,
            "exp": pet.exp,
            "mood": pet.mood,
            "stress": pet.stress,
            "exp_to_next_level": max(0, pet.level * 100 - pet.exp),
        }
    finally:
        db.close()


def get_activity_snapshot() -> Dict[str, Any]:
    """현재 사용자의 실시간 PC 활동 스냅샷을 반환한다.

    사용자가 "나 지금 집중하고 있어?", "CPU 얼마나 써?" 같은 질문을 할 때,
    또는 WellnessCoach 가 피로도를 판단할 때 호출. 호출해도 카운터는 리셋되지 않는다.

    Returns:
        {cpu_percent, mem_percent, click_count, key_count, active_tabs, focus_score}
    """
    mon = SystemMonitor.instance()
    mon.start()  # idempotent
    snap = mon.peek_snapshot()
    # click/key 가 일정 시간 누적됐으면 focused 로 간주
    score = 0
    try:
        if snap.get("cpu_percent", 0) >= 40:
            score += 30
        if snap.get("click_count", 0) + snap.get("key_count", 0) >= 50:
            score += 40
        if snap.get("mem_percent", 0) >= 70:
            score += 20
    except Exception:  # noqa: BLE001
        pass
    snap["focus_score"] = min(100, score)
    return snap


def get_user_profile(*, tool_context: ToolContext) -> Dict[str, Any]:
    """사용자 프로필(이름/직군/성향/회사 좌표 등)을 반환한다.

    에이전트가 자기소개나 맞춤 조언을 할 때 참조하기 위해 호출한다.
    """
    u = _fetch_user(tool_context)
    if not u:
        return {"error": "no_user"}
    return {
        "display_name": u.display_name,
        "job_role": u.job_role,
        "dev_tendency": u.dev_tendency,
        "gender": u.gender,
        "age": u.age,
        "company_lat": u.company_lat,
        "company_lng": u.company_lng,
        "company_address": u.company_address,
        "bus_stop_id": u.bus_stop_id,
        "bus_route_id": u.bus_route_id,
    }


async def ask_user(
    message: str,
    *,
    tool_context: ToolContext,
) -> str:
    """사용자에게 질문을 던져 추가 정보를 요청합니다.
    정류소 번호를 모르거나, 구체적인 조건이 필요할 때 등 LLM이 직접 물어봐야 할 때 사용
    Args:
        message: 사용자에게 보여줄 질문 메시지 (예: "어느 정류소 정보를 알려드릴까요?")

    Returns:
        사용자가 입력한 텍스트 응답.
    """
    ctx = tool_context.get_invocation_context()
    request = RequestInput(message=message)
    # GetInput 노드를 동적으로 실행하여 사용자의 응답을 기다림
    response = await ctx.run_node(GetInput(request, name="hitl_ask_user"))
    return str(response)


# ---------- FunctionTool 래핑 ----------------------------------------------
bus_arrival_tool = FunctionTool(get_bus_arrival)
bus_search_tool = FunctionTool(search_bus_stations)
cafe_tool = FunctionTool(search_nearby_places)
lunch_tool = FunctionTool(draw_lunch)
calendar_tool = FunctionTool(get_calendar_events)
pet_status_tool = FunctionTool(get_pet_status)
activity_tool = FunctionTool(get_activity_snapshot)
profile_tool = FunctionTool(get_user_profile)
ask_user_tool = FunctionTool(ask_user)


__all__ = [
    "bus_arrival_tool",
    "bus_search_tool",
    "cafe_tool",
    "lunch_tool",
    "calendar_tool",
    "pet_status_tool",
    "activity_tool",
    "profile_tool",
    "ask_user_tool",
]
