from __future__ import annotations

from typing import Any, AsyncGenerator
from google.adk.workflow import BaseNode
from google.adk.events import RequestInput


class GetInput(BaseNode):
    """사용자의 입력을 기다리기 위해 실행을 일시 중지하는 노드."""
    rerun_on_resume = False  # 재개 시 결과를 다시 출력으로 산출

    def __init__(self, request: RequestInput, name: str = "get_user_input"):
        self.request = request
        self.name = name

    def get_name(self) -> str:
        return self.name

    async def run(self) -> AsyncGenerator[Any, None]:
        # RequestInput을 yield하면 워크플로우가 중단되고 입력을 기다립니다.
        yield self.request
