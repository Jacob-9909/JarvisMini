"""지도 API 래퍼 (Kakao Local / Naver Place).

카페/맛집 레이더에 사용. KAKAO_REST_KEY 미설정 시 mock.
"""

from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

KAKAO_REST_KEY = os.getenv("KAKAO_REST_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")


async def nearby_places(
    lat: float,
    lng: float,
    radius_m: int = 500,
    category: str = "CE7",
    query: Optional[str] = None,
    size: int = 10,
) -> List[Dict[str, Any]]:
    """반경 내 장소 검색.

    category_group_code (Kakao):
        CE7: 카페, FD6: 음식점, CS2: 편의점
    """
    if not KAKAO_REST_KEY:
        return _mock_places(category, query)

    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    params = {
        "x": lng,
        "y": lat,
        "radius": radius_m,
        "size": size,
        "sort": "distance",
    }
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    if query:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        params["query"] = query
    else:
        params["category_group_code"] = category

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            out: List[Dict[str, Any]] = []
            for doc in data.get("documents", []):
                try:
                    lat_v = float(doc.get("y")) if doc.get("y") else None
                    lng_v = float(doc.get("x")) if doc.get("x") else None
                except (TypeError, ValueError):
                    lat_v, lng_v = None, None
                out.append(
                    {
                        "name": doc.get("place_name"),
                        "category": doc.get("category_name"),
                        "distance_m": int(doc.get("distance") or 0),
                        "address": doc.get("road_address_name")
                        or doc.get("address_name"),
                        "url": doc.get("place_url"),
                        "lat": lat_v,
                        "lng": lng_v,
                    }
                )
            return out
    except Exception as e:
        logger.warning("Kakao Local failed (%s) → mock", e)
        return _mock_places(category, query)


def _mock_places(category: str, query: Optional[str]) -> List[Dict[str, Any]]:
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
