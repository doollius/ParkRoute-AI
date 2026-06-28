from __future__ import annotations

import streamlit as st

from models.visit_rule import rule_label
from pages.input import render_places_map
from services import place_service, visit_rule_service
from state.session_manager import go_to


def render() -> None:
    st.title("입력 확인")

    region = st.session_state.get("travel_region", "")
    mode = st.session_state.get("optimization_mode", "minimize_walk")
    mode_label = "도보 최소화" if mode == "minimize_walk" else "총 이동시간 최소화"

    start = place_service.get_place_by_id(st.session_state.get("start_place_id"))
    end = place_service.get_place_by_id(st.session_state.get("end_place_id"))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**여행 지역:** {region}")
        st.markdown(f"**최적화 모드:** {mode_label}")
        st.markdown(f"**출발 시각:** {st.session_state.get('trip_start_time', '09:00')}")
        st.markdown(
            f"**출발지:** {_place_summary(start)}"
        )
        st.markdown(
            f"**도착지:** {_place_summary(end)}"
        )
    with col2:
        summary = place_service.progress_summary()
        st.metric("좌표 변환 완료", f"{summary['geocoded_count']} / {summary['place_count']}")

    st.divider()
    st.subheader("방문 장소 목록")

    for i, place in enumerate(st.session_state.places):
        with st.container(border=True):
            st.markdown(f"**{i + 1}. {place.get('type', '-')}**")
            st.write(place.get("normalized_address") or place.get("raw_input"))
            if place.get("lat") is not None:
                st.caption(f"좌표: {place['lat']:.5f}, {place['lng']:.5f}")
            elif place.get("raw_input", "").strip():
                st.error(place.get("geocode_error") or "좌표 변환 실패 — 최적화에서 제외")
            if place.get("reservation_time"):
                st.caption(f"예약: {place['reservation_time']}")

    excluded = place_service.failed_geocode_places()
    geocoded = place_service.geocoded_places()
    if excluded and geocoded:
        st.warning(
            f"좌표 변환 실패 {len(excluded)}곳은 제외하고 "
            f"{len(geocoded)}곳으로 최적화합니다."
        )

    st.divider()
    rules = st.session_state.get("visit_rules", [])
    if rules:
        st.subheader("방문 규칙")
        labels = visit_rule_service.place_labels()
        for rule in rules:
            st.write(f"· {rule_label(rule, labels)}")

    st.divider()
    st.subheader("입력 위치 미리보기")
    render_places_map(
        place_service.geocoded_places(),
        st.session_state.get("start_place_id"),
        st.session_state.get("end_place_id"),
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 수정하기"):
            go_to("input")
            st.rerun()
    with col2:
        if st.button("최적 경로 생성 →", type="primary"):
            st.session_state._route_computed = False
            st.session_state.route = None
            st.session_state.pop("parking_candidates_cache", None)
            st.session_state.pop("tmap_route_cache", None)
            go_to("loading")
            st.rerun()


def _place_summary(place: dict | None) -> str:
    if not place:
        return "(미선택)"
    addr = place.get("normalized_address") or place.get("raw_input") or "-"
    return f"[{place.get('type', '-')}] {addr}"
