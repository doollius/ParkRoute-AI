from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

from models.visit_rule import PICK_NONE, RULE_BEFORE, RULE_IMMEDIATE, rule_label
from services import place_service, visit_rule_service
from state.session_manager import go_to, reset_places_step, reset_trip_step
from utils.ui_helpers import bottom_action_row, bottom_button, is_confirm_pending, render_confirm_box, request_confirm

_ADDRESS_HELP_HTML = """
<div style="font-size:0.9rem;line-height:1.6;margin:0.25rem 0 0.75rem 0;">
ℹ️ <strong>주소를 찾고 복사하는 방법</strong><br>
🔗 <a href="https://map.naver.com" target="_blank">네이버 지도</a>
&nbsp;→&nbsp;장소 검색&nbsp;→&nbsp;장소 선택&nbsp;→&nbsp;도로명/지번 주소 옆 '복사' 클릭
&nbsp;&nbsp;|&nbsp;&nbsp;
🔗 <a href="https://www.google.com/maps" target="_blank">구글 지도</a>
&nbsp;→&nbsp;장소 검색&nbsp;→&nbsp;장소 선택&nbsp;→&nbsp;표시된 주소 복사
</div>
"""


def render() -> None:
    if st.session_state.pop("_do_reset_trip", False):
        reset_trip_step()
    if st.session_state.pop("_do_reset_places", False):
        reset_places_step()

    place_service.ensure_default_places()
    place_service.ensure_widget_keys()
    place_service.sync_places_from_widgets()

    step = st.session_state.get("input_step", "places")
    if step == "places_confirm":
        _render_places_confirm_step()
    elif step == "trip":
        place_service.geocode_custom_endpoints()
        _render_trip_step()
    else:
        _render_places_step()


def _render_places_step() -> None:
    st.title("방문 장소")
    st.caption("1/3 · 지도에 등록된 장소명 또는 도로명 주소·지번 주소를 입력해주세요.")

    st.markdown(_ADDRESS_HELP_HTML, unsafe_allow_html=True)

    _render_places_section()
    st.divider()
    _render_places_progress()
    _render_places_actions()


def _render_places_confirm_step() -> None:
    st.title("방문 장소 확인")
    st.caption("2/3 · 입력한 장소를 TMAP에서 검색했습니다. 결과를 확인해 주세요.")

    if st.session_state.pop("_batch_resolving", False):
        total = len(st.session_state.places)
        with st.status("입력한 장소를 확인하고 있습니다…", expanded=True) as status:
            progress = st.progress(0.0, text="검색 준비 중…")
            for i in range(total):
                progress.progress(i / max(total, 1), text=f"검색 중… ({i + 1}/{total})")
                place_service.batch_resolve_place_at(i)
            progress.progress(1.0, text="검색 완료")
            status.update(label="장소 검색 완료", state="complete", expanded=False)

    for i, place in enumerate(st.session_state.places):
        pid = place["id"]
        input_label = place.get("type", "").strip()
        if place.get("use_manual_address"):
            input_label = f"{input_label} · {place.get('raw_input', '').strip()}"

        with st.container(border=True):
            st.markdown(f"**장소 {i + 1}** · 입력: `{input_label or '(비어 있음)'}`")

            status = place.get("geocode_status")
            if status == "confirmed" and place.get("lat") is not None:
                matched = place.get("matched_name") or place.get("type", "")
                addr = place.get("normalized_address") or ""
                st.success(f"✔ {matched}")
                if addr and addr != matched:
                    st.caption(addr)
            elif status == "needs_pick":
                st.warning("검색 결과가 여러 개입니다. 올바른 장소를 선택하세요.")
                candidates = place.get("poi_candidates") or []
                options = list(range(len(candidates)))
                labels = [
                    f"{c['name']} — {c['normalized_address']}" for c in candidates
                ]
                picked = st.radio(
                    "후보 선택",
                    options,
                    format_func=lambda idx: labels[idx],
                    key=f"pick_{pid}",
                    label_visibility="collapsed",
                )
                if st.button("이 장소로 확정", key=f"pick_btn_{pid}"):
                    place_service.select_poi_candidate(pid, picked)
                    st.rerun()
            else:
                st.error(place.get("geocode_error") or "검색에 실패했습니다.")
                st.caption("← 이전으로 돌아가 입력을 수정하세요.")

    st.divider()
    _render_places_confirm_actions()


def _render_trip_step() -> None:
    st.title("추가 정보 입력")
    st.caption("3/3 · 경로 계산에 반영할 조건을 입력해주세요.")

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
    st.caption(
        "기본: 지도에서 검색되는 **공식 장소명·상호명**을 입력합니다. "
        "개인 주택 등은 **직접 주소 입력**을 사용하세요."
    )

    header_col, add_col = st.columns([4, 1])
    with add_col:
        if st.button("+ 장소 추가", use_container_width=True):
            place_service.add_place()
            st.rerun()

    for i, place in enumerate(st.session_state.places):
        pid = place["id"]
        manual = bool(st.session_state.get(f"manual_{pid}", False))

        with st.container(border=True):
            row1, del_col = st.columns([5, 1])
            with row1:
                st.markdown(f"**장소 {i + 1}**")
            with del_col:
                if st.button("삭제", key=f"del_{pid}", disabled=len(st.session_state.places) <= 2):
                    place_service.delete_place(pid)
                    st.rerun()

            st.text_input(
                "장소명 *",
                key=f"type_{pid}",
                placeholder="예: 경복궁, 현충원, SK아카데미, 부산역",
            )
            if manual:
                st.caption("방문 순서 등에서 보여질 이름입니다. (예: 외할머니댁)")
            else:
                st.caption("지도에서 검색되는 공식 장소명·상호명을 입력하세요.")

            st.checkbox("직접 주소 입력", key=f"manual_{pid}")

            if manual:
                st.text_input(
                    "주소 (도로명/지번) *",
                    key=f"raw_{pid}",
                    placeholder="예: 부산광역시 해운대구 해운대해변로 264",
                )


def _reset_rule_pick_widgets() -> None:
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
    st.metric("입력 장소", f"{summary['place_count']}곳")

    errors = place_service.places_step_errors()
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
    if is_confirm_pending("confirm_reset_places"):
        action = render_confirm_box(
            "confirm_reset_places",
            "이 페이지에서 입력한 **방문 장소**를 모두 지웁니다. 계속하시겠습니까?",
            confirm_label="초기화",
            cancel_label="취소",
        )
        if action == "confirm":
            st.session_state._do_reset_places = True
            st.rerun()
        if action == "pending":
            return

    with bottom_action_row(2) as (left, right):
        if bottom_button(left, "← 이전"):
            go_to("start")
            st.rerun()
        if bottom_button(
            right,
            "다음 →",
            type="primary",
            disabled=not place_service.can_proceed_to_places_confirm(),
        ):
            st.session_state.input_step = "places_confirm"
            st.session_state._batch_resolving = True
            st.rerun()

    st.divider()
    with bottom_action_row(2) as (left, _):
        if bottom_button(left, "초기화"):
            request_confirm("confirm_reset_places")
            st.rerun()


def _render_places_confirm_actions() -> None:
    errors = place_service.places_confirm_errors()
    if errors:
        with st.expander("확인 필요", expanded=True):
            for err in errors:
                st.warning(err)

    with bottom_action_row(2) as (left, right):
        if bottom_button(left, "← 이전"):
            st.session_state.input_step = "places"
            st.rerun()
        if bottom_button(
            right,
            "다음 →",
            type="primary",
            disabled=not place_service.can_proceed_to_trip_step(),
        ):
            st.session_state.input_step = "trip"
            st.rerun()


def _render_trip_actions() -> None:
    if is_confirm_pending("confirm_reset_trip"):
        action = render_confirm_box(
            "confirm_reset_trip",
            "이 페이지에서 입력한 **추가 정보**(최적화·방문 규칙·출발·도착)를 초기화합니다. 계속하시겠습니까?",
            confirm_label="초기화",
            cancel_label="취소",
        )
        if action == "confirm":
            st.session_state._do_reset_trip = True
            st.rerun()
        if action == "pending":
            return

    partial = place_service.uses_partial_geocoding() and place_service.can_complete()
    complete_label = "입력 완료 (일부 제외) →" if partial and place_service.validation_errors() else "입력 완료 →"

    with bottom_action_row(2) as (left, right):
        if bottom_button(left, "← 이전"):
            st.session_state.input_step = "places_confirm"
            st.rerun()
        if bottom_button(right, complete_label, type="primary", disabled=not place_service.can_complete()):
            go_to("review")
            st.rerun()

    st.divider()
    with bottom_action_row(2) as (left, _):
        if bottom_button(left, "초기화"):
            request_confirm("confirm_reset_trip")
            st.rerun()


def render_places_map(places: list, start_id: str | None, end_id: str | None) -> None:
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
