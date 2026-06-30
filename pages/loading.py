from __future__ import annotations

import time

import streamlit as st

from controller.route_controller import (
    RouteOptimizationError,
    format_eta_range,
    finalize_success,
    run_optimization,
)
from services import place_service
from state.session_manager import go_to


def _progress_fraction(msg: str) -> float:
    if msg.startswith("1/4"):
        if "%" in msg:
            try:
                pct = int(msg.split("(")[1].split("%")[0])
                return 0.05 + pct / 100 * 0.35
            except (IndexError, ValueError):
                return 0.15
        if "완료" in msg:
            return 0.4
        return 0.1
    if msg.startswith("2/4"):
        if "완료" in msg:
            return 0.42
        try:
            part = msg.split("(")[1].split(")")[0]
            done_s, total_s = part.split("/")
            return 0.22 + int(done_s) / max(1, int(total_s)) * 0.18
        except (IndexError, ValueError):
            return 0.32
    if msg.startswith("3/4"):
        try:
            part = msg.split("(")[1].split(")")[0]
            done_s, total_s = part.split("/")
            return 0.45 + int(done_s) / max(1, int(total_s)) * 0.3
        except (IndexError, ValueError):
            return 0.55
    if "OR-Tools" in msg or "최적화" in msg:
        return 0.78
    if "재구성" in msg:
        return 0.9
    return 0.1


def _status_caption(msg: str, elapsed: int) -> str:
    if "OR-Tools" in msg:
        return f"{msg} · 약 1~2분 소요됩니다"
    return f"{msg} · {elapsed}초 경과"


def render() -> None:
    st.title("경로 최적화 중...")

    if st.session_state.get("_route_computed") and st.session_state.get("route"):
        go_to("result")
        st.rerun()
        return

    places, _, excluded, _ = place_service.prepare_optimization_input()
    n = len(places)
    st.caption(
        f"장소 {n}곳 · 예상 소요 {format_eta_range(n)} "
        "(외부 지도 API 호출 — 네트워크에 따라 더 걸릴 수 있습니다)"
    )
    st.caption("창을 닫지 마세요. 지도·주차장 데이터를 불러오는 중입니다.")

    started = time.time()
    progress = st.progress(0, text="준비 중…")
    status = st.empty()
    st.session_state.pop("parking_candidates_cache", None)
    st.session_state.pop("parking_coverage_cache", None)
    st.session_state.pop("_route_explanation", None)
    st.session_state.pop("_route_explanation_key", None)

    def on_progress(msg: str) -> None:
        elapsed = int(time.time() - started)
        status.caption(_status_caption(msg, elapsed))
        progress.progress(min(0.98, _progress_fraction(msg)), text=msg)

    try:
        progress.progress(0.02, text="입력 검증")
        status.caption(_status_caption("입력 검증", 0))
        with st.status("경로를 계산하고 있습니다…", expanded=True) as run_status:
            route = run_optimization(on_progress=on_progress)
            run_status.update(label="계산 완료", state="complete", expanded=False)
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
            st.session_state.input_step = "trip"
            go_to("input")
            st.rerun()
    except Exception as exc:
        progress.empty()
        status.empty()
        st.error(f"최적화 중 오류가 발생했습니다: {exc}")
        if st.button("← 입력 수정"):
            st.session_state.input_step = "trip"
            go_to("input")
            st.rerun()
