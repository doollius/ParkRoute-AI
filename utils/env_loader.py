from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Streamlit 실행 cwd와 무관하게 프로젝트 루트 .env 로드
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")


def get_env(key: str, default: str = "") -> str:
    """Read config from Streamlit secrets (cloud) or .env (local)."""
    try:
        import streamlit as st

        if key in st.secrets:
            value = str(st.secrets[key]).strip()
            if value:
                return value
    except Exception:
        pass
    return os.getenv(key, default).strip()
