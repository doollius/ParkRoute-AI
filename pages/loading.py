from __future__ import annotations

import streamlit as st

from state.session_manager import go_to


def render() -> None:
    st.title("경로 최적화 중...")
    steps = [
        "주소 분석",
        "좌표 변환",
        "그래프 생성",
        "주차장 탐색",
        "OR-Tools 실행",
        "결과 생성",
    ]
    progress = st.progress(0, text="준비 중...")
    for i, step in enumerate(steps):
        progress.progress((i + 1) / len(steps), text=step)

    st.warning("Optimizer 엔진은 다음 단계에서 연결됩니다. 지금은 데모 결과로 이동합니다.")
    st.session_state.route = {
        "stops": ["S", "1", "2", "E"],
        "message": "데모 경로 (OR-Tools 미연결)",
    }
    st.session_state.optimized = True

    if st.button("결과 보기 →", type="primary"):
        go_to("result")
        st.rerun()
