from __future__ import annotations

from typing import Any, AsyncGenerator, TYPE_CHECKING

from google.adk.workflow import BaseNode
from google.adk.events import RequestInput

if TYPE_CHECKING:
    from google.adk.agents.context import Context


class GetInput(BaseNode):
    """사용자의 입력을 기다리기 위해 실행을 일시 중지하는 노드.

    동작 흐름:
      1) 최초 진입: ``ctx.resume_inputs`` 가 비어 있으므로 ``RequestInput`` 을
         yield → 워크플로우가 interrupt Event 를 내고 일시 정지한다.
      2) function_response 로 재개: ``rerun_on_resume=True`` 덕분에 노드가 다시
         실행되고, 이때 ``ctx.resume_inputs`` 에 interrupt_id→사용자응답이 담긴다.
         이 응답을 그대로 yield 하면 상위 ``tool_context.run_node(GetInput(...))``
         호출이 그 값을 반환한다.
    """

    request: RequestInput
    rerun_on_resume: bool = True

    async def _run_impl(
        self,
        *,
        ctx: "Context",
        node_input: Any,
    ) -> AsyncGenerator[Any, None]:
        resume_inputs = getattr(ctx, "resume_inputs", None) or {}
        my_id = self.request.interrupt_id
        if resume_inputs:
            # 재개 — 내 interrupt_id 에 해당하는 응답 우선, 없으면 아무 응답 하나.
            response = (
                resume_inputs.get(my_id)
                if my_id and my_id in resume_inputs
                else next(iter(resume_inputs.values()))
            )
            yield response
            return
        yield self.request
