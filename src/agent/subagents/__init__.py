"""펫 Supervisor 에 delegate 되는 도메인별 Sub-agents."""

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
