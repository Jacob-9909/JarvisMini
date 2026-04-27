"""펫 Supervisor 에 delegate 되는 도메인별 Sub-agents."""

try:
    from google.adk.models.lite_llm import LiteLlm, LiteLLMClient
    from google.adk.models.registry import LLMRegistry

    class NvidiaNimClient(LiteLLMClient):
        async def acompletion(self, model, messages, tools, **kwargs):
            # NVIDIA NIM API expects strings, not lists for content
            for msg in messages:
                content = msg.get("content")
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif isinstance(part, str):
                            text_parts.append(part)
                    msg["content"] = "\n".join(text_parts)
            return await super().acompletion(model, messages, tools, **kwargs)

        def completion(self, model, messages, tools, stream=False, **kwargs):
            for msg in messages:
                content = msg.get("content")
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif isinstance(part, str):
                            text_parts.append(part)
                    msg["content"] = "\n".join(text_parts)
            return super().completion(model, messages, tools, stream=stream, **kwargs)
    
    class NvidiaNimLlm(LiteLlm):
        def __init__(self, model: str, **kwargs):
            # NVIDIA NIM DeepSeek models often need thinking: False to avoid mixed output
            extra_body = kwargs.get("extra_body", {})
            if "chat_template_kwargs" not in extra_body:
                extra_body["chat_template_kwargs"] = {"thinking": False}
            kwargs["extra_body"] = extra_body
            super().__init__(model, **kwargs)
            # Inject custom client to fix message formatting
            self.llm_client = NvidiaNimClient()

    LLMRegistry._register(r"nvidia_nim/.*", NvidiaNimLlm)
except ImportError:
    pass


from src.agent.subagents.bus_agent import bus_agent
from src.agent.subagents.calendar_agent import calendar_agent
from src.agent.subagents.general_agent import general_chat_agent
from src.agent.subagents.lunch_agent import lunch_agent
from src.agent.subagents.navigation_agent import navigation_agent
from src.agent.subagents.wellness_coach import wellness_coach

ALL_SUBAGENTS = [
    bus_agent,
    lunch_agent,
    calendar_agent,
    wellness_coach,
    navigation_agent,
    general_chat_agent,
]

__all__ = [
    "bus_agent",
    "lunch_agent",
    "calendar_agent",
    "wellness_coach",
    "navigation_agent",
    "general_chat_agent",
    "ALL_SUBAGENTS",
]
