from __future__ import annotations

from typing import Any

from constants.config import PARKING_WALK_MAX_DISTANCE_M


def walk_distance_m(leg: dict[str, Any]) -> int | None:
    raw = leg.get("walk_distance_m")
    if raw is None:
        return None
    return int(raw)


def walk_leg_ok_distance(
    leg: dict[str, Any],
    max_m: int = PARKING_WALK_MAX_DISTANCE_M,
) -> bool:
    """TMAP 도보 경로 거리가 max_m 이하인지 (주차 횟수 최소화 모드)."""
    dist = walk_distance_m(leg)
    return dist is not None and dist <= max_m


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
) -> str:
    if force_mode:
        return force_mode
    if parking_mode and (prefer_walk or walk_leg_ok_distance(leg)):
        if leg.get("walk_time_sec") is not None:
            return "walk"
    if prefer_walk and leg.get("walk_allowed"):
        return "walk"
    from optimizer.scoring import choose_segment_mode

    return choose_segment_mode(leg)
