from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from services import place_service
from services.route_service import RouteOptimizationError, optimize_route


def estimate_optimization_seconds(place_count: int) -> int:
    """Rough ETA for TMAP matrix + OR-Tools (Rules.md performance hint)."""
    n = max(2, place_count)
    pairs = n * (n - 1)
    return max(20, 10 + pairs * 2)


def run_optimization(
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    places, input_warnings, excluded, visit_rules = place_service.prepare_optimization_input()
    return optimize_route(
        places=places,
        start_place_id=st.session_state.start_place_id,
        end_place_id=st.session_state.end_place_id,
        travel_region=st.session_state.get("travel_region", ""),
        optimization_mode=st.session_state.get("optimization_mode", "minimize_walk"),
        visit_rules=visit_rules,
        trip_start_time=st.session_state.get("trip_start_time", "09:00"),
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
    "run_optimization",
    "finalize_success",
]
