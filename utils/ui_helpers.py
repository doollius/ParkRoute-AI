from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st
from streamlit.delta_generator import DeltaGenerator


MOBILE_CSS = """
<style>
@media (max-width: 768px) {
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    [data-testid="stMetric"] {
        margin-bottom: 0.25rem;
    }
}
</style>
"""


def inject_responsive_css() -> None:
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)


@contextmanager
def bottom_action_row(button_count: int) -> Iterator[list[DeltaGenerator]]:
    """하단 액션 버튼 슬롯. 2개=양끝, 3개=양끝+중앙."""
    if button_count == 2:
        left, _, right = st.columns([1, 6, 1])
        yield [left, right]
    elif button_count == 3:
        left, mid, right = st.columns([1, 1, 1])
        _, mid_slot, _ = mid.columns([1, 1, 1])
        _, right_slot = right.columns([1, 1])
        yield [left, mid_slot, right_slot]
    else:
        raise ValueError("button_count must be 2 or 3")


def request_confirm(key: str) -> None:
    st.session_state[key] = True


def clear_confirm(key: str) -> None:
    st.session_state.pop(key, None)


def is_confirm_pending(key: str) -> bool:
    return bool(st.session_state.get(key))


def render_confirm_box(
    key: str,
    message: str,
    confirm_label: str = "확인",
    cancel_label: str = "취소",
) -> str | None:
    """Returns 'confirm', 'cancel', or None if not pending."""
    if not is_confirm_pending(key):
        return None
    st.warning(message)
    with bottom_action_row(2) as (left, right):
        if left.button(confirm_label, key=f"{key}_yes", type="primary"):
            clear_confirm(key)
            return "confirm"
        if right.button(cancel_label, key=f"{key}_no"):
            clear_confirm(key)
            return "cancel"
    return "pending"
