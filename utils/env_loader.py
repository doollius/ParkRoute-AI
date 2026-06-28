from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default: str = "") -> str:
    """Read config from Streamlit secrets (cloud) or .env (local)."""
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default).strip()
