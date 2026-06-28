from __future__ import annotations

import streamlit as st

from models.place import place_selection_label
from models.visit_rule import PICK_NONE, RULE_BEFORE, RULE_IMMEDIATE, create_visit_rule, rule_label
from optimizer.constraint_builder import validate_visit_rules


def ensure_rule_widget_keys() -> None:
    if "rule_from_pick" not in st.session_state:
        st.session_state.rule_from_pick = PICK_NONE
    if "rule_to_pick" not in st.session_state:
        st.session_state.rule_to_pick = PICK_NONE
    if "rule_type_pick" not in st.session_state:
        st.session_state.rule_type_pick = PICK_NONE


def validate_rule_form(from_id: str, to_id: str, rule_type: str) -> str | None:
    picks = [from_id, to_id, rule_type]
    none_count = sum(1 for item in picks if item == PICK_NONE)
    if none_count == 3:
        return "규칙을 추가하려면 세 항목을 모두 선택해 주세요."
    if none_count > 0:
        return "선행 장소, 후행 장소, 규칙을 모두 선택해 주세요."
    if from_id == to_id:
        return "선행 장소와 후행 장소는 달라야 합니다."
    return None


def add_rule(from_id: str, to_id: str, rule_type: str) -> bool:
    err = validate_rule_form(from_id, to_id, rule_type)
    if err:
        return False
    if from_id == PICK_NONE:
        return False
    st.session_state.visit_rules.append(create_visit_rule(from_id, to_id, rule_type))
    return True


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
