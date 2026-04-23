"""map_api 거리·파싱 보조 함수 테스트."""

from __future__ import annotations

from src.tools.map_api import _haversine_m, _places_from_kakao_documents


def test_haversine_seoul_short() -> None:
    # 구로 디지털단지 부근 ~ 회기역 부근 (대략 15km 전후)
    guro_lat, guro_lng = 37.4856, 126.9008
    hoegi_lat, hoegi_lng = 37.5894, 127.0576
    m = _haversine_m(guro_lat, guro_lng, hoegi_lat, hoegi_lng)
    assert 10_000 < m < 25_000


def test_places_from_documents() -> None:
    docs = [
        {
            "place_name": "회기역 1호선",
            "category_name": "가까운 지하철역",
            "distance": "1200",
            "y": "37.5894",
            "x": "127.0576",
            "road_address_name": "",
            "address_name": "서울 동대문구",
            "place_url": "",
        }
    ]
    out = _places_from_kakao_documents(docs)
    assert len(out) == 1
    assert out[0]["name"] == "회기역 1호선"
    assert out[0]["lat"] == 37.5894
    assert out[0]["lng"] == 127.0576
