"""간이 스모크 테스트.

uv run python test_runner.py

실제 API 키 없이도 mock 으로 모든 경로가 한 번씩 돌아가는지 확인한다.
"""

from __future__ import annotations

import asyncio
import logging

from google.adk import Runner
from google.adk.sessions import InMemorySessionService

from src.db.session import init_db
from src.scheduler import seed_test_user
from src.workflow.agent import root_agent, WorkflowInput

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def _run(user_id: int, action: str) -> None:
    runner = Runner(
        node=root_agent,
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
    print(f"\n=== action={action} ===")
    async for event in runner.run_async(
        user_id=str(user_id),
        session_id=f"smoke_{action}",
        state_delta={
            "input": WorkflowInput(user_id=user_id, action=action).model_dump()
        },
    ):
        etype = getattr(event, "event_type", type(event).__name__)
        out = getattr(event, "output", None)
        print(f"  · {etype}  →  {out!s:.160}")


async def main() -> None:
    init_db()
    user_id = seed_test_user()
    for action in ("status", "monitor", "bus", "directions", "lunch_roulette", "calendar", "pet_interact"):
        await _run(user_id, action)


if __name__ == "__main__":
    asyncio.run(main())
