"""펫/시스템/프로필 자기 참조 툴 — 에이전트가 자기 상태·사용자 정보를 읽을 때 사용."""

from __future__ import annotations

from typing import Any, Dict

from google.adk.tools import FunctionTool, ToolContext

from src.agent.tools._context import fetch_pet, fetch_user
from src.db.models import PetProfile, User
from src.tools.system_monitor import SystemMonitor


def _pet_to_dict(pet: PetProfile) -> Dict[str, Any]:
    return {
        "species": pet.species,
        "nickname": pet.nickname,
        "level": pet.level,
        "exp": pet.exp,
        "mood": pet.mood,
        "stress": pet.stress,
        "exp_to_next_level": max(0, pet.level * 100 - pet.exp),
    }


def _user_to_dict(u: User) -> Dict[str, Any]:
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


def _focus_score(snap: Dict[str, Any]) -> int:
    """click/key 누적량 + CPU/RAM 사용률로 0-100 집중도 점수 추정."""
    score = 0
    try:
        if snap.get("cpu_percent", 0) >= 40:
            score += 30
        if snap.get("click_count", 0) + snap.get("key_count", 0) >= 50:
            score += 40
        if snap.get("mem_percent", 0) >= 70:
            score += 20
    except Exception:
        pass
    return min(100, score)


def get_pet_status(*, tool_context: ToolContext) -> Dict[str, Any]:
    """사용자의 현재 펫 상태(레벨/EXP/무드/스트레스)를 반환한다.

    사용자가 "너 지금 어때?", "펫 레벨 알려줘" 같은 자기 참조형 질문을 할 때 호출.

    Returns:
        {species, nickname, level, exp, mood, stress, exp_to_next_level}
    """
    pet = fetch_pet(tool_context)
    if pet is None:
        return {"error": "no_pet_or_user"}
    return _pet_to_dict(pet)


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
    snap["focus_score"] = _focus_score(snap)
    return snap


def get_user_profile(*, tool_context: ToolContext) -> Dict[str, Any]:
    """사용자 프로필(이름/직군/성향/회사 좌표 등)을 반환한다.

    에이전트가 자기소개나 맞춤 조언을 할 때 참조하기 위해 호출한다.
    """
    u = fetch_user(tool_context)
    if u is None:
        return {"error": "no_user"}
    return _user_to_dict(u)


pet_status_tool = FunctionTool(get_pet_status)
activity_tool = FunctionTool(get_activity_snapshot)
profile_tool = FunctionTool(get_user_profile)

__all__ = ["pet_status_tool", "activity_tool", "profile_tool"]
