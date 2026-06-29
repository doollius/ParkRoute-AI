from __future__ import annotations

import streamlit as st

from models.place import create_place
from models.visit_rule import PICK_NONE


def _clear_place_widget_keys(place_ids: list[str]) -> None:
    for pid in place_ids:
        for prefix in ("raw_", "type_", "manual_", "mlat_", "mlng_", "pick_"):
            st.session_state.pop(f"{prefix}{pid}", None)


def _clear_trip_step_fields() -> None:
    st.session_state.visit_rules = []
    st.session_state.start_place_id = None
    st.session_state.end_place_id = None
    st.session_state.use_custom_start = False
    st.session_state.custom_start_address = ""
    st.session_state.use_custom_end = False
    st.session_state.custom_end_address = ""
    for key in (
        "custom_start_node",
        "custom_end_node",
        "custom_start_geocode_error",
        "custom_end_geocode_error",
    ):
        st.session_state.pop(key, None)
    st.session_state.rule_from_pick = PICK_NONE
    st.session_state.rule_to_pick = PICK_NONE
    st.session_state.rule_type_pick = PICK_NONE


def reset_places_step() -> None:
    """방문 장소(1/2) 페이지 입력만 초기화."""
    old_ids = [p["id"] for p in st.session_state.get("places", [])]
    _clear_place_widget_keys(old_ids)

    st.session_state.places = [create_place(), create_place()]
    for place in st.session_state.places:
        pid = place["id"]
        st.session_state[f"raw_{pid}"] = ""
        st.session_state[f"type_{pid}"] = ""
        st.session_state[f"manual_{pid}"] = False

    # 장소 ID가 바뀌므로 추가 정보(2/2)의 장소 연동 항목도 함께 초기화
    _clear_trip_step_fields()


def reset_trip_step() -> None:
    """추가 정보 입력(2/2) 페이지 입력만 초기화."""
    st.session_state.optimization_mode = "minimize_walk"
    st.session_state.congestion_level = "normal"
    _clear_trip_step_fields()
    st.session_state._reset_rule_picks = True


def init_session() -> None:
    defaults = {
        "page": "start",
        "input_step": "places",
        "travel_region": "",
        "start_place_id": None,
        "end_place_id": None,
        "optimization_mode": "minimize_walk",
        "places": [],
        "visit_rules": [],
        "use_custom_start": False,
        "custom_start_address": "",
        "use_custom_end": False,
        "custom_end_address": "",
        "rule_from_pick": "__none__",
        "rule_to_pick": "__none__",
        "rule_type_pick": "__none__",
        "trip_start_time": "09:00",
        "congestion_level": "normal",
        "route": None,
        "optimized": False,
        "logs": [],
        "run_api_check": False,
        "api_check_results": [],
        "api_check_all_passed": False,
        "_route_computed": False,
        "tmap_route_cache": {},
        "geocode_cache": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go_to(page: str) -> None:
    st.session_state.page = page


def reset_all() -> None:
    keys = list(st.session_state.keys())
    for key in keys:
        del st.session_state[key]
    init_session()
    st.session_state.places = [create_place(), create_place()]
