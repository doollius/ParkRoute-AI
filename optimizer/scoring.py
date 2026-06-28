from __future__ import annotations

from typing import Any


def choose_segment_mode(travel: dict[str, Any]) -> str:
    if travel.get("walk_allowed") and travel.get("walk_time_sec") is not None:
        walk = int(travel["walk_time_sec"])
        car = int(travel.get("car_time_sec") or 0)
        if walk <= car:
            return "walk"
    return "car"


def build_route_summary(
    segments: list[dict[str, Any]],
    parkings: list[dict[str, Any]] | int,
) -> dict[str, Any]:
    if isinstance(parkings, int):
        parking_count = parkings
        parking_cost = 0
    else:
        parking_count = len(parkings)
        parking_cost = sum(p.get("estimated_cost") or 0 for p in parkings)

    car_time = sum(s["time_sec"] for s in segments if s["mode"] == "car")
    walk_time = sum(s["time_sec"] for s in segments if s["mode"] == "walk")
    total_distance = sum(s.get("distance_m") or 0 for s in segments)
    return {
        "total_time_sec": car_time + walk_time,
        "car_time_sec": car_time,
        "walk_time_sec": walk_time,
        "total_distance_m": total_distance,
        "parking_count": parking_count,
        "parking_cost_won": parking_cost,
        "segment_count": len(segments),
    }


def format_duration(seconds: int) -> str:
    minutes = max(1, seconds // 60)
    if minutes < 60:
        return f"{minutes}분"
    h, m = divmod(minutes, 60)
    return f"{h}시간 {m}분" if m else f"{h}시간"
