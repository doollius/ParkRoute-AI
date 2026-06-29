from __future__ import annotations

from typing import Callable

import streamlit as st

from constants.config import APP_TAGLINE, APP_TITLE
from services import api_status
from state.session_manager import go_to

_LIVE_TESTS: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
    ("TMAP", api_status.test_tmap),
    ("공공데이터 주차장", api_status.test_parking),
    ("OpenAI", api_status.test_openai),
]


def render() -> None:
    st.title(APP_TITLE)
    st.markdown(
        f"""
        **{APP_TAGLINE}**

        **도로명·지번 주소**를 입력하면,
        AI가 주차·도보·차량 이동을 고려해 **가장 편한 방문 순서**를 제안합니다.
        """
    )

    st.caption("필요한 API 연결 상태를 확인한 후 시작해주세요.")

    can_start = st.session_state.get("api_check_all_passed", False)

    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        api_check_clicked = st.button("API 연결 확인", use_container_width=True)
    with col2:
        if st.button(
            "시작하기",
            type="primary",
            use_container_width=True,
            disabled=not can_start,
        ):
            st.session_state.input_step = "places"
            go_to("input")
            st.rerun()

    check_progress = st.empty()
    if api_check_clicked:
        _run_live_api_check(check_progress)
        st.rerun()

    _render_live_test_results()


def _run_live_api_check(progress_slot) -> None:
    st.session_state.run_api_check = True
    results: list[tuple[str, bool, str]] = []
    total = len(_LIVE_TESTS)

    with progress_slot.status("⏳ 확인 중…", expanded=True) as status:
        st.caption("TMAP · 공공데이터 · OpenAI 순서로 연결을 확인합니다.")
        progress_bar = st.progress(0.0, text="API 연결 확인 준비 중…")
        for i, (label, test_fn) in enumerate(_LIVE_TESTS):
            progress_bar.progress(
                i / total,
                text=f"확인 중… ({i + 1}/{total}) · {label}",
            )
            st.markdown(f"**{label}** 연결 확인 중…")
            ok, detail = test_fn()
            results.append((label, ok, detail))
            icon = "✅" if ok else "❌"
            st.markdown(f"{icon} {label}: {detail}")
        progress_bar.progress(1.0, text="확인 완료")
        status.update(label="API 연결 확인 완료", state="complete", expanded=False)

    st.session_state.api_check_results = results
    st.session_state.api_check_all_passed = all(ok for _, ok, _ in results)


def _render_live_test_results() -> None:
    if not st.session_state.get("run_api_check"):
        return

    st.divider()
    st.caption("실시간 연결 테스트 (TMAP · 공공데이터 · OpenAI)")
    for label, ok, detail in st.session_state.get("api_check_results", []):
        icon = "✅" if ok else "❌"
        st.write(f"{icon} **{label}**: {detail}")

    if st.session_state.get("api_check_all_passed"):
        st.success("모든 API 연결이 확인되었습니다. 「시작하기」로 진행할 수 있습니다.")
    else:
        st.warning("일부 API 연결에 실패했습니다. 키 설정을 확인한 뒤 다시 테스트해 주세요.")
