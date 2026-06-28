from __future__ import annotations

import streamlit as st


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
    c1, c2 = st.columns(2)
    if c1.button(confirm_label, key=f"{key}_yes", type="primary"):
        clear_confirm(key)
        return "confirm"
    if c2.button(cancel_label, key=f"{key}_no"):
        clear_confirm(key)
        return "cancel"
    return "pending"
