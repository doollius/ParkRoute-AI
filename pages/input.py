from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from models.place import PLACE_TYPES
from services import place_service
from state.session_manager import go_to, reset_all


def render() -> None:
    place_service.ensure_default_places()
    place_service.ensure_widget_keys()
    place_service.sync_places_from_widgets()
    place_service.geocode_pending_places()

    st.title("여행 정보 입력")
    st.caption("도로명주소 또는 지번주소만 입력합니다. (네이버 공유 URL 미지원)")

    _render_travel_section()
    st.divider()
    _render_places_section()
    st.divider()
    _render_route_section()
    st.divider()
    _render_progress()
    _render_actions()


def _render_travel_section() -> None:
    st.subheader("여행 정보")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("여행 지역 *", key="travel_region", placeholder="예: 부산")
    with col2:
        st.selectbox(
            "최적화 모드",
            options=["minimize_walk", "minimize_time"],
            format_func=lambda x: "도보 최소화" if x == "minimize_walk" else "총 이동시간 최소화",
            key="optimization_mode",
        )


def _render_places_section() -> None:
    st.subheader("방문 장소")
    header_col, add_col = st.columns([4, 1])
    with add_col:
        if st.button("+ 장소 추가", use_container_width=True):
            place_service.add_place()
            st.rerun()

    for i, place in enumerate(st.session_state.places):
        pid = place["id"]
        has_coords = place.get("lat") is not None and place.get("lng") is not None
        error = place.get("geocode_error")
        border = "border: 2px solid #ef4444;" if error else ""

        with st.container(border=True):
            if border:
                st.markdown(f'<div style="{border}"></div>', unsafe_allow_html=True)

            row1, del_col = st.columns([5, 1])
            with row1:
                st.markdown(f"**장소 {i + 1}**")
            with del_col:
                if st.button("삭제", key=f"del_{pid}", disabled=len(st.session_state.places) <= 2):
                    place_service.delete_place(pid)
                    st.rerun()

            st.text_input(
                "주소 (도로명/지번) *",
                key=f"raw_{pid}",
                placeholder="예: 부산광역시 해운대구 해운대해변로 264",
            )

            c1, c2 = st.columns(2)
            with c1:
                st.selectbox("유형", PLACE_TYPES, key=f"type_{pid}")
            with c2:
                st.text_input(
                    "예약 시간 (선택)",
                    key=f"res_{pid}",
                    placeholder="HH:MM 예: 14:00",
                )

            if has_coords:
                st.success(
                    f"좌표 확인 · {place.get('normalized_address') or place.get('raw_input')} "
                    f"({place['lat']:.5f}, {place['lng']:.5f})"
                )
            elif error:
                st.error(error)
            elif place.get("raw_input", "").strip():
                if st.button("좌표 확인", key=f"geo_{pid}"):
                    place["_force_geocode"] = True
                    st.rerun()
                else:
                    st.info("주소 입력 후 자동 확인되거나, '좌표 확인'을 누르세요.")


def _render_route_section() -> None:
    st.subheader("출발 · 도착")
    options = place_service.place_options()
    if not options:
        st.warning("장소를 먼저 입력하세요.")
        return

    ids = [opt[0] for opt in options]
    labels = {opt[0]: opt[1] for opt in options}

    start_index = ids.index(st.session_state.start_place_id) if st.session_state.get("start_place_id") in ids else 0
    end_index = ids.index(st.session_state.end_place_id) if st.session_state.get("end_place_id") in ids else min(1, len(ids) - 1)

    col1, col2 = st.columns(2)
    with col1:
        st.session_state.start_place_id = st.selectbox(
            "출발지 *",
            options=ids,
            index=start_index,
            format_func=lambda x: labels[x],
        )
    with col2:
        st.session_state.end_place_id = st.selectbox(
            "도착지 *",
            options=ids,
            index=end_index,
            format_func=lambda x: labels[x],
        )


def _render_progress() -> None:
    summary = place_service.progress_summary()
    region_ok = bool(str(st.session_state.get("travel_region", "")).strip())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("여행 지역", "완료" if region_ok else "미입력")
    c2.metric("장소", f"{summary['geocoded_count']}/{summary['place_count']} 좌표확인")
    c3.metric("예약", f"{summary['reservation_count']}건")
    c4.metric("출발·도착", "설정됨" if st.session_state.get("start_place_id") and st.session_state.get("end_place_id") else "미설정")

    errors = place_service.validation_errors()
    if errors:
        with st.expander("입력 확인 필요", expanded=True):
            for err in errors:
                st.warning(err)


def _render_actions() -> None:
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
        complete = st.button("입력 완료 →", type="primary", disabled=not place_service.can_complete())
        if complete:
            go_to("review")
            st.rerun()


def render_places_map(places: list, start_id: str | None, end_id: str | None) -> None:
    """Review 화면용 — Geocoding된 장소 지도."""
    points = [p for p in places if p.get("lat") is not None and p.get("lng") is not None]
    if not points:
        st.info("지도에 표시할 좌표가 없습니다.")
        return

    center_lat = sum(p["lat"] for p in points) / len(points)
    center_lng = sum(p["lng"] for p in points) / len(points)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

    for i, place in enumerate(places):
        if place.get("lat") is None:
            continue
        pid = place["id"]
        if pid == start_id:
            label = "S"
            color = "#16a34a"
        elif pid == end_id:
            label = "E"
            color = "#dc2626"
        else:
            label = str(i + 1)
            color = "#2563eb"

        folium.Marker(
            [place["lat"], place["lng"]],
            popup=place.get("normalized_address") or place.get("raw_input"),
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:13px;font-weight:bold;color:white;'
                    f"background:{color};border-radius:50%;width:26px;height:26px;"
                    f'display:flex;align-items:center;justify-content:center;">{label}</div>'
                )
            ),
        ).add_to(m)

    st_folium(m, width=None, height=380, returned_objects=[])
