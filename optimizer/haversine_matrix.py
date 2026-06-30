from __future__ import annotations

from typing import Any

from constants.config import PARKING_HAVERSINE_PREFILTER_M, WALK_TIME_LIMIT_MINUTES
from utils.geo import estimate_travel_sec, haversine_m

WALK_LIMIT_SEC = WALK_TIME_LIMIT_MINUTES * 60


def haversine_leg(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
) -> dict[str, Any]:
    """Pass 1 — TMAP 없이 직선 기반 이동 leg."""
    straight_m = haversine_m(from_lat, from_lng, to_lat, to_lng)
    car = estimate_travel_sec(from_lat, from_lng, to_lat, to_lng, "car")
    walk = estimate_travel_sec(from_lat, from_lng, to_lat, to_lng, "walk")
    walk_allowed = (
        straight_m <= PARKING_HAVERSINE_PREFILTER_M
        and int(walk["time_sec"]) <= WALK_LIMIT_SEC
    )
    return {
        "car_time_sec": car["time_sec"],
        "car_distance_m": car["distance_m"],
        "walk_time_sec": walk["time_sec"],
        "walk_distance_m": walk["distance_m"],
        "walk_allowed": walk_allowed,
        "walk_error": None,
        "car_estimated": True,
        "walk_estimated": True,
        "estimated": True,
    }


def build_haversine_travel_matrix(
    nodes: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """N×N 직선 기반 travel matrix (API 호출 없음)."""
    n = len(nodes)
    matrix: list[list[dict[str, Any]]] = []
    for i in range(n):
        row: list[dict[str, Any]] = []
        for j in range(n):
            if i == j:
                row.append(
                    {
                        "car_time_sec": 0,
                        "car_distance_m": 0,
                        "walk_time_sec": 0,
                        "walk_distance_m": 0,
                        "walk_allowed": True,
                        "walk_error": None,
                        "car_estimated": False,
                        "walk_estimated": False,
                        "estimated": False,
                    }
                )
            else:
                a, b = nodes[i], nodes[j]
                row.append(
                    haversine_leg(
                        float(a["lat"]),
                        float(a["lng"]),
                        float(b["lat"]),
                        float(b["lng"]),
                    )
                )
        matrix.append(row)
    return matrix
