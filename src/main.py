"""Smart Office Life Agent 진입점.

사용 예:
    uv run python -m src.main --mode desktop    --user-id 1   # macOS 네이티브 창 (기본)
    uv run python -m src.main --mode web        --user-id 1   # 브라우저 탭으로 띄우기
    uv run python -m src.main --mode scheduler
    uv run python -m src.main --mode seed

데스크톱 창 옵션:
    --on-top       # 항상 최상단
    --frameless    # 타이틀바 제거 (본문 드래그로 이동)
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from src.db.session import init_db
from src.scheduler import run_scheduler, seed_test_user
from src.ui.web import run_web, run_desktop

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Office Life Agent")
    parser.add_argument(
        "--mode",
        choices=["desktop", "web", "scheduler", "seed", "init-db"],
        default="desktop",
    )
    parser.add_argument("--user-id", type=int, default=None)
    parser.add_argument("--channel", type=str, default="")
    parser.add_argument("--username", type=str, default="test_user")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--on-top", action="store_true", help="desktop: 창을 항상 최상단")
    parser.add_argument("--frameless", action="store_true", help="desktop: 타이틀바 제거")
    parser.add_argument("--width", type=int, default=420)
    parser.add_argument("--height", type=int, default=600)
    return parser.parse_args()


async def _async_main(args: argparse.Namespace) -> None:
    """desktop 이외의 비동기 경로."""
    if args.mode == "scheduler":
        await run_scheduler()
        return

    user_id = args.user_id
    if user_id is None:
        user_id = seed_test_user(username=args.username)

    if args.mode == "web":
        await run_web(user_id, host=args.host, port=args.port)
        return


def main() -> None:
    args = _parse_args()

    if args.mode == "init-db":
        init_db()
        print("DB schemas & tables ensured.")
        return

    if args.mode == "seed":
        uid = seed_test_user(username=args.username, channel_id=args.channel)
        print(f"seeded user_id={uid}")
        return

    if args.mode == "desktop":
        # pywebview 는 macOS 메인 스레드의 NSApp 이벤트 루프를 점유하므로
        # asyncio.run 바깥(=메인 스레드)에서 동기적으로 실행한다.
        user_id = args.user_id
        if user_id is None:
            user_id = seed_test_user(username=args.username)
        run_desktop(
            user_id,
            host=args.host,
            port=args.port,
            width=args.width,
            height=args.height,
            on_top=args.on_top,
            frameless=args.frameless,
        )
        return

    asyncio.run(_async_main(args))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("stopped by user")
