from __future__ import annotations

from typing import Any

from constants.config import PARKING_WALK_MAX_DISTANCE_M
from utils.geo import haversine_m


def walk_distance_m(leg: dict[str, Any]) -> int | None:
    raw = leg.get("walk_distance_m")
    if raw is None:
        return None
    return int(raw)


def walk_leg_ok_distance(
    leg: dict[str, Any],
    max_m: int = PARKING_WALK_MAX_DISTANCE_M,
    *,
    from_lat: float | None = None,
    from_lng: float | None = None,
    to_lat: float | None = None,
    to_lng: float | None = None,
) -> bool:
    """TMAP 도보 경로 거리가 max_m 이하인지. API 실패·미호출 시 직선거리로 판정."""
    dist = walk_distance_m(leg)
    if dist is not None and dist <= max_m:
        return True
    if (
        from_lat is not None
        and from_lng is not None
        and to_lat is not None
        and to_lng is not None
        and (leg.get("walk_estimated") or dist is None)
    ):
        return int(haversine_m(from_lat, from_lng, to_lat, to_lng)) <= max_m
    return False


def walk_sec_for_leg(
    leg: dict[str, Any],
    *,
    parking_mode: bool = False,
    max_walk_m: int = PARKING_WALK_MAX_DISTANCE_M,
) -> int | None:
    """도보 시간(초). parking_mode면 거리≤max_walk_m, 아니면 walk_allowed(9분)."""
    if leg.get("walk_time_sec") is None:
        return None
    if parking_mode:
        if walk_leg_ok_distance(leg, max_walk_m):
            return int(leg["walk_time_sec"])
        return None
    if leg.get("walk_allowed"):
        return int(leg["walk_time_sec"])
    return None


def segment_mode_for_leg(
    leg: dict[str, Any],
    *,
    parking_mode: bool = False,
    prefer_walk: bool = False,
    force_mode: str | None = None,
    from_lat: float | None = None,
    from_lng: float | None = None,
    to_lat: float | None = None,
    to_lng: float | None = None,
) -> str:
    if force_mode:
        return force_mode
    walk_ok = walk_leg_ok_distance(
        leg,
        from_lat=from_lat,
        from_lng=from_lng,
        to_lat=to_lat,
        to_lng=to_lng,
    )
    if parking_mode and (prefer_walk or walk_ok):
        if leg.get("walk_time_sec") is not None:
            return "walk"
    if prefer_walk and leg.get("walk_allowed"):
        return "walk"
    from optimizer.scoring import choose_segment_mode

    return choose_segment_mode(leg)
