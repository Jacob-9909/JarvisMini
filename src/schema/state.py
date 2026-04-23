"""Smart Office Life Agent 상태 스키마.

ADK 2.0 Graph Workflow 에서 노드 간 전달/저장되는 컨텍스트 정의.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


PetSpecies = Literal["fox", "turtle", "owl", "dragon", "egg"]
PetMood = Literal["happy", "neutral", "tired", "stressed", "focused"]
DashboardAction = Literal[
    "status", "bus", "directions", "lunch_roulette", "calendar", "pet_interact", "noop"
]


class UserContext(BaseModel):
    user_id: int
    display_name: Optional[str] = None
    job_role: Optional[str] = None
    dev_tendency: Optional[str] = None
    company_lat: Optional[float] = None
    company_lng: Optional[float] = None
    bus_stop_id: Optional[str] = None
    bus_route_id: Optional[str] = None


class PetStatus(BaseModel):
    species: PetSpecies = "egg"
    nickname: Optional[str] = None
    level: int = 1
    exp: int = 0
    mood: PetMood = "neutral"
    stress: int = 0

    def exp_to_next_level(self) -> int:
        # 간단한 공식: 다음 레벨까지 level*100 EXP 필요
        return max(0, self.level * 100 - self.exp)


class SystemSnapshot(BaseModel):
    ts: datetime = Field(default_factory=datetime.utcnow)
    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    click_count: int = 0
    key_count: int = 0
    active_tabs: int = 0
    top_processes: List[Dict[str, Any]] = Field(default_factory=list)
    screen_active_sec: int = 0


class DashboardResult(BaseModel):
    user_id: int
    action: DashboardAction
    title: str
    lines: List[str] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)


class PetCareResult(BaseModel):
    user_id: int
    exp_gain: int = 0
    stress_delta: int = 0
    mood: PetMood = "neutral"
    leveled_up: bool = False
    evolved_to: Optional[PetSpecies] = None
    message: Optional[str] = None
