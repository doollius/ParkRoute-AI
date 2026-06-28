"""ParkRoute AI — Streamlit entry point."""

import streamlit as st

from pages import input as input_page
from pages import loading, result, review, start
from state.session_manager import init_session

init_session()

st.set_page_config(
    page_title="ParkRoute AI",
    page_icon="🅿️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PAGES = {
    "start": start.render,
    "input": input_page.render,
    "review": review.render,
    "loading": loading.render,
    "result": result.render,
}

page = st.session_state.get("page", "start")
render_fn = PAGES.get(page, start.render)
render_fn()
