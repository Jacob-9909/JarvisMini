from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ActionBody(BaseModel):
    """일반 액션(/api/action) 요청 바디."""
    action: str = "status"
    payload: Dict[str, Any] = {}


class FunctionResponsePayload(BaseModel):
    """HITL 재개용 function_response 페이로드.

    - ``id`` 는 서버가 보낸 interrupt 이벤트의 ``interrupt_id``.
    - ``response`` 는 사용자가 입력한 자유 텍스트 또는 구조화된 객체. 서버에서
      ``{"result": <value>}`` 로 감싼 뒤 ADK Runner 에 전달한다.
    """
    id: str
    response: Any = None


class ChatBody(BaseModel):
    """채팅(/api/chat) 요청 바디.

    ``function_response`` 가 채워져 있으면 이 턴은 HITL interrupt 를 재개하는
    턴으로 해석되며, 일반 ``message`` 입력보다 우선한다.
    """
    message: str = ""
    session_id: Optional[str] = None
    function_response: Optional[FunctionResponsePayload] = None


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
