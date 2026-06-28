from __future__ import annotations

import streamlit as st


def init_session() -> None:
    defaults = {
        "page": "start",
        "travel_region": "",
        "start_place_id": None,
        "end_place_id": None,
        "optimization_mode": "minimize_walk",
        "places": [],
        "visit_rules": [],
        "route": None,
        "optimized": False,
        "logs": [],
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
