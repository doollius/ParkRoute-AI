from __future__ import annotations

import math

from constants.config import (
    KOREA_LAT_MAX,
    KOREA_LAT_MIN,
    KOREA_LNG_MAX,
    KOREA_LNG_MIN,
    TMAP_MIN_ROUTE_DISTANCE_M,
)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def coord_key(lat: float, lng: float) -> str:
    return f"{lat:.5f},{lng:.5f}"


def is_valid_korea_coord(lat: float, lng: float) -> bool:
    return KOREA_LAT_MIN <= lat <= KOREA_LAT_MAX and KOREA_LNG_MIN <= lng <= KOREA_LNG_MAX


def fix_coordinate_order(lat: float, lng: float) -> tuple[float, float]:
    """위·경도가 뒤바뀐 경우(한국 좌표 패턴) 자동 교정."""
    if (
        KOREA_LNG_MIN <= lat <= KOREA_LNG_MAX
        and KOREA_LAT_MIN <= lng <= KOREA_LAT_MAX
    ):
        return lng, lat
    return lat, lng


def prepare_route_coords(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> tuple[float, float, float, float, str | None]:
    """Route API 호출 전 좌표 정규화. 오류 시 (0,0,0,0, reason)."""
    s_lat, s_lng = fix_coordinate_order(start_lat, start_lng)
    e_lat, e_lng = fix_coordinate_order(end_lat, end_lng)

    if not is_valid_korea_coord(s_lat, s_lng):
        return 0.0, 0.0, 0.0, 0.0, f"출발 좌표가 유효하지 않습니다 (lat={s_lat}, lng={s_lng})"
    if not is_valid_korea_coord(e_lat, e_lng):
        return 0.0, 0.0, 0.0, 0.0, f"도착 좌표가 유효하지 않습니다 (lat={e_lat}, lng={e_lng})"
    return s_lat, s_lng, e_lat, e_lng, None


def is_trivial_route(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> bool:
    return haversine_m(start_lat, start_lng, end_lat, end_lng) < TMAP_MIN_ROUTE_DISTANCE_M


def zero_route_metrics() -> dict[str, int]:
    return {"time_sec": 0, "distance_m": 0}


# Rules.md ER-009 fallback speeds
CAR_SPEED_KMH = 40
WALK_SPEED_KMH = 4


def estimate_travel_sec(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
    mode: str,
) -> dict[str, int]:
    distance_m = int(haversine_m(lat1, lng1, lat2, lng2))
    if distance_m < TMAP_MIN_ROUTE_DISTANCE_M:
        return zero_route_metrics()
    speed_kmh = WALK_SPEED_KMH if mode == "walk" else CAR_SPEED_KMH
    speed_mps = speed_kmh * 1000 / 3600
    time_sec = max(60, int(distance_m / speed_mps)) if speed_mps > 0 else 60
    return {"time_sec": time_sec, "distance_m": distance_m}

