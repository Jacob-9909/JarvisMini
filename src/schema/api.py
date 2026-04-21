from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ActionBody(BaseModel):
    """일반 액션(/api/action) 요청 바디."""
    action: str = "status"
    payload: Dict[str, Any] = {}


class ChatBody(BaseModel):
    """채팅(/api/chat) 요청 바디."""
    message: str
    session_id: Optional[str] = None


class BusConfigBody(BaseModel):
    """버스 설정 저장 요청 바디."""
    stop_id: Optional[str] = None
    route_id: Optional[str] = None


class UserProfileBody(BaseModel):
    """사용자 프로필 온보딩/수정 요청 바디."""
    display_name: str
    gender: str
    age: int = Field(ge=1, le=120)
    job_role: str
    dev_tendency: str
    company_lat: float
    company_lng: float
    company_address: Optional[str] = None
