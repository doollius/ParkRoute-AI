from __future__ import annotations

import streamlit as st

from services.route_service import RouteOptimizationError, optimize_route
from state.session_manager import go_to


def render() -> None:
    st.title("경로 최적화 중...")

    if st.session_state.get("_route_computed") and st.session_state.get("route"):
        go_to("result")
        st.rerun()
        return

    steps = [
        "주소 분석",
        "좌표 변환",
        "이동시간 계산",
        "주차장 탐색",
        "OR-Tools 실행",
        "결과 생성",
    ]
    progress = st.progress(0, text="준비 중...")

    try:
        for i, step in enumerate(steps[:4]):
            progress.progress((i + 1) / len(steps), text=step)

        route = optimize_route(
            places=st.session_state.places,
            start_place_id=st.session_state.start_place_id,
            end_place_id=st.session_state.end_place_id,
            travel_region=st.session_state.get("travel_region", ""),
            optimization_mode=st.session_state.get("optimization_mode", "minimize_walk"),
            visit_rules=st.session_state.get("visit_rules", []),
            trip_start_time=st.session_state.get("trip_start_time", "09:00"),
        )

        progress.progress(5 / len(steps), text=steps[4])
        progress.progress(6 / len(steps), text=steps[5])

        st.session_state.route = route
        st.session_state.optimized = True
        st.session_state._route_computed = True
        progress.progress(1.0, text="완료!")
        go_to("result")
        st.rerun()

    except RouteOptimizationError as exc:
        progress.empty()
        st.error(str(exc))
        if st.button("← 입력 수정"):
            go_to("input")
            st.rerun()
    except Exception as exc:
        progress.empty()
        st.error(f"최적화 중 오류가 발생했습니다: {exc}")
        if st.button("← 입력 수정"):
            go_to("input")
            st.rerun()
