from __future__ import annotations

import streamlit as st

from models.visit_rule import rule_label
from services import place_service, visit_rule_service
from state.session_manager import go_to
from utils.ui_helpers import bottom_action_row, bottom_button


def render() -> None:
    st.title("여행 정보 확인")

    excluded = place_service.failed_geocode_places()
    geocoded = place_service.geocoded_places()
    if excluded and geocoded:
        st.warning(
            f"좌표 변환 실패 {len(excluded)}곳은 제외하고 "
            f"{len(geocoded)}곳으로 최적화합니다."
        )

    st.subheader("출발지")
    st.write(place_service.get_review_start_text())

    st.subheader("방문지")
    visit_types = place_service.get_review_visit_types()
    if visit_types:
        for name in visit_types:
            st.write(name)
    else:
        st.write("없음")

    st.subheader("방문 규칙")
    rules = st.session_state.get("visit_rules", [])
    if rules:
        labels = visit_rule_service.place_labels()
        for rule in rules:
            st.write(f"· {rule_label(rule, labels)}")
    else:
        st.write("없음")

    st.subheader("도착지")
    st.write(place_service.get_review_end_text())

    st.subheader("최적화 목표")
    st.write(place_service.get_review_optimization_goal())

    st.divider()
    with bottom_action_row(2) as (left, right):
        if bottom_button(left, "← 수정하기"):
            st.session_state.input_step = "trip"
            go_to("input")
            st.rerun()
        if bottom_button(right, "최적 경로 생성 →", type="primary"):
            st.session_state._route_computed = False
            st.session_state.route = None
            st.session_state.pop("parking_candidates_cache", None)
            st.session_state.pop("parking_coverage_cache", None)
            st.session_state.pop("tmap_route_cache", None)
            go_to("loading")
            st.rerun()
