from __future__ import annotations

import streamlit as st

from models.place import place_selection_label
from models.visit_rule import RULE_BEFORE, RULE_IMMEDIATE, create_visit_rule, rule_label
from optimizer.constraint_builder import validate_visit_rules


def ensure_rule_widget_keys() -> None:
    if "rule_from" not in st.session_state:
        st.session_state.rule_from = None
    if "rule_to" not in st.session_state:
        st.session_state.rule_to = None
    if "rule_type" not in st.session_state:
        st.session_state.rule_type = RULE_IMMEDIATE


def add_rule(from_id: str, to_id: str, rule_type: str) -> None:
    if not from_id or not to_id:
        return
    st.session_state.visit_rules.append(create_visit_rule(from_id, to_id, rule_type))


def delete_rule(rule_id: str) -> None:
    st.session_state.visit_rules = [
        r for r in st.session_state.get("visit_rules", []) if r.get("id") != rule_id
    ]


def validation_errors(place_ids: set[str], start_id: str | None, end_id: str | None) -> list[str]:
    return validate_visit_rules(
        st.session_state.get("visit_rules", []),
        place_ids,
        start_id,
        end_id,
    )


def place_labels() -> dict[str, str]:
    places = st.session_state.get("places", [])
    return {p["id"]: place_selection_label(p, i, places) for i, p in enumerate(places)}


def rule_type_label(rule_type: str) -> str:
    return "바로 다음" if rule_type == RULE_IMMEDIATE else "다음 (순서만)"
