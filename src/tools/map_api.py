"""지도 API 래퍼 (Kakao Local / Naver Place).

주변 장소 검색(길찾기 도착지 후보 등)에 사용.
KAKAO_REST_KEY 가 비어 있을 때만 구로 mock 을 쓴다(개발용).
키가 있는데 API 가 실패하면 mock 으로 숨기지 않고 빈 목록을 반환한다.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")


def kakao_rest_key() -> str:
    """`.env` 반영을 위해 매번 읽는다(import 순서로 키가 비는 문제 완화)."""
    return (os.getenv("KAKAO_REST_KEY") or "").strip()


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """WGS84 두 점 사이 거리(미터, 구면 근사)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _places_from_kakao_documents(documents: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(documents, list):
        return out
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        try:
            lat_v = float(doc.get("y")) if doc.get("y") is not None else None
            lng_v = float(doc.get("x")) if doc.get("x") is not None else None
        except (TypeError, ValueError):
            lat_v, lng_v = None, None
        out.append(
            {
                "name": doc.get("place_name"),
                "category": doc.get("category_name"),
                "distance_m": int(doc.get("distance") or 0),
                "address": doc.get("road_address_name") or doc.get("address_name"),
                "url": doc.get("place_url"),
                "lat": lat_v,
                "lng": lng_v,
            }
        )
    return out


async def nearby_places(
    lat: float,
    lng: float,
    radius_m: int = 500,
    category: str = "CE7",
    query: Optional[str] = None,
    size: int = 10,
) -> List[Dict[str, Any]]:
    """장소 검색 (Kakao Local).

    - **키워드** (`query` 있음): ``x,y`` 기준 **거리순** 정렬만 하고 ``radius`` 는 넣지 않는다.
      역·지명이 회사에서 20km 넘어도 잡힌다. (반경을 쓰면 회기역 같은 원거리 목적지가 비는 경우가 많음)
    - **카테고리만**: ``radius_m`` + ``category_group_code`` 로 반경 검색.

    category_group_code (Kakao):
        CE7: 카페, FD6: 음식점, CS2: 편의점
    """
    key = kakao_rest_key()
    if not key:
        return _mock_places(category, query)

    headers = {"Authorization": f"KakaoAK {key}"}
    params: Dict[str, Any] = {
        "x": lng,
        "y": lat,
        "size": size,
    }
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    if query:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        params["query"] = query
        params["sort"] = "distance"
    else:
        params["radius"] = radius_m
        params["sort"] = "distance"
        params["category_group_code"] = category

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if not resp.is_success:
                logger.warning(
                    "Kakao Local HTTP %s %s — body: %s",
                    resp.status_code,
                    url,
                    (resp.text or "")[:400],
                )
                return []
            data = resp.json()
            out = _places_from_kakao_documents(data.get("documents") or [])

            # 1차(x,y+거리순, 반경 없음)가 비면: 키워드만 전국 검색 후 회사 좌표와의 직선거리로 정렬
            if query and not out:
                kw_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
                resp2 = await client.get(
                    kw_url,
                    params={"query": query, "size": 15},
                    headers=headers,
                )
                if resp2.is_success:
                    data2 = resp2.json()
                    cand = _places_from_kakao_documents(data2.get("documents") or [])
                    with_coords = [
                        p
                        for p in cand
                        if p.get("lat") is not None and p.get("lng") is not None
                    ]
                    with_coords.sort(
                        key=lambda p: _haversine_m(
                            lat, lng, float(p["lat"]), float(p["lng"])
                        )
                    )
                    out = []
                    for p in with_coords[:size]:
                        d_m = int(
                            _haversine_m(lat, lng, float(p["lat"]), float(p["lng"]))
                        )
                        out.append({**p, "distance_m": d_m})

            return out
    except Exception as e:
        logger.warning("Kakao Local request failed: %s", e)
        return []


def _mock_places(category: str, query: Optional[str]) -> List[Dict[str, Any]]:
    """KAKAO_REST_KEY 없을 때만 사용. (키 있는데 API 실패 시에는 호출하지 않음)"""
    # 구로구 구로동 대륭포스트타워8차 부근 mock 좌표 — 지도 시각화 테스트용
    if category == "FD6" or query:
        return [
            {"name": "구로 한식당", "category": "음식점 > 한식", "distance_m": 110, "address": "서울 구로구 디지털로26길 111", "url": "", "lat": 37.4862, "lng": 126.9001},
            {"name": "디지털단지 스시바", "category": "음식점 > 일식", "distance_m": 240, "address": "서울 구로구 구로동 188-25", "url": "", "lat": 37.4851, "lng": 126.9012},
            {"name": "포스트타워 마라탕", "category": "음식점 > 중식", "distance_m": 165, "address": "서울 구로구 디지털로31길 12", "url": "", "lat": 37.4865, "lng": 126.8994},
        ]
    return [
        {"name": "카페 구로점", "category": "카페 > 스페셜티", "distance_m": 85, "address": "서울 구로구 디지털로26길 43", "url": "", "lat": 37.4856, "lng": 126.9008},
        {"name": "스타벅스 구로디지털", "category": "카페 > 프랜차이즈", "distance_m": 195, "address": "서울 구로구 구로동 197-11", "url": "", "lat": 37.4868, "lng": 126.8999},
        {"name": "투썸플레이스 대륭", "category": "카페 > 프랜차이즈", "distance_m": 320, "address": "서울 구로구 디지털로 300", "url": "", "lat": 37.4849, "lng": 126.9018},
    ]
