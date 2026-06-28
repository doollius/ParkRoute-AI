from __future__ import annotations

from typing import Callable

import streamlit as st

from constants.config import APP_TAGLINE, APP_TITLE
from services import api_status
from state.session_manager import go_to
from utils.ui_helpers import bottom_action_row

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

    st.markdown("#### ℹ️ 주소를 찾고 복사하는 방법")
    st.markdown(
        """
**🔗 [네이버 지도](https://map.naver.com)**
- 장소 검색
- 장소 선택
- 도로명 주소 또는 지번 주소 옆 **복사** 클릭

**🔗 [구글 지도](https://www.google.com/maps)**
- 장소 검색
- 장소 선택
- 표시된 주소 옆 **주소 복사** 클릭
        """
    )

    can_start = st.session_state.get("api_check_all_passed", False)

    with bottom_action_row(2) as (left, right):
        if left.button("API 연결 확인"):
            _run_live_api_check()
            st.rerun()
        if right.button(
            "시작하기",
            type="primary",
            disabled=not can_start,
        ):
            st.session_state.input_step = "places"
            go_to("input")
            st.rerun()

    _render_live_test_results()


def _run_live_api_check() -> None:
    st.session_state.run_api_check = True
    results: list[tuple[str, bool, str]] = []
    for label, test_fn in _LIVE_TESTS:
        ok, detail = test_fn()
        results.append((label, ok, detail))
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
