"""Minimal router — decide + HITL finalize.

직접 ``google.genai`` 를 호출해 JSON 하나만 받는다. ADK ``Runner`` 없이 LLM
인보케이션이 신뢰 가능하도록 하기 위함. 또한 흔한 도메인 키워드는 LLM 호출
없이 바로 라우트를 선택하는 fast-path 를 둔다.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal, Optional, get_args

from google.adk import Event
from google.adk.events import RequestInput
from pydantic import BaseModel

from src.schema.chat import ChatRouteInput

logger = logging.getLogger(__name__)
MODEL = os.getenv("MODEL", "gemini-2.5-flash")

RouteName = Literal[
    "bus_agent",
    "lunch_agent",
    "calendar_agent",
    "wellness_coach",
    "navigation_agent",
    "general_chat_agent",
]
VALID_ROUTES: frozenset[str] = frozenset(get_args(RouteName))

# router_finalize / 짧은 긍정(점심 HITL 후속) 공통
_POSITIVE_TOKENS = frozenset(
    {
        "",
        "ok",
        "okay",
        "yes",
        "y",
        "예",
        "네",
        "응",
        "어",
        "ㅇㅇ",
        "그래",
        "맞아",
        "맞음",
        "수락",
        "수락함",
        "accept",
        "confirm",
        "좋아",
        "좋음",
    }
)


class RouteDecision(BaseModel):
    route: RouteName


class HitlDecision(BaseModel):
    final_route: RouteName


# ---------------------------------------------------------------------------
# Keyword fast-path — LLM 실패/지연 없이 명백한 의도를 즉시 라우팅.
# ---------------------------------------------------------------------------
_NAV_KEYWORDS = (
    "지하철", "전철", "대중교통", "길찾기", "길 찾", "경로",
    "도보", "차로", "자동차", "환승", "몇 정거장",
)
_NAV_STATION_RE = re.compile(r"[가-힣A-Za-z0-9]+역")  # 'ㅇㅇ역'
_BUS_KEYWORDS = ("버스", "정류장", "도착 정보", "몇 분", "언제 와", "배차")
_LUNCH_KEYWORDS = ("점심", "메뉴", "뭐 먹", "뭐먹", "룰렛", "사다리")
_CALENDAR_KEYWORDS = ("일정", "미팅", "스케줄", "캘린더", "회의", "약속", "이번 주", "오늘 일정")
_WELLNESS_KEYWORDS = ("피곤", "지쳐", "쉬고", "휴식", "스트레스", "졸려", "힘들")


def _keyword_route(message: str) -> Optional[str]:
    if not message:
        return None
    low = message.lower()
    # 역명이 2개 이상 또는 교통 키워드 포함 → navigation
    stations = _NAV_STATION_RE.findall(message)
    if len(stations) >= 1 and any(k in message for k in _NAV_KEYWORDS):
        return "navigation_agent"
    if len(stations) >= 2:
        return "navigation_agent"
    if any(k in message for k in _NAV_KEYWORDS):
        return "navigation_agent"
    if any(k in message for k in _BUS_KEYWORDS):
        return "bus_agent"
    if any(k in message for k in _LUNCH_KEYWORDS):
        return "lunch_agent"
    if any(k in message for k in _CALENDAR_KEYWORDS):
        return "calendar_agent"
    if any(k in low for k in _WELLNESS_KEYWORDS):
        return "wellness_coach"
    return None


# ---------------------------------------------------------------------------
# genai direct call
# ---------------------------------------------------------------------------
_ROUTE_SYSTEM = """사용자 발화를 보고 라우트 하나를 고른다.
출력은 **JSON 객체 하나만**, 코드펜스/설명 금지:
{"route":"<bus_agent|lunch_agent|calendar_agent|wellness_coach|navigation_agent|general_chat_agent>"}

- bus_agent: 버스 도착/노선/정류장
- lunch_agent: 점심 메뉴/추첨
- calendar_agent: 일정/미팅/캘린더
- wellness_coach: 피로/휴식/스트레스 조언
- navigation_agent: 길찾기·경로·역↔역·지하철·전철·대중교통·도보·차로
- general_chat_agent: 위 어디에도 해당 안 되는 잡담
"""

_HITL_SYSTEM = """HITL 재분류. 입력 JSON 을 보고 최종 라우트 하나를 고른다.
user_reply 가 긍정('네','ok','수락','그래' 등)이면 guessed_route 를 그대로 쓴다.
반대/다른 의도면 original_message+user_reply 로 재분류.

출력은 **JSON 객체 하나만**, 코드펜스/설명 금지:
{"final_route":"<bus_agent|lunch_agent|calendar_agent|wellness_coach|navigation_agent|general_chat_agent>"}
"""


_JSON_OBJ_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _extract_json_obj(text: str) -> Optional[dict]:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    for m in _JSON_OBJ_RE.finditer(s):
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


_genai_client = None


def _get_genai_client():
    global _genai_client
    if _genai_client is not None:
        return _genai_client
    try:
        from google import genai

        _genai_client = genai.Client()
    except Exception:
        logger.exception("failed to init genai client")
        _genai_client = None
    return _genai_client


async def _llm_json(system: str, user: str, schema_cls: type[BaseModel], key: str) -> Optional[BaseModel]:
    """genai 로 JSON 한 번 뽑아 ``schema_cls`` 로 검증.

    ``response_mime_type=application/json`` + ``response_schema`` 로 구조 강제.
    실패 시 텍스트에서 수동 추출 시도.
    """
    client = _get_genai_client()
    if client is None:
        return None
    try:
        from google.genai import types as genai_types

        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema_cls,
            temperature=0,
        )
        resp = await client.aio.models.generate_content(
            model=MODEL,
            contents=user,
            config=config,
        )
    except Exception:
        logger.exception("genai generate_content failed")
        return None

    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, schema_cls):
        return parsed

    text = getattr(resp, "text", None) or ""
    obj = _extract_json_obj(text)
    if obj is None or key not in obj:
        logger.warning("llm_json no key %r in text=%r parsed=%r", key, text[:200], parsed)
        return None
    try:
        return schema_cls.model_validate(obj)
    except Exception:
        logger.warning("llm_json validate failed: %r", obj)
        return None


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def _coerce_user_id_message(node_input: Any) -> tuple[int, str]:
    """init_node 의 ChatRouteInput / dict / HITL resume str 모두에서 user_id/message 추출."""
    if node_input is None:
        return 0, ""
    if isinstance(node_input, ChatRouteInput):
        return int(node_input.user_id or 0), str(node_input.message or "")
    if isinstance(node_input, dict):
        uid = node_input.get("user_id") or 0
        msg = node_input.get("message")
        if msg is None:
            msg = node_input.get("response") or node_input.get("result") or ""
        try:
            return int(uid or 0), str(msg or "")
        except Exception:
            return 0, str(msg or "")
    if isinstance(node_input, str):
        return 0, node_input
    return int(getattr(node_input, "user_id", 0) or 0), str(
        getattr(node_input, "message", "") or ""
    )


async def router_decide_node(ctx, node_input: Any):
    user_id, message = _coerce_user_id_message(node_input)

    kw_route = _keyword_route(message)
    if kw_route:
        target_route = kw_route
        logger.info("[router/kw] msg=%r → %s", message[:60], target_route)
    else:
        decision = await _llm_json(_ROUTE_SYSTEM, message, RouteDecision, "route")
        target_route = getattr(decision, "route", None)
        logger.info("[router/llm] msg=%r → %s", message[:60], target_route)
        if target_route not in VALID_ROUTES:
            target_route = "general_chat_agent"

    yield Event(
        state={
            "user_id": user_id,
            "router_candidate_route": target_route,
            "router_original_message": message,
        }
    )
    # 키워드로 라우트가 확정이면 라우터 HITL 생략
    if kw_route is None:
        yield RequestInput(
            message=(
                "의도 분류 결과 확인.\n"
                f"현재 추정 route: `{target_route}`\n"
                "맞으면 수락, 아니면 원하는 의도를 자유롭게 입력"
            ),
        )


async def router_finalize_node(ctx, node_input: Any):
    # HITL resume 시 node_input 은 raw str("길찾기"), 또는 {"response": ...} dict.
    user_id, user_reply = _coerce_user_id_message(node_input)
    if not user_id:
        try:
            user_id = int(ctx.state.get("user_id") or 0)
        except Exception:
            user_id = 0

    original_message = str(ctx.state.get("router_original_message") or user_reply)
    guessed_route = str(ctx.state.get("router_candidate_route") or "general_chat_agent")

    stripped = (user_reply or "").strip().lower()
    if stripped in _POSITIVE_TOKENS and guessed_route in VALID_ROUTES:
        target_route = guessed_route
        logger.info("[router/finalize/pos] guess=%s", guessed_route)
    else:
        # user_reply 에서 키워드 룰 먼저 시도
        kw = _keyword_route(user_reply) or _keyword_route(original_message)
        if kw:
            target_route = kw
            logger.info("[router/finalize/kw] reply=%r → %s", user_reply[:40], target_route)
        else:
            prompt = (
                f'{{"original_message": {json.dumps(original_message, ensure_ascii=False)},'
                f' "guessed_route": "{guessed_route}",'
                f' "user_reply": {json.dumps(user_reply, ensure_ascii=False)}}}'
            )
            hitl = await _llm_json(_HITL_SYSTEM, prompt, HitlDecision, "final_route")
            target_route = getattr(hitl, "final_route", None)
            if target_route not in VALID_ROUTES:
                target_route = guessed_route if guessed_route in VALID_ROUTES else "general_chat_agent"
            logger.info("[router/finalize/llm] reply=%r guess=%s → %s", user_reply[:40], guessed_route, target_route)

    yield Event(
        route=[target_route],
        output=ChatRouteInput(user_id=user_id, message=original_message, route=target_route),
        state={
            "current_route": target_route,
            "user_id": user_id,
            "original_message": original_message,
            "router_candidate_route": "",
            "router_original_message": "",
        },
    )


__all__ = ["router_decide_node", "router_finalize_node", "_keyword_route"]
