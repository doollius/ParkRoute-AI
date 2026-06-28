from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from models.route import RouteResult
from optimizer.scoring import format_duration
from state.session_manager import go_to
from utils.parking_cost import format_won
from utils.ui_helpers import is_confirm_pending, render_confirm_box, request_confirm


def render() -> None:
    st.title("최적 경로 결과")

    route = st.session_state.get("route") or {}
    if not route.get("stops"):
        st.warning("경로 데이터가 없습니다. 입력부터 다시 진행해 주세요.")
        if st.button("← 입력 화면"):
            st.session_state.input_step = "places"
            go_to("input")
            st.rerun()
        return

    if route.get("warnings"):
        for warning in route["warnings"]:
            st.warning(warning)

    excluded = route.get("excluded_places") or []
    if excluded:
        with st.expander(f"제외된 장소 ({len(excluded)}곳)", expanded=False):
            for place in excluded:
                st.write(f"· {place.get('raw_input', '-')} — {place.get('geocode_error') or '좌표 없음'}")

    if route.get("message") and route["message"] != "최적 경로가 생성되었습니다.":
        st.info(route["message"])

    parsed = RouteResult.from_dict(route)
    summary = parsed.summary
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("방문 순서")
        for stop in parsed.stops:
            extra = ""
            if stop.reservation_time:
                extra = f" · 예약 {stop.reservation_time}"
            if stop.arrival_time:
                extra += f" · 예상 도착 {stop.arrival_time}"
            st.write(f"**{stop.label}** — [{stop.type or '-'}] {stop.name}{extra}")

        st.divider()
        st.subheader("구간별 이동 (TMAP)")
        for seg in parsed.segments:
            mode_label = "🚗 차량" if seg.mode == "car" else "🚶 도보"
            dist = f" · {seg.distance_m // 1000}km" if seg.distance_m >= 1000 else (
                f" · {seg.distance_m}m" if seg.distance_m else ""
            )
            st.caption(
                f"{seg.from_label} → {seg.to_label}: "
                f"{mode_label} {format_duration(seg.time_sec)}{dist}"
            )

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
        parking_cost = summary.get("parking_cost_won")
        if parking_cost:
            st.metric("예상 주차비", format_won(parking_cost))
        if summary.get("total_distance_m"):
            st.caption(f"총 거리 약 {summary['total_distance_m'] // 1000}km")

        if route.get("parkings"):
            st.divider()
            st.subheader("추천 주차장")
            for p in route["parkings"]:
                fee = p.get("estimated_cost")
                if fee is not None:
                    fee_text = f" · 예상 {format_won(fee)}"
                elif p.get("base_fee"):
                    fee_text = f" · 기본요금 {p['base_fee']}"
                else:
                    fee_text = ""
                stay = p.get("stay_minutes")
                stay_text = f" · 체류 약 {stay}분" if stay else ""
                st.write(f"**{p['label']}** {p['name']}{fee_text}{stay_text}")
                if p.get("address"):
                    st.caption(p["address"])
            if parking_cost:
                st.caption(
                    f"총 예상 주차비 {format_won(parking_cost)} — "
                    "실제 요금은 현장·운영 정책에 따라 달라질 수 있습니다."
                )

        if parsed.explanation:
            st.divider()
            st.subheader("AI 추천 이유")
            st.info(parsed.explanation)

    with col_right:
        st.subheader("경로 지도")
        _render_route_map(route)

    if is_confirm_pending("confirm_home"):
        action = render_confirm_box(
            "confirm_home",
            "입력 화면으로 돌아갑니다. **입력 내용은 유지됩니다.**",
            confirm_label="확인",
            cancel_label="취소",
        )
        if action == "confirm":
            st.session_state._route_computed = False
            st.session_state.input_step = "trip"
            go_to("input")
            st.rerun()

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("← 입력 수정"):
            st.session_state._route_computed = False
            st.session_state.input_step = "trip"
            go_to("input")
            st.rerun()
    with col2:
        if st.button("← 처음으로"):
            request_confirm("confirm_home")
            st.rerun()
    with col3:
        if st.button("재계산"):
            st.session_state._route_computed = False
            st.session_state.pop("parking_candidates_cache", None)
            st.session_state.pop("tmap_route_cache", None)
            go_to("loading")
            st.rerun()


def _render_route_map(route: dict) -> None:
    stops = route.get("stops", [])
    segments = route.get("segments", [])
    if not stops:
        st.info("표시할 경로가 없습니다.")
        return

    stop_by_id = {s["id"]: s for s in stops}
    center_lat = sum(s["lat"] for s in stops) / len(stops)
    center_lng = sum(s["lng"] for s in stops) / len(stops)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

    label_colors = {"S": "#16a34a", "E": "#dc2626"}
    for stop in stops:
        label = stop["label"]
        if stop.get("kind") == "parking" or str(label).startswith("P"):
            color = "#9333ea"
            shape = "border-radius:4px;padding:2px 6px;width:auto;height:auto;"
        else:
            color = label_colors.get(label, "#2563eb")
            shape = "border-radius:50%;width:28px;height:28px;"
        folium.Marker(
            [stop["lat"], stop["lng"]],
            popup=stop.get("name"),
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:13px;font-weight:bold;color:white;'
                    f"background:{color};{shape}"
                    f'display:flex;align-items:center;justify-content:center;">{label}</div>'
                )
            ),
        ).add_to(m)

    for seg in segments:
        from_stop = stop_by_id.get(seg.get("from_id"))
        to_stop = stop_by_id.get(seg.get("to_id"))
        if not from_stop or not to_stop:
            continue
        mode = seg.get("mode", "car")
        color = "#2563eb" if mode == "car" else "#16a34a"
        dash = "8, 8" if mode == "walk" else None
        folium.PolyLine(
            [[from_stop["lat"], from_stop["lng"]], [to_stop["lat"], to_stop["lng"]]],
            color=color,
            weight=4 if mode == "car" else 3,
            opacity=0.85,
            dash_array=dash,
        ).add_to(m)

    st.caption("파란 실선: 차량 · 초록 점선: 도보")
    st_folium(m, width=None, height=450, returned_objects=[])
