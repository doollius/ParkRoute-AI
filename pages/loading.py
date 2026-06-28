from __future__ import annotations

import streamlit as st

from controller.route_controller import (
    RouteOptimizationError,
    estimate_optimization_seconds,
    finalize_success,
    run_optimization,
)
from services import place_service
from state.session_manager import go_to


def render() -> None:
    st.title("경로 최적화 중...")

    if st.session_state.get("_route_computed") and st.session_state.get("route"):
        go_to("result")
        st.rerun()
        return

    places, _, excluded, _ = place_service.prepare_optimization_input()
    n = len(places)
    eta = estimate_optimization_seconds(n)
    st.caption(f"장소 {n}곳 · 예상 소요 약 {eta // 60}분 {eta % 60}초 (TMAP API 호출량에 따라 달라질 수 있습니다)")

    progress = st.progress(0, text="준비 중...")
    status = st.empty()
    st.session_state.pop("parking_candidates_cache", None)

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
        route = run_optimization(on_progress=on_progress)
        finalize_success(route)
        progress.progress(1.0, text="완료!")
        status.empty()
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
