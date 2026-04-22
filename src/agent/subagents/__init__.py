"""펫 Supervisor 에 delegate 되는 도메인별 Sub-agents."""

from src.agent.subagents.bus_agent import bus_agent
from src.agent.subagents.cafe_agent import cafe_agent
from src.agent.subagents.lunch_agent import lunch_agent
from src.agent.subagents.calendar_agent import calendar_agent
from src.agent.subagents.wellness_coach import wellness_coach

ALL_SUBAGENTS = [
    bus_agent,
    cafe_agent,
    lunch_agent,
    calendar_agent,
    wellness_coach,
]

__all__ = [
    "bus_agent",
    "cafe_agent",
    "lunch_agent",
    "calendar_agent",
    "wellness_coach",
    "ALL_SUBAGENTS",
]
