"""점심 메뉴 추첨기.

3가지 방식(제비뽑기 / 사다리타기 / 룰렛) 중 하나를 **랜덤으로 골라**
사용자가 입력한 메뉴 중에서 하나를 뽑아 준다. 결과는 메모리에 잠시
(기본 24시간, 최근 10개) 저장해 오른쪽 이력 패널에 보여 준다.

입력 메뉴가 비어 있으면 :data:`DEFAULT_MENUS` 로 폴백한다.

내보내는 API
-------------
- :func:`draw(user_id, menus, method=None, preferred=None)`
- :func:`recent_picks(user_id)` / :func:`clear_history(user_id)`
- :data:`METHODS`
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MENUS = [
    "김치찌개", "된장찌개", "돈까스", "짜장면", "짬뽕",
    "마라탕", "초밥", "라멘", "쌀국수", "파스타",
    "햄버거", "치킨", "덮밥", "비빔밥", "샐러드",
]

METHODS = ("lottery", "ladder", "roulette")  # 제비뽑기 / 사다리타기 / 룰렛
METHOD_LABEL = {
    "lottery": "제비뽑기",
    "ladder": "사다리타기",
    "roulette": "룰렛",
}

# 사용자별 최근 기록 (메모리. 프로세스 재시작 시 비워짐)
_HISTORY_MAX = 10
_HISTORY_TTL = 60 * 60 * 24  # 24h
_history: Dict[int, Deque[Dict[str, Any]]] = {}
_history_lock = Lock()


# --------------------------------------------------------------------- #
#  Utilities
# --------------------------------------------------------------------- #


def _cleaned_menus(menus: Optional[List[str]]) -> List[str]:
    """중복·공백 제거. 최대 20개."""
    if not menus:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for m in menus:
        if not isinstance(m, str):
            continue
        t = m.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t[:24])
        if len(out) >= 20:
            break
    return out


def _pick_method(preferred: Optional[str]) -> str:
    if preferred in METHODS:
        return preferred  # type: ignore[return-value]
    return random.choice(METHODS)


# --------------------------------------------------------------------- #
#  Method-specific "애니메이션용" 데이터 생성
# --------------------------------------------------------------------- #


def _lottery_meta(menus: List[str], winner_idx: int) -> Dict[str, Any]:
    """제비뽑기: 종이 쪽지 n개 → 하나 뒤집기. 오픈 순서만 섞어 둔다."""
    indices = list(range(len(menus)))
    random.shuffle(indices)
    # 최종 당첨을 마지막에 뒤집도록 배치
    if winner_idx in indices:
        indices.remove(winner_idx)
    reveal_order = indices + [winner_idx]
    return {"reveal_order": reveal_order}


def _ladder_meta(menus: List[str], winner_idx: int) -> Dict[str, Any]:
    """사다리타기: 세로선 n개 + 각 층의 랜덤 가로선.

    실제 사다리 경로와 당첨 결과가 *시각적으로* 맞도록, 상단 시작 인덱스
    ``start_idx`` → ``winner_idx`` 가 되는 legs 배열을 만든다.
    """
    n = len(menus)
    levels = max(4, n + 2)
    # level 별 가로선 위치: set of left-endpoint col in [0, n-2]
    legs: List[List[int]] = []
    # 경로를 맞추기 위해 단순 접근: 시작 = winner (거울 구조) → 맨 위에서 섞지 않고 고정
    # 정확한 사다리 결과를 맞추기 위해 "선택 지점"을 역추적으로 만들지 않고,
    # 프론트에서 legs 를 따라 그대로 내려가 결과가 나오게 한다.
    cols = list(range(n - 1))
    current = list(range(n))  # current[i] = 시작 i 에서 현재 level 직전의 열 위치
    for _ in range(levels):
        used: set[int] = set()
        layer: List[int] = []
        # 각 열에 최대 하나의 가로선, 인접 중복 금지
        random.shuffle(cols)
        for c in cols:
            if c in used or (c - 1) in used or (c + 1) in used:
                continue
            if random.random() < 0.45:
                layer.append(c)
                used.add(c)
        layer.sort()
        # swap current[]
        pos_to_start = {v: k for k, v in enumerate(current)}
        for c in layer:
            left_start = pos_to_start[c]
            right_start = pos_to_start[c + 1]
            current[left_start], current[right_start] = (
                current[right_start],
                current[left_start],
            )
            pos_to_start = {v: k for k, v in enumerate(current)}
        legs.append(layer)

    # 결과: 시작 인덱스 s 는 current 가 winner_idx 가 되는 s 이다.
    try:
        start_idx = current.index(winner_idx)
    except ValueError:
        start_idx = winner_idx
    return {"legs": legs, "levels": levels, "start_idx": start_idx}


def _roulette_meta(menus: List[str], winner_idx: int) -> Dict[str, Any]:
    """룰렛: 360° 를 n 등분, 회전각으로 winner 섹터 중앙이 오게."""
    n = len(menus)
    seg = 360.0 / n
    full_turns = random.randint(4, 7)
    # 최종 정지: pointer(12시 방향) 가 winner 섹터 중앙
    final_angle = full_turns * 360 + (360 - (winner_idx + 0.5) * seg)
    return {
        "segment_deg": round(seg, 3),
        "final_angle": round(final_angle, 2),
        "duration_ms": 2600,
    }


_META_BUILDERS = {
    "lottery": _lottery_meta,
    "ladder": _ladder_meta,
    "roulette": _roulette_meta,
}


# --------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------- #


def draw(
    user_id: int,
    menus: Optional[List[str]] = None,
    method: Optional[str] = None,
    preferred: Optional[str] = None,  # 방식 강제 지정(테스트용, 없으면 랜덤)
) -> Dict[str, Any]:
    """메뉴 목록에서 한 개를 뽑는다. 방식은 랜덤(또는 ``preferred``).

    Returns
    -------
    dict
        ``{method, method_label, menus, winner, winner_idx, meta, pick_id, ts}``
    """
    cleaned = _cleaned_menus(menus) or list(DEFAULT_MENUS)
    chosen_method = _pick_method(preferred or method)
    winner_idx = random.randrange(len(cleaned))
    winner = cleaned[winner_idx]
    meta = _META_BUILDERS[chosen_method](cleaned, winner_idx)

    result = {
        "pick_id": uuid.uuid4().hex[:10],
        "ts": time.time(),
        "method": chosen_method,
        "method_label": METHOD_LABEL[chosen_method],
        "menus": cleaned,
        "winner": winner,
        "winner_idx": winner_idx,
        "meta": meta,
        "from_default_menus": not _cleaned_menus(menus),
    }
    _remember(user_id, result)
    return result


def recent_picks(user_id: int) -> List[Dict[str, Any]]:
    """메모리에 저장된 최근 기록(최신순). TTL 지난 항목은 정리."""
    now = time.time()
    with _history_lock:
        dq = _history.get(user_id)
        if not dq:
            return []
        # 만료 항목 제거
        while dq and (now - dq[0]["ts"]) > _HISTORY_TTL:
            dq.popleft()
        # 최신이 먼저 오도록 역순
        return [
            {
                "pick_id": r["pick_id"],
                "ts": r["ts"],
                "method": r["method"],
                "method_label": r["method_label"],
                "winner": r["winner"],
                "menus": r["menus"],
            }
            for r in list(dq)[::-1]
        ]


def clear_history(user_id: int) -> int:
    with _history_lock:
        n = len(_history.get(user_id, []))
        _history.pop(user_id, None)
        return n


def _remember(user_id: int, record: Dict[str, Any]) -> None:
    with _history_lock:
        dq = _history.setdefault(user_id, deque(maxlen=_HISTORY_MAX))
        dq.append(record)
