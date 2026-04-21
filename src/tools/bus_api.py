"""서울특별시 실시간 버스 도착 정보 API 래퍼.

공공데이터포털 `서울특별시_정류소정보조회` 서비스의
`getStationByUidItem` (`.../stationinfo/getStationByUid`) 엔드포인트를 사용한다.
정류소 번호(ARS ID, 5자리) 하나로 해당 정류소의 모든 경유 노선별 도착
예정 정보를 한 번에 받을 수 있어 서비스 호출량이 적다.

보조로 `getStationByName`(정류소명, 자연어 문장은 후보 여러 개로 전처리)과
ARS 숫자 전용 `getStationByUid` 조합으로 정류소 검색을 제공한다.

환경변수
--------
- ``SEOUL_BUS_API_KEY``  : 활용신청 후 마이페이지의 **인증키(Decoding)** 또는
  **인증키(Encoding)** 중 하나. 내부에서 정규화한다. 비어 있으면 mock.
- ``SEOUL_BUS_BASE_URL`` : 기본 ``http://ws.bus.go.kr/api/rest/stationinfo``
- ``BUS_USE_MOCK``       : ``1`` 이면 강제 mock (오프라인/개발 용)

응답 필드 요약 (``getStationByUid`` → 각 노선 item)::

    stNm           정류소명
    arsId          정류소 번호
    rtNm           노선명 (안내용)
    arrmsg1/2      도착정보 메시지 ("2분후[2번째 전]" / "곧 도착" / "출발대기")
    traTime1/2     남은 여행시간(초)
    congestion1/2  혼잡도 코드  (3:여유, 4:보통, 5:혼잡)
    busType1/2     차량 유형   (0:일반, 1:저상, 2:굴절)
    isLast1/2      막차 여부
    isFullFlag1/2  만차 여부
    isArrive1/2    최종 정류소 도착 여부
    stationNm1/2   해당 버스의 최종 정류소명
    adirection     방향

출처: 서울특별시 정류소정보조회 서비스 활용가이드(2025-09-24),
        서울특별시 버스도착정보조회 서비스 활용가이드(2025-08-14).
"""

from __future__ import annotations

import logging
import math
import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)


def _normalize_seoul_bus_api_key(raw: str) -> str:
    """공공데이터포털은 **인증키(Encoding)** / **인증키(Decoding)** 두 종류를 준다.

    - **Decoding 키**: 일반 문자열. ``httpx`` 가 ``serviceKey`` 쿼리로 보낼 때 한 번만
      URL 인코딩하면 된다 → ``.env`` 에 이 값을 넣는 것을 권장.
    - **Encoding 키**: 이미 ``%2F``, ``%3D`` 등으로 인코딩된 문자열. 그대로 넣으면
      클라이언트가 다시 인코딩해 **이중 인코딩**되어 API 가 거절하는 경우가 많다.
      → ``urllib.parse.unquote`` 로 원문으로 되돌린 뒤 전달한다.

    둘 중 어떤 것을 ``SEOUL_BUS_API_KEY`` 에 넣어도 동작하도록 정규화한다.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if "%" in s:
        try:
            return unquote(s)
        except Exception:
            return s
    return s


BUS_API_KEY = _normalize_seoul_bus_api_key(os.getenv("SEOUL_BUS_API_KEY", ""))
BUS_BASE_URL = os.getenv(
    "SEOUL_BUS_BASE_URL",
    "http://ws.bus.go.kr/api/rest/stationinfo",
)
BUS_USE_MOCK = os.getenv("BUS_USE_MOCK", "0").lower() in {"1", "true", "yes"}


_CONGESTION_MAP = {
    "3": "여유",
    "4": "보통",
    "5": "혼잡",
}
_BUSTYPE_MAP = {
    "0": "",         # 일반버스 — 표시 생략
    "1": "저상",
    "2": "굴절",
}
_ROUTE_TYPE_MAP = {
    "1": "공항",
    "2": "마을",
    "3": "간선",
    "4": "지선",
    "5": "순환",
    "6": "광역",
    "7": "인천",
    "8": "경기",
}

_MIN_RE = re.compile(r"(\d+)\s*분")
_SEC_RE = re.compile(r"(\d+)\s*초")
_STOP_ORD_RE = re.compile(r"\[?\s*(\d+)\s*번째\s*전\s*\]?")


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def _is_ok_header(code: Any) -> bool:
    return _as_str(code).strip() in {"0", "00"}


def _parse_stop_count(msg: Optional[str]) -> Optional[int]:
    if not msg:
        return None
    m = _STOP_ORD_RE.search(msg)
    return int(m.group(1)) if m else None


def _seconds_to_minutes(value: Any) -> Optional[int]:
    try:
        s = int(float(value))
    except (TypeError, ValueError):
        return None
    if s <= 0:
        return 0
    return max(1, math.ceil(s / 60))


def _minutes_from_msg(msg: Optional[str]) -> Optional[int]:
    """arrmsg 문자열에서 분을 추출. 실패 시 None."""
    if not msg:
        return None
    m = msg.strip()
    if "곧 도착" in m or m == "도착":
        return 0
    if "출발대기" in m or "운행종료" in m:
        return None
    mm = _MIN_RE.search(m)
    ss = _SEC_RE.search(m)
    if mm:
        total = int(mm.group(1)) + (int(ss.group(1)) / 60 if ss else 0)
        return max(0, math.ceil(total))
    if ss:
        return _seconds_to_minutes(int(ss.group(1)))
    return None


def _stop_label(stop_count: Optional[int], fallback: Optional[str] = None) -> str:
    if stop_count is None:
        return fallback or "-"
    if stop_count <= 0:
        return "도착"
    if stop_count == 1:
        return "곧 도착"
    if stop_count <= 3:
        return f"임박 · {stop_count}정거장"
    return f"{stop_count}정거장 전"


def _seat_label(
    congestion_code: Optional[str],
    is_full: bool,
    is_arrived: bool,
    stop_count: Optional[int],
    fallback_msg: Optional[str],
) -> str:
    if is_full:
        return "만차"
    if is_arrived:
        return "도착"
    level = _CONGESTION_MAP.get(_as_str(congestion_code))
    if level:
        return level
    return _stop_label(stop_count, fallback=fallback_msg)


def _flatten_item(item: Dict[str, Any], idx: int) -> Optional[Dict[str, Any]]:
    """`getStationByUid` item 의 arrmsg{idx} 계열을 평탄화."""
    msg = _as_str(item.get(f"arrmsg{idx}")).strip()
    if not msg:
        return None
    if "출발대기" in msg or "운행종료" in msg:
        return None

    minutes_from_tra = _seconds_to_minutes(item.get(f"traTime{idx}"))
    minutes_from_msg = _minutes_from_msg(msg)
    # traTime 이 정확도가 높으나 종종 0으로 내려오는 경우가 있어 msg 값을 우선.
    minutes = minutes_from_msg if minutes_from_msg is not None else (minutes_from_tra or 0)

    stop_count = _parse_stop_count(msg)
    congestion_code = _as_str(item.get(f"congestion{idx}"))
    is_full = _as_str(item.get(f"isFullFlag{idx}")) == "1"
    is_last = _as_str(item.get(f"isLast{idx}")) == "1"
    is_arrived = _as_str(item.get(f"isArrive{idx}")) == "1"
    bus_type = _BUSTYPE_MAP.get(_as_str(item.get(f"busType{idx}")), "")

    return {
        "minutes": int(minutes),
        "seat": _seat_label(congestion_code, is_full, is_arrived, stop_count, msg),
        "plate": "",  # 서울시 공공 API 는 차량번호 미제공
        "stop_count": stop_count,
        "route": _as_str(item.get("rtNm")) or _as_str(item.get("busRouteAbrv")),
        "direction": _as_str(item.get("adirection")),
        "final_stop": _as_str(item.get(f"stationNm{idx}")),
        "bus_type": bus_type,
        "congestion": _CONGESTION_MAP.get(congestion_code, ""),
        "is_full": is_full,
        "is_last": is_last,
        "is_arrived": is_arrived,
        "message": msg,
    }


def _unwrap_service_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    """JSON 응답이 ``{"ServiceResult": {...}}`` 로 래핑되는 경우를 흡수."""
    if isinstance(payload.get("ServiceResult"), dict):
        return payload["ServiceResult"]
    return payload


def _items_of(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    body = payload.get("msgBody") or {}
    raw = body.get("itemList")
    if raw is None:
        raw = body.get("item")
    if raw is None:
        items: List[Any] = []
    elif isinstance(raw, dict):
        items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    return [x for x in items if isinstance(x, dict)]


async def get_arrival(
    stop_id: str, route_id: Optional[str] = None
) -> Dict[str, Any]:
    """정류소 번호(ARS) 기준 실시간 도착 예정 정보.

    Parameters
    ----------
    stop_id : str
        ARS 정류소 번호 (예: ``"12121"``). 5자리 숫자.
    route_id : Optional[str]
        쉼표로 구분된 노선명(예: ``"7211,146"``). ``None`` 이면 전체 노선.

    Returns
    -------
    Dict[str, Any]
        ``{"stop_id", "stop_name", "route_id", "arrivals": [...]}`` 형태.
        ``arrivals`` 원소 구조는 ``_flatten_item`` 참고.
    """
    stop_id_str = _as_str(stop_id).strip()
    if not stop_id_str:
        return _empty_result(stop_id, route_id, note="정류소 번호(arsId)가 비어 있습니다.")

    if BUS_USE_MOCK or not BUS_API_KEY:
        if not BUS_API_KEY and not BUS_USE_MOCK:
            logger.warning(
                "SEOUL_BUS_API_KEY not set → returning mock bus data. "
                "공공데이터포털에서 발급 후 .env 에 SEOUL_BUS_API_KEY 를 설정해 주세요."
            )
        return _mock_arrival(stop_id_str, route_id)

    routes = {r.strip() for r in (route_id or "").split(",") if r.strip()}

    params = {
        "serviceKey": BUS_API_KEY,
        "arsId": stop_id_str,
        "resultType": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BUS_BASE_URL}/getStationByUid", params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.warning("Seoul bus API failed (%s) → mock fallback", e)
        return _mock_arrival(stop_id_str, route_id)

    root = _unwrap_service_result(payload)
    header = (root.get("msgHeader") or {})
    if not _is_ok_header(header.get("headerCd")):
        msg = _as_str(header.get("headerMsg")) or "Seoul Bus API error"
        logger.warning("Seoul bus API headerCd=%s (%s)", header.get("headerCd"), msg)
        return _empty_result(stop_id_str, route_id, note=msg)

    items = _items_of(root)
    arrivals: List[Dict[str, Any]] = []
    stop_name = ""
    for item in items:
        stop_name = stop_name or _as_str(item.get("stNm"))
        route_name = _as_str(item.get("rtNm")) or _as_str(item.get("busRouteAbrv"))
        if routes and route_name not in routes:
            continue
        for idx in (1, 2):
            entry = _flatten_item(item, idx)
            if entry is not None:
                # 노선 부가정보: 배차간격/유형 (UI 서브라인용)
                entry["route_type"] = _ROUTE_TYPE_MAP.get(
                    _as_str(item.get("routeType")), ""
                )
                entry["interval_min"] = _as_str(item.get("term"))
                arrivals.append(entry)

    arrivals.sort(key=lambda a: (a["minutes"], a.get("stop_count") or 999))

    return {
        "stop_id": stop_id_str,
        "stop_name": stop_name,
        "route_id": route_id,
        "arrivals": arrivals,
    }


async def get_routes_by_station(ars_id: str) -> List[Dict[str, Any]]:
    """정류소에서 경유하는 노선 전체 목록(`getRouteByStation`).

    반환 각 원소::

        {
          "route":        "7211",              # 노선명(안내용)
          "route_id":     "100100344",         # 노선 ID
          "type":         "지선",              # 노선유형 한글
          "interval_min": "7",                 # 배차간격 (분)
          "first_time":   "0410",              # 금일 첫차 HHMM
          "last_time":    "2300",              # 금일 막차 HHMM
          "begin":        "진관공영차고지",     # 기점
          "end":          "신설동",            # 종점
        }
    """
    ars_id_str = _as_str(ars_id).strip()
    if not ars_id_str:
        return []

    if BUS_USE_MOCK or not BUS_API_KEY:
        return _mock_routes(ars_id_str)

    params = {
        "serviceKey": BUS_API_KEY,
        "arsId": ars_id_str,
        "resultType": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BUS_BASE_URL}/getRouteByStation", params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.warning("routes-by-station failed (%s) → mock", e)
        return _mock_routes(ars_id_str)

    root = _unwrap_service_result(payload)
    items = _items_of(root)

    results: List[Dict[str, Any]] = []
    for item in items:
        route_nm = (
            _as_str(item.get("busRouteAbrv"))
            or _as_str(item.get("busRouteNm"))
        )
        if not route_nm:
            continue
        results.append(
            {
                "route": route_nm,
                "route_id": _as_str(item.get("busRouteId")),
                "type": _ROUTE_TYPE_MAP.get(
                    _as_str(item.get("busRouteType")), ""
                ),
                "interval_min": _as_str(item.get("term")),
                "first_time": _hhmm(_as_str(item.get("firstBusTm"))),
                "last_time": _hhmm(_as_str(item.get("lastBusTm"))),
                "begin": _as_str(item.get("stBegin")),
                "end": _as_str(item.get("stEnd")),
            }
        )

    # 노선 유형별 우선순위: 간선 > 광역 > 지선 > 순환 > 공항 > 경기/인천 > 마을
    type_order = {
        "간선": 0, "광역": 1, "지선": 2, "순환": 3,
        "공항": 4, "경기": 5, "인천": 6, "마을": 7, "": 9,
    }
    results.sort(
        key=lambda r: (type_order.get(r["type"], 9), r["route"])
    )
    return results


def _hhmm(raw: str) -> str:
    """`firstBusTm` 등은 보통 'YYYYMMDDHHMMSS' 또는 'HHMM' 로 내려옴."""
    r = raw.strip()
    if not r:
        return ""
    if len(r) >= 12:  # YYYYMMDDHHMMSS → HHMM
        return f"{r[8:10]}:{r[10:12]}"
    if len(r) == 4:
        return f"{r[0:2]}:{r[2:4]}"
    return r


_ARS_ONLY_RE = re.compile(r"^\s*\d{4,5}\s*$")

# 자연어 문장에서 잘라 낼 때 쓰는 잡어(긴 것부터 제거)
_STATION_QUERY_NOISE = (
    "버스정류장에서",
    "버스정류소에서",
    "버스정류장",
    "버스 정류장",
    "버스정류소",
    "버스 정류소",
    "정류장에서",
    "정류소에서",
    "정류장",
    "정류소",
    "버스 ",
    "앞에서",
    "앞으로",
    " 앞",
    " 근처",
    " 쪽",
    "에서",
    "까지",
    "으로",
    "으로는",
    "로는",
    "타려고",
    "타고 싶",
    "타고",
    "가는",
    "가려고",
    "제일 가까운",
    "가까운",
    "출근할 때",
    "퇴근할 때",
    "여기서",
    "이쪽",
)


def _natural_station_name_queries(raw: str) -> List[str]:
    """자연어 한 줄에서 ``getStationByName`` 용 검색어 후보를 여러 개 만든다.

    예: "강남역 앞에서 버스 타려고" → ["강남역 앞에서 버스 타려고", "강남역", "강남역앞에서버스타려고"(띄어쓰기 제거)] 등.
    공공 API는 부분 일치이므로 핵심 지명이 들어간 짧은 후보가 잘 먹는 경우가 많다.
    """
    s = _as_str(raw).strip()
    if not s:
        return []
    seen: set[str] = set()
    out: List[str] = []

    def add(t: str) -> None:
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 2:
            return
        if len(t) > 80:
            t = t[:80].rstrip()
        if t in seen:
            return
        seen.add(t)
        out.append(t)

    add(s)

    # 「강남역」·"서울역" 등 따옴표 안 지명
    for m in re.finditer(r"[「\"']([^「」\"']{2,})[」\"']", s):
        add(m.group(1).strip())

    # 쉼표·줄바꿈으로 나뉜 덩어리 — 뒤쪽이 정류소명인 경우가 많아 **역순**으로 후보에 넣음
    if any(x in s for x in (",", "，", "\n")):
        parts = [
            p.strip()
            for p in re.split(r"[,，\n]+", s)
            if p.strip()
        ]
        for part in reversed(parts):
            add(part)

    # 잡어 제거 후 (긴 패턴부터)
    stripped = s
    for noise in sorted(_STATION_QUERY_NOISE, key=len, reverse=True):
        stripped = stripped.replace(noise, " ")
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped and stripped != s:
        add(stripped)

    # 띄어쓰기만 다른 표기 (강남 역 → 강남역)
    nospace = re.sub(r"\s+", "", s)
    if nospace != s and len(nospace) >= 2:
        add(nospace)

    return out


async def _lookup_one_station_by_ars(ars_id: str) -> Optional[Dict[str, Any]]:
    """ARS(5자리)로 정류소 한 곳만 해석. 이름 검색(`getStationByName`)은 숫자로는 잘 안 맞는다.

    순서: ``getStationByUid`` 로 정류소명 확보 → 비어 있으면 ``getRouteByStation`` 으로 유효성만 확인.
    """
    ars = _as_str(ars_id).strip().zfill(5)
    if not ars.isdigit():
        return None

    params = {
        "serviceKey": BUS_API_KEY,
        "arsId": ars,
        "resultType": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BUS_BASE_URL}/getStationByUid", params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.warning("getStationByUid (station search) failed: %s", e)
        payload = None

    if payload is not None:
        root = _unwrap_service_result(payload)
        header = root.get("msgHeader") or {}
        if _is_ok_header(header.get("headerCd")):
            items = _items_of(root)
            if items:
                it = items[0]
                ars_out = _as_str(it.get("arsId")) or ars
                return {
                    "stop_id": ars_out,
                    "station_id": _as_str(it.get("stId")),
                    "name": _as_str(it.get("stNm")) or f"ARS {ars_out}",
                    "lat": _as_float(it.get("tmY")),
                    "lng": _as_float(it.get("tmX")),
                }
        else:
            logger.info(
                "getStationByUid search headerCd=%s headerMsg=%s",
                header.get("headerCd"),
                header.get("headerMsg"),
            )

    # 도착 예정 노선이 없어 itemList 가 비어도 정류소는 존재할 수 있음 → 경유 노선으로 확인
    routes = await get_routes_by_station(ars)
    if routes:
        return {
            "stop_id": ars,
            "station_id": "",
            "name": f"ARS {ars} 정류장",
            "lat": None,
            "lng": None,
        }
    return None


async def _fetch_stations_by_name_single(
    client: httpx.AsyncClient, st_srch: str
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """``getStationByName`` 1회 호출. 성공 시 (rows, None), header 오류 시 (None, msg)."""
    params = {
        "serviceKey": BUS_API_KEY,
        "stSrch": st_srch,
        "resultType": "json",
    }
    try:
        resp = await client.get(f"{BUS_BASE_URL}/getStationByName", params=params)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning("getStationByName HTTP failed (%s)", e)
        return None, str(e)

    root = _unwrap_service_result(payload)
    header = root.get("msgHeader") or {}
    if not _is_ok_header(header.get("headerCd")):
        msg = _as_str(header.get("headerMsg")) or "API 오류"
        logger.info(
            "getStationByName stSrch=%r headerCd=%s (%s)",
            st_srch[:40],
            header.get("headerCd"),
            msg,
        )
        return None, msg

    items = _items_of(root)
    results: List[Dict[str, Any]] = []
    for item in items:
        ars = _as_str(item.get("arsId")) or "0"
        results.append(
            {
                "stop_id": ars,
                "station_id": _as_str(item.get("stId")),
                "name": _as_str(item.get("stNm")),
                "lat": _as_float(item.get("tmY")),
                "lng": _as_float(item.get("tmX")),
            }
        )
    results.sort(key=lambda r: (r["stop_id"] in ("", "0"), r["name"]))
    return results, None


async def search_stations(
    name: str, limit: int = 10
) -> Tuple[List[Dict[str, Any]], str]:
    """정류소 검색. 자연어 문장 → 후보 검색어 다중 시도 + ARS 숫자 전용 조회.

    Returns
    -------
    items : list
        ``stop_id``(ARS), ``name``, ``station_id``, ``lat``, ``lng``.
    hint : str
        결과가 없을 때 UI 에 보여 줄 안내 문구(빈 문자열이면 생략 가능).
    """
    q = _as_str(name).strip()
    if not q:
        return [], ""

    if BUS_USE_MOCK or not BUS_API_KEY:
        if _ARS_ONLY_RE.match(q):
            ars = q.strip().zfill(5)
            return (
                [
                    {
                        "stop_id": ars,
                        "station_id": "MOCK",
                        "name": f"(모의) ARS {ars} 정류장",
                        "lat": 37.5665,
                        "lng": 126.9780,
                    }
                ],
                "",
            )
        qs = _natural_station_name_queries(q)
        label = qs[0] if qs else q
        return _mock_search(label), ""

    # ----- 숫자만 4~5자리: ARS 번호로 간주 (이름 검색이 아님) -----
    if _ARS_ONLY_RE.match(q):
        ars = q.strip().zfill(5)
        one = await _lookup_one_station_by_ars(ars)
        if one:
            return [one][:limit], ""
        return [], (
            "이 ARS 번호로 정류소를 찾지 못했습니다. "
            "지도 앱에서 ARS를 확인하거나, 「○○역」처럼 정류소 이름으로 검색해 보세요."
        )

    # ----- 자연어·정류소명: 후보를 순서대로 시도 -----
    queries = _natural_station_name_queries(q)
    if not queries:
        return [], "검색어를 두 글자 이상 입력해 주세요."

    last_api_msg = ""
    async with httpx.AsyncClient(timeout=5.0) as client:
        for cand in queries:
            rows, err = await _fetch_stations_by_name_single(client, cand)
            if err is not None:
                last_api_msg = err
                continue
            if rows:
                return rows[:limit], ""

    if last_api_msg:
        return [], last_api_msg
    return [], (
        "검색 결과가 없습니다. 정류소 이름(예: 강남역, 서울역버스환승센터)만 적거나, "
        "「역 이름」처럼 따옴표로 감싸 보세요. ARS 번호(5자리)도 사용할 수 있습니다."
    )


def _as_float(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return x if x != 0.0 else None
    except (TypeError, ValueError):
        return None


def _empty_result(
    stop_id: Any, route_id: Optional[str], note: str = ""
) -> Dict[str, Any]:
    return {
        "stop_id": _as_str(stop_id),
        "stop_name": "",
        "route_id": route_id,
        "arrivals": [],
        "note": note,
    }


# ------------------------------------------------------------------ #
# Mock (키 미설정 또는 BUS_USE_MOCK=1 일 때)
# ------------------------------------------------------------------ #


def _mock_arrival(stop_id: str, route_id: Optional[str]) -> Dict[str, Any]:
    routes = [r.strip() for r in (route_id or "146,7711").split(",") if r.strip()]
    out: List[Dict[str, Any]] = []
    for r in routes[:2]:
        first_stop = random.randint(1, 3)
        second_stop = random.randint(4, 10)
        out.extend(
            [
                {
                    "minutes": random.randint(1, 5),
                    "seat": _seat_label("3", False, False, first_stop, None),
                    "plate": "",
                    "stop_count": first_stop,
                    "route": r,
                    "direction": "모의 방향",
                    "final_stop": "모의 종점",
                    "bus_type": "저상" if random.random() > 0.5 else "",
                    "congestion": "여유",
                    "is_full": False,
                    "is_last": False,
                    "is_arrived": False,
                    "message": f"{random.randint(1,5)}분후[{first_stop}번째 전]",
                    "route_type": "간선",
                    "interval_min": "7",
                },
                {
                    "minutes": random.randint(6, 20),
                    "seat": _seat_label("4", False, False, second_stop, None),
                    "plate": "",
                    "stop_count": second_stop,
                    "route": r,
                    "direction": "모의 방향",
                    "final_stop": "모의 종점",
                    "bus_type": "",
                    "congestion": "보통",
                    "is_full": False,
                    "is_last": False,
                    "is_arrived": False,
                    "message": f"{random.randint(6,20)}분후[{second_stop}번째 전]",
                    "route_type": "간선",
                    "interval_min": "9",
                },
            ]
        )
    out.sort(key=lambda a: (a["minutes"], a.get("stop_count") or 999))
    return {
        "stop_id": stop_id,
        "stop_name": "모의정류장",
        "route_id": route_id,
        "arrivals": out,
    }


def _mock_search(name: str) -> List[Dict[str, Any]]:
    return [
        {"stop_id": "12121", "station_id": "111000033", "name": f"{name} (모의1)", "lat": 37.612, "lng": 126.928},
        {"stop_id": "03737", "station_id": "102900092", "name": f"{name} (모의2)", "lat": 37.538, "lng": 126.956},
    ]


def _mock_routes(ars_id: str) -> List[Dict[str, Any]]:
    return [
        {"route": "146", "route_id": "100100118", "type": "간선", "interval_min": "6",
         "first_time": "04:20", "last_time": "23:30", "begin": "상계주공7단지", "end": "강남역"},
        {"route": "360", "route_id": "100100123", "type": "간선", "interval_min": "8",
         "first_time": "04:30", "last_time": "23:10", "begin": "송파공영차고지", "end": "영등포역"},
        {"route": "7211", "route_id": "100100344", "type": "지선", "interval_min": "7",
         "first_time": "04:10", "last_time": "23:00", "begin": "진관공영차고지", "end": "신설동"},
        {"route": "9401", "route_id": "200100001", "type": "광역", "interval_min": "10",
         "first_time": "05:00", "last_time": "22:40", "begin": "분당", "end": "서울역"},
    ]
