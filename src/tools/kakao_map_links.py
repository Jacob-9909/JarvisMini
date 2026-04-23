"""Kakao 지도 웹 길찾기·지도 링크 (브라우저용, 별도 SDK 키 불필요).

참고: https://apis.map.kakao.com/web/guide/ — ``/link/by/{수단}/`` 패턴.
수단: ``traffic``(대중교통), ``car``, ``walk``, ``bicycle``
지하철: ``/link/by/subway/{region}/{출발역}/{도착역}``
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

KakaoRouteMode = Literal["traffic", "car", "walk", "bicycle"]
KakaoSubwayRegion = Literal["seoul", "busan", "daegu", "gwangju", "daejeon"]
SUBWAY_REGIONS: tuple[str, ...] = ("seoul", "busan", "daegu", "gwangju", "daejeon")


def _segment(name: str, lat: float, lng: float) -> str:
    n = (name or "").strip() or "장소"
    return f"{quote(n, safe='')},{lat},{lng}"


def kakao_directions_by_mode(
    from_name: str,
    from_lat: float,
    from_lng: float,
    to_name: str,
    to_lat: float,
    to_lng: float,
    mode: KakaoRouteMode = "traffic",
) -> str:
    """회사→목적지 길찾기 URL (카카오맵 웹)."""
    a = _segment(from_name, from_lat, from_lng)
    b = _segment(to_name, to_lat, to_lng)
    return f"https://map.kakao.com/link/by/{mode}/{a}/{b}"


def kakao_subway_directions(
    from_station: str,
    to_station: str,
    region: KakaoSubwayRegion = "seoul",
) -> str:
    """지하철 노선도 기반 길찾기 URL (카카오맵 웹).

    ``region`` 은 seoul/busan/daegu/gwangju/daejeon 중 하나.
    역명은 '강남역'처럼 접미사 포함해서 넣는다.
    """
    a = quote((from_station or "").strip(), safe="")
    b = quote((to_station or "").strip(), safe="")
    r = region if region in SUBWAY_REGIONS else "seoul"
    return f"https://map.kakao.com/link/by/subway/{r}/{a}/{b}"


__all__ = [
    "kakao_directions_by_mode",
    "kakao_subway_directions",
    "KakaoRouteMode",
    "KakaoSubwayRegion",
    "SUBWAY_REGIONS",
]
