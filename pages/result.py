from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from optimizer.scoring import format_duration
from state.session_manager import go_to


def render() -> None:
    st.title("최적 경로 결과")

    route = st.session_state.get("route") or {}
    if not route.get("stops"):
        st.warning("경로 데이터가 없습니다. 입력부터 다시 진행해 주세요.")
        if st.button("← 입력 화면"):
            go_to("input")
            st.rerun()
        return

    summary = route.get("summary", {})
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("방문 순서")
        for stop in route.get("stops", []):
            extra = ""
            if stop.get("reservation_time"):
                extra = f" · 예약 {stop['reservation_time']}"
            arrival = stop.get("arrival_time")
            if arrival:
                extra += f" · 예상 도착 {arrival}"
            st.write(f"**{stop['label']}** — [{stop.get('type', '-')}] {stop.get('name', '')}{extra}")

        st.divider()
        st.subheader("이동 요약")
        st.metric("총 이동", format_duration(summary.get("total_time_sec", 0)))
        c1, c2 = st.columns(2)
        c1.metric("차량", format_duration(summary.get("car_time_sec", 0)))
        c2.metric("도보", format_duration(summary.get("walk_time_sec", 0)))
        st.caption(f"출발 시각: {route.get('trip_start_time', '09:00')}")
        if route.get("visit_rules_applied"):
            st.caption(f"적용된 방문 규칙: {route['visit_rules_applied']}건")
        st.metric("주차장", f"{summary.get('parking_count', 0)}곳")
        if summary.get("total_distance_m"):
            st.caption(f"총 거리 약 {summary['total_distance_m'] // 1000}km")

        if route.get("parkings"):
            st.divider()
            st.subheader("추천 주차장")
            for p in route["parkings"]:
                dist = f" · {p['distance_m']}m" if p.get("distance_m") else ""
                st.write(f"**{p['label']}** {p['name']}{dist}")
                if p.get("address"):
                    st.caption(p["address"])

        if route.get("explanation"):
            st.divider()
            st.subheader("AI 추천 이유")
            st.info(route["explanation"])

    with col_right:
        st.subheader("경로 지도")
        _render_route_map(route)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 처음으로"):
            go_to("start")
            st.rerun()
    with col2:
        if st.button("재계산"):
            st.session_state._route_computed = False
            go_to("loading")
            st.rerun()


def _render_route_map(route: dict) -> None:
    stops = route.get("stops", [])
    if not stops:
        st.info("표시할 경로가 없습니다.")
        return

    center_lat = sum(s["lat"] for s in stops) / len(stops)
    center_lng = sum(s["lng"] for s in stops) / len(stops)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

    label_colors = {"S": "#16a34a", "E": "#dc2626"}
    for stop in stops:
        label = stop["label"]
        color = label_colors.get(label, "#2563eb")
        folium.Marker(
            [stop["lat"], stop["lng"]],
            popup=stop.get("name"),
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:13px;font-weight:bold;color:white;'
                    f"background:{color};border-radius:50%;width:28px;height:28px;"
                    f'display:flex;align-items:center;justify-content:center;">{label}</div>'
                )
            ),
        ).add_to(m)

    for p in route.get("parkings", []):
        folium.Marker(
            [p["lat"], p["lng"]],
            popup=p.get("name"),
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:12px;font-weight:bold;color:white;'
                    f'background:#9333ea;border-radius:4px;padding:2px 6px;">{p["label"]}</div>'
                )
            ),
        ).add_to(m)

    path = [[s["lat"], s["lng"]] for s in stops]
    if len(path) >= 2:
        folium.PolyLine(path, color="#2563eb", weight=4, opacity=0.85).add_to(m)

    st_folium(m, width=None, height=450, returned_objects=[])
