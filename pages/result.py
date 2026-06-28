from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from state.session_manager import go_to

# Demo coordinates (Busan area) for map skeleton
DEMO_POINTS = [
    ("S", "출발", 35.1596, 129.0602),
    ("1", "장소 1", 35.1588, 129.0620),
    ("2", "장소 2", 35.1575, 129.0645),
    ("E", "도착", 35.1560, 129.0670),
]


def render() -> None:
    st.title("최적 경로 결과")

    route = st.session_state.get("route") or {}
    st.write(route.get("message", ""))

    col_left, col_right = st.columns([1, 2])
    with col_left:
        st.subheader("방문 순서")
        for label, name, _, _ in DEMO_POINTS:
            st.write(f"**{label}** — {name}")
        st.caption("AI 설명 · 주차 정보는 Optimizer 연결 후 표시됩니다.")

    with col_right:
        st.subheader("지도 (데모)")
        m = folium.Map(location=[35.158, 129.062], zoom_start=15)
        for label, name, lat, lng in DEMO_POINTS:
            folium.Marker(
                [lat, lng],
                popup=name,
                icon=folium.DivIcon(
                    html=f'<div style="font-size:14px;font-weight:bold;color:white;'
                    f'background:#2563eb;border-radius:50%;width:28px;height:28px;'
                    f'display:flex;align-items:center;justify-content:center;">{label}</div>'
                ),
            ).add_to(m)
        folium.PolyLine(
            [[lat, lng] for _, _, lat, lng in DEMO_POINTS],
            color="#2563eb",
            weight=4,
        ).add_to(m)
        st_folium(m, width=None, height=400, returned_objects=[])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 처음으로"):
            go_to("start")
            st.rerun()
    with col2:
        if st.button("재계산"):
            go_to("loading")
            st.rerun()
