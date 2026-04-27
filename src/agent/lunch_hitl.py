"""Lunch HITL nodes."""

from __future__ import annotations

import logging
import re
from typing import Any

from google.adk import Event
from google.adk.events import RequestInput

from src.tools import lunch_roulette

logger = logging.getLogger(__name__)

_DEFAULT_MENUS = ["한식", "일식", "중식", "샐러드", "분식"]
_SPLIT_RE = re.compile(r"[·•,/|\s\[\]{}()]+")
_STRIP_CHARS = "*#-_`\"'.:~"
_LABEL_PREFIX_RE = re.compile(r"^\s*후보\s*[:：]\s*")

_CANCEL_KEYS = ("cancel", "취소", "관뒀", "그만", "안 뽑", "됐어")
_REROLL_KEYS = ("reroll", "다시", "재뽑", "한 번 더", "재추첨")


def _text(node_input: Any) -> str: # 노드 입력을 텍스트로 변환
    if node_input is None:
        return ""
    if isinstance(node_input, dict):
        return str(node_input.get("response") or node_input.get("result") or "")
    return str(node_input)


def _has(text: str, keys: tuple[str, ...]) -> bool: # 텍스트에 키워드가 포함되어 있는지 확인
    low = (text or "").lower().strip()
    return any(k in low for k in keys)


def _uid(ctx) -> int: # 사용자 ID 읽기
    try:
        return int(ctx.state.get("user_id") or 0)
    except Exception:
        return 0


def _parse_candidates(text: str) -> list[str]: # 후보 메뉴 파싱
    text = _LABEL_PREFIX_RE.sub("", text or "")
    out: list[str] = []
    for tok in _SPLIT_RE.split(text or ""):
        tok = tok.strip(_STRIP_CHARS).strip()
        if tok and not tok.isdigit() and 1 <= len(tok) <= 10:
            out.append(tok)
    seen, uniq = set(), []
    for m in out:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq[:8]


def _draw(ctx, candidates: list[str], fallback_winner: str = "?") -> tuple[str, str]: # 추첨
    try:
        result = lunch_roulette.draw(user_id=_uid(ctx), menus=candidates)
    except Exception as e:
        logger.warning("lunch_roulette.draw failed: %s", e)
        result = {"winner": fallback_winner, "method_label": "기본"}
    return str(result.get("winner") or fallback_winner), str(result.get("method_label") or "추첨")


async def lunch_candidates_node(ctx, node_input: Any): # 후보 메뉴 제안 노드
    raw = _text(node_input)
    candidates = _parse_candidates(raw) or list(_DEFAULT_MENUS)

    yield Event(
        state={
            "lunch_candidates": candidates,
            "lunch_agent_text": raw, 
            "pending_lunch_status": None, # 새 후보 제안마다 이전 상태를 비워 후속 라우팅·보상 판별이 꼬이지 않게 함
            "lunch_winner": None,
            "lunch_method": None,
        }
    )

    message = (
        f"🍱 추천 후보: {' · '.join(candidates)}\n"
        "이대로 뽑을까요?\n"
        "한국어로 네, 응, 좋아, 그래 처럼 짧게 답해도 그대로 추첨으로 진행돼요.\n"
        "- accept : 그대로 추첨\n"
        "- edit 메뉴1, 메뉴2, … : 후보 교체\n"
        "- cancel : 취소"
    )
    yield RequestInput(
        message=message,
        payload={"candidates": candidates},
    )


async def lunch_draw_node(ctx, node_input: Any): # 추첨 노드 (HITL 없이 즉시 추첨)
    agent_text = _text(node_input)
    parsed = _parse_candidates(agent_text)
    candidates = parsed or list(ctx.state.get("lunch_candidates") or _DEFAULT_MENUS)

    winner, method = _draw(ctx, candidates, candidates[0] if candidates else "?")

    # 추첨 결과는 별도 확정 HITL 없이 바로 accepted (post_process 보상 동일)
    text = f"🎲 {method} → 🍽 {winner}\n🍽 오늘은 {winner}! ({method})"
    yield Event(
        state={
            "lunch_candidates": candidates,
            "lunch_agent_text": agent_text,
            "lunch_winner": winner,
            "lunch_method": method,
            "pending_lunch_status": "accepted",
        },
        output={
            "response": text,
            "lunch_status": "accepted",
            "winner": winner,
        },
    )


async def lunch_finalize_node(ctx, node_input: Any): # 추첨 결과 확정 노드
    user_resp = _text(node_input)
    candidates = list(ctx.state.get("lunch_candidates") or _DEFAULT_MENUS)
    winner = str(ctx.state.get("lunch_winner") or "?")
    method = str(ctx.state.get("lunch_method") or "추첨")

    if _has(user_resp, _REROLL_KEYS):
        winner, method = _draw(ctx, candidates, winner)
        status = "rerolled"
        text = f"🎲 {method} → 🍽 {winner} (재추첨 최종)"
    elif _has(user_resp, _CANCEL_KEYS):
        status = "cancelled"
        text = "점심 추첨 취소."
    else:
        status = "accepted"
        text = f"🍽 오늘은 {winner}! ({method})"

    yield Event(
        state={
            "pending_lunch_status": status,
            "lunch_winner": winner,
            "lunch_method": method,
        },
        output={
            "response": text,
            "lunch_status": status,
            "winner": winner,
        },
    )


__all__ = [
    "lunch_candidates_node",
    "lunch_draw_node",
    "lunch_finalize_node",
]
