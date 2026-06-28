from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from models.visit_rule import PICK_NONE, RULE_BEFORE, RULE_IMMEDIATE, rule_label
from services import place_service, visit_rule_service
from state.session_manager import go_to, reset_all
from utils.ui_helpers import bottom_action_row, is_confirm_pending, render_confirm_box, request_confirm


def render() -> None:
    place_service.ensure_default_places()
    place_service.ensure_widget_keys()
    place_service.sync_places_from_widgets()
    place_service.geocode_pending_places()

    step = st.session_state.get("input_step", "places")
    if step == "trip":
        place_service.geocode_custom_endpoints()
        _render_trip_step()
    else:
        _render_places_step()


def _render_places_step() -> None:
    st.title("방문 장소")
    st.caption("1/2 · 도로명주소 또는 지번주소만 입력합니다. (네이버 공유 URL 미지원)")

    _render_places_section()
    st.divider()
    _render_places_progress()
    _render_places_actions()


def _render_trip_step() -> None:
    st.title("추가 정보 입력")
    st.caption("2/2 · 경로 계산에 반영할 조건을 입력해주세요.")

    _render_travel_section()
    st.divider()
    _render_visit_rules_section()
    st.divider()
    _render_route_section()
    st.divider()
    _render_trip_progress()
    _render_trip_actions()


def _render_travel_section() -> None:
    st.subheader("최적화 모드")
    st.selectbox(
        "최적화 모드",
        options=["minimize_walk", "minimize_time"],
        format_func=lambda x: "도보 최소화" if x == "minimize_walk" else "총 이동시간 최소화",
        key="optimization_mode",
        label_visibility="collapsed",
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

            row1, order_col, del_col = st.columns([4, 1, 1])
            with row1:
                st.markdown(f"**장소 {i + 1}**")
            with order_col:
                up_col, down_col = st.columns(2)
                with up_col:
                    if st.button("↑", key=f"up_{pid}", disabled=i == 0):
                        place_service.move_place(pid, -1)
                        st.rerun()
                with down_col:
                    if st.button("↓", key=f"down_{pid}", disabled=i == len(st.session_state.places) - 1):
                        place_service.move_place(pid, 1)
                        st.rerun()
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
                st.text_input(
                    "유형 *",
                    key=f"type_{pid}",
                    placeholder="예: 경복궁, 현충원, SK아카데미",
                )
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
                if place.get("_geocode_note"):
                    st.caption(place["_geocode_note"])
                if place.get("_manual_coords"):
                    st.caption("수동 입력 좌표")
            elif error:
                st.error(error)
                _render_manual_coords(pid)
            elif place.get("raw_input", "").strip():
                if st.button("좌표 확인", key=f"geo_{pid}"):
                    place["_force_geocode"] = True
                    st.rerun()
                else:
                    st.info("주소 입력 후 자동 확인되거나, '좌표 확인'을 누르세요.")


def _render_manual_coords(pid: str) -> None:
    with st.expander("수동 좌표 입력 (ER-004)", expanded=False):
        st.caption("Geocoding 실패 시 위·경도를 직접 입력하세요. (예: 35.158, 129.060)")
        c1, c2 = st.columns(2)
        lat = c1.number_input("위도 (lat)", key=f"mlat_{pid}", format="%.6f", value=0.0)
        lng = c2.number_input("경도 (lng)", key=f"mlng_{pid}", format="%.6f", value=0.0)
        if st.button("좌표 적용", key=f"mapply_{pid}"):
            if lat == 0.0 and lng == 0.0:
                st.error("유효한 좌표를 입력하세요.")
            else:
                err = place_service.set_manual_coords(pid, lat, lng)
                if err:
                    st.error(err)
                else:
                    st.rerun()


def _reset_rule_pick_widgets() -> None:
    """Selectbox key 값은 위젯 렌더링 전에만 변경 가능."""
    st.session_state.rule_from_pick = PICK_NONE
    st.session_state.rule_to_pick = PICK_NONE
    st.session_state.rule_type_pick = PICK_NONE


def _render_visit_rules_section() -> None:
    st.subheader("방문 규칙 (선택)")
    st.caption("식사 후 카페처럼 **반드시 지켜야 하는 순서**를 지정합니다.")

    if st.session_state.pop("_reset_rule_picks", False):
        _reset_rule_pick_widgets()

    visit_rule_service.ensure_rule_widget_keys()
    options = place_service.place_options()
    if len(options) < 2:
        st.info("장소 2개 이상 입력 후 규칙을 추가할 수 있습니다.")
        return

    visit_ids = [o[0] for o in options]
    labels = visit_rule_service.place_labels()
    from_options = [PICK_NONE] + visit_ids
    to_options = [PICK_NONE] + visit_ids
    rule_options = [PICK_NONE, RULE_IMMEDIATE, RULE_BEFORE]

    def _place_fmt(place_id: str) -> str:
        if place_id == PICK_NONE:
            return "(없음)"
        return labels[place_id]

    def _rule_fmt(rule_type: str) -> str:
        if rule_type == PICK_NONE:
            return "(없음)"
        return "바로 다음" if rule_type == RULE_IMMEDIATE else "다음 (순서만)"

    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        from_id = st.selectbox(
            "선행 장소",
            from_options,
            format_func=_place_fmt,
            key="rule_from_pick",
        )
    with col2:
        to_id = st.selectbox(
            "후행 장소",
            to_options,
            format_func=_place_fmt,
            key="rule_to_pick",
        )
    with col3:
        rule_type = st.selectbox(
            "규칙",
            rule_options,
            format_func=_rule_fmt,
            key="rule_type_pick",
        )
    with col4:
        st.write("")
        st.write("")
        if st.button("+ 규칙 추가", use_container_width=True):
            err = visit_rule_service.validate_rule_form(from_id, to_id, rule_type)
            if err:
                st.warning(err)
            elif visit_rule_service.add_rule(from_id, to_id, rule_type):
                st.session_state._reset_rule_picks = True
                st.rerun()

    rules = st.session_state.get("visit_rules", [])
    if rules:
        for rule in rules:
            c1, c2 = st.columns([5, 1])
            with c1:
                st.write(f"· {rule_label(rule, labels)}")
            with c2:
                if st.button("삭제", key=f"rule_del_{rule['id']}"):
                    visit_rule_service.delete_rule(rule["id"])
                    st.rerun()
    else:
        st.caption("등록된 방문 규칙이 없습니다.")


def _route_option_ids() -> tuple[list[str], dict[str, str]]:
    options = place_service.place_options()
    visit_ids = [o[0] for o in options]
    visit_labels = {o[0]: o[1] for o in options}
    all_ids = [PICK_NONE] + visit_ids
    labels = {PICK_NONE: "(없음)", **visit_labels}
    return all_ids, labels


def _show_custom_geocode_status(kind: str) -> None:
    node_key = f"custom_{kind}_node"
    err_key = f"custom_{kind}_geocode_error"
    node = st.session_state.get(node_key) or {}
    err = st.session_state.get(err_key)
    if node.get("lat") is not None:
        st.success(
            f"좌표 확인 · {node.get('normalized_address') or node.get('raw_input')} "
            f"({node['lat']:.5f}, {node['lng']:.5f})"
        )
    elif err:
        st.error(err)
    elif str(st.session_state.get(f"custom_{kind}_address", "")).strip():
        st.info("주소 입력 후 자동으로 좌표를 확인합니다.")


def _render_route_section() -> None:
    st.subheader("출발 · 도착")
    st.caption(
        "출발지·도착지 **중 하나만** 지정해도 됩니다. "
        "(없음)이면 해당 방향은 자동으로 최적 선택됩니다."
    )
    all_ids, labels = _route_option_ids()
    if len(all_ids) <= 1:
        st.warning("장소를 먼저 입력하세요.")
        return

    def _fmt(place_id: str) -> str:
        return labels.get(place_id, place_id)

    current_start = st.session_state.get("start_place_id") or PICK_NONE
    if current_start not in all_ids:
        current_start = PICK_NONE
    current_end = st.session_state.get("end_place_id") or PICK_NONE
    if current_end not in all_ids:
        current_end = PICK_NONE

    col1, col2 = st.columns(2)
    with col1:
        if not st.session_state.get("use_custom_start"):
            picked_start = st.selectbox(
                "출발지 (선택)",
                all_ids,
                index=all_ids.index(current_start),
                format_func=_fmt,
            )
            st.session_state.start_place_id = None if picked_start == PICK_NONE else picked_start
        else:
            st.session_state.start_place_id = None
            st.selectbox(
                "출발지 (선택)",
                all_ids,
                index=0,
                format_func=_fmt,
                disabled=True,
            )

        st.checkbox("다른 장소에서 출발", key="use_custom_start")
        if st.session_state.get("use_custom_start"):
            st.text_input(
                "출발 주소",
                key="custom_start_address",
                placeholder="주소를 입력해주세요.",
                label_visibility="collapsed",
            )
            _show_custom_geocode_status("start")

    with col2:
        if not st.session_state.get("use_custom_end"):
            picked_end = st.selectbox(
                "도착지 (선택)",
                all_ids,
                index=all_ids.index(current_end),
                format_func=_fmt,
            )
            st.session_state.end_place_id = None if picked_end == PICK_NONE else picked_end
        else:
            st.session_state.end_place_id = None
            st.selectbox(
                "도착지 (선택)",
                all_ids,
                index=0,
                format_func=_fmt,
                disabled=True,
            )

        st.checkbox("다른 장소에 도착", key="use_custom_end")
        if st.session_state.get("use_custom_end"):
            st.text_input(
                "도착 주소",
                key="custom_end_address",
                placeholder="주소를 입력해주세요.",
                label_visibility="collapsed",
            )
            _show_custom_geocode_status("end")


def _render_places_progress() -> None:
    summary = place_service.progress_summary()
    failed_count = len(place_service.failed_geocode_places())
    c1, c2 = st.columns(2)
    geocode_label = f"{summary['geocoded_count']}/{summary['place_count']}"
    if failed_count:
        geocode_label += f" ({failed_count} 실패)"
    c1.metric("장소", geocode_label)
    c2.metric("예약", f"{summary['reservation_count']}건")

    errors = place_service.places_step_errors()
    if place_service.uses_partial_geocoding() and place_service.can_proceed_to_trip_step():
        st.info(
            f"좌표 변환 실패 {len(place_service.failed_geocode_places())}곳은 "
            "다음 단계에서 제외하고 진행할 수 있습니다. (ER-005)"
        )
    if errors:
        with st.expander("입력 확인 필요", expanded=True):
            for err in errors:
                st.warning(err)


def _render_trip_progress() -> None:
    summary = place_service.progress_summary()
    failed_count = len(place_service.failed_geocode_places())
    mode = st.session_state.get("optimization_mode", "minimize_walk")
    mode_label = "도보 최소화" if mode == "minimize_walk" else "총 이동시간 최소화"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("최적화 모드", mode_label)
    geocode_label = f"{summary['geocoded_count']}/{summary['place_count']}"
    if failed_count:
        geocode_label += f" ({failed_count} 제외)"
    c2.metric("장소", geocode_label)
    c3.metric("방문 규칙", f"{len(st.session_state.get('visit_rules', []))}건")
    c4.metric("출발·도착", place_service.route_endpoint_status())

    errors = place_service.validation_errors()
    if place_service.uses_partial_geocoding() and not place_service.partial_validation_errors():
        st.info(
            f"좌표 변환 실패 {len(place_service.failed_geocode_places())}곳은 "
            "제외하고 진행할 수 있습니다. (ER-005)"
        )
        errors = place_service.partial_validation_errors()
    if errors:
        with st.expander("입력 확인 필요", expanded=True):
            for err in errors:
                st.warning(err)


def _render_places_actions() -> None:
    if is_confirm_pending("confirm_reset"):
        action = render_confirm_box(
            "confirm_reset",
            "모든 입력을 삭제합니다. 계속하시겠습니까?",
            confirm_label="삭제",
            cancel_label="취소",
        )
        if action == "confirm":
            reset_all()
            st.rerun()
        if action == "pending":
            return

    with bottom_action_row(3) as (left, center, right):
        if left.button("← 시작 화면"):
            go_to("start")
            st.rerun()
        if center.button("초기화"):
            request_confirm("confirm_reset")
            st.rerun()
        if right.button(
            "다음 →",
            type="primary",
            disabled=not place_service.can_proceed_to_trip_step(),
        ):
            st.session_state.input_step = "trip"
            st.rerun()


def _render_trip_actions() -> None:
    if is_confirm_pending("confirm_reset"):
        action = render_confirm_box(
            "confirm_reset",
            "모든 입력을 삭제합니다. 계속하시겠습니까?",
            confirm_label="삭제",
            cancel_label="취소",
        )
        if action == "confirm":
            reset_all()
            st.rerun()
        if action == "pending":
            return

    partial = place_service.uses_partial_geocoding() and place_service.can_complete()
    complete_label = "입력 완료 (일부 제외) →" if partial and place_service.validation_errors() else "입력 완료 →"

    with bottom_action_row(3) as (left, center, right):
        if left.button("← 시작 화면"):
            go_to("start")
            st.rerun()
        if center.button("초기화"):
            request_confirm("confirm_reset")
            st.rerun()
        if right.button(complete_label, type="primary", disabled=not place_service.can_complete()):
            go_to("review")
            st.rerun()

    st.divider()
    if st.button("← 이전", use_container_width=True):
        st.session_state.input_step = "places"
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
