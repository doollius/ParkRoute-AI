from __future__ import annotations

import threading
import time
from typing import Any

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


def _start_optimization_job() -> dict[str, Any]:
    st.session_state.pop("parking_candidates_cache", None)
    st.session_state.pop("parking_coverage_cache", None)
    st.session_state.pop("_route_explanation", None)
    st.session_state.pop("_route_explanation_key", None)

    job: dict[str, Any] = {
        "started": time.time(),
        "msg": "준비 중…",
        "done": False,
        "route": None,
        "error": None,
        "error_kind": None,
    }

    def worker() -> None:
        def on_progress(msg: str) -> None:
            job["msg"] = msg

        try:
            job["route"] = run_optimization(on_progress=on_progress)
        except RouteOptimizationError as exc:
            job["error_kind"] = "route"
            job["error"] = str(exc)
        except Exception as exc:
            job["error_kind"] = "generic"
            job["error"] = str(exc)
        finally:
            job["done"] = True

    threading.Thread(target=worker, daemon=True, name="route-optimization").start()
    return job


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

    job = st.session_state.get("_loading_job")
    if job is None:
        job = _start_optimization_job()
        st.session_state._loading_job = job

    progress = st.progress(0, text=job["msg"])
    status = st.empty()

    if job["done"]:
        st.session_state.pop("_loading_job", None)
        progress.empty()
        status.empty()

        if job["error_kind"] == "route":
            st.error(job["error"])
            if st.button("← 입력 수정"):
                st.session_state.input_step = "trip"
                go_to("input")
                st.rerun()
            return

        if job["error_kind"] == "generic":
            st.error(f"최적화 중 오류가 발생했습니다: {job['error']}")
            if st.button("← 입력 수정"):
                st.session_state.input_step = "trip"
                go_to("input")
                st.rerun()
            return

        finalize_success(job["route"])
        go_to("result")
        st.rerun()
        return

    elapsed = int(time.time() - job["started"])
    msg = job["msg"]
    status.caption(f"{msg} · {elapsed}초 경과")
    progress.progress(min(0.98, _progress_fraction(msg)), text=msg)

    with st.status("경로를 계산하고 있습니다…", expanded=True):
        st.caption(f"현재 단계: {msg}")
        st.caption(f"경과 {elapsed}초")

    # Streamlit은 메인 스크립트가 끝나야 화면이 갱신됨 → 1초마다 rerun
    time.sleep(1)
    st.rerun()
