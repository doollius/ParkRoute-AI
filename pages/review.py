from __future__ import annotations

import streamlit as st

from state.session_manager import go_to


def render() -> None:
    st.title("입력 확인")
    st.write(f"**여행 지역:** {st.session_state.travel_region or '(미입력)'}")
    st.write(f"**장소 수:** {len(st.session_state.places)}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 수정하기"):
            go_to("input")
            st.rerun()
    with col2:
        if st.button("최적 경로 생성 →", type="primary"):
            go_to("loading")
            st.rerun()
