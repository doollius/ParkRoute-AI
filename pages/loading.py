from __future__ import annotations

import streamlit as st

from services import place_service
from services.route_service import RouteOptimizationError, optimize_route
from state.session_manager import go_to


def render() -> None:
    st.title("경로 최적화 중...")

    if st.session_state.get("_route_computed") and st.session_state.get("route"):
        go_to("result")
        st.rerun()
        return

    progress = st.progress(0, text="준비 중...")
    status = st.empty()

    st.session_state.pop("parking_candidates_cache", None)

    places, input_warnings, excluded, visit_rules = place_service.prepare_optimization_input()

    def on_progress(msg: str) -> None:
        status.caption(msg)
        if "OR-Tools" in msg:
            progress.progress(0.75, text=msg)
        elif "경로 재구성" in msg:
            progress.progress(0.9, text=msg)
        elif "주차장" in msg:
            progress.progress(0.55, text=msg)
        elif "이동시간" in msg:
            if "완료" in msg:
                progress.progress(0.5, text=msg)
            elif "%" in msg:
                try:
                    pct = int(msg.split("(")[1].split("%")[0])
                    progress.progress(0.1 + pct / 100 * 0.4, text=msg)
                except (IndexError, ValueError):
                    progress.progress(0.2, text=msg)
            else:
                progress.progress(0.15, text=msg)
        else:
            progress.progress(0.1, text=msg)

    try:
        progress.progress(0.05, text="입력 검증")
        route = optimize_route(
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

        st.session_state.route = route
        st.session_state.optimized = True
        st.session_state._route_computed = True
        progress.progress(1.0, text="완료!")
        status.empty()
        if route.get("warnings"):
            st.session_state.route_warnings = route["warnings"]
        else:
            st.session_state.pop("route_warnings", None)
        go_to("result")
        st.rerun()

    except RouteOptimizationError as exc:
        progress.empty()
        status.empty()
        st.error(str(exc))
        if st.button("← 입력 수정"):
            go_to("input")
            st.rerun()
    except Exception as exc:
        progress.empty()
        status.empty()
        st.error(f"최적화 중 오류가 발생했습니다: {exc}")
        if st.button("← 입력 수정"):
            go_to("input")
            st.rerun()
