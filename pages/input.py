from __future__ import annotations

import streamlit as st

from state.session_manager import go_to, reset_all


def render() -> None:
    st.title("여행 정보 입력")
    st.caption("도로명주소 또는 지번주소만 입력합니다. (네이버 공유 URL 미지원)")

    st.text_input("여행 지역", key="travel_region", placeholder="예: 부산")

    st.divider()
    st.subheader("방문 장소")
    st.info("장소 카드 UI는 다음 단계에서 구현됩니다. 현재는 골격 화면입니다.")

    if not st.session_state.places:
        st.session_state.places = [
            {"id": "1", "raw_input": "", "type": "맛집"},
            {"id": "2", "raw_input": "", "type": "카페"},
        ]

    for i, place in enumerate(st.session_state.places):
        with st.container(border=True):
            st.text_input(
                f"장소 {i + 1} 주소",
                key=f"place_{place['id']}",
                placeholder="예: 부산광역시 해운대구 해운대해변로 264",
            )
            st.selectbox(
                "유형",
                ["숙소", "맛집", "카페", "관광지"],
                key=f"type_{place['id']}",
            )

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("← 시작 화면"):
            go_to("start")
            st.rerun()
    with col2:
        if st.button("초기화"):
            reset_all()
            st.rerun()
    with col3:
        if st.button("입력 완료 →", type="primary"):
            go_to("review")
            st.rerun()
