from __future__ import annotations

import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)

from google.adk import Event

from src.schema.state import DashboardResult
from src.tools import bus_api, calendar_api, lunch_roulette
from src.tools.kakao_map_links import SUBWAY_REGIONS, kakao_subway_directions
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
    elif action == "directions":
        title = "전철 길찾기"
        p = payload or {}
        from_station = str(p.get("from_station") or p.get("from") or "").strip()
        to_station = str(p.get("to_station") or p.get("to") or "").strip()
        region_raw = str(p.get("region") or "seoul").strip().lower()
        region = region_raw if region_raw in SUBWAY_REGIONS else "seoul"
        base_data: Dict[str, object] = {
            "region": region,
            "regions": list(SUBWAY_REGIONS),
            "last_from": from_station,
            "last_to": to_station,
        }
        if not from_station or not to_station:
            lines = [
                "🚉 출발역과 도착역을 모두 입력해 주세요.",
                "예) 출발: 회기역, 도착: 강남역",
            ]
            data = {**base_data, "needs_query": True}
        else:
            url = kakao_subway_directions(from_station, to_station, region=region)  # type: ignore[arg-type]
            lines = [
                f"🚉 {from_station} → {to_station} ({region})",
                "카카오맵 지하철 길찾기에서 노선·환승·소요시간을 확인하세요.",
            ]
            data = {
                **base_data,
                "kakao_url": url,
                "needs_query": False,
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
        bundle = calendar_api.week_bundle()
        events = bundle["events"]
        wk = bundle.get("week") or {}
        title = f"이번 주 일정 ({wk.get('start_date', '')} ~ {wk.get('end_date', '')})"
        lines = [f"🗓 {e['summary']} — {e['start']}" for e in events] or ["이번 주 일정 없음"]
        data = bundle
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
