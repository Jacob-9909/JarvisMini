"""시스템 모니터 샘플 → 활동 로그 저장 → 펫 경험치 반영.

워크플로의 `system_monitor_node` + `pet_care_node`(monitor 출처)와
웹 서버 백그라운드 루프가 **동일한 규칙**을 쓰도록 공통화한다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import psutil

from src.db.models import ActivityLog, PetProfile, User
from src.db.session import SessionLocal
from src.schema.state import PetCareResult, PetStatus, SystemSnapshot, UserContext
from src.tools.pet import pick_species_for
from src.tools.system_monitor import SystemMonitor

logger = logging.getLogger(__name__)


def snapshot_from_dict(snap_dict: Dict[str, Any]) -> SystemSnapshot:
    return SystemSnapshot(
        ts=snap_dict["ts"],
        cpu_percent=float(snap_dict.get("cpu_percent") or 0.0),
        mem_percent=float(snap_dict.get("mem_percent") or 0.0),
        click_count=int(snap_dict.get("click_count") or 0),
        key_count=int(snap_dict.get("key_count") or 0),
        active_tabs=int(snap_dict.get("active_tabs") or 0),
        top_processes=list(snap_dict.get("top_processes") or []),
        screen_active_sec=int(snap_dict.get("screen_active_sec") or 0),
    )


def compute_exp_stress_deltas(
    snap_dict: Dict[str, Any], snapshot: SystemSnapshot
) -> Tuple[int, int]:
    exp_gain = 0
    stress_delta = 0
    activity = snapshot.click_count + snapshot.key_count
    if activity >= 200:
        exp_gain += 20
    elif activity >= 50:
        exp_gain += 8
    elif activity > 0:
        exp_gain += 3

    if snap_dict.get("heavy_ide"):
        exp_gain += 10
    if snapshot.active_tabs >= 20:
        stress_delta += 15
    elif snapshot.active_tabs >= 12:
        stress_delta += 5
    if snapshot.mem_percent >= 90:
        stress_delta += 10
    elif snapshot.mem_percent >= 75:
        stress_delta += 3
    return exp_gain, stress_delta


def persist_activity_log(
    user_id: int,
    snapshot: SystemSnapshot,
    exp_gain: int,
    stress_delta: int,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            ActivityLog(
                user_id=user_id,
                ts=snapshot.ts,
                click_count=snapshot.click_count,
                key_count=snapshot.key_count,
                active_tabs=snapshot.active_tabs,
                cpu_percent=snapshot.cpu_percent,
                mem_percent=snapshot.mem_percent,
                top_processes=snapshot.top_processes,
                screen_active_sec=snapshot.screen_active_sec,
                computed_exp_gain=exp_gain,
                computed_stress_delta=stress_delta,
            )
        )
        db.commit()
    except Exception as e:
        logger.warning("ActivityLog write failed: %s", e)
    finally:
        db.close()


def user_row_to_context(u: User) -> UserContext:
    return UserContext(
        user_id=u.id,
        display_name=u.display_name,
        job_role=u.job_role,
        dev_tendency=u.dev_tendency,
        company_lat=u.company_lat,
        company_lng=u.company_lng,
        bus_stop_id=u.bus_stop_id,
        bus_route_id=u.bus_route_id,
    )


def pet_row_to_status(p: PetProfile) -> PetStatus:
    return PetStatus(
        species=p.species,  # type: ignore[arg-type]
        nickname=p.nickname,
        level=p.level,
        exp=p.exp,
        mood=p.mood,  # type: ignore[arg-type]
        stress=p.stress,
    )


def apply_pet_care_deltas(
    user_id: int,
    user_ctx: UserContext,
    pet: PetStatus,
    pending_exp: int,
    pending_stress: int,
    source: str,
) -> PetCareResult:
    """DB 의 PetProfile 을 갱신하고 PetCareResult 반환."""
    new_exp = pet.exp + pending_exp
    new_stress = max(0, min(100, pet.stress + pending_stress))

    leveled_up = False
    threshold = pet.level * 100
    level = pet.level
    if new_exp >= threshold:
        level += 1
        new_exp -= threshold
        leveled_up = True

    if new_stress >= 70:
        mood = "stressed"
    elif new_stress >= 40:
        mood = "tired"
    elif source == "monitor" and pending_exp >= 15:
        mood = "focused"
    elif leveled_up:
        mood = "happy"
    else:
        mood = "neutral"

    evolved_to = None
    species = pet.species
    if species == "egg" and level >= 2:
        species = pick_species_for(user_ctx.job_role, user_ctx.dev_tendency)
        evolved_to = species
    elif (
        level >= 5
        and species != "dragon"
        and (user_ctx.job_role or "").lower() in {"ai", "infra", "ml"}
    ):
        species = "dragon"
        evolved_to = "dragon"

    db = SessionLocal()
    try:
        row = db.query(PetProfile).filter(PetProfile.user_id == user_id).first()
        if row:
            row.exp = new_exp
            row.level = level
            row.stress = new_stress
            row.mood = mood
            row.species = species
            row.last_fed_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.warning("PetProfile update failed: %s", e)
    finally:
        db.close()

    return PetCareResult(
        user_id=user_id,
        exp_gain=pending_exp,
        stress_delta=pending_stress,
        mood=mood,
        leveled_up=leveled_up,
        evolved_to=evolved_to,
        message=(
            f"{'✨ 레벨업! ' if leveled_up else ''}"
            f"{'🔥 진화했어요!' if evolved_to else ''}"
        ).strip()
        or None,
    )


def run_monitor_tick_for_user(user_id: int) -> Optional[PetCareResult]:
    """전역 클릭/키보드(psutil) 샘플 1회 → 로그 저장 → 펫 EXP 반영.

    웹 서버 백그라운드·스케줄러에서 공통으로 호출 가능.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        pet = db.query(PetProfile).filter(PetProfile.user_id == user_id).first()
        if not user or not pet:
            logger.warning("run_monitor_tick: missing user or pet row user_id=%s", user_id)
            return None
        user_ctx = user_row_to_context(user)
        pet_status = pet_row_to_status(pet)
    finally:
        db.close()

    mon = SystemMonitor.instance()
    mon.start()
    snap_dict = mon.get_snapshot_and_reset()
    snapshot = snapshot_from_dict(snap_dict)
    exp_gain, stress_delta = compute_exp_stress_deltas(snap_dict, snapshot)
    persist_activity_log(user_id, snapshot, exp_gain, stress_delta)

    return apply_pet_care_deltas(
        user_id,
        user_ctx,
        pet_status,
        exp_gain,
        stress_delta,
        source="monitor",
    )


def read_live_cpu_mem() -> Tuple[float, float]:
    """UI용 CPU·RAM (%).

    `cpu_percent(interval=None)` 는 첫 호출·짧은 간격에서 거의 항상 0 이라
    (psutil 문서상 '무시하라'는 값) 워커 캐시를 우선 쓰고, 그래도 0이면
    짧은 블로킹 샘플로 한 번 더 잰다. RAM 은 `virtual_memory()` 가 항상 유효.
    """
    mem = float(psutil.virtual_memory().percent)

    mon = SystemMonitor.instance()
    mon.start()
    cpu_cached, _mem_cached = mon.get_latest_cpu_mem()

    cpu = float(cpu_cached)
    if cpu <= 0.0:
        cpu = float(psutil.cpu_percent(interval=0.12))

    return cpu, mem
