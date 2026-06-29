from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from constants.config import (
    OPTIMIZATION_BASE_SEC,
    TMAP_REQUEST_DELAY_SEC,
    TMAP_SEC_PER_PARKING_LEG,
)
from services.parking_service import tmap_parking_validate_limit
from services import place_service
from services.route_service import RouteOptimizationError, optimize_route


def _estimate_near_walk_pairs(place_count: int) -> int:
    """근거리 도보 API 호출 수 상한 (실제는 장소 배치에 따라 더 적을 수 있음)."""
    n = max(2, place_count)
    # 도시 내 여행: 대략 인접 쌍만 근거리로 가정
    return min(n * (n - 1), n * 3)


def estimate_optimization_range(place_count: int) -> tuple[int, int]:
    """TMAP 행렬 + 주차장 매칭 API 지연을 반영한 예상 소요(초) 범위."""
    n = max(2, place_count)
    car_matrix_sec = 8  # Matrix API 1회
    walk_pairs = _estimate_near_walk_pairs(n)
    walk_sec = walk_pairs * TMAP_SEC_PER_PARKING_LEG
    parking_legs = tmap_parking_validate_limit(n) * n * TMAP_SEC_PER_PARKING_LEG
    api_calls = 1 + walk_pairs + tmap_parking_validate_limit(n) * n
    kakao_sec = n * 1  # POI별 카카오 1회
    throttle_sec = int(api_calls * TMAP_REQUEST_DELAY_SEC)
    low = OPTIMIZATION_BASE_SEC + car_matrix_sec + walk_sec + parking_legs + throttle_sec + kakao_sec
    high = int(low * 1.75) + 15
    return max(45, low), max(75, high)


def estimate_optimization_seconds(place_count: int) -> int:
    """하위 호환 — 상한(초) 반환."""
    return estimate_optimization_range(place_count)[1]


def format_eta_range(place_count: int) -> str:
    low, high = estimate_optimization_range(place_count)
    if high >= 120:
        return f"약 {low // 60}~{high // 60}분"
    return f"약 {low // 60}분 {low % 60}초~{high // 60}분 {high % 60}초"


def run_optimization(
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    visit_places, input_warnings, excluded, visit_rules = place_service.prepare_optimization_input()
    nodes, start_idx, end_idx = place_service.build_optimization_graph(visit_places)
    if len(nodes) < 2:
        raise RouteOptimizationError("최적화할 좌표가 2곳 이상 필요합니다.")

    return optimize_route(
        nodes=nodes,
        start_idx=start_idx,
        end_idx=end_idx,
        travel_region=place_service.infer_travel_region(visit_places),
        optimization_mode=st.session_state.get("optimization_mode", "minimize_walk"),
        visit_rules=visit_rules,
        trip_start_time=st.session_state.get("trip_start_time", "09:00"),
        congestion_level=st.session_state.get("congestion_level", "normal"),
        on_progress=on_progress,
        input_warnings=input_warnings,
        excluded_places=excluded,
    )


def finalize_success(route: dict[str, Any]) -> None:
    st.session_state.route = route
    st.session_state.optimized = True
    st.session_state._route_computed = True
    if route.get("warnings"):
        st.session_state.route_warnings = route["warnings"]
    else:
        st.session_state.pop("route_warnings", None)


__all__ = [
    "RouteOptimizationError",
    "estimate_optimization_seconds",
    "estimate_optimization_range",
    "format_eta_range",
    "run_optimization",
    "finalize_success",
]
