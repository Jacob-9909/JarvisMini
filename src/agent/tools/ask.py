"""HITL ask_user 툴 — LLM 이 사용자에게 되묻고 응답을 받는다.

``GetInput`` 노드가 interrupt 를 내고, function_response 로 재개되면
사용자 응답 문자열을 그대로 반환한다.
"""

from __future__ import annotations

from google.adk.events import RequestInput
from google.adk.tools import FunctionTool, ToolContext

from src.agent.hitl import GetInput


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
    # run_node() 는 InvocationContext 가 아니라 Context(ToolContext) 에만 있다.
    request = RequestInput(message=message)
    response = await tool_context.run_node(
        GetInput(name="hitl_ask_user", request=request)
    )
    return str(response)


ask_user_tool = FunctionTool(ask_user)

__all__ = ["ask_user_tool"]
