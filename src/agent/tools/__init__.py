"""ADK 2.0 FunctionTool 레지스트리.

도메인별 파일에서 각 툴을 정의하고 여기서 모아 re-export 한다.
서브에이전트는 ``from src.agent.tools import *_tool`` 로 필요한 것만 가져간다.

각 tool 함수의 **docstring 이 LLM 의 tool schema** 가 되므로 구체적인
`Args`/`Returns` 로 "언제 쓰는지" 를 반드시 기술한다.

``user_id`` 는 세션 상태(`state['user_id']`) 에서 읽으며, 모든 툴이 같은
규칙을 따른다. ``/api/chat`` 엔드포인트가 세션 최초 생성 시 주입한다.
"""

from src.agent.tools.ask import ask_user_tool
from src.agent.tools.bus import bus_arrival_tool, bus_search_tool
from src.agent.tools.cafe import cafe_tool
from src.agent.tools.calendar import calendar_tool
from src.agent.tools.diagnostics import activity_tool, pet_status_tool, profile_tool
from src.agent.tools.lunch import lunch_tool

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
