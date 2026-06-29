from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from api.tmap_api import TmapApiError, get_car_route, get_car_route_matrix, get_walk_route
from constants.config import PARKING_HAVERSINE_PREFILTER_M, WALK_TIME_LIMIT_MINUTES
from utils.geo import coord_key, estimate_travel_sec, haversine_m, is_trivial_route, zero_route_metrics

WALK_LIMIT_SEC = WALK_TIME_LIMIT_MINUTES * 60


def _cache() -> dict[str, dict[str, Any]]:
    if "tmap_route_cache" not in st.session_state:
        st.session_state.tmap_route_cache = {}
    return st.session_state.tmap_route_cache


def _leg_key(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> str:
    return f"{coord_key(from_lat, from_lng)}->{coord_key(to_lat, to_lng)}"


def _empty_leg() -> dict[str, Any]:
    return {
        "car_time_sec": 0,
        "car_distance_m": 0,
        "walk_time_sec": 0,
        "walk_distance_m": 0,
        "walk_allowed": True,
        "walk_error": None,
        "estimated": False,
        "car_estimated": False,
        "walk_estimated": False,
    }


def _cache_leg(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    leg: dict[str, Any],
) -> None:
    _cache()[_leg_key(from_lat, from_lng, to_lat, to_lng)] = leg


def _fetch_walk_leg(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
) -> tuple[dict[str, int], bool, str | None]:
    if is_trivial_route(from_lat, from_lng, to_lat, to_lng):
        return zero_route_metrics(), False, None

    walk_error: str | None = None
    estimated = False
    try:
        walk = get_walk_route(from_lng, from_lat, to_lng, to_lat)
    except TmapApiError as exc:
        walk = estimate_travel_sec(from_lat, from_lng, to_lat, to_lng, "walk")
        estimated = True
        walk_error = str(exc)
    return walk, estimated, walk_error


def _fetch_car_leg(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
) -> tuple[dict[str, int], bool, str | None]:
    if is_trivial_route(from_lat, from_lng, to_lat, to_lng):
        return zero_route_metrics(), False, None

    car_error: str | None = None
    estimated = False
    try:
        car = get_car_route(from_lng, from_lat, to_lng, to_lat)
    except TmapApiError as exc:
        car = estimate_travel_sec(from_lat, from_lng, to_lat, to_lng, "car")
        estimated = True
        car_error = str(exc)
    return car, estimated, car_error


def _walk_leg_for_matrix(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
) -> tuple[dict[str, int], bool, bool, str | None]:
    """근거리만 TMAP 도보 API 호출. 장거리는 API 생략 + walk_allowed=False."""
    straight_m = haversine_m(from_lat, from_lng, to_lat, to_lng)
    if straight_m > PARKING_HAVERSINE_PREFILTER_M:
        est = estimate_travel_sec(from_lat, from_lng, to_lat, to_lng, "walk")
        return est, False, False, None

    walk, walk_est, walk_err = _fetch_walk_leg(from_lat, from_lng, to_lat, to_lng)
    walk_allowed = int(walk["time_sec"]) <= WALK_LIMIT_SEC
    return walk, walk_est, walk_allowed, walk_err


def _leg_from_parts(
    car: dict[str, int],
    *,
    car_estimated: bool,
    walk: dict[str, int],
    walk_estimated: bool,
    walk_allowed: bool,
    error: str | None,
    walk_only: bool = False,
) -> dict[str, Any]:
    walk_sec = walk["time_sec"] if walk else None
    return {
        "car_time_sec": car["time_sec"],
        "car_distance_m": car["distance_m"],
        "walk_time_sec": walk_sec,
        "walk_distance_m": walk.get("distance_m") if walk else None,
        "walk_allowed": walk_allowed,
        "walk_error": error,
        "car_estimated": car_estimated,
        "walk_estimated": walk_estimated,
        "estimated": walk_estimated if walk_only else car_estimated,
    }


def get_travel_times(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    *,
    walk_only: bool = False,
) -> dict[str, Any]:
    """Return car/walk time between two coordinates (cached). walk_only면 도보 API만 호출."""
    key = _leg_key(from_lat, from_lng, to_lat, to_lng)
    cache = _cache()
    cached = cache.get(key)
    if cached and (not walk_only or cached.get("walk_time_sec") is not None):
        return cached

    walk_error: str | None = cached.get("walk_error") if cached else None
    car_estimated = bool(cached and cached.get("car_estimated"))
    walk_estimated = bool(cached and cached.get("walk_estimated"))

    if walk_only:
        walk, walk_est, walk_err = _fetch_walk_leg(from_lat, from_lng, to_lat, to_lng)
        walk_error = walk_err or walk_error
        walk_estimated = walk_estimated or walk_est
        car = {
            "time_sec": int(cached.get("car_time_sec") or 0) if cached else 0,
            "distance_m": int(cached.get("car_distance_m") or 0) if cached else 0,
        }
        walk_allowed = int(walk["time_sec"]) <= WALK_LIMIT_SEC
        result = _leg_from_parts(
            car,
            car_estimated=car_estimated,
            walk=walk,
            walk_estimated=walk_estimated,
            walk_allowed=walk_allowed,
            error=walk_error,
            walk_only=True,
        )
    else:
        car, car_est, car_err = _fetch_car_leg(from_lat, from_lng, to_lat, to_lng)
        walk, walk_est, walk_allowed, walk_err = _walk_leg_for_matrix(
            from_lat, from_lng, to_lat, to_lng
        )
        car_estimated = car_estimated or car_est
        walk_estimated = walk_estimated or walk_est
        walk_error = car_err or walk_err or walk_error
        result = _leg_from_parts(
            car,
            car_estimated=car_estimated,
            walk=walk,
            walk_estimated=walk_estimated,
            walk_allowed=walk_allowed,
            error=walk_error,
        )

    cache[key] = result
    return result


def apply_walk_limit(
    travel_matrix: list[list[dict[str, Any]]],
    limit_minutes: int,
) -> list[list[dict[str, Any]]]:
    """Re-evaluate walk_allowed without extra API calls (ER-006 fallback)."""
    limit_sec = limit_minutes * 60
    updated: list[list[dict[str, Any]]] = []
    for row in travel_matrix:
        new_row: list[dict[str, Any]] = []
        for leg in row:
            walk_sec = leg.get("walk_time_sec")
            new_row.append(
                {
                    **leg,
                    "walk_allowed": walk_sec is not None and int(walk_sec) <= limit_sec,
                }
            )
        updated.append(new_row)
    return updated


def build_travel_matrix(
    nodes: list[dict[str, Any]],
    on_progress: Callable[[str], None] | None = None,
) -> list[list[dict[str, Any]]]:
    """Build NxN travel data matrix — 차량은 Matrix API 1회, 도보는 근거리만 개별 호출."""
    n = len(nodes)
    coords = [(float(node["lat"]), float(node["lng"])) for node in nodes]
    matrix: list[list[dict[str, Any]]] = []
    estimated_count = 0
    walk_estimated_count = 0
    car_matrix_estimated = False
    car_matrix_error: str | None = None

    if on_progress:
        on_progress("1/4 차량 이동시간 일괄 계산 중…")

    try:
        car_grid = get_car_route_matrix(coords)
    except TmapApiError as exc:
        car_matrix_estimated = True
        car_matrix_error = str(exc)
        car_grid = [
            [
                zero_route_metrics()
                if i == j
                else estimate_travel_sec(coords[i][0], coords[i][1], coords[j][0], coords[j][1], "car")
                for j in range(n)
            ]
            for i in range(n)
        ]

    walk_jobs = 0
    for i in range(n):
        for j in range(n):
            if i != j and haversine_m(*coords[i], *coords[j]) <= PARKING_HAVERSINE_PREFILTER_M:
                walk_jobs += 1
    walk_done = 0
    total_walk = max(1, walk_jobs)

    for i in range(n):
        row: list[dict[str, Any]] = []
        for j in range(n):
            if i == j:
                row.append(_empty_leg())
                continue

            a_lat, a_lng = coords[i]
            b_lat, b_lng = coords[j]
            car = {
                "time_sec": int(car_grid[i][j].get("time_sec") or 0),
                "distance_m": int(car_grid[i][j].get("distance_m") or 0),
            }
            car_estimated = car_matrix_estimated or bool(car_grid[i][j].get("estimated"))

            walk, walk_est, walk_allowed, walk_err = _walk_leg_for_matrix(
                a_lat, a_lng, b_lat, b_lng
            )
            if haversine_m(a_lat, a_lng, b_lat, b_lng) <= PARKING_HAVERSINE_PREFILTER_M:
                walk_done += 1
                if on_progress:
                    pct = min(99, int(walk_done / total_walk * 100))
                    on_progress(f"1/4 도보 이동시간 계산 중… ({pct}%)")

            leg = _leg_from_parts(
                car,
                car_estimated=car_estimated,
                walk=walk,
                walk_estimated=walk_est,
                walk_allowed=walk_allowed,
                error=car_matrix_error or walk_err,
            )
            _cache_leg(a_lat, a_lng, b_lat, b_lng, leg)

            if leg.get("car_estimated") and int(leg.get("car_time_sec") or 0) > 0:
                estimated_count += 1
            if leg.get("walk_estimated") and int(leg.get("walk_time_sec") or 0) > 0:
                walk_estimated_count += 1
            row.append(leg)
        matrix.append(row)

    if estimated_count and on_progress:
        on_progress(f"1/4 이동시간 계산 완료 (차량 구간 추정 {estimated_count}건)")
    elif walk_estimated_count and on_progress:
        on_progress(f"1/4 이동시간 계산 완료 (도보 구간 추정 {walk_estimated_count}건)")
    elif on_progress:
        on_progress("1/4 이동시간 계산 완료")
    return matrix
