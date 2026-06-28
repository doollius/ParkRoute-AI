from __future__ import annotations

import streamlit as st

from constants.config import APP_TAGLINE, APP_TITLE
from services import api_status
from state.session_manager import go_to


def render() -> None:
    st.title(APP_TITLE)
    st.markdown(
        f"""
        **{APP_TAGLINE}**

        네이버지도에서 찾은 **도로명·지번 주소**를 입력하면,
        AI가 주차·도보·차량 이동을 고려해 **가장 편한 방문 순서**를 제안합니다.
        """
    )

    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("시작하기", type="primary", use_container_width=True):
            go_to("input")
            st.rerun()
    with col2:
        if st.button("API 연결 확인", use_container_width=True):
            st.session_state.run_api_check = True
            st.rerun()

    _render_api_panel()


def _render_api_panel() -> None:
    with st.expander("API 설정 상태", expanded=st.session_state.get("run_api_check", False)):
        warning = api_status.keys_validation_message()
        if warning:
            st.error(f"Secrets 확인 필요: {warning}")

        for env_name, label in [
            ("TMAP_APP_KEY", "TMAP"),
            ("DATA_GO_KR_SERVICE_KEY", "DATA_GO_KR"),
            ("OPENAI_API_KEY", "OPENAI"),
        ]:
            detail = api_status.key_detail(env_name)
            ok = detail["looks_ok"]
            icon = "✅" if ok else "❌"
            st.write(
                f"{icon} **{label}** — "
                f"{'키 OK' if ok else '키 확인 필요'} "
                f"(로드됨: `{detail['masked']}`)"
            )

        if st.session_state.get("run_api_check"):
            st.divider()
            st.caption("실시간 연결 테스트 (TMAP · 공공데이터 · OpenAI)")
            for label, fn in [
                ("TMAP", api_status.test_tmap),
                ("공공데이터 주차장", api_status.test_parking),
                ("OpenAI", api_status.test_openai),
            ]:
                ok, detail = fn()
                icon = "✅" if ok else "❌"
                st.write(f"{icon} {label}: {detail}")
