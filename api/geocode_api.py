from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st

from api.tmap_api import TmapApiError, geocode_address, search_poi


def _cache() -> dict[str, dict[str, Any]]:
    if "geocode_cache" not in st.session_state:
        st.session_state.geocode_cache = {}
    return st.session_state.geocode_cache


def _cache_key(address: str) -> str:
    return hashlib.sha256(address.strip().encode("utf-8")).hexdigest()


def resolve_address(address: str) -> dict[str, Any]:
    """Geocoding with session cache and POI search fallback."""
    key = _cache_key(address)
    cached = _cache().get(key)
    if cached:
        return dict(cached)

    try:
        result = geocode_address(address)
        result["source"] = "geocoding"
    except TmapApiError as geo_exc:
        try:
            result = search_poi(address)
            result["source"] = "poi"
            result["geocode_note"] = f"주소 검색 실패 → POI 검색 사용 ({geo_exc})"
        except TmapApiError as poi_exc:
            raise TmapApiError(f"좌표 변환 실패: {geo_exc} / POI: {poi_exc}") from poi_exc

    _cache()[key] = result
    return dict(result)
