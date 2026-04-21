from __future__ import annotations

import time
from typing import Dict

from google.adk import Event

from src.schema.state import DashboardResult
from src.tools import bus_api, calendar_api, lunch_roulette, map_api
from src.tools.pet import Pet
from src.workflow.context import InitResult, StateBundle
from src.workflow.helpers import log_node, session_id


async def dashboard_node(ctx, node_input: InitResult) -> Event:
    started = time.perf_counter()
    user = node_input.user
    action = node_input.action
    payload = node_input.payload or {}
    title = action
    lines: list[str] = []
    data: Dict[str, object] = {}

    if action == "bus":
        if not user.bus_stop_id:
            lines = ["🚌 등록된 정류장이 없어요. 프로필에서 bus_stop_id 를 설정해 주세요."]
        else:
            info = await bus_api.get_arrival(user.bus_stop_id, user.bus_route_id)
            arrivals = info.get("arrivals", [])
            stop_name = info.get("stop_name") or user.bus_stop_id
            title = f"실시간 버스 도착 · {stop_name}"
            lines = [
                f"🚌 {a.get('route','-')}번 · {a['minutes']}분 · {a.get('seat','-')}"
                for a in arrivals
            ] or ["도착 예정 버스가 없습니다."]
            data = info
    elif action == "cafe":
        if user.company_lat is None:
            lines = ["📍 회사 좌표가 비어있어요. 프로필을 먼저 채워 주세요."]
        else:
            places = await map_api.nearby_places(
                user.company_lat, user.company_lng, radius_m=500, category="CE7"
            )
            title = "주변 카페 레이더 (500m)"
            lines = [f"☕ {p['name']} · {p['distance_m']}m · {p['category']}" for p in places[:8]]
            data = {
                "places": places,
                "center": {
                    "lat": user.company_lat,
                    "lng": user.company_lng,
                    "label": user.display_name or "회사",
                },
                "radius_m": 500,
            }
    elif action == "lunch_roulette":
        menus_in = payload.get("menus") or []
        if isinstance(menus_in, str):
            menus_in = [m for m in menus_in.replace("\n", ",").split(",")]
        result = lunch_roulette.draw(
            user_id=user.user_id,
            menus=menus_in if isinstance(menus_in, list) else None,
            method=payload.get("method"),
        )
        title = f"🎲 {result['method_label']} · 오늘의 점심"
        lines = [f"🍽 {result['winner']}"]
        data = {**result, "history": lunch_roulette.recent_picks(user.user_id)}
    elif action == "calendar":
        events = calendar_api.upcoming_events(hours=4)
        title = "다가오는 일정 (4h)"
        lines = [f"🗓 {e['summary']} — {e['start']}" for e in events] or ["일정 없음"]
        data = {"events": events}
    elif action == "pet_interact":
        title = "펫 인터랙션"
        pet = Pet(species=node_input.pet.species, nickname=node_input.pet.nickname)
        lines = pet.frame(node_input.pet.mood) + ["", pet.say(node_input.pet.mood)]
    else:
        pet = node_input.pet
        title = "오피스 상태 보드"
        lines = [
            f"🐾 펫: {pet.species} Lv.{pet.level} · {pet.mood} · stress {pet.stress}",
            f"✨ EXP: {pet.exp} (다음 레벨까지 {pet.exp_to_next_level()})",
            f"👤 사용자: {user.display_name or user.user_id} · {user.job_role or '-'}",
        ]

    result = DashboardResult(user_id=user.user_id, action=action, title=title, lines=lines, data=data)
    log_node(session_id(ctx), user.user_id, "dashboard_node", started, route="pet_care_node")
    return Event(
        output=StateBundle(
            user=user,
            pet=node_input.pet,
            snapshot=None,
            dashboard=result,
            pending_exp=1,
            pending_stress=-1,
            source="dashboard",
        )
    )
