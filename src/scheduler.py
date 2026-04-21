"""백그라운드 스케줄러.

- 주기적 System Monitor 샘플링 (업무 활동량 수집)
- 사용자별 등록된 버스 노선 도착 임박 알림 (Slack)
- 펫 스트레스 회복 (idle decay)
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.db.session import init_db, SessionLocal
from src.db.models import User, PetProfile
from src.tools.system_monitor import SystemMonitor
from src.tools.notifier import SlackNotifier
from src.tools import bus_api
from src.tools.monitor_pipeline import run_monitor_tick_for_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

MONITOR_INTERVAL_SEC = int(os.getenv("AGENT_INTERVAL_SECONDS", "60"))
BUS_INTERVAL_SEC = int(os.getenv("BUS_INTERVAL_SECONDS", "60"))
BUS_NOTIFY_THRESHOLD_MIN = int(os.getenv("BUS_NOTIFY_THRESHOLD_MIN", "5"))
IDLE_DECAY_INTERVAL_SEC = int(os.getenv("IDLE_DECAY_INTERVAL_SECONDS", "600"))


async def tick_monitor() -> None:
    SystemMonitor.instance().start()
    db = SessionLocal()
    try:
        user_ids = [u.id for u in db.query(User).filter(User.is_active.is_(True)).all()]
    finally:
        db.close()
    for uid in user_ids:
        await asyncio.to_thread(run_monitor_tick_for_user, uid)
    logger.info("[monitor] processed %d users", len(user_ids))


async def tick_bus() -> None:
    notifier = SlackNotifier()
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(User.is_active.is_(True), User.bus_stop_id.isnot(None))
            .all()
        )
        info_list = [(u.id, u.slack_channel_id, u.bus_stop_id, u.bus_route_id) for u in users]
    finally:
        db.close()

    for user_id, channel, stop_id, route_id in info_list:
        info = await bus_api.get_arrival(stop_id, route_id)
        arrivals = info.get("arrivals", [])
        if not arrivals:
            continue
        imminent = [a for a in arrivals if a.get("minutes", 999) <= BUS_NOTIFY_THRESHOLD_MIN]
        if imminent and channel:
            msg = (
                f"🚌 곧 버스가 도착합니다 (약 {imminent[0]['minutes']}분)\n"
                f"정류장: {stop_id} / 노선: {route_id or '-'}"
            )
            await notifier.send_message(channel, msg)
            logger.info("[bus] notified user=%s", user_id)


async def tick_idle_decay() -> None:
    """사용자가 쉬거나 자리를 비울 때 펫 스트레스 자연 감소."""
    db = SessionLocal()
    try:
        pets = db.query(PetProfile).all()
        for p in pets:
            if p.stress > 0:
                p.stress = max(0, p.stress - 5)
        db.commit()
    finally:
        db.close()


async def run_scheduler() -> None:
    init_db()
    SystemMonitor.instance().start()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(tick_monitor, "interval", seconds=MONITOR_INTERVAL_SEC, id="monitor")
    scheduler.add_job(tick_bus, "interval", seconds=BUS_INTERVAL_SEC, id="bus")
    scheduler.add_job(tick_idle_decay, "interval", seconds=IDLE_DECAY_INTERVAL_SEC, id="idle_decay")
    scheduler.start()
    logger.info(
        "Smart Office Scheduler started (monitor=%ss, bus=%ss, idle_decay=%ss)",
        MONITOR_INTERVAL_SEC,
        BUS_INTERVAL_SEC,
        IDLE_DECAY_INTERVAL_SEC,
    )

    # 포그라운드 유지
    stop = asyncio.Event()
    try:
        await stop.wait()
    finally:
        scheduler.shutdown(wait=False)
        SystemMonitor.instance().stop()


def seed_test_user(username: str = "test_user", channel_id: str = "") -> int:
    """CLI 테스트용 사용자 주입. 이미 있으면 id 반환."""
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user:
            return user.id
        user = User(
            username=username,
            display_name="테스트 사용자",
            gender="etc",
            age=28,
            job_role="ai",
            dev_tendency="explorer",
            company_lat=37.4979,
            company_lng=127.0276,
            company_address="서울 강남구 역삼동",
            bus_stop_id="23-102",
            bus_route_id="146",
            slack_channel_id=channel_id or None,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            PetProfile(
                user_id=user.id,
                species="egg",
                nickname="삐약이",
                level=1,
                exp=0,
                mood="neutral",
                stress=0,
            )
        )
        db.commit()
        logger.info("Seeded user id=%s", user.id)
        return user.id
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--channel", type=str, default="")
    args = parser.parse_args()

    if args.seed:
        uid = seed_test_user(channel_id=args.channel)
        print(f"seeded user_id={uid}")
    else:
        try:
            asyncio.run(run_scheduler())
        except KeyboardInterrupt:
            logger.info("scheduler stopped")
